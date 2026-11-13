# -*- coding: utf-8 -*-
"""Modo SIMULACION de ordenes de Mercado Libre: cliente simulado y guarda de red (sin modelos).

Una simulacion importa una venta a partir de un *bundle* JSON por el MISMO camino real del import
(`mercadolibre.orders.orders_update_order_json`), sin que la venta exista en ML:

    {"order": {...json de /orders/<id>...},
     "routes": {"/shipments/123": {...}, "/orders/<id>/discounts": {...},
                "https://api.mercadopago.com/v1/payments/456": {...}},
     "meta": {...libre: origen, anonimizado, notas...}}

Garantias (por construccion, no por convencion):
  * `MeliSimClient` responde los GET desde el bundle y NO deja salir ninguna escritura
    (POST/PUT/DELETE/upload): la anota en `blocked` y devuelve un error 403 «meli_simulation».
  * Mientras la simulacion esta ACTIVA en el hilo, `meli.util.get_new_instance()` devuelve el mismo
    cliente simulado (el import crea clientes nuevos en ~200 lugares).
  * El codigo que llama a `requests` directo (MercadoPago) o al SDK (urllib3) pasa por una guarda
    instalada en `requests.adapters.HTTPAdapter.send` y en `urllib3 HTTPConnectionPool.urlopen`:
    sólo actua en el hilo que simula y sólo para hosts de ML/MP; GET desde el bundle, el resto
    bloqueado. Fuera de una simulacion la guarda es un `if` de un atributo thread-local.
  * Ruta GET no cubierta ⇒ `{}` y queda en `missing` (o, con `fallback_real_reads`, GET real con el
    token de la cuenta; nunca escrituras).
"""
import copy
import json
import logging
import threading
from contextlib import contextmanager
from urllib.parse import urlencode, urlsplit

_logger = logging.getLogger(__name__)

MELI_SIM_BLOCKED = {"error": "meli_simulation", "status": 403,
                    "message": "Escritura bloqueada: venta SIMULADA (no existe en Mercado Libre)"}

_STATE = threading.local()
_GUARD_INSTALLED = False
_GUARD_LOCK = threading.Lock()


def meli_sim_is_ml_host(host):
    host = (host or '').lower().split(':', 1)[0]
    return any(h in host for h in ('mercadolibre', 'mercadolivre', 'mercadopago'))


def meli_sim_parse_bundle(bundle):
    """str/bytes/dict ⇒ dict validado. Lanza ValueError con un motivo legible."""
    if isinstance(bundle, (bytes, bytearray)):
        bundle = bundle.decode('utf-8')
    if isinstance(bundle, str):
        try:
            bundle = json.loads(bundle)
        except ValueError as e:
            raise ValueError("el bundle no es un JSON válido: %s" % e)
    if not isinstance(bundle, dict):
        raise ValueError("el bundle tiene que ser un objeto JSON")
    order = bundle.get('order')
    if not isinstance(order, dict) and 'id' in bundle and 'order_items' in bundle:
        # se acepta el JSON pelado de /orders/<id>
        bundle = {'order': bundle, 'routes': {}, 'meta': {}}
        order = bundle['order']
    if not isinstance(order, dict) or not order.get('id'):
        raise ValueError("el bundle no trae «order» con «id»")
    routes = bundle.get('routes') or {}
    if not isinstance(routes, dict):
        raise ValueError("«routes» tiene que ser un objeto {ruta: json}")
    return {'order': order, 'routes': routes, 'meta': bundle.get('meta') or {}}


def _norm_key(url):
    """(clave_con_query, clave_sin_query). ML ⇒ path ('/orders/1'); otro host ⇒ URL sin esquema."""
    s = str(url or '')
    parts = urlsplit(s if '://' in s else 'https://api.mercadolibre.com/' + s.lstrip('/'))
    host = parts.netloc.lower()
    path = '/' + parts.path.lstrip('/')
    path = path.rstrip('/') or '/'
    if 'api.mercadolibre.com' in host or 'api.mercadolivre.com' in host:
        base = path
    else:
        base = 'https://%s%s' % (host, path)
    q = '&'.join(sorted(p for p in (parts.query or '').split('&') if p and not p.startswith('access_token=')))
    return (base + '?' + q) if q else base, base


