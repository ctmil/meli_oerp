# -*- coding: utf-8 -*-
"""#caso-K03 cliente A (build 26.282) -- la re-sincronizacion de una orden ML respeta la direccion cambiada a mano.

Recorre el camino real orders_update_order_json con ML simulado (sin red):
1. orden nueva: el pedido toma la entrega de ML (y queda registrada como puesta por el conector).
2. re-sync SIN cambio manual y con la direccion cambiada en ML: la entrega se actualiza (no se congela).
3. el usuario edita la calle del contacto de entrega a mano: la re-sync NO la devuelve a la de ML.
4. el usuario elige otro contacto de entrega en el pedido: la re-sync NO lo reemplaza.
5. el usuario elige otro contacto de factura: la re-sync NO lo reemplaza.
Control (origin sin el fix): 3, 4 y 5 tienen que FALLAR.
"""
import copy
from unittest.mock import patch

from odoo.tests import common, tagged
from odoo.tools import mute_logger


class _MPNoDisponible:
    """Respuesta de MercadoPago no disponible (503): mismo resultado que sin red (no hay datos
    de MP y la orden sigue), sin el WARNING de red que ensucia el log del build."""
    ok = False
    status_code = 503

    def __bool__(self):
        return False

    def json(self):
        return {}


OID = 2000282043025486
BUYER_ID = 51300101
STREET_ML = 'Calle Falsa 123'
STREET_ML2 = 'Avenida Nueva 456'
STREET_MANUAL = 'Carrera 7 # 12-34 (corregida a mano)'


class _Resp:
    status_code = 200
    ok = True

    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class _FakeMeli:
    access_token = 'TEST'

    def __init__(self, routes):
        self.routes = routes

    def get(self, path, params=None, **kwargs):
        for prefix, data in self.routes:
            if path.startswith(prefix):
                return _Resp(copy.deepcopy(data))
        return _Resp({})

    def need_login(self):
        return False


def _receiver(street):
    return {'address_line': street, 'receiver_name': 'Sebastian Prueba', 'zip_code': '1000',
            'city': {'name': 'Buenos Aires'}, 'state': {'id': 'AR-C', 'name': 'Capital Federal'},
            'country': {'id': 'AR', 'name': 'Argentina'}, 'comment': ''}


def _order_json(street=STREET_ML):
    return {
        'id': OID, 'status': 'paid', 'status_detail': None,
        'date_created': '2026-10-22T10:00:00.000-03:00', 'date_closed': '2026-10-22T10:00:01.000-03:00',
        'total_amount': 1000.0, 'paid_amount': 1000.0, 'currency_id': 'ARS',
        'coupon': {'id': None, 'amount': 0},
        'order_items': [{'item': {'id': 'MLA554523', 'title': 'Prueba K03', 'variation_id': None,
                                  'seller_sku': 'SKU554523', 'category_id': 'MLA1'},
                         'quantity': 1, 'unit_price': 1000.0, 'full_unit_price': 1000.0, 'currency_id': 'ARS'}],
        'payments': [{'id': 99513001, 'transaction_amount': 1000.0, 'total_paid_amount': 1000.0,
                      'currency_id': 'ARS', 'status': 'approved', 'coupon_amount': 0,
                      'shipping_cost': 0, 'date_created': '2026-10-22T10:00:01.000-03:00',
                      'date_last_modified': '2026-10-22T10:00:01.000-03:00'}],
        'buyer': {'id': BUYER_ID, 'nickname': 'COMPRADORK03', 'first_name': 'Sebastian',
                  'last_name': 'Prueba', 'name': 'Sebastian Prueba', 'email': 'sebaK03@example.com',
                  'phone': {'area_code': '11', 'number': '45556666'}},
        'seller': {'id': 513999},
        'tags': ['paid'], 'context': {'channel': 'marketplace', 'site': 'MLA'},
        'shipping': {'id': None, 'receiver_address': _receiver(street)}, 'pack_id': None,
    }


