# -*- coding: utf-8 -*-
"""26.229 -- integracion: orders_update_order_json con ML simulado (sin red).

Reproduce el camino REAL del import de una orden NUEVA (self = recordset vacio, como en la
notificacion / el cron) con el cupon a cargo del vendedor de ML 2000000000000001
(5.324, cupon 266,20, amounts.seller = 266,20, pagado 5.057,80), y el re-sync de una venta
confirmada a la que le falta encontrar su linea (ML 2000000000000004).
"""
from unittest.mock import patch

import requests

from odoo.tests import common, tagged

OID = 2000000000000001


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


def _order_json(oid=OID, unit=5324.0, paid=5057.80, coupon=266.20, item='MLM000TEST', status='paid'):
    return {
        'id': oid, 'status': status, 'status_detail': None,
        'date_created': '2026-10-08T10:00:00.000-06:00', 'date_closed': '2026-10-08T10:00:01.000-06:00',
        'total_amount': unit, 'paid_amount': paid, 'currency_id': 'MXN',
        'coupon': {'id': 'C1', 'amount': coupon} if coupon else {'id': None, 'amount': 0},
        'order_items': [{'item': {'id': item, 'title': 'Refaccion', 'variation_id': None,
                                  'seller_sku': 'SKU000', 'category_id': 'MLM1'},
                         'quantity': 1, 'unit_price': unit, 'full_unit_price': unit, 'currency_id': 'MXN'}],
        'payments': [{'id': 99000001, 'transaction_amount': paid, 'total_paid_amount': paid,
                      'currency_id': 'MXN', 'status': 'approved', 'coupon_amount': coupon,
                      'shipping_cost': 0, 'date_created': '2026-10-08T10:00:01.000-06:00',
                      'date_last_modified': '2026-10-08T10:00:01.000-06:00'}],
        'buyer': {'id': 123001, 'nickname': 'COMPRADOR123', 'first_name': 'Comprador', 'last_name': 'Test',
                  'name': 'Comprador Test', 'email': 'comprador@example.com',
                  'phone': {'area_code': '81', 'number': '00000000'}, 'alternative_phone': {}},
        'seller': {'id': 123999},
        'tags': ['paid'], 'context': {'channel': 'marketplace', 'site': 'MLM'},
        'shipping': {'id': None}, 'pack_id': None,
    }


def _discounts(seller=266.20):
    return {'details': [{'type': 'coupon', 'items': [{'id': 'MLM000TEST', 'quantity': 1,
                                                       'amounts': {'total': seller, 'seller': seller}}]}]}


@tagged('post_install', '-at_install', 'meli', 'meli_26229')
class TestImportCuponLinea(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        pricelist = cls.env['product.pricelist'].search([], limit=1) or cls.env['product.pricelist'].create({'name': 'Lista ML'})
        cls.company.mercadolibre_pricelist = pricelist
        # contacto fijo para las ventas ML (evita depender del alta de clientes)
        cls.contact = cls.env['res.partner'].create({'name': 'Cliente ML'})
        if 'mercadolibre_contact_partner' in cls.company._fields:
            cls.company.mercadolibre_contact_partner = cls.contact
        if 'mercadolibre_cron_get_orders_shipment_client' in cls.company._fields:
            cls.company.mercadolibre_cron_get_orders_shipment_client = True
        cls.product = cls.env['product.product'].create({
            'name': 'Refaccion', 'taxes_id': [(5, 0, 0)], 'meli_id': 'MLM000TEST', 'default_code': 'SKU000'})

    def _run(self, order_json, routes, records=None):
        meli = _FakeMeli(routes)
        Orders = records if records is not None else self.env['mercadolibre.orders']
        with patch('odoo.addons.meli_oerp.models.orders.requests.get', side_effect=requests.exceptions.ConnectionError('sin red')):
            res = Orders.orders_update_order_json({'id': False, 'order_json': order_json}, meli=meli, config=self.company)
        return res, meli

    def test_1_new_order_seller_coupon_line_is_net(self):
        routes = [('/orders/%s/discounts' % OID, _discounts()), ('/items/', {'id': 'MLM000TEST', 'title': 'Refaccion'})]
        res, meli = self._run(_order_json(), routes)
        self.assertFalse(isinstance(res, dict) and res.get('error'), res)
        so = self.env['sale.order'].search([('meli_order_id', '=', str(OID))], limit=1)
        self.assertTrue(so, "no se creo la venta: %s" % (res,))
        self.assertIn('/orders/%s/discounts' % OID, meli.calls)
        self.assertAlmostEqual(sum(so.order_line.filtered(lambda l: not l.is_delivery).mapped('price_unit')), 5057.80, places=2)
        self.assertAlmostEqual(so.amount_total, 5057.80, places=2)

    def test_1_coupon_only_in_payments_still_fetches_discounts(self):
        oj = _order_json()
        oj['coupon'] = {'id': None, 'amount': 0}
        routes = [('/orders/%s/discounts' % OID, _discounts()), ('/items/', {'id': 'MLM000TEST'})]
        res, meli = self._run(oj, routes)
        self.assertIn('/orders/%s/discounts' % OID, meli.calls)
        so = self.env['sale.order'].search([('meli_order_id', '=', str(OID))], limit=1)
        self.assertAlmostEqual(so.amount_total, 5057.80, places=2)

    def test_1_pack_member_coupon_only_in_payments_does_not_fetch(self):
        """Orden miembro de un PACK con el cupon solo en los pagos: NO se consulta /discounts (el cupon
        es del pack y no se resta por linea sin prorratear)."""
        oj = _order_json()
        oj['coupon'] = {'id': None, 'amount': 0}
        oj['pack_id'] = 2000000000000099
        routes = [('/orders/%s/discounts' % OID, _discounts()), ('/items/', {'id': 'MLM000TEST'})]
        res, meli = self._run(oj, routes)
        self.assertNotIn('/orders/%s/discounts' % OID, meli.calls)

    def test_6_resync_does_not_add_line_to_confirmed_sale(self):
        oid = 2000000000000004
        routes = [('/items/', {'id': 'MLM000TEST'})]
        oj = _order_json(oid=oid, unit=1610.0, paid=1610.0, coupon=0)
        self._run(oj, routes)
        so = self.env['sale.order'].search([('meli_order_id', '=', str(oid))], limit=1)
        self.assertTrue(so)
        if so.state not in ('sale', 'done'):
            so.action_confirm()
        n_lines = len(so.order_line)
        # la linea pierde su referencia al item (como si se hubiera tocado a mano) y el pago
        # ahora "no cuadra": antes el re-sync agregaba otra linea a la venta confirmada.
        so.order_line.write({'meli_order_item_id': False})
        so.meli_discount_seller_amount = 260.49
        oj2 = _order_json(oid=oid, unit=1610.0, paid=1610.0, coupon=0)
        self._run(oj2, routes)
        self.assertEqual(len(so.order_line), n_lines)
        self.assertAlmostEqual(so.amount_total, 1610.0, places=2)