class MeliSimClient(object):
    """Cliente ML simulado con la interfaz de MeliApiNoSDK (get/post/put/delete/... + response/rjson)."""

    is_meli_simulation = True
    _session = None  # meli_instance_session(meli) cae a `requests` ⇒ pasa por la guarda

    def __init__(self, bundle, seller_id=None, real=None, fallback_real_reads=False):
        self.bundle = meli_sim_parse_bundle(bundle)
        order = self.bundle['order']
        self.order_id = str(order['id'])
        self.routes = {}
        for k, v in (self.bundle.get('routes') or {}).items():
            self.routes[_norm_key(k)[0]] = v
        self.routes.setdefault('/orders/%s' % self.order_id, order)
        self.seller_id = str(seller_id or (order.get('seller') or {}).get('id') or '')
        self.access_token = 'APP_USR-SIMULACION-%s' % (self.seller_id or '0')
        self.refresh_token = ''
        self.client_id = self.client_secret = self.redirect_uri = ''
        self.api_host = 'https://api.mercadolibre.com'
        self.AUTH_URL = ''
        self.needlogin_state = False
        self.response = self.rjson = None
        self._real = real if fallback_real_reads else None
        self.calls = []     # GET servidos (ruta)
        self.missing = []   # GET sin ruta en el bundle
        self.blocked = []   # escrituras que NO salieron
        self.real_reads = []

    # --- lectura -------------------------------------------------------------------------------
    def lookup(self, url, params=None):
        """(encontrado, json) para una URL/ruta (ML o MP) con sus params de query."""
        if params:
            q = {k: v for k, v in dict(params).items()
                 if k not in ('access_token', 'headers', 'timeout', 'query') and v is not None}
            if isinstance(dict(params).get('query'), dict):
                q.update(params['query'])
            if q:
                url = str(url) + ('&' if '?' in str(url) else '?') + urlencode(q)
        full, base = _norm_key(url)
        for key in (full, base):
            if key in self.routes:
                return True, copy.deepcopy(self.routes[key])
        return False, full

    def _set(self, data):
        self.response = self.rjson = data
        return self

    def get(self, path, params=None, extra_headers=None, **kwargs):
        found, data = self.lookup(path, params)
        if found:
            self.calls.append(_norm_key(path)[0])
            return self._set(data)
        if self._real is not None:
            self.real_reads.append(data)
            with meli_sim_passthrough():
                r = self._real.get(path, params or {'access_token': getattr(self._real, 'access_token', '')},
                                   extra_headers=extra_headers)
            try:
                return self._set(r.json())
            except Exception:
                return self._set({})
        if data not in self.missing:
            self.missing.append(data)
        return self._set({})

    def get_mini(self, path, params=None, extra_headers=None, **kwargs):
        return self.get(path, params, extra_headers=extra_headers)

    # --- escritura: nunca sale -----------------------------------------------------------------
    def _block(self, method, path):
        self.blocked.append('%s %s' % (method, _norm_key(path)[1]))
        _logger.info("meli simulacion: %s %s bloqueado (no sale a ML)", method, path)
        return self._set(dict(MELI_SIM_BLOCKED))

    def post(self, path, body=None, params=None, extra_headers=None, **kwargs):
        return self._block('POST', path)

    def post_mini(self, path, body=None, params=None, extra_headers=None, **kwargs):
        return self._block('POST', path)

    def put(self, path, body=None, params=None, extra_headers=None, **kwargs):
        return self._block('PUT', path)

    def put_mini(self, path, body=None, params=None, extra_headers=None, **kwargs):
        return self._block('PUT', path)

    def delete(self, path, params=None, extra_headers=None, **kwargs):
        return self._block('DELETE', path)

    def upload(self, path, files=None, params=None, **kwargs):
        return self._block('UPLOAD', path)

    def uploadfiles(self, path, files=None, params=None, **kwargs):
        return self._block('UPLOAD', path)

    # --- resto de la interfaz ------------------------------------------------------------------
    def need_login(self):
        return False

    def json(self):
        return self.rjson

    def get_refresh_token(self, *a, **k):
        return None

    def auth_url(self, *a, **k):
        return ''

    def redirect_login(self, *a, **k):
        return ''

    def authorize(self, *a, **k):
        return None

    def get_sale_terms(self, *a, **k):
        return {}

    def get_user_product_stock_with_version(self, *a, **k):
        return {}, None

    def summary(self):
        return {'calls': list(self.calls), 'missing': list(self.missing),
                'blocked': list(self.blocked), 'real_reads': list(self.real_reads)}


