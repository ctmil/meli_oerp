# -*- coding: utf-8 -*-

import pytz

from odoo import models, api, fields
from odoo.tools.translate import _

import requests
from requests.adapters import HTTPAdapter
import json
try:
    from urllib import urlencode
except ImportError:
    from urllib.parse import urlencode
import logging
_logger = logging.getLogger(__name__)

from .meli_oerp_config import REDIRECT_URI

from urllib3.util.retry import Retry

from datetime import datetime
from .versions import *
from . import versions as _versions


class LoggingRetry(Retry):
    def increment(self, *args, **kwargs):
        retry_number = kwargs.get('total', self.total)
        reason = kwargs.get('reason', 'Unknown reason')
        _logger.info(f"Reintentando... Intento {self.total - retry_number + 1} debido a: {reason}")
        return super().increment(*args, **kwargs)


# ---------------------------------------------------------------------------
#  Configuraciones (siempre se crean ambas; se elige al final del módulo)
# ---------------------------------------------------------------------------

# NoSDK: requests Session con retry
class MeliConfiguration:
    def __init__(self, host="https://api.mercadolibre.com"):
        self.host = host
        self.retries = LoggingRetry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[413, 429, 503],
            raise_on_status=False
        )

    def get_session(self):
        session = requests.Session()
        adapter = HTTPAdapter(max_retries=self.retries)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session


configuration_nosdk = MeliConfiguration(host="https://api.mercadolibre.com")

# SDK: meli.Configuration (solo si el SDK está instalado)
configuration_sdk = None
_meli_sdk = None
_ApiClient = None
_ApiException = None
if _versions.MELI_SDK_AVAILABLE:
    try:
        import meli as _meli_sdk
        from meli.rest import ApiException as _ApiException
        from meli.api_client import ApiClient as _ApiClient
        configuration_sdk = _meli_sdk.Configuration(host="https://api.mercadolibre.com")
        configuration_sdk.retries = LoggingRetry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[413, 429, 503],
            raise_on_status=False
        )
    except Exception as e:
        _logger.warning("meli SDK import falló: %s", str(e))
        _versions.MELI_SDK_AVAILABLE = False
        _versions.USE_MELI_SDK = False