@tagged('post_install', '-at_install', 'meli', 'meli_K03')
class TestMeliK03DireccionesManuales(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        pricelist = cls.env['product.pricelist'].search([], limit=1) or \
            cls.env['product.pricelist'].create({'name': 'Lista ML'})
        cls.company.mercadolibre_pricelist = pricelist
        if 'mercadolibre_cron_get_orders_shipment_client' in cls.company._fields:
            cls.company.mercadolibre_cron_get_orders_shipment_client = True
        cls.product = cls.env['product.product'].create({
            'name': 'Prueba K03', 'taxes_id': [(5, 0, 0)], 'meli_id': 'MLA554523', 'default_code': 'SKU554523'})

    def _sync(self, street=STREET_ML):
        oj = _order_json(street)
        routes = [('/orders/%s/billing_info' % OID, {}), ('/orders/%s/discounts' % OID, {}),
                  ('/orders/%s' % OID, oj), ('/items/', {'id': 'MLA554523', 'title': 'Prueba K03'})]
        with patch('odoo.addons.meli_oerp.models.orders.requests.get', return_value=_MPNoDisponible()), \
                mute_logger('odoo.addons.meli_oerp_multiple.models.sale'):
            res = self.env['mercadolibre.orders'].orders_update_order_json(
                {'id': False, 'order_json': oj}, meli=_FakeMeli(routes), config=self.company)
        self.assertFalse(isinstance(res, dict) and res.get('error'), res)
        so = self.env['sale.order'].search([('meli_order_id', '=', str(OID))], limit=1)
        self.assertTrue(so, "la sincronizacion no creo el pedido: %s" % (res,))
        so.invalidate_recordset()
        return so

    def test_1_nueva_toma_la_entrega_de_ml(self):
        so = self._sync()
        self.assertEqual(so.partner_shipping_id.street, STREET_ML)
        self.assertNotEqual(so.partner_shipping_id, so.partner_id, "la entrega no es el contacto de entrega de ML")

    def test_2_sin_cambio_manual_sigue_actualizando(self):
        so = self._sync()
        so = self._sync(STREET_ML2)
        self.assertEqual(so.partner_shipping_id.street, STREET_ML2,
                         "sin edicion manual, el cambio de direccion en ML tiene que entrar")

    def test_3_calle_editada_a_mano_se_conserva(self):
        so = self._sync()
        ship = so.partner_shipping_id
        ship.write({'street': STREET_MANUAL})
        so = self._sync()
        self.assertEqual(so.partner_shipping_id, ship)
        self.assertEqual(so.partner_shipping_id.street, STREET_MANUAL,
                         "la re-sincronizacion devolvio la calle editada a mano a la de ML")

    def test_4_otro_contacto_de_entrega_se_conserva(self):
        so = self._sync()
        otro = self.env['res.partner'].create({'name': 'Bodega del cliente', 'type': 'delivery',
                                               'parent_id': so.partner_id.id, 'street': STREET_MANUAL})
        so.write({'partner_shipping_id': otro.id})
        so = self._sync()
        self.assertEqual(so.partner_shipping_id, otro,
                         "la re-sincronizacion reemplazo el contacto de entrega elegido a mano")
        self.assertEqual(otro.street, STREET_MANUAL)

    def test_5_otro_contacto_de_factura_se_conserva(self):
        so = self._sync()
        if so.partner_invoice_id == so.partner_id and not so.partner_invoice_id:
            self.skipTest('sin contacto de factura')
        otro = self.env['res.partner'].create({'name': 'Razon social a mano', 'street': STREET_MANUAL})
        so.write({'partner_invoice_id': otro.id})
        so = self._sync()
        self.assertEqual(so.partner_invoice_id, otro,
                         "la re-sincronizacion reemplazo el contacto de factura elegido a mano")
