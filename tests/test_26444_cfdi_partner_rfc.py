# -*- coding: utf-8 -*-
"""26.444: MLM, comprador con RFC propio => la venta factura a SU contacto fiscal.

Antes: con «Contacto de Facturacion Predeterminado» (MERCADO LIBRE FULL, XAXX010101000) el
predeterminado pisaba SIEMPRE al contacto fiscal del comprador; el uso de CFDI del comprador (G03/G01)
igual entraba a la venta => factura XAXX/616 con G03 => el PAC la rechaza (CFDI40161).
Ahora (opcion mercadolibre_mx_invoice_partner_by_rfc, default prendida):
  - RFC propio => partner_invoice_id = contacto fiscal del comprador (regimen y uso de ML);
  - RFC generico => el predeterminado como siempre y uso S01 (guarda);
  - opcion apagada => 26.440;
  - venta ya facturada => no se cambia el contacto;
  - pack (shipment.py) usa los mismos helpers.
Las venta entran por el camino REAL del import (modo simulacion, sin red). Con l10n_mx_edi(_sale)
instalado se verifican ademas regimen / uso; sin el, esas aserciones se saltean (campos ausentes).
"""
from odoo.tests import common, tagged
from odoo.tools import mute_logger

OID = 9000000000044401
RFC_RESICO = 'PEPJ920901AB1'
RFC_PFAE = 'ROLC590924TD1'
XAXX = 'XAXX010101000'


def _bi(doc, regime, usage, name='Juana', last='Perez Perez'):
    return {'buyer': {'billing_info': {
        'name': name, 'last_name': last,
        'identification': {'type': 'RFC', 'number': doc},
        'taxes': {'taxpayer_type': {'id': regime, 'description': 'x'}, 'cfdi': {'id': usage, 'description': 'x'}},
        'address': {'street_name': 'Calle X', 'street_number': '1', 'city_name': 'Ciudad',
                    'state': {'name': 'Ciudad de Mexico'}, 'zip_code': '01000'},
        'attributes': {'cust_type': 'CO'},
    }}, 'site_id': 'MLM'}


def _bundle(oid, bi, buyer_id):
    unit = 500.0
    order = {
        'id': oid, 'site_id': 'MLM', 'status': 'paid', 'status_detail': None,
        'date_created': '2026-11-20T10:00:00.000-06:00', 'date_closed': '2026-11-20T10:00:01.000-06:00',
        'total_amount': unit, 'paid_amount': unit, 'currency_id': 'MXN',
        'coupon': {'id': None, 'amount': 0},
        'order_items': [{'item': {'id': 'MLM000SIM', 'title': 'Croquetas sim', 'variation_id': None,
                                  'seller_sku': 'SKUMX', 'category_id': 'MLM1'},
                         'quantity': 1, 'unit_price': unit, 'full_unit_price': unit, 'currency_id': 'MXN'}],
        'payments': [],
        'buyer': {'id': buyer_id, 'nickname': 'COMPRADORMX%s' % buyer_id, 'first_name': 'Comprador',
                  'last_name': 'Mx', 'name': 'Comprador Mx', 'email': 'c%s@example.com' % buyer_id,
                  'phone': {'area_code': '55', 'number': '00000000'}, 'alternative_phone': {},
                  'billing_info': {'id': 'BI%s' % oid}},
        'seller': {'id': 900999},
        'tags': ['paid'], 'context': {'channel': 'marketplace', 'site': 'MLM'},
        'shipping': {'id': None}, 'pack_id': None,
    }
    return {'order': order,
            'routes': {'/items/MLM000SIM': {'id': 'MLM000SIM', 'title': 'Croquetas sim', 'seller_custom_field': 'SKUMX'},
                       '/orders/billing-info/MLM/BI%s' % oid: bi},
            'meta': {'origen': 'test', 'anonimizado': True}}


