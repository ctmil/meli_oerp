# -*- coding: utf-8 -*-
"""Brasil A / A3 (26.310): Mercado Livre Brasil empezo a devolver IDs de pago ALFANUMERICOS.

Camino REAL del import (orders_update_order_json con ML simulado, sin red, igual que
test_import_cupon_linea): una orden MLB/BRL con payment_id alfanumerico tiene que crear la venta
y el mercadolibre.payments con el ID tal cual (texto, sin castear a int), y un re-sync no tiene que
duplicar el pago. Tambien una orden cuyo propio id no es numerico.
"""
from unittest.mock import patch

from odoo.tests import common, tagged
from odoo.tools import mute_logger

PAY_ID = 'MLB-abc123XYZ'


class _MPNoDisponible:
    ok = False
    status_code = 503

    def __bool__(self):
        return False

    def json(self):
        return {}


class _Resp:
    def __init__(self, data):
        self._data = data
        self.ok = True

    def json(self):
        return self._data


class _FakeMeli:
    access_token = 'TEST'

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, path, params=None):
        self.calls.append(path)
        for prefix, data in self.routes:
            if path.startswith(prefix):
                return _Resp(data)
        return _Resp({})

    def need_login(self):
        return False


def _order_json(oid, pay_id=PAY_ID, unit=199.90, item='MLB000TEST'):
    return {
        'id': oid, 'status': 'paid', 'status_detail': None,
        'date_created': '2026-10-26T10:00:00.000-03:00', 'date_closed': '2026-10-26T10:00:01.000-03:00',
        'total_amount': unit, 'paid_amount': unit, 'currency_id': 'BRL',
        'coupon': {'id': None, 'amount': 0},
        'order_items': [{'item': {'id': item, 'title': 'Produto', 'variation_id': None,
                                  'seller_sku': 'SKUBR0', 'category_id': 'MLB1'},
                         'quantity': 1, 'unit_price': unit, 'full_unit_price': unit, 'currency_id': 'BRL'}],
        'payments': [{'id': pay_id, 'transaction_amount': unit, 'total_paid_amount': unit,
                      'currency_id': 'BRL', 'status': 'approved', 'coupon_amount': 0,
                      'shipping_cost': 0, 'date_created': '2026-10-26T10:00:01.000-03:00',
                      'date_last_modified': '2026-10-26T10:00:01.000-03:00'}],
        'buyer': {'id': 777001, 'nickname': 'COMPRADORBR', 'first_name': 'Comprador', 'last_name': 'Brasil',
                  'name': 'Comprador Brasil', 'email': 'comprador.br@example.com',
                  'phone': {'area_code': '11', 'number': '00000000'}, 'alternative_phone': {}},
        'seller': {'id': 777999},
        'tags': ['paid'], 'context': {'channel': 'marketplace', 'site': 'MLB'},
        'shipping': {'id': None}, 'pack_id': None,
    }


@tagged('post_install', '-at_install', 'meli', 'meli_26310')
class TestMLBIdsAlfanumericos26310(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        pricelist = cls.env['product.pricelist'].search([], limit=1) or cls.env['product.pricelist'].create({'name': 'Lista ML'})
        cls.company.mercadolibre_pricelist = pricelist
        cls.contact = cls.env['res.partner'].create({'name': 'Cliente ML BR'})
        if 'mercadolibre_contact_partner' in cls.company._fields:
            cls.company.mercadolibre_contact_partner = cls.contact
        if 'mercadolibre_cron_get_orders_shipment_client' in cls.company._fields:
            cls.company.mercadolibre_cron_get_orders_shipment_client = True
        cls.product = cls.env['product.product'].create({
            'name': 'Produto', 'taxes_id': [(5, 0, 0)], 'meli_id': 'MLB000TEST', 'default_code': 'SKUBR0'})

    def _run(self, order_json):
        meli = _FakeMeli([('/items/', {'id': 'MLB000TEST', 'title': 'Produto'})])
        with patch('odoo.addons.meli_oerp.models.orders.requests.get', return_value=_MPNoDisponible()), \
                mute_logger('odoo.addons.meli_oerp_multiple.models.sale'):
            res = self.env['mercadolibre.orders'].orders_update_order_json(
                {'id': False, 'order_json': order_json}, meli=meli, config=self.company)
        self.assertFalse(isinstance(res, dict) and res.get('error'), res)
        return res

    def _payments(self, pay_id=PAY_ID):
        return self.env['mercadolibre.payments'].search([('payment_id', '=', pay_id)])

    def test_payment_id_alfanumerico_se_guarda_tal_cual(self):
        oid = 2000012345670001
        self._run(_order_json(oid))
        so = self.env['sale.order'].search([('meli_order_id', '=', str(oid))], limit=1)
        self.assertTrue(so, 'no se creo la venta MLB')
        pay = self._payments()
        self.assertEqual(len(pay), 1)
        self.assertEqual(pay.payment_id, PAY_ID)
        self.assertEqual(pay.currency_id, 'BRL')
        self.assertTrue(pay.mercadopago_url.endswith('/' + PAY_ID))

    def test_resync_no_duplica_pago_alfanumerico(self):
        oid = 2000012345670002
        self._run(_order_json(oid))
        self._run(_order_json(oid))
        self.assertEqual(len(self._payments()), 1)

    def test_order_id_alfanumerico(self):
        oid = 'MLB-abc123XYZ-ORD'
        self._run(_order_json(oid, pay_id='MLBpay-ORD-77'))
        so = self.env['sale.order'].search([('meli_order_id', '=', oid)], limit=1)
        self.assertTrue(so, 'orden con id no numerico no genero la venta')
        self.assertEqual(len(self._payments('MLBpay-ORD-77')), 1)