# ---------------------------------------------------------------------------
#  MeliApiNoSDK — implementación con requests puro
# ---------------------------------------------------------------------------
class MeliApiNoSDK:
    """
    Cliente API de MercadoLibre sin dependencia del SDK oficial.
    Usa requests directamente para todas las operaciones HTTP y OAuth.
    """

    AUTH_URL = "https://auth.mercadolibre.com.ar/authorization"
    TOKEN_URL = "https://api.mercadolibre.com/oauth/token"

    needlogin_state = True

    client_id = ""
    client_secret = ""
    access_token = ""
    refresh_token = ""
    redirect_uri = ""
    seller_id = ""

    response = ""
    code = ""
    rjson = {}

    user = {}

    # Benchmarking support - set to True to enable API timing logs
    _benchmark_enabled = False
    _benchmark_stats = {
        'get': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
        'get_mini': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
        'post': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
        'post_mini': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
        'put': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
        'put_mini': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
        'delete': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
    }
    _benchmark_slow_threshold = 2.0  # seconds

    @classmethod
    def enable_benchmark(cls, enabled=True, slow_threshold=2.0):
        """Enable or disable API benchmarking"""
        cls._benchmark_enabled = enabled
        cls._benchmark_slow_threshold = slow_threshold
        if enabled:
            cls.reset_benchmark_stats()
            _logger.info("MELI API BENCHMARK: ENABLED (slow threshold: %.1fs)", slow_threshold)
        else:
            _logger.info("MELI API BENCHMARK: DISABLED")

    @classmethod
    def reset_benchmark_stats(cls):
        """Reset benchmark statistics"""
        cls._benchmark_stats = {
            'get': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
            'get_mini': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
            'post': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
            'post_mini': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
            'put': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
            'put_mini': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
            'delete': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
        }

    @classmethod
    def get_benchmark_stats(cls):
        """Get benchmark statistics summary"""
        stats = cls._benchmark_stats
        total_calls = sum(s['count'] for s in stats.values())
        total_time = sum(s['total_time'] for s in stats.values())
        summary = {
            'total_calls': total_calls,
            'total_time': total_time,
            'by_method': {}
        }
        for method, s in stats.items():
            if s['count'] > 0:
                summary['by_method'][method] = {
                    'count': s['count'],
                    'total_time': round(s['total_time'], 2),
                    'avg_time': round(s['total_time'] / s['count'], 3),
                    'slow_calls': len(s['slow_calls'])
                }
        return summary

    @classmethod
    def log_benchmark_stats(cls):
        """Log benchmark statistics"""
        if not cls._benchmark_enabled:
            return
        stats = cls.get_benchmark_stats()
        _logger.info("MELI API BENCHMARK SUMMARY: total_calls=%d total_time=%.2fs",
                    stats['total_calls'], stats['total_time'])
        for method, s in stats['by_method'].items():
            _logger.info("  %s: calls=%d time=%.2fs avg=%.3fs slow=%d",
                        method, s['count'], s['total_time'], s['avg_time'], s['slow_calls'])

    def _record_benchmark(self, method, path, elapsed):
        """Record benchmark data for an API call"""
        if not MeliApiNoSDK._benchmark_enabled:
            return
        stats = MeliApiNoSDK._benchmark_stats.get(method)
        if stats:
            stats['count'] += 1
            stats['total_time'] += elapsed
            if elapsed > MeliApiNoSDK._benchmark_slow_threshold:
                stats['slow_calls'].append({'path': path, 'time': elapsed})
                _logger.warning("MELI API SLOW %s: %s took %.2fs", method.upper(), path, elapsed)

    def __init__(self, config=None):
        """
        Inicializa el cliente API.

        Args:
            config: MeliConfiguration opcional. Si no se pasa, usa la configuración global.
        """
        self.config = config or configuration
        self.base_url = self.config.host
        self._session = self.config.get_session()

    def _abs_url(self, path):
        """Convierte un path relativo a URL absoluta"""
        if not path:
            return path
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return self.base_url.rstrip("/") + "/" + path.lstrip("/")

    def _parse_response(self, resp):
        """Parsea la respuesta HTTP a JSON o texto"""
        try:
            return resp.json()
        except Exception:
            return resp.text

    def need_login(self):
        return self.needlogin_state

    def json(self):
        return self.rjson

    def get(self, path, params={}, extra_headers=None):
        """
        GET genérico sin SDK.
        - Firma: get(self, path, params={}, extra_headers=None)
        - Mantiene self.response y self.rjson
        - Retorna self
        """
        import time as _time_module
        _t_start = _time_module.time() if MeliApiNoSDK._benchmark_enabled else 0
        _original_path = path

        # Extrae datos de params sin mutar el original
        atok = params.get("access_token", "") or ""
        if atok == "PASIVA":
            atok = ""

        headers = (params.get("headers") or {}).copy()
        if extra_headers:
            headers.update(extra_headers)
        timeout = params.get("timeout", 20)
        scroll_id = params.get("scroll_id", None)
        qparams = params.get("query", None)

        # Compatibilidad con viejo estilo de query
        if qparams is None:
            reserved = {"access_token", "headers", "timeout", "scroll_id", "query"}
            qparams = {k: v for k, v in params.items() if k not in reserved}
            if not qparams:
                qparams = None

        # Construye query string
        url = self._abs_url(path)
        query_parts = []
        if qparams:
            query_parts.append(urlencode(qparams))
        if scroll_id:
            query_parts.append(f"scroll_id={scroll_id}")
        if query_parts:
            sep = "&" if ("?" in url) else "?"
            url = f"{url}{sep}{'&'.join(query_parts)}"

        # Headers finales
        final_headers = {"Accept": "application/json"}
        if atok:
            final_headers["Authorization"] = f"Bearer {atok}"
        final_headers.update(headers)

        try:
            resp = self._session.get(
                url,
                headers=final_headers,
                timeout=timeout,
                allow_redirects=True
            )
            self.response = self._parse_response(resp)
            self.rjson = self.response

            # Log según status code
            if resp.status_code == 404:
                _logger.debug("GET %s: 404 Not Found", path)
            elif resp.status_code in (401, 403):
                _logger.warning(
                    "GET %s: Auth error status=%s | Seller ID: %s",
                    path, resp.status_code, self.seller_id
                )
            elif resp.status_code >= 400:
                _logger.warning(
                    "GET %s falló: status=%s body=%s",
                    path, resp.status_code, str(self.rjson)[:200]
                )

        except requests.RequestException as e:
            _logger.warning("GET %s error: %s", path, str(e))
            self.rjson = {
                "error": "get error",
                "status": 0,
                "cause": "request_exception",
                "message": str(e),
                "get_url": path
            }
            self.response = self.rjson
        finally:
            if MeliApiNoSDK._benchmark_enabled:
                self._record_benchmark('get', _original_path, _time_module.time() - _t_start)

        return self

    def get_mini(self, path, params={}):
        """GET via requests — alias de get() para compatibilidad"""
        import time as _time_module
        _t_start = _time_module.time() if MeliApiNoSDK._benchmark_enabled else 0
        result = self.get(path, params)
        if MeliApiNoSDK._benchmark_enabled:
            self._record_benchmark('get_mini', path, _time_module.time() - _t_start)
        return result

    def post(self, path, body=None, params={}):
        """
        POST genérico sin SDK.
        - Firma: post(self, path, body=None, params={})
        - Mantiene self.response y self.rjson
        - Retorna self
        """
        import time as _time_module
        _t_start = _time_module.time() if MeliApiNoSDK._benchmark_enabled else 0
        _original_path = path

        # Extrae y NO muta el dict original
        atok = params.get("access_token", "") or ""
        headers = (params.get("headers") or {}).copy()
        timeout = params.get("timeout", 20)
        files = params.get("files", None)
        qparams = params.get("query", None)

        # Compatibilidad: si no se pasó 'query', construyo con el resto
        if qparams is None:
            reserved = {"access_token", "headers", "timeout", "files", "query"}
            qparams = {k: v for k, v in params.items() if k not in reserved}
            if not qparams:
                qparams = None

        # Construcción de URL
        url = self._abs_url(path)
        if qparams:
            sep = "&" if ("?" in url) else "?"
            url = f"{url}{sep}{urlencode(qparams)}"

        # Headers finales
        final_headers = {"Accept": "application/json"}
        if atok:
            final_headers["Authorization"] = f"Bearer {atok}"
        if isinstance(body, (dict, list)) and not files:
            if "Content-Type" not in {k.title(): v for k, v in headers.items()}:
                final_headers["Content-Type"] = "application/json"
        final_headers.update(headers)

        try:
            resp = self._session.post(
                url,
                headers=final_headers,
                json=body if (isinstance(body, (dict, list)) and not files) else None,
                data=None if (isinstance(body, (dict, list)) and not files) else body,
                files=files,
                timeout=timeout,
                allow_redirects=True,
            )
            self.response = self._parse_response(resp)
            self.rjson = self.response

            if resp.status_code >= 400:
                _logger.warning(
                    "POST %s falló: status=%s body=%s",
                    path, resp.status_code, str(self.rjson)[:200]
                )

        except requests.RequestException as e:
            _logger.warning("POST %s error: %s", path, str(e))
            self.rjson = {
                "error": "post error",
                "status": 0,
                "cause": "request_exception",
                "message": str(e),
                "post_url": path
            }
            self.response = self.rjson
        finally:
            if MeliApiNoSDK._benchmark_enabled:
                self._record_benchmark('post', _original_path, _time_module.time() - _t_start)

        return self

    def post_mini(self, path, body=None, params={}):
        """POST via requests — alias de post() para compatibilidad"""
        import time as _time_module
        _t_start = _time_module.time() if MeliApiNoSDK._benchmark_enabled else 0
        result = self.post(path, body, params)
        if MeliApiNoSDK._benchmark_enabled:
            self._record_benchmark('post_mini', path, _time_module.time() - _t_start)
        return result

    def put(self, path, body=None, params={}):
        """
        PUT genérico sin SDK.
        - Firma: put(self, path, body=None, params={})
        - Mantiene self.response y self.rjson
        - Retorna self
        """
        import time as _time_module
        _t_start = _time_module.time() if MeliApiNoSDK._benchmark_enabled else 0
        _original_path = path

        atok = params.get("access_token", "") or ""
        headers = (params.get("headers") or {}).copy()
        timeout = params.get("timeout", 20)
        qparams = params.get("query", None)

        url = self._abs_url(path)

        # Headers finales
        final_headers = {"Accept": "application/json"}
        if atok:
            final_headers["Authorization"] = f"Bearer {atok}"
        if isinstance(body, (dict, list)) and "Content-Type" not in {k.title(): v for k, v in headers.items()}:
            final_headers["Content-Type"] = "application/json"
        final_headers.update(headers)

        try:
            resp = self._session.put(
                url,
                headers=final_headers,
                json=body if isinstance(body, (dict, list)) else None,
                data=None if isinstance(body, (dict, list)) else body,
                params=qparams,
                timeout=timeout,
                allow_redirects=True,
            )
            self.response = self._parse_response(resp)
            self.rjson = self.response

            if resp.status_code >= 400:
                _logger.warning(
                    "PUT %s falló: status=%s body=%s",
                    path, resp.status_code, str(self.rjson)[:200]
                )

        except requests.RequestException as e:
            _logger.warning("PUT %s error: %s", path, str(e))
            self.rjson = {
                "error": "put error",
                "status": 0,
                "cause": "request_exception",
                "message": str(e)
            }
            self.response = self.rjson
        finally:
            if MeliApiNoSDK._benchmark_enabled:
                self._record_benchmark('put', _original_path, _time_module.time() - _t_start)

        return self

    def put_mini(self, path, body=None, params={}):
        """PUT via requests — alias de put() para compatibilidad"""
        import time as _time_module
        _t_start = _time_module.time() if MeliApiNoSDK._benchmark_enabled else 0
        result = self.put(path, body, params)
        if MeliApiNoSDK._benchmark_enabled:
            self._record_benchmark('put_mini', path, _time_module.time() - _t_start)
        return result

    def delete(self, path, params={}):
        """
        DELETE genérico sin SDK.
        - Firma: delete(self, path, params={})
        - Mantiene self.response y self.rjson
        - Retorna self
        """
        import time as _time_module
        _t_start = _time_module.time() if MeliApiNoSDK._benchmark_enabled else 0
        _original_path = path

        atok = params.get("access_token", "") or ""
        headers = (params.get("headers") or {}).copy()
        timeout = params.get("timeout", 20)

        url = self._abs_url(path)

        final_headers = {"Accept": "application/json"}
        if atok:
            final_headers["Authorization"] = f"Bearer {atok}"
        final_headers.update(headers)

        try:
            resp = self._session.delete(
                url,
                headers=final_headers,
                timeout=timeout,
                allow_redirects=True
            )
            self.response = self._parse_response(resp)
            self.rjson = self.response

            if resp.status_code >= 400:
                _logger.warning(
                    "DELETE %s falló: status=%s body=%s",
                    path, resp.status_code, str(self.rjson)[:200]
                )

        except requests.RequestException as e:
            _logger.warning("DELETE %s error: %s", path, str(e))
            self.rjson = {
                "error": "delete error",
                "status": 0,
                "cause": "request_exception",
                "message": str(e)
            }
            self.response = self.rjson
        finally:
            if MeliApiNoSDK._benchmark_enabled:
                self._record_benchmark('delete', _original_path, _time_module.time() - _t_start)

        return self

    def upload(self, path, files, params={}):
        """
        Upload de archivos usando multipart/form-data (sin SDK).
        Los archivos se pasan en el parámetro files.
        """
        atok = params.get("access_token", "") or ""
        timeout = params.get("timeout", 60)

        url = self._abs_url(path)

        # Para upload legacy, usamos query param access_token
        if atok:
            sep = "&" if ("?" in url) else "?"
            url = f"{url}{sep}access_token={atok}"

        try:
            resp = self._session.post(
                url,
                files=files,
                timeout=timeout
            )
            self.response = self._parse_response(resp)
            self.rjson = self.response

        except requests.RequestException as e:
            _logger.warning("UPLOAD %s error: %s", path, str(e))
            self.rjson = {"error": str(e)}
            self.response = self.rjson

        return self

    def uploadfiles(self, path, files, params={}):
        """
        Upload de archivos usando Authorization Bearer (sin SDK).
        """
        atok = params.get("access_token", "") or ""
        timeout = params.get("timeout", 60)

        url = self._abs_url(path)

        headers = {"Accept": "application/json"}
        if atok:
            headers["Authorization"] = f"Bearer {atok}"

        try:
            resp = self._session.post(
                url,
                files=files,
                headers=headers,
                timeout=timeout
            )
            self.response = self._parse_response(resp)
            self.rjson = self.response

        except requests.RequestException as e:
            _logger.warning("UPLOADFILES %s error: %s", path, str(e))
            self.rjson = {"error": str(e)}
            self.response = self.rjson

        return self

    def auth_url(self, redirect_URI=None):
        """Genera la URL de autorización OAuth para login"""
        now = datetime.now()
        if redirect_URI:
            self.redirect_uri = redirect_URI
        random_id = str(now)
        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'redirect_uri': self.redirect_uri,
            'state': random_id
        }
        url = self.AUTH_URL + '?' + urlencode(params)
        return url

    def redirect_login(self):
        """Retorna acción de redirección para login en Odoo"""
        url_login_meli = str(self.auth_url())
        return {
            "type": "ir.actions.act_url",
            "url": url_login_meli,
            "target": "self",
        }

    def authorize(self, code, redirect_uri=None):
        """
        Obtiene access_token usando authorization_code (sin SDK).
        POST a https://api.mercadolibre.com/oauth/token
        """
        if redirect_uri:
            self.redirect_uri = redirect_uri

        data = {
            'grant_type': 'authorization_code',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'redirect_uri': self.redirect_uri
        }

        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        try:
            resp = self._session.post(
                self.TOKEN_URL,
                data=data,
                headers=headers,
                timeout=30
            )
            response_info = self._parse_response(resp)

            if isinstance(response_info, dict) and 'access_token' in response_info:
                self.access_token = response_info['access_token']
                self.refresh_token = response_info.get('refresh_token', '')
            else:
                _logger.warning("authorize falló: %s", str(response_info)[:200])

            return response_info

        except requests.RequestException as e:
            _logger.error("authorize error: %s", str(e))
            return {"error": "authorize_error", "message": str(e)}

    def get_refresh_token(self, code=None, redirect_uri=None):
        """
        Renueva access_token usando refresh_token (sin SDK).
        POST a https://api.mercadolibre.com/oauth/token
        """
        data = {
            'grant_type': 'refresh_token',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': self.refresh_token
        }

        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        try:
            resp = self._session.post(
                self.TOKEN_URL,
                data=data,
                headers=headers,
                timeout=30
            )
            response_info = self._parse_response(resp)

            if isinstance(response_info, dict) and 'access_token' in response_info:
                self.access_token = response_info['access_token']
                self.refresh_token = response_info.get('refresh_token', '')
            else:
                _logger.warning("get_refresh_token falló: %s", str(response_info)[:200])

            return response_info

        except requests.RequestException as e:
            _logger.error("get_refresh_token error: %s", str(e))
            return {"error": "refresh_token_error", "message": str(e)}

    def get_sale_terms(self, category_id=None, sale_term_id=None, productjson=None):
        """Obtiene los términos de venta para una categoría"""
        sale_terms_by_id = {}

        if category_id:
            url = f"/categories/{category_id}/sale_terms"
            res = self.get(url)

            if res and res.rjson and isinstance(res.rjson, list):
                for rj in res.rjson:
                    stid = rj.get("id")
                    if stid:
                        sale_terms_by_id[stid] = rj

        if sale_term_id:
            # Buscar en el JSON del producto si se proporcionó
            if productjson and "sale_terms" in productjson:
                for st in productjson["sale_terms"]:
                    if st.get("id") == sale_term_id:
                        return st
                return False

            # Buscar en los términos de la categoría
            if sale_term_id in sale_terms_by_id:
                return sale_terms_by_id[sale_term_id]

        return sale_terms_by_id

    def get_user_product_stock_with_version(self, up_id, access_token):
        """
        Obtiene stock de user-product con x-version header (sin SDK).
        Retorna (data, x_version)
        """
        url = self._abs_url(f"user-products/{up_id}/stock")

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}"
        }

        try:
            resp = self._session.get(url, headers=headers, timeout=20)
            data = self._parse_response(resp)
            xver = resp.headers.get('x-version') or resp.headers.get('X-Version')
            return data, xver

        except requests.RequestException as e:
            _logger.warning("get_user_product_stock_with_version error: %s", str(e))
            return {"error": str(e)}, None


