# -*- coding: utf-8 -*-
"""#caso-K17 (caso-K02 cliente J / cliente H, 23-oct-2026; al source en 26.300).

(a) DNI: el contacto de facturacion (type=invoice, con el DNI/CUIT) se reutiliza por VAT entre packs del mismo
    comprador y conserva el meli_order_id del PRIMER pack. shipment.py lo buscaba solo por pack_id, asi que la
    venta del 2do pack quedaba facturando al contacto principal (sin DNI). Ahora cae al contacto `invoice`
    cuyo VAT es el `billing_info_doc_number` del comprador antes que al principal.
(b) Movil: el conector solo escribia `phone`; el modulo de WhatsApp del cliente lee
    `partner_shipping_id.mobile`. Ahora escribe `phone` Y `mobile` (si el campo existe: Odoo 19 lo elimino),
    sin pisar un mobile cargado a mano.

Sin red: no se llama a ML. Correr:
  odoo-bin ... -u meli_oerp --test-enable --test-tags meli_K17_dni_movil --stop-after-init
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'meli_K17_dni_movil')
class TestPackInvoicePartner682(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.Partner = self.env['res.partner']
        self.Shipment = self.env['mercadolibre.shipment']
        self.buyer_ml_id = '68200001'
        self.principal = self.Partner.create({
            'name': 'Comprador ML 682', 'meli_buyer_id': self.buyer_ml_id})
        # contacto de facturacion creado con el PRIMER pack del comprador
        self.factura = self.Partner.create({
            'name': 'Comprador ML 682 (factura)', 'type': 'invoice', 'vat': '96314392',
            'meli_order_id': '2000274377563134'})
        self.env['mercadolibre.buyers'].create({
            'buyer_id': self.buyer_ml_id, 'nickname': 'COMPRADORK17',
            'billing_info_doc_number': '96314392'})

    def _resolver(self, pack_ref):
        return self.Shipment._meli_pack_invoice_partner(
            self.Partner.with_user(1), pack_ref, self.buyer_ml_id, self.principal, self.company)

    def test_primer_pack_por_pack_id(self):
        self.assertEqual(self._resolver('2000274377563134'), self.factura)

    def test_segundo_pack_mismo_comprador_usa_contacto_con_dni(self):
        """El caso del ticket: 2do pack, sin contacto con ese pack_id => el de facturacion por DNI, no el principal."""
        res = self._resolver('2000233773023476')
        self.assertEqual(res, self.factura)
        self.assertEqual(res.vat, '96314392')

    def test_sin_documento_cae_al_principal(self):
        self.env['mercadolibre.buyers'].search([('buyer_id', '=', self.buyer_ml_id)]).billing_info_doc_number = False
        self.assertEqual(self._resolver('2000233773023476'), self.principal)

    def test_no_toma_contacto_de_otra_compania(self):
        otra = self.env['res.company'].create({'name': 'Otra compania 682'})
        self.factura.company_id = otra
        self.assertEqual(self._resolver('2000233773023476'), self.principal)


@tagged('post_install', '-at_install', 'meli_K17_dni_movil')
class TestTelefonoMovil682(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.company.mercadolibre_cron_get_orders_shipment_client = True
        self.has_mobile = 'mobile' in self.env['res.partner']._fields
        self.principal = self.env['res.partner'].create({'name': 'Comprador ML 682 tel', 'meli_buyer_id': '68200002'})
        self.receiver = {
            'receiver_name': 'Receptor 682', 'address_line': 'Calle Falsa 123', 'zip_code': '1414',
            'city': {'name': 'CABA'}, 'country': {'id': 'AR', 'name': 'Argentina'},
            'receiver_phone': '1157747482',
        }

    def _delivery(self):
        return self.env['mercadolibre.shipment'].partner_delivery_id(
            partner_id=self.principal, Receiver=dict(self.receiver), config=self.company)

    def test_contacto_de_entrega_nuevo_lleva_phone_y_mobile(self):
        deliv = self._delivery()
        self.assertTrue(deliv)
        self.assertEqual(deliv.phone, '1157747482')
        if self.has_mobile:
            self.assertEqual(deliv.mobile, '1157747482')

    def test_contacto_de_entrega_existente_sin_mobile_lo_completa(self):
        deliv = self.env['res.partner'].create({
            'name': 'Receptor 682', 'type': 'delivery', 'parent_id': self.principal.id,
            'street': 'Calle Falsa 123', 'phone': '1100000000'})
        res = self._delivery()
        self.assertEqual(res, deliv)
        self.assertEqual(deliv.phone, '1157747482')
        if self.has_mobile:
            self.assertEqual(deliv.mobile, '1157747482')

    def test_no_pisa_mobile_cargado_a_mano(self):
        if not self.has_mobile:
            self.skipTest('res.partner sin campo mobile (Odoo 19+)')
        deliv = self.env['res.partner'].create({
            'name': 'Receptor 682', 'type': 'delivery', 'parent_id': self.principal.id,
            'street': 'Calle Falsa 123', 'phone': '1100000000', 'mobile': '+54 9 11 2222-3333'})
        self._delivery()
        self.assertEqual(deliv.phone, '1157747482')
        self.assertEqual(deliv.mobile, '+54 9 11 2222-3333')

    def test_helper_valores(self):
        Orders = self.env['mercadolibre.orders']
        self.assertEqual(Orders._meli_phone_mobile_vals(''), {})
        vals = Orders._meli_phone_mobile_vals('1157747482')
        self.assertEqual(vals.get('phone'), '1157747482')
        self.assertEqual('mobile' in vals, self.has_mobile)
