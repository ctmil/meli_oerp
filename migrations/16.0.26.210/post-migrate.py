# -*- coding: utf-8 -*-
"""[#661 fase 3] La URL de la API pasa a un único campo validado: res.company.meli_api_url.

Hasta 26.209 el host alternativo (proxy de rescate) estaba en res.company.mercadolibre_http_proxy,
que desde 26.210 es un alias sin almacenar. Su columna sigue en la base (Odoo no borra columnas):
acá se copia su valor al campo nuevo para que quien usa el proxy siga exactamente igual.
Idempotente: sólo toca compañías que quedaron con la URL oficial (o vacía) y tienen proxy viejo.
Un valor viejo inválido (p. ej. sin https://, que requests ya rechazaba) se informa y queda la oficial.
"""
import logging

_logger = logging.getLogger(__name__)

API_HOST_DEFAULT = "https://api.mercadolibre.com"


def _column_exists(cr, table, column):
    cr.execute("SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s",
               (table, column))
    return bool(cr.fetchone())


def migrate(cr, version):
    if not _column_exists(cr, 'res_company', 'mercadolibre_http_proxy') \
            or not _column_exists(cr, 'res_company', 'meli_api_url'):
        return
    from odoo.addons.meli_oerp.models.meli_util import meli_normalize_api_url
    cr.execute("""
        SELECT id, mercadolibre_http_proxy FROM res_company
         WHERE coalesce(trim(mercadolibre_http_proxy), '') <> ''
           AND (meli_api_url IS NULL OR meli_api_url IN ('', %s, %s))
    """, (API_HOST_DEFAULT, API_HOST_DEFAULT + '/'))
    for company_id, old in cr.fetchall():
        try:
            url = meli_normalize_api_url(old)
        except ValueError as e:
            _logger.warning("MELI 26.210: compañía %s: proxy viejo %r inválido (%s); queda la URL oficial",
                            company_id, old, e)
            continue
        cr.execute("UPDATE res_company SET meli_api_url=%s WHERE id=%s", (url, company_id))
        _logger.warning("MELI 26.210: compañía %s: URL de la API = %s (copiada de mercadolibre_http_proxy)",
                        company_id, url)
    cr.execute("UPDATE res_company SET meli_api_url=%s WHERE meli_api_url IS NULL OR meli_api_url=''",
               (API_HOST_DEFAULT,))