# ---------------------------------------------------------------------------
#  MeliApiSDK — implementación con el SDK oficial de MercadoLibre
#  Solo se define si el SDK está disponible.
# ---------------------------------------------------------------------------
if _versions.MELI_SDK_AVAILABLE and _meli_sdk and _ApiClient:
    class MeliApiSDK(_meli_sdk.RestClientApi):
        """Cliente API de MercadoLibre usando el SDK oficial (meli)."""

        AUTH_URL = "https://auth.mercadolibre.com.ar/authorization"
        needlogin_state = True
        client_id = ""
        client_secret = ""
        access_token = ""
        refresh_token = ""
        redirect_uri = ""
        seller_id = ""
        response = ""
        code = ""
        rjson = {}
        user = {}

        # Benchmarking support - class-level attributes (for compatibility with MeliApiNoSDK)
        _benchmark_enabled = False
        _benchmark_stats = {
            'get': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
            'get_mini': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
            'post': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
            'post_mini': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
            'put': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
            'put_mini': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
            'delete': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
        }
        _benchmark_slow_threshold = 2.0

        @classmethod
        def enable_benchmark(cls, enabled=True, slow_threshold=2.0):
            """Enable or disable API benchmarking"""
            cls._benchmark_enabled = enabled
            cls._benchmark_slow_threshold = slow_threshold
            if enabled:
                cls.reset_benchmark_stats()
                _logger.info("MELI API BENCHMARK (SDK): ENABLED (slow threshold: %.1fs)", slow_threshold)
            else:
                _logger.info("MELI API BENCHMARK (SDK): DISABLED")

        @classmethod
        def reset_benchmark_stats(cls):
            """Reset benchmark statistics"""
            cls._benchmark_stats = {
                'get': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
                'get_mini': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
                'post': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
                'post_mini': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
                'put': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
                'put_mini': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
                'delete': {'count': 0, 'total_time': 0.0, 'slow_calls': []},
            }

        @classmethod
        def get_benchmark_stats(cls):
            """Get benchmark statistics summary"""
            return cls._benchmark_stats

        def __init__(self, *args, **kwargs):
            super(MeliApiSDK, self).__init__(*args, **kwargs)
            self.api_auth_client = _meli_sdk.OAuth20Api(self.api_client)

        def need_login(self):
            return self.needlogin_state

        def json(self):
            return self.rjson

        def get(self, path, params={}, extra_headers=None):
            # When custom headers are required (e.g. x-version for versioned
            # endpoints) the SDK's resource_get does not expose a per-call
            # header hook, so fall back to the requests-based client which
            # supports arbitrary headers.
            if extra_headers:
                return self.get_mini(path, params, extra_headers=extra_headers)
            try:
                atok = ("access_token" in params and params["access_token"]) or ""
                if atok == "PASIVA":
                    atok = ""
                    del params["access_token"]
                scroll_id = ("scroll_id" in params and params["scroll_id"]) or None
                if atok:
                    del params["access_token"]
                if scroll_id:
                    del params["scroll_id"]
                if params:
                    path += "?" + urlencode(params)
                    if scroll_id:
                        path += "&scroll_id=" + scroll_id
                self.response = self.resource_get(resource=path, access_token=atok)
                self.rjson = self.response
            except _ApiException as e:
                self.rjson = {
                    "error": "get error",
                    "status": getattr(e, "status", None),
                    "cause": getattr(e, "reason", None),
                    "message": getattr(e, "body", None),
                }
            except:
                pass
            return self

        # get_mini y post_mini usan requests directo (como en la versión original)
        def get_mini(self, path, params={}, extra_headers=None):
            """GET sin SDK (requests directo) - para compatibilidad"""
            _nosdk = MeliApiNoSDK(config=configuration_nosdk)
            _nosdk.__dict__.update({k: v for k, v in self.__dict__.items()
                                     if k in ('client_id', 'client_secret', 'access_token',
                                              'refresh_token', 'redirect_uri', 'seller_id')})
            _nosdk.get(path, params, extra_headers=extra_headers)
            self.response = _nosdk.response
            self.rjson = _nosdk.rjson
            return self

        def post(self, path, body=None, params={}):
            try:
                atok = ("access_token" in params and params["access_token"]) or ""
                if atok:
                    del params["access_token"]
                if params:
                    path += "?" + urlencode(params)
                self.response = self.resource_post(resource=path, access_token=atok, body=body)
                self.rjson = self.response
            except _ApiException as e:
                self.rjson = {"error": "post error", "status": e.status, "cause": e.reason, "message": e.body}
            except:
                pass
            return self

        def post_mini(self, path, body=None, params={}):
            """POST sin SDK (requests directo) - para compatibilidad"""
            _nosdk = MeliApiNoSDK(config=configuration_nosdk)
            _nosdk.__dict__.update({k: v for k, v in self.__dict__.items()
                                     if k in ('client_id', 'client_secret', 'access_token',
                                              'refresh_token', 'redirect_uri', 'seller_id')})
            _nosdk.post(path, body, params)
            self.response = _nosdk.response
            self.rjson = _nosdk.rjson
            return self

        def put(self, path, body=None, params={}):
            try:
                atok = params.get("access_token", "") or ""
                headers = params.get("headers", {}) or {}
                self.response = self.resource_put(resource=path, access_token=atok, body=body, headers=headers)
                self.rjson = self.response
            except _ApiException as e:
                self.rjson = {"error": "put error", "status": e.status, "cause": e.reason, "message": e.body}
            except:
                pass
            return self

        def put_mini(self, path, body=None, params={}):
            """PUT sin SDK (requests directo) - para compatibilidad"""
            _nosdk = MeliApiNoSDK(config=configuration_nosdk)
            _nosdk.__dict__.update({k: v for k, v in self.__dict__.items()
                                     if k in ('client_id', 'client_secret', 'access_token',
                                              'refresh_token', 'redirect_uri', 'seller_id')})
            _nosdk.put(path, body, params)
            self.response = _nosdk.response
            self.rjson = _nosdk.rjson
            return self

        def delete(self, path, params={}):
            try:
                atok = ("access_token" in params and params["access_token"]) or ""
                self.response = self.resource_delete(resource=path, access_token=atok)
                self.rjson = self.response
            except _ApiException as e:
                self.rjson = {"error": str(e), "status": e.status, "cause": e.reason, "message": e.body}
            except:
                pass
            return self

        def upload(self, path, files, params={}):
            try:
                atok = ("access_token" in params and params["access_token"]) or ""
                uri = configuration_sdk.host + str(path)
                self.response = requests.post(uri, files=files, params=urlencode({"access_token": atok}), headers={})
                self.rjson = self.response.json()
            except Exception as e:
                self.rjson = {"error": str(e)}
            return self

        def uploadfiles(self, path, files, params={}):
            try:
                atok = ("access_token" in params and params["access_token"]) or ""
                uri = configuration_sdk.host + str(path)
                headers = {'Authorization': 'Bearer ' + atok}
                self.response = requests.post(uri, files=files, params={}, headers=headers)
                self.rjson = self.response.json()
            except Exception as e:
                self.rjson = {"error": str(e)}
            return self

        def auth_url(self, redirect_URI=None):
            now = datetime.now()
            if redirect_URI:
                self.redirect_uri = redirect_URI
            random_id = str(now)
            params = {'client_id': self.client_id, 'response_type': 'code', 'redirect_uri': self.redirect_uri, 'state': random_id}
            return self.AUTH_URL + '?' + urlencode(params)

        def redirect_login(self):
            return {"type": "ir.actions.act_url", "url": str(self.auth_url()), "target": "self"}

        def authorize(self, code, redirect_uri=None):
            api_client = _ApiClient()
            api_auth_client = _meli_sdk.OAuth20Api(api_client)
            if redirect_uri:
                self.redirect_uri = redirect_uri
            response_info = api_auth_client.get_token(
                grant_type='authorization_code', client_id=self.client_id,
                client_secret=self.client_secret, redirect_uri=self.redirect_uri,
                code=code, refresh_token=self.refresh_token)
            if 'access_token' in response_info:
                self.access_token = response_info['access_token']
                self.refresh_token = response_info.get('refresh_token', '')
            return response_info

        def get_refresh_token(self, code=None, redirect_uri=None):
            api_client = _ApiClient()
            api_auth_client = _meli_sdk.OAuth20Api(api_client)
            response_info = api_auth_client.get_token(
                grant_type='refresh_token', client_id=self.client_id,
                client_secret=self.client_secret, refresh_token=self.refresh_token)
            if 'access_token' in response_info:
                self.access_token = response_info['access_token']
                self.refresh_token = response_info.get('refresh_token', '')
            return response_info

        def get_sale_terms(self, category_id=None, sale_term_id=None, productjson=None):
            sale_terms_by_id = {}
            if category_id:
                res = self.get("/categories/" + str(category_id) + "/sale_terms")
                if res and res.rjson:
                    for rj in res.rjson:
                        stid = "id" in rj and rj["id"]
                        if stid:
                            sale_terms_by_id[stid] = rj
            if sale_term_id:
                if productjson and "sale_terms" in productjson:
                    for st in productjson["sale_terms"]:
                        if "id" in st and st["id"] == sale_term_id:
                            return st
                    return False
                if sale_term_id in sale_terms_by_id:
                    return sale_terms_by_id[sale_term_id]
            return sale_terms_by_id

        def get_user_product_stock_with_version(self, up_id, access_token):
            data, status, headers = self.resource_get_with_http_info(
                resource="user-products/{}/stock".format(up_id),
                access_token=access_token, _return_http_data_only=False)
            xver = None
            if headers:
                xver = headers.get('x-version') or headers.get('X-Version')
            return data, xver