@tagged('post_install', '-at_install', 'meli', 'meli_26444')
class TestMeli26444CfdiPartnerRfc(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        mx = cls.env.ref('base.mx')
        cls.company.country_id = mx  # l10n_mx_edi_sale: country_code MX
        cls.mx_partner_path = 'l10n_mx_edi_fiscal_regime' in cls.env['res.partner']._fields
        cls.mxn = cls.env.ref('base.MXN')
        cls.mxn.active = True
        pricelist = cls.env['product.pricelist'].create({'name': 'Lista ML MX', 'currency_id': cls.mxn.id})
        cls.company.mercadolibre_pricelist = pricelist
        cls.full = cls.env['res.partner'].create({'name': 'MERCADO LIBRE FULL', 'country_id': mx.id, 'zip': '01000'})
        cls.env.cr.execute("UPDATE res_partner SET vat=%s WHERE id=%s", (XAXX, cls.full.id))  # sin base_vat
        cls.full.invalidate_recordset()
        cls.mx_fields = 'l10n_mx_edi_usage' in cls.env['sale.order']._fields
        if 'l10n_mx_edi_usage' in cls.full._fields:
            cls.full.write({'l10n_mx_edi_usage': 'S01', 'l10n_mx_edi_fiscal_regime': '616'})
        cls.company.mercadolibre_contact_partner = cls.full
        cls.company.mercadolibre_invoice_partner = cls.full
        cls.company.mercadolibre_cron_get_orders_shipment_client = True
        cls.env['product.product'].create({'name': 'Croquetas sim', 'taxes_id': [(5, 0, 0)],
                                           'meli_id': 'MLM000SIM', 'default_code': 'SKUMX'})
        cls.company.sudo().meli_simulation_enabled = True

    def _so(self, oid, bi, buyer_id):
        with mute_logger('odoo.addons.meli_oerp_multiple.models.sale'):
            res = self.env['mercadolibre.orders'].meli_simulate_order(_bundle(oid, bi, buyer_id), config=self.company)
        self.assertTrue(res.get('ok'), res)
        return self.env['sale.order'].browse(res['sale_order'])

    def _usage(self, so):
        return so['l10n_mx_edi_usage'] if self.mx_fields else None

    # -- camino real (venta suelta) -----------------------------------------------------------
    def _need_mx(self):
        # sin l10n_mx_edi el import MLM no arma el contacto fiscal (orders.py: rama l10n_mx_edi_fiscal_regime)
        if not self.mx_partner_path:
            self.skipTest("sin l10n_mx_edi: el import no crea contacto fiscal MX")

    def test_01_rfc_resico_g03_factura_al_comprador(self):
        self._need_mx()
        so = self._so(OID, _bi(RFC_RESICO, '626', 'G03'), 944401)
        inv = so.partner_invoice_id
        self.assertNotEqual(inv, self.full, "con RFC propio la factura no va al predeterminado")
        self.assertEqual(inv.vat, RFC_RESICO)
        self.assertEqual(inv.zip, '01000')
        self.assertEqual(so.partner_id, self.full, "el cliente de la venta sigue siendo el predeterminado")
        if self.mx_fields:
            self.assertEqual(self._usage(so), 'G03')
            self.assertEqual(inv.l10n_mx_edi_fiscal_regime, '626', "regimen de ML en el contacto del comprador")

    def test_02_rfc_pfae_g01(self):
        self._need_mx()
        so = self._so(OID + 1, _bi(RFC_PFAE, '612', 'G01', name='Carlos', last='Rojo Lopez'), 944402)
        self.assertEqual(so.partner_invoice_id.vat, RFC_PFAE)
        if self.mx_fields:
            self.assertEqual(self._usage(so), 'G01')
            self.assertEqual(so.partner_invoice_id.l10n_mx_edi_fiscal_regime, '612')

    def test_03_control_xaxx_s01_queda_en_full(self):
        so = self._so(OID + 2, _bi(XAXX, '616', 'S01', name='Publico', last='General'), 944403)
        self.assertEqual(so.partner_invoice_id, self.full)
        if self.mx_fields:
            self.assertEqual(self._usage(so), 'S01')

    def test_04_guarda_xaxx_con_g03_de_ml_va_s01(self):
        so = self._so(OID + 3, _bi(XAXX, '616', 'G03', name='Publico', last='General'), 944404)
        self.assertEqual(so.partner_invoice_id, self.full)
        if self.mx_fields:
            self.assertEqual(self._usage(so), 'S01', "XAXX nunca con uso distinto de S01 (CFDI40161)")

    def test_05_opcion_apagada_es_26440(self):
        self.company.mercadolibre_mx_invoice_partner_by_rfc = False
        so = self._so(OID + 4, _bi(RFC_RESICO, '626', 'G03'), 944405)
        self.assertEqual(so.partner_invoice_id, self.full)

    def test_06_mismo_rfc_reusa_el_contacto(self):
        self._need_mx()
        so1 = self._so(OID + 5, _bi(RFC_RESICO, '626', 'G03'), 944406)
        so2 = self._so(OID + 6, _bi(RFC_RESICO, '626', 'G03'), 944406)
        self.assertEqual(so1.partner_invoice_id, so2.partner_invoice_id, "un RFC = un contacto fiscal")

    def _receptor(self, so):
        """Receptor del CFDI tal como lo arma l10n_mx_edi con lo que la venta pasa a la factura."""
        if 'l10n_mx_edi.document' not in self.env:
            self.skipTest("sin l10n_mx_edi")
        vals = so._prepare_invoice()
        partner = self.env['res.partner'].browse(vals['partner_id'])
        cfdi = {'issued_address': self.company.partner_id, 'company': self.company}
        self.env['l10n_mx_edi.document']._add_customer_cfdi_values(
            cfdi, customer=partner, usage=vals.get('l10n_mx_edi_usage'), to_public=vals.get('l10n_mx_edi_cfdi_to_public'))
        r = cfdi['receptor']
        return (r['rfc'], r['regimen_fiscal_receptor'], r['uso_cfdi'])

    def test_07_receptor_cfdi_ya_no_es_xaxx_con_g03(self):
        """El rechazo CFDI40161 era XAXX010101000 + uso G03/G01. Comprador con RFC => su RFC/regimen/uso;
        generico con G03 de ML => XAXX + S01."""
        self._need_mx()
        so = self._so(OID + 7, _bi(RFC_RESICO, '626', 'G03'), 944408)
        self.assertEqual(self._receptor(so), (RFC_RESICO, '626', 'G03'))
        so = self._so(OID + 8, _bi(XAXX, '616', 'G03', name='Publico', last='General'), 944409)
        rfc, regime, usage = self._receptor(so)
        self.assertEqual((rfc, usage), (XAXX, 'S01'))

    # -- helpers (los usa tambien el pack en shipment.py) ---------------------------------------
    def test_10_helpers_pack(self):
        Orders = self.env['mercadolibre.orders']
        buyer = self.env['res.partner'].create({'name': 'Comprador pack', 'type': 'invoice'})
        self.env.cr.execute("UPDATE res_partner SET vat=%s WHERE id=%s", (RFC_RESICO, buyer.id))
        buyer.invalidate_recordset()
        # sin site_id (pack): MLM por el pais de la compania
        self.company.country_id = self.env.ref('base.mx')
        p, by_rfc = Orders._meli_mx_invoice_partner(self.full, buyer, config=self.company, company=self.company)
        self.assertEqual((p, by_rfc), (buyer, True))
        # comprador generico => predeterminado
        p, by_rfc = Orders._meli_mx_invoice_partner(self.full, self.full, config=self.company, company=self.company)
        self.assertEqual((p, by_rfc), (self.full, False))
        # no MLM (MLA) => predeterminado
        p, _ = Orders._meli_mx_invoice_partner(self.full, buyer, config=self.company, company=self.company, site_id='MLA')
        self.assertEqual(p, self.full)
        # sin predeterminado => el comprador (26.440)
        p, _ = Orders._meli_mx_invoice_partner(False, buyer, config=self.company, company=self.company)
        self.assertEqual(p, buyer)
        if self.mx_fields:
            buyer.l10n_mx_edi_usage = 'G03'
            self.assertEqual(Orders._meli_mx_pack_usage_vals(buyer, True, config=self.company, company=self.company),
                             {'l10n_mx_edi_usage': 'G03'})
            self.assertEqual(Orders._meli_mx_pack_usage_vals(self.full, False, config=self.company, company=self.company),
                             {'l10n_mx_edi_usage': 'S01'})

    def test_11_venta_facturada_no_cambia_de_contacto(self):
        from unittest.mock import patch
        Orders = self.env['mercadolibre.orders']
        buyer = self.env['res.partner'].create({'name': 'Comprador facturado', 'type': 'invoice'})
        self.env.cr.execute("UPDATE res_partner SET vat=%s WHERE id=%s", (RFC_RESICO, buyer.id))
        buyer.invalidate_recordset()
        so = self.env['sale.order'].create({'partner_id': self.full.id})
        with patch.object(type(Orders), '_meli_order_has_invoices', lambda self, s: True):
            p, by_rfc = Orders._meli_mx_invoice_partner(self.full, buyer, config=self.company, company=self.company,
                                                        site_id='MLM', sorder=so)
        self.assertEqual((p, by_rfc), (self.full, False))


@tagged('post_install', '-at_install', 'meli', 'meli_26444')
class TestMeli26444Pure(common.BaseCase):
    """Funciones puras (sin base)."""

    def test_rfc(self):
        from odoo.addons.meli_oerp.models import orders as o
        self.assertTrue(o._meli_mx_rfc_is_fiscal(RFC_RESICO))
        self.assertTrue(o._meli_mx_rfc_is_fiscal('ABC920901XY1'))   # persona moral (3 letras)
        self.assertTrue(o._meli_mx_rfc_is_fiscal('MX' + RFC_RESICO))
        self.assertFalse(o._meli_mx_rfc_is_fiscal(XAXX))
        self.assertFalse(o._meli_mx_rfc_is_fiscal('XEXX010101000'))
        self.assertFalse(o._meli_mx_rfc_is_fiscal(''))
        self.assertFalse(o._meli_mx_rfc_is_fiscal('12345678'))      # DNI / no RFC
        self.assertFalse(o._meli_mx_rfc_is_fiscal(RFC_RESICO, [RFC_RESICO]))  # generico configurado
        k = o._meli_mx_keep_buyer_invoice_partner
        self.assertTrue(k(True, True, True, RFC_RESICO, [], False))
        self.assertFalse(k(False, True, True, RFC_RESICO, [], False))
        self.assertFalse(k(True, False, True, RFC_RESICO, [], False))
        self.assertFalse(k(True, True, False, RFC_RESICO, [], False))
        self.assertFalse(k(True, True, True, RFC_RESICO, [], True))   # ya facturada
        self.assertFalse(k(True, True, True, XAXX, [], False))
        u = o._meli_mx_public_usage
        US = ['G01', 'G03', 'S01']
        self.assertEqual(u(XAXX, [], US, 'G03', False), 'S01')
        self.assertIsNone(u(XAXX, [], US, 'S01', False))
        self.assertIsNone(u(XAXX, [], US, 'G03', True))
        self.assertIsNone(u(RFC_RESICO, [], US, 'G03', False))
        self.assertIsNone(u('', [], US, 'G03', False))
        self.assertIsNone(u(XAXX, [], ['G03'], 'G03', False))
