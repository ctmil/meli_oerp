# -*- coding: utf-8 -*-
"""Direccion del contacto de facturacion: TODA de la misma fuente (billing_info) — 29-oct-2026.

Antes: calle, ciudad y CP salian de billing_info y el ESTADO del envio (state() devolvia el del receiver
apenas matcheaba su codigo, sin mirar STATE_NAME). Un comprador que factura en Merida (Yucatan) y recibe
en Guadalajara quedaba con "calle de Merida, Merida, 97000, JALISCO": un domicilio fiscal que no existe,
y es el que usa el CFDI (MX) o la provincia de la factura (AR).

Payloads: forma REAL de /orders/billing-info/MLM/<id> (x-version 2) tomada de prod 535 el 23-oct
(leaves/2026-10-23-535-billing-v2-mlm/probe4.out, anonimizado: <46>, <5>... = largos); valores sinteticos.
Sin red: ML simulado. Correr:
  odoo-bin ... -u meli_oerp --test-enable --test-tags meli_billing_addr --stop-after-init
"""
from unittest.mock import patch

from odoo.tests import common, tagged
from odoo.tools import mute_logger

OID = 2000699900000001
BUYER_ID = 69990001
RFC = 'AAA010101AA1'  # RFC sintetico (no generico: XAXX/XEXX irian al principal)


class _MPNoDisponible:
    ok = False
    status_code = 503

    def __bool__(self):
        return False

    def json(self):
        return {}


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
                return _Resp(data)
        return _Resp({})

    def need_login(self):
        return False


# receiver_address del envio: Guadalajara, Jalisco
RECEIVER = {
    'id': 69990001, 'address_line': 'Av. Envio 100', 'street_name': 'Av. Envio', 'street_number': '100',
    'zip_code': '44100', 'receiver_name': 'Receptor', 'receiver_phone': 'XXXXXXX', 'comment': '',
    'city': {'id': 'TUxNQ0dVQTUxNzY', 'name': 'Guadalajara'},
    'state': {'id': 'MX-JAL', 'name': 'Jalisco'},
    'country': {'id': 'MX', 'name': 'Mexico'},
}


def _billing_v2(address):
    """billing-info v2 MLM con la forma de probe4 (cust_type CO, RFC, regimen 616 / uso S01)."""
    return {'buyer': {'cust_id': str(BUYER_ID), 'billing_info': {
        'name': 'Fiscal', 'last_name': 'Prueba',
        'identification': {'type': 'RFC', 'number': RFC},
        'taxes': {'taxpayer_type': {'id': '616', 'description': 'Sin obligaciones fiscales'},
                  'cfdi': {'id': 'S01', 'description': 'Sin efectos fiscales'}},
        'address': address,
        'attributes': {'vat_discriminated_billing': 'True', 'normalized': 'True', 'cust_type': 'CO'},
    }}, 'seller': {'cust_id': '999999999'}}


# 1) billing_info completo: Merida, Yucatan (estado con codigo con prefijo, como en prod: 'MX-YUC')
ADDR_COMPLETA = {'street_name': 'Calle Fiscal', 'street_number': '60', 'city_name': 'Merida',
                 'state': {'code': 'MX-YUC', 'name': 'Yucatan'}, 'zip_code': '97000', 'country_id': 'MX'}
# 2) billing_info SIN estado, CP de facturacion distinto al del envio
ADDR_SIN_ESTADO = {'street_name': 'Calle Fiscal', 'street_number': '60', 'city_name': 'Merida',
                   'zip_code': '97000', 'country_id': 'MX'}
# 3) billing_info SIN estado pero con el MISMO CP que el envio (=> mismo lugar)
ADDR_SIN_ESTADO_MISMO_CP = {'street_name': 'Calle Fiscal', 'street_number': '60', 'city_name': 'Guadalajara',
                            'zip_code': '44100', 'country_id': 'MX'}