else:
    # SDK no disponible: MeliApiSDK es None
    MeliApiSDK = None


# ---------------------------------------------------------------------------
#  Selección de implementación según USE_MELI_SDK
# ---------------------------------------------------------------------------
if _versions.USE_MELI_SDK and MeliApiSDK is not None:
    MeliApi = MeliApiSDK
    configuration = configuration_sdk
    _logger.info("MeliApi: usando SDK (meli.RestClientApi)")
else:
    MeliApi = MeliApiNoSDK
    configuration = configuration_nosdk
    _logger.info("MeliApi: usando requests directo (sin SDK)")


class MeliUtil(models.AbstractModel):

    _name = 'meli.util'
    _description = 'Utilidades para Mercado Libre'

    def get_meli_state(self):
        return self.get_new_instance()

    @api.model
    def get_new_instance(self, company=None, refresh_force=False):

        if not company:
            company = self.env.user.company_id

        # Proxy de rescate: si la empresa tiene configurado un host alternativo,
        # rutear la API (y el OAuth, vía _abs_url) por ese reverse proxy.
        api_host = company.mercadolibre_http_proxy or "https://api.mercadolibre.com"
        use_custom_host = api_host != "https://api.mercadolibre.com"

        # Crear instancia de MeliApi según modo activo (SDK o requests)
        if _versions.USE_MELI_SDK and MeliApiSDK is not None:
            if use_custom_host:
                sdk_config = _meli_sdk.Configuration(host=api_host)
                # Host de rescate: sin auto-retry (los 429 agravan el rate-limit del proxy).
                sdk_config.retries = False
                api_client = _ApiClient(configuration=sdk_config)
            else:
                api_client = _ApiClient(configuration=configuration_sdk)
            api_rest_client = MeliApi(api_client)
        else:
            config = MeliConfiguration(host=api_host) if use_custom_host else configuration_nosdk
            api_rest_client = MeliApi(config=config)
        api_rest_client.client_id = company.mercadolibre_client_id
        api_rest_client.client_secret = company.mercadolibre_secret_key
        api_rest_client.access_token = company.mercadolibre_access_token or ''
        api_rest_client.refresh_token = company.mercadolibre_refresh_token
        api_rest_client.redirect_uri = company.mercadolibre_redirect_uri
        api_rest_client.seller_id = company.mercadolibre_seller_id
        api_rest_client.AUTH_URL = company.get_ML_AUTH_URL(meli=api_rest_client)
        last_token = api_rest_client.access_token

        #api_response = api_instance.get_token(grant_type=grant_type, client_id=CLIENT_ID, client_secret=CLIENT_SECRET, redirect_uri=REDIRECT_URI, code=CODE, refresh_token=REFRESH_TOKEN)
        #taken from res.company get_meli_state()
        api_rest_client.needlogin_state = False
        message = "Login to ML needed in Odoo."

        #pdb.set_trace()
        try:
            if not (company.mercadolibre_seller_id==False) and api_rest_client.access_token!='':
                response = api_rest_client.get("/users/"+str(company.mercadolibre_seller_id), {'access_token':api_rest_client.access_token} )

                #_logger.info("get_new_instance connection response:"+str(response))
                rjson = response.json()

                status = "status" in rjson and rjson["status"]
                cause = "cause" in rjson and rjson["cause"]

                if status==429:
                    return api_rest_client
                
                if status==500 and cause=="Internal Server Error":
                    return api_rest_client

                if status==504 and cause=="Gateway Time-out":
                    return api_rest_client

                if cause and status and int(status)>=500:
                    return api_rest_client

                right_access_token = ("-"+str(api_rest_client.seller_id)) in str(api_rest_client.access_token)
                if not right_access_token:
                    api_rest_client.needlogin_state = True
                    return api_rest_client

                #_logger.info(rjson)
                if ( rjson and "error" in rjson) or refresh_force==True:

                    if company.mercadolibre_cron_refresh or api_rest_client.access_token:
                        internals = {
                            "application_id": company.mercadolibre_client_id,
                            "user_id": company.mercadolibre_seller_id,
                            "topic": "internal",
                            "resource": "get_new_instance #"+str(company.name),
                            "state": "PROCESSING"
                        }
                        noti = self.env["mercadolibre.notification"].start_internal_notification( internals )

                        errors = str(rjson)+"\n"
                        logs = str(rjson)+"\n"

                        api_rest_client.needlogin_state = True

                        #_logger.error(rjson)

                        if rjson["error"]=="not_found":
                            api_rest_client.needlogin_state = True
                            logs+= "NOT FOUND"+"\n"

                        if "message" in rjson:
                            message = rjson["message"]
                            if "message" in message:
                                #message is e.body, fix thiss
                                try:
                                    mesjson = json.loads(message)
                                    message = mesjson["message"]
                                except:
                                    message = "invalid_token"
                                    pass;
                            logs+= str(message)+"\n"
                            _logger.info("message: " +str(message))
                            if (refresh_force or ( message and "invalid" in str(message)) or ( message and "expired" in str(message)) 
                                or message=="expired_token" or message=="invalid_token" or message=="internal_server_error"):
                                api_rest_client.needlogin_state = True
                                try:
                                    #refresh = meli.get_refresh_token()
                                    refresh = api_rest_client.get_refresh_token()
                                    _logger.info("Refresh result: "+str(refresh))
                                    if (refresh):
                                        #refjson = refresh.json()
                                        refjson = refresh
                                        logs+= str(refjson)+"\n"
                                        if "access_token" in refjson:
                                            api_rest_client.access_token = refjson["access_token"]
                                            api_rest_client.refresh_token = refjson["refresh_token"]
                                            api_rest_client.code = ''
                                            company.write({ 'mercadolibre_access_token': api_rest_client.access_token,
                                                            'mercadolibre_refresh_token': api_rest_client.refresh_token,
                                                            'mercadolibre_code': '' } )
                                            api_rest_client.needlogin_state = False
                                except Exception as e:
                                    errors += str(e)
                                    logs += str(e)
                                    _logger.error(e)
                                    pass;
                                except:
                                    pass;

                        noti.stop_internal_notification( errors=errors , logs=logs )

                else:
                    #saving user info, brand, official store ids, etc...
                    #if "phone" in rjson:
                    #    _logger.info("phone:")
                    response.user = rjson
                    if "mercadolibre_user_product_seller" in company._fields:
                        mercadolibre_user_product_seller = ("tags"in rjson and "user_product_seller" in rjson["tags"])
                        if (company.mercadolibre_user_product_seller!=mercadolibre_user_product_seller):
                            company.mercadolibre_user_product_seller = mercadolibre_user_product_seller

                    if "mercadolibre_multiwarehouse" in company._fields:
                        mercadolibre_multiwarehouse = ("tags" in rjson and "multiwarehouse" in rjson["tags"])
                        if (company.mercadolibre_multiwarehouse != mercadolibre_multiwarehouse):
                            company.mercadolibre_multiwarehouse = mercadolibre_multiwarehouse


            else:
                api_rest_client.needlogin_state = True

            #        except requests.exceptions.HTTPError as e:
            #            _logger.info( "And you get an HTTPError:", e.message )

        except requests.exceptions.ConnectionError as e:
            #raise osv.except_osv( _('MELI WARNING'), _('NO INTERNET CONNECTION TO API.MERCADOLIBRE.COM: complete the Cliend Id, and Secret Key and try again'))
            api_rest_client.needlogin_state = True
            error_msg = 'MELI WARNING: NO INTERNET CONNECTION TO API.MERCADOLIBRE.COM: complete the Cliend Id, and Secret Key and try again '
            _logger.error(error_msg)

        if api_rest_client.access_token=='' or api_rest_client.access_token==False:
            api_rest_client.needlogin_state = True

        try:
            if api_rest_client.needlogin_state:
                _logger.warning("Need login for "+str(company.name))

                # IMPORTANTE: NO se borran mercadolibre_access_token/refresh_token/code
                # ni se apaga mercadolibre_cron_refresh. El refresh_token de ML sigue
                # siendo válido aunque el access_token haya vencido, y conservarlo
                # permite recuperar la conexión en la próxima corrida del cron.
                if (company.mercadolibre_cron_refresh and company.mercadolibre_cron_mail):
                    # we put the job_exception in context to be able to print it inside
                    # the email template
                    context = {
                        'job_exception': message,
                        'dbname': MeliCr( self ).dbname,
                    }

                    _logger.info(
                        "Sending scheduler error email with context=%s", context)
                    _logger.info("Sending to company:" + str(company.name)+ " mail:" + str(company.email)  )
                    rese = self.env['mail.template'].browse(
                                company.mercadolibre_cron_mail.id
                            ).with_context(context).sudo().send_mail( (company.id), force_send=True)
                    _logger.info("Result sending:" + str(rese) )

        except Exception as e:
            _logger.error(e)

        for comp in company:
            if (last_token!=comp.mercadolibre_access_token):#comp.mercadolibre_state!=api_rest_client.needlogin_state:
                _logger.info("mercadolibre_state : "+str(api_rest_client.needlogin_state))
                comp.mercadolibre_state = api_rest_client.needlogin_state
            #else:
            #    _logger.info("mercadolibre_state already set: "+str(api_rest_client.needlogin_state))

        return api_rest_client

    @api.model
    def get_url_meli_login(self, app_instance):
        if not company:
            company = self.env.user.company_id
        REDIRECT_URI = company.mercadolibre_redirect_uri
        url_login_meli = app_instance.auth_url(redirect_URI=REDIRECT_URI)
        return {
            "type": "ir.actions.act_url",
            "url": url_login_meli,
            "target": "self",
        }

    def convert_to_datetime(self, date_str):
        if not date_str:
            return False
        date_str = date_str.replace('T', ' ')
        date_convert = fields.Datetime.from_string(date_str)
        fields_model = self.env['ir.fields.converter']
        from_zone = fields_model._input_tz()
        to_zone = pytz.UTC
        #si no hay informacion de zona horaria, establecer la zona horaria
        if not date_convert.tzinfo:
            date_convert = from_zone.localize(date_convert)
        date_convert = date_convert.astimezone(to_zone)
        return date_convert




"""    {
"id": "WARRANTY_TYPE",
"name": "Tipo de garantía",
"tags": {
},
"hierarchy": "SALE_TERMS",
"relevance": 2,
"value_type": "list",
"values": [
{
"id": "2230280",
"name": "Garantía del vendedor"
},
{
"id": "2230279",
"name": "Garantía de fábrica"
},
{
"id": "6150835",
"name": "Sin garantía"
}
],
"attribute_group_id": "OTHERS",
"attribute_group_name": "Otros"
}
"""
