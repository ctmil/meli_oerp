# -*- coding: utf-8 -*-
"""Build de flota 13-nov-2026: un status HTTP de error NO se lee como éxito aunque el cuerpo no traiga «error».

ML responde el token vencido/inválido con UNAUTHORIZED {"code": "unauthorized", "message": "invalid access token"}
— sin clave `error`. Todo el código decide éxito con `"error" in rjson`: el cron de precio contaba los PUT
rechazados como publicados (cientos por semana en una instancia nuestra). `_parse_response` ahora agrega `error`/`status`.
"""
from http import HTTPStatus as H

from odoo.tests import TransactionCase, tagged

from odoo.addons.meli_oerp.models.meli_util import MeliApiNoSDK


class _Resp(object):
    def __init__(self, status, data=None, text=None):
        self.status_code = status
        self._data = data
        self.text = text if text is not None else ''
        self.url = 'https://api.mercadolibre.com/items/MLAPRUEBA'

    def json(self):
        if self._data is None:
            raise ValueError('sin json')
        return self._data


@tagged('post_install', '-at_install', 'meli_put_rechazado')
class TestPutRechazadoNoEsExito(TransactionCase):

    def _parse(self, resp):
        return MeliApiNoSDK._parse_response(None, resp)

    def test_unauthorized_sin_error_queda_como_error(self):
        r = self._parse(_Resp(H.UNAUTHORIZED, {'code': 'unauthorized', 'message': 'invalid access token'}))
        self.assertIn('error', r)
        self.assertEqual(r['error'], 'unauthorized')
        self.assertEqual(r['status'], H.UNAUTHORIZED)
        self.assertEqual(r['message'], 'invalid access token')

    def test_forbidden_sin_code_usa_http_status(self):
        r = self._parse(_Resp(H.FORBIDDEN, {'message': 'forbidden for this item'}))
        self.assertEqual(r['error'], 'http_%d' % H.FORBIDDEN)
        self.assertEqual(r['status'], H.FORBIDDEN)

    def test_error_de_ml_no_se_toca(self):
        body = {'message': 'Item not found', 'error': 'not_found', 'status': int(H.NOT_FOUND), 'cause': []}
        self.assertEqual(self._parse(_Resp(H.NOT_FOUND, dict(body))), body)

    def test_exito_no_se_toca(self):
        body = {'id': 'MLAPRUEBA', 'price': 100}
        self.assertEqual(self._parse(_Resp(H.OK, dict(body))), body)

    def test_lista_y_texto_no_se_tocan(self):
        self.assertEqual(self._parse(_Resp(H.BAD_REQUEST, [1, 2])), [1, 2])
        r = self._parse(_Resp(H.TOO_MANY_REQUESTS, None, ''))
        self.assertEqual(r['error'], 'http_%d' % H.TOO_MANY_REQUESTS)   # el caso vacío de antes sigue igual
