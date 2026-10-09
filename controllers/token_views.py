# -*- coding: utf-8 -*-
"""#661 (542) — Vistas de la API de MercadoLibre SIN el access_token en la URL.

Antes, el link "Link Api" de la publicación, el botón "Abrir API" y los links de
descarga de etiquetas llevaban `?access_token=APP_USR-...` pegado: el token quedaba
en la pantalla, en el historial del navegador, en el Referer y en logs de proxies.
Ahora esos links apuntan acá: Odoo resuelve el token del lado del servidor y lo
manda en el header `Authorization: Bearer`, nunca al navegador.

Sólo usuarios internos. El token se resuelve con hooks overridables
(`meli.util._meli_view_instance`, `mercadolibre.shipment._meli_label_instance`)
para que meli_oerp_multiple use la cuenta correcta.
"""
import json
import logging
import re

import requests

from odoo import http
from odoo import release as odoo_release
from odoo.http import request

_logger = logging.getLogger(__name__)

_MELI_ID_RE = re.compile(r'^[A-Z]{3,4}\d{1,20}$')
_IDS_RE = re.compile(r'^\d{1,12}(,\d{1,12}){0,199}$')
_LABEL_TYPES = ('pdf', 'zpl2')


def _check_read(records):
    """Chequeo de lectura compatible 16/17 (check_access_rights/rule) y 18/19 (check_access)."""
    if odoo_release.version_info[0] >= 18:
        records.check_access('read')
    else:
        records.check_access_rights('read')
        records.check_access_rule('read')


def _forbidden():
    return request.make_response('Forbidden', status=403, headers=[('Content-Type', 'text/plain')])


def _bad_request(msg):
    return request.make_response(msg, status=400, headers=[('Content-Type', 'text/plain; charset=utf-8')])


class MeliTokenlessViews(http.Controller):

    @http.route(['/meli/item_api/<string:meli_id>'], type='http', auth='user', methods=['GET'])
    def meli_item_api(self, meli_id, account=None, **kw):
        if not request.env.user.has_group('base.group_user'):
            return _forbidden()
        meli_id = (meli_id or '').strip().upper()
        if not _MELI_ID_RE.match(meli_id):
            return _bad_request('meli_id inválido')
        account_id = int(account) if (account and str(account).isdigit()) else False
        meli = request.env['meli.util']._meli_view_instance(account_id=account_id)
        if not meli or meli.need_login():
            return _bad_request('La cuenta de MercadoLibre necesita volver a iniciar sesión.')
        response = meli.get('/items/' + meli_id, {'access_token': meli.access_token, 'include_attributes': 'all'})
        try:
            rjson = response.json()
        except Exception:
            rjson = {'error': 'respuesta no JSON de MercadoLibre'}
        body = json.dumps(rjson, indent=2, ensure_ascii=False)
        return request.make_response(body, headers=[('Content-Type', 'application/json; charset=utf-8')])

    @http.route(['/meli/shipment_labels'], type='http', auth='user', methods=['GET'])
    def meli_shipment_labels(self, ids=None, response_type='pdf', **kw):
        if not request.env.user.has_group('base.group_user'):
            return _forbidden()
        if not ids or not _IDS_RE.match(ids):
            return _bad_request('ids inválidos')
        if response_type not in _LABEL_TYPES:
            return _bad_request('response_type inválido')
        shipments = request.env['mercadolibre.shipment'].browse([int(i) for i in ids.split(',')]).exists()
        if not shipments:
            return _bad_request('envíos inexistentes')
        _check_read(shipments)
        tokens = {}
        for shipment in shipments:
            meli = shipment._meli_label_instance()
            tok = meli and meli.access_token or ''
            if not tok or tok == 'PASIVA':
                return _bad_request('La cuenta de MercadoLibre del envío %s necesita volver a iniciar sesión.' % (shipment.shipping_id or shipment.id))
            tokens.setdefault(tok, []).append(shipment.shipping_id)
        if len(tokens) != 1:
            return _bad_request('Los envíos pertenecen a cuentas distintas: bajalos por separado.')
        tok, shipping_ids = next(iter(tokens.items()))
        url = 'https://api.mercadolibre.com/shipment_labels'
        try:
            resp = requests.get(
                url,
                params={'shipment_ids': ','.join(shipping_ids), 'response_type': response_type},
                headers={'Authorization': 'Bearer %s' % tok},
                timeout=60,
            )
        except requests.RequestException as e:
            _logger.warning("meli_shipment_labels: error de red (%s)", type(e).__name__)
            return request.make_response('Error de red al consultar MercadoLibre', status=502,
                                         headers=[('Content-Type', 'text/plain; charset=utf-8')])
        if resp.status_code != 200:
            _logger.info("meli_shipment_labels: ML respondió %s para %s envío(s)", resp.status_code, len(shipping_ids))
            return request.make_response(resp.content, status=resp.status_code,
                                         headers=[('Content-Type', resp.headers.get('Content-Type', 'text/plain'))])
        ctype = resp.headers.get('Content-Type') or ('application/pdf' if response_type == 'pdf' else 'application/zip')
        ext = 'pdf' if 'pdf' in ctype else ('zip' if 'zip' in ctype else 'txt')
        filename = 'Etiquetas_%s.%s' % ('_'.join(shipping_ids[:3]) + ('_etc' if len(shipping_ids) > 3 else ''), ext)
        return request.make_response(resp.content, headers=[
            ('Content-Type', ctype),
            ('Content-Disposition', 'inline; filename="%s"' % filename),
            ('Cache-Control', 'no-store'),
        ])
