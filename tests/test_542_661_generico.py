# -*- coding: utf-8 -*-
"""#542-661 (build 26.264) -- tres correcciones genericas de orders_update_order_json, con ML simulado.

1. En una orden NUEVA el comprador (mercadolibre.buyers) queda vinculado a la orden (antes solo se
   vinculaba si la orden ya existia al entrar).
2. Si la orden se vuelve a pedir a ML (llega sin datos del comprador), data['order_json'] queda con
   el JSON que uso la importacion: los modulos que post-procesan despues de super() leen ese.
3. 'Consumidor Final' informado por ML cuenta como dato fiscal EXPLICITO: corrige una condicion
   AFIP previa del contacto (antes caia al default 5 pero como dato implicito y no se escribia).
Sin red: ML simulado.
"""
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


OID = 2000000054266101
BUYER_ID = 54266101


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
        self.calls = []

    def get(self, path, params=None, **kwargs):
        self.calls.append(path)
        for prefix, data in self.routes:
            if path.startswith(prefix):
                return _Resp(data)
        return _Resp({})

    def need_login(self):
        return False


def _buyer(full=True):
    b = {'id': BUYER_ID, 'nickname': 'COMPRADOR542'}
    if full:
        b.update({'first_name': 'Juana', 'last_name': 'Prueba', 'name': 'Juana Prueba',
                  'email': 'juana@example.com', 'phone': {'area_code': '11', 'number': '45556666'}})
    return b


def _order_json(oid=OID, full_buyer=True):
    return {
        'id': oid, 'status': 'paid', 'status_detail': None,
        'date_created': '2026-10-22T10:00:00.000-03:00', 'date_closed': '2026-10-22T10:00:01.000-03:00',
        'total_amount': 1000.0, 'paid_amount': 1000.0, 'currency_id': 'ARS',
        'coupon': {'id': None, 'amount': 0},
        'order_items': [{'item': {'id': 'MLA542661', 'title': 'Prueba 542', 'variation_id': None,
                                  'seller_sku': 'SKU542661', 'category_id': 'MLA1'},
                         'quantity': 1, 'unit_price': 1000.0, 'full_unit_price': 1000.0, 'currency_id': 'ARS'}],
        'payments': [{'id': 99542661, 'transaction_amount': 1000.0, 'total_paid_amount': 1000.0,
                      'currency_id': 'ARS', 'status': 'approved', 'coupon_amount': 0,
                      'shipping_cost': 0, 'date_created': '2026-10-22T10:00:01.000-03:00',
                      'date_last_modified': '2026-10-22T10:00:01.000-03:00'}],
        'buyer': _buyer(full_buyer),
        'seller': {'id': 542999},
        'tags': ['paid'], 'context': {'channel': 'marketplace', 'site': 'MLA'},
        'shipping': {'id': None}, 'pack_id': None,
    }


def _billing_cf_dni(dni='28000000'):
    return {'billing_info': {'doc_type': 'DNI', 'doc_number': dni, 'additional_info': [
        {'type': 'TAXPAYER_TYPE_ID', 'value': 'Consumidor Final'},
        {'type': 'FIRST_NAME', 'value': 'Juana'}, {'type': 'LAST_NAME', 'value': 'Prueba'},
        {'type': 'DOC_TYPE', 'value': 'DNI'}, {'type': 'DOC_NUMBER', 'value': dni},
    ]}}


@tagged('post_install', '-at_install', 'meli', 'meli_542_661')
class TestMeli542661Generico(common.TransactionCase):

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
            'name': 'Prueba 542', 'taxes_id': [(5, 0, 0)], 'meli_id': 'MLA542661', 'default_code': 'SKU542661'})

    def _run(self, data, routes):
        meli = _FakeMeli(routes)
        with patch('odoo.addons.meli_oerp.models.orders.requests.get', return_value=_MPNoDisponible()), \
                mute_logger('odoo.addons.meli_oerp_multiple.models.sale'):
            res = self.env['mercadolibre.orders'].orders_update_order_json(data, meli=meli, config=self.company)
        return res, meli

    def _routes(self, oid=OID, billing=None):
        return [('/orders/%s/billing_info' % oid, billing or {}),
                ('/orders/%s/discounts' % oid, {}),
                ('/orders/%s' % oid, _order_json(oid)),
                ('/items/', {'id': 'MLA542661', 'title': 'Prueba 542'})]

    def _order(self, oid=OID):
        return self.env['mercadolibre.orders'].search([('order_id', '=', str(oid))], limit=1)

    def test_1_new_order_links_buyer(self):
        res, meli = self._run({'id': False, 'order_json': _order_json()}, self._routes())
        self.assertFalse(isinstance(res, dict) and res.get('error'), res)
        order = self._order()
        self.assertTrue(order, "no se creo la orden: %s" % (res,))
        self.assertTrue(order.buyer, "orden NUEVA sin comprador vinculado")
        self.assertEqual(order.buyer.buyer_id, str(BUYER_ID))

    def test_2_refetched_order_json_is_shared(self):
        data = {'id': False, 'order_json': _order_json(full_buyer=False)}
        res, meli = self._run(data, self._routes())
        self.assertIn('/orders/%s' % OID, meli.calls, "el caso tiene que forzar el re-fetch de la orden")
        self.assertEqual(data['order_json'].get('buyer', {}).get('first_name'), 'Juana',
                         "data['order_json'] no es el JSON que uso la importacion")

    def test_3_consumidor_final_is_explicit(self):
        if 'l10n_ar_afip_responsibility_type_id' not in self.env['res.partner']._fields:
            self.skipTest('sin l10n_ar')
        Resp = self.env['l10n_ar.afip.responsibility.type']
        ri, cf = Resp.search([('code', '=', '1')], limit=1), Resp.search([('code', '=', '5')], limit=1)
        self.company.country_id = self.env.ref('base.ar')
        # contacto del comprador ya existente, cargado antes como Responsable Inscripto
        prev = self.env['res.partner'].create({
            'name': 'Juana Prueba', 'meli_buyer_id': str(BUYER_ID),
            'l10n_ar_afip_responsibility_type_id': ri.id})
        res, meli = self._run({'id': False, 'order_json': _order_json()},
                              self._routes(billing=_billing_cf_dni()))
        self.assertFalse(isinstance(res, dict) and res.get('error'), res)
        so = self.env['sale.order'].search([('meli_order_id', '=', str(OID))], limit=1)
        self.assertTrue(so)
        fiscal = so.partner_invoice_id or prev
        self.assertEqual(fiscal.l10n_ar_afip_responsibility_type_id, cf,
                         "ML informo Consumidor Final y el contacto fiscal quedo en %s" %
                         fiscal.l10n_ar_afip_responsibility_type_id.name)