# ------------------------------------------------------------------------------------------------
# Estado por hilo
# ------------------------------------------------------------------------------------------------
def meli_sim_active(dbname=None):
    """Cliente simulado activo en este hilo (y para esta base), o None."""
    client = getattr(_STATE, 'client', None)
    if client is None:
        return None
    if dbname and getattr(_STATE, 'dbname', None) not in (None, dbname):
        return None
    return client


@contextmanager
def meli_sim_activate(client, dbname=None):
    meli_sim_install_guard()
    prev = (getattr(_STATE, 'client', None), getattr(_STATE, 'dbname', None))
    _STATE.client, _STATE.dbname = client, dbname
    try:
        yield client
    finally:
        _STATE.client, _STATE.dbname = prev


@contextmanager
def meli_sim_passthrough():
    prev = getattr(_STATE, 'passthrough', False)
    _STATE.passthrough = True
    try:
        yield
    finally:
        _STATE.passthrough = prev


def _guard_target():
    """Cliente simulado si la guarda tiene que actuar en este hilo."""
    client = getattr(_STATE, 'client', None)
    if client is None or getattr(_STATE, 'passthrough', False):
        return None
    return client


# ------------------------------------------------------------------------------------------------
# Guarda de red (requests + urllib3): sólo en el hilo que simula, sólo hosts de ML/MP
# ------------------------------------------------------------------------------------------------
def _fake_requests_response(request, status, data):
    import requests
    r = requests.models.Response()
    r.status_code = status
    r._content = json.dumps(data).encode('utf-8')
    r.headers['Content-Type'] = 'application/json'
    r.encoding = 'utf-8'
    r.url = getattr(request, 'url', '')
    r.request = request
    r.reason = 'OK' if status < 400 else 'Simulation'
    return r


def meli_sim_install_guard():
    global _GUARD_INSTALLED
    if _GUARD_INSTALLED:
        return
    with _GUARD_LOCK:
        if _GUARD_INSTALLED:
            return
        try:
            import requests.adapters as _ra
            _orig_send = _ra.HTTPAdapter.send

            def _sim_send(self, request, *args, **kwargs):
                client = _guard_target()
                if client is None:
                    return _orig_send(self, request, *args, **kwargs)
                host = urlsplit(request.url).netloc
                if not meli_sim_is_ml_host(host):
                    return _orig_send(self, request, *args, **kwargs)
                method = (request.method or 'GET').upper()
                if method != 'GET':
                    client.blocked.append('%s %s' % (method, _norm_key(request.url)[1]))
                    _logger.info("meli simulacion: %s %s bloqueado en requests", method, request.url.split('?')[0])
                    return _fake_requests_response(request, 403, dict(MELI_SIM_BLOCKED))
                found, data = client.lookup(request.url)
                if found:
                    client.calls.append(_norm_key(request.url)[0])
                    return _fake_requests_response(request, 200, data)
                if data not in client.missing:
                    client.missing.append(data)
                return _fake_requests_response(request, 404, {"error": "not_found", "status": 404,
                                                              "message": "ruta no cubierta por el bundle de simulacion"})

            _ra.HTTPAdapter.send = _sim_send
        except Exception as e:  # pragma: no cover
            _logger.warning("meli simulacion: no se pudo instalar la guarda de requests: %s", e)
        try:
            import urllib3.connectionpool as _cp
            _orig_urlopen = _cp.HTTPConnectionPool.urlopen

            def _sim_urlopen(self, method, url, *args, **kwargs):
                client = _guard_target()
                if client is not None and meli_sim_is_ml_host(getattr(self, 'host', '')):
                    # sólo llega acá lo que NO pasó por requests (SDK oficial): se bloquea entero.
                    import urllib3.exceptions as _ue
                    client.blocked.append('%s https://%s%s' % ((method or '').upper(), self.host, str(url).split('?')[0]))
                    raise _ue.ProtocolError("bloqueado por la simulación de Mercado Libre")
                return _orig_urlopen(self, method, url, *args, **kwargs)

            _cp.HTTPConnectionPool.urlopen = _sim_urlopen
        except Exception as e:  # pragma: no cover
            _logger.warning("meli simulacion: no se pudo instalar la guarda de urllib3: %s", e)
        _GUARD_INSTALLED = True