def _order_json():
    return {
        'id': OID, 'status': 'paid', 'status_detail': None, 'site_id': 'MLM',
        'date_created': '2026-10-29T10:00:00.000-06:00', 'date_closed': '2026-10-29T10:00:01.000-06:00',
        'total_amount': 1000.0, 'paid_amount': 1000.0, 'currency_id': 'MXN',
        'coupon': {'id': None, 'amount': 0},
        'order_items': [{'item': {'id': 'MLM699900', 'title': 'Prueba billing', 'variation_id': None,
                                  'seller_sku': 'SKU699900', 'category_id': 'MLM1'},
                         'quantity': 1, 'unit_price': 1000.0, 'full_unit_price': 1000.0, 'currency_id': 'MXN'}],
        'payments': [{'id': 99699900, 'transaction_amount': 1000.0, 'total_paid_amount': 1000.0,
                      'currency_id': 'MXN', 'status': 'approved', 'coupon_amount': 0,
                      'shipping_cost': 0, 'date_created': '2026-10-29T10:00:01.000-06:00',
                      'date_last_modified': '2026-10-29T10:00:01.000-06:00'}],
        'buyer': {'id': BUYER_ID, 'nickname': 'COMPRADORBILL', 'first_name': 'Juana', 'last_name': 'Prueba',
                  'email': 'juana@example.com', 'phone': {'area_code': '33', 'number': '00000000'},
                  'billing_info': {'id': 'BI699900'}},
        'seller': {'id': 699999},
        'tags': ['paid'], 'context': {'channel': 'marketplace', 'site': 'MLM'},
        'shipping': {'id': None, 'receiver_address': dict(RECEIVER)}, 'pack_id': None,
    }


@tagged('post_install', '-at_install', 'meli', 'meli_billing_addr')
class TestBillingAddressMismaFuente(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.mx = cls.env.ref('base.mx')
        State = cls.env['res.country.state']
        cls.jal = State.search([('country_id', '=', cls.mx.id), ('code', '=', 'JAL')], limit=1)
        cls.yuc = State.search([('country_id', '=', cls.mx.id), ('code', '=', 'YUC')], limit=1)
        pricelist = cls.env['product.pricelist'].search([], limit=1) or \
            cls.env['product.pricelist'].create({'name': 'Lista ML'})
        cls.company.mercadolibre_pricelist = pricelist
        if 'mercadolibre_cron_get_orders_shipment_client' in cls.company._fields:
            cls.company.mercadolibre_cron_get_orders_shipment_client = True
        cls.product = cls.env['product.product'].create({
            'name': 'Prueba billing', 'taxes_id': [(5, 0, 0)], 'meli_id': 'MLM699900', 'default_code': 'SKU699900'})

    def _import(self, address, force_on_main=False):
        # Modo 3 (contacto de facturacion independiente) por defecto; force_on_main = estrategia B
        # (los datos fiscales, y la direccion de facturacion, van al contacto principal).
        for fname, val in (('mercadolibre_billing_force_on_main', force_on_main),
                           ('mercadolibre_skip_same_name_billing_contact', False)):
            if fname in self.company._fields:
                self.company[fname] = val
        routes = [('/orders/billing-info/MLM/BI699900', _billing_v2(address) if address is not None else {}),
                  ('/orders/%s/billing_info' % OID, {}),
                  ('/orders/%s/discounts' % OID, {}),
                  ('/orders/%s' % OID, _order_json()),
                  ('/items/', {'id': 'MLM699900', 'title': 'Prueba billing'})]
        Orders = type(self.env['mercadolibre.orders'])
        _orig_fix_locals = Orders.fix_locals

        def _fix_locals_con_rfc(rec, Receiver={}, Buyer={}):
            # El RFC lo pone la localizacion (l10n_mx_edi), que el banco no instala: lo inyectamos por
            # el mismo canal (fix_locals se mergea en meli_buyer_fields antes del BILLING_SPLIT).
            out = _orig_fix_locals(rec, Receiver=Receiver, Buyer=Buyer)
            if address is not None:
                out['vat'] = RFC
            return out

        with patch('odoo.addons.meli_oerp.models.orders.requests.get', return_value=_MPNoDisponible()), \
                patch.object(Orders, 'fix_locals', _fix_locals_con_rfc), \
                mute_logger('odoo.addons.meli_oerp_multiple.models.sale'):
            res = self.env['mercadolibre.orders'].orders_update_order_json(
                {'id': False, 'order_json': _order_json()}, meli=_FakeMeli(routes), config=self.company)
        self.assertFalse(isinstance(res, dict) and res.get('error'), res)
        principal = self.env['res.partner'].search([('meli_buyer_id', '=', str(BUYER_ID))], limit=1)
        factura = self.env['res.partner'].search([('vat', '=', RFC), ('type', '=', 'invoice')], limit=1)
        if force_on_main:
            factura = principal
        self.assertTrue(principal, "no se creo el contacto principal: %s" % (res,))
        return principal, factura

    def test_1_billing_completo_estado_de_facturacion(self):
        principal, factura = self._import(ADDR_COMPLETA)
        self.assertTrue(factura, "no se creo el contacto de facturacion")
        for p in (factura, principal):
            self.assertEqual(p.street, 'Calle Fiscal 60', p.name)
            self.assertEqual(p.city, 'Merida', p.name)
            self.assertEqual(p.zip, '97000', p.name)
            self.assertEqual(p.state_id, self.yuc,
                             "%s: estado del ENVIO (%s) con calle/CP de facturacion" % (p.name, p.state_id.name))

    def test_1b_billing_completo_forzado_al_principal(self):
        principal, factura = self._import(ADDR_COMPLETA, force_on_main=True)
        self.assertEqual(principal.vat, RFC)
        self.assertEqual(principal.zip, '97000')
        self.assertEqual(principal.state_id, self.yuc,
                         "estado del ENVIO (%s) con calle/CP de facturacion" % principal.state_id.name)

    def test_2_billing_sin_estado_no_toma_el_del_envio(self):
        principal, factura = self._import(ADDR_SIN_ESTADO)
        self.assertTrue(factura, "no se creo el contacto de facturacion")
        for p in (factura, principal):
            self.assertEqual(p.city, 'Merida', p.name)
            self.assertEqual(p.zip, '97000', p.name)
            self.assertNotEqual(p.state_id, self.jal,
                                "%s: billing sin estado tomo el estado del ENVIO (Jalisco)" % p.name)
            # MX sin catalogo CP->estado en el banco: no se puede deducir => vacio
            self.assertFalse(p.state_id, p.name)

    def test_3_billing_sin_estado_mismo_cp_que_el_envio(self):
        principal, factura = self._import(ADDR_SIN_ESTADO_MISMO_CP)
        self.assertTrue(factura, "no se creo el contacto de facturacion")
        # mismo CP => mismo lugar: el estado se DEDUCE por CP (no es mezclar fuentes)
        self.assertEqual(factura.state_id, self.jal)
        self.assertEqual(factura.zip, '44100')

    def test_4_sin_direccion_de_facturacion_usa_el_envio_entero(self):
        principal, factura = self._import(None)
        self.assertEqual(principal.street, 'Av. Envio 100')
        self.assertEqual(principal.city, 'Guadalajara')
        self.assertEqual(principal.state_id, self.jal)

    def test_5_helper_estado_vacio_no_devuelve_el_primero_del_pais(self):
        Orders = self.env['mercadolibre.orders']
        self.assertFalse(Orders._meli_state_by_code_or_name(self.mx.id, code='', name=''))
        cmx = self.env['res.country.state'].search([('country_id', '=', self.mx.id), ('code', '=', 'CMX')], limit=1)
        if cmx:
            self.assertEqual(Orders._meli_state_by_code_or_name(self.mx.id, code='CMX'), cmx.id)
        self.assertEqual(Orders._meli_state_by_code_or_name(self.mx.id, code='MX-YUC'), self.yuc.id)
