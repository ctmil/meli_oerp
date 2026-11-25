# -*- coding: utf-8 -*-
"""26.450 -- «Envío ML: <meli_shipping_id>» en la factura impresa (pedido de un cliente).

ML imprime en la etiqueta el número de ENVÍO, no el de venta; la factura sólo mostraba el Origen.
El template report_invoice_meli_shipping agrega la línea como HERMANO de div#informations: l10n_ar (y
otras localizaciones) hacen una copia primary del reporte y REEMPLAZAN ese div, así que un xpath adentro
quedaría borrado sin error.
Control (origin 26.449 + este test): test_1/test_2 FALLAN (no aparece «Envío ML»), test_4 ERROR (no existe el template).
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'meli', 'meli_26450')
class TestEnvioMlEnFactura26450(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.partner = env['res.partner'].create({'name': 'Comprador E450'})
        cls.product = env['product.product'].create({
            'name': 'Servicio E450', 'type': 'service', 'invoice_policy': 'order', 'list_price': 100.0})

    def _factura(self, shipping_id):
        so = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {'product_id': self.product.id, 'product_uom_qty': 1, 'price_unit': 100.0})]})
        if shipping_id:
            so.meli_shipping_id = shipping_id
        so.action_confirm()
        inv = so._create_invoices()
        self.assertTrue(inv.invoice_line_ids.sale_line_ids, "la factura quedó sin vínculo a la venta")
        return inv

    def _html(self, inv):
        html = self.env['ir.actions.report']._render_qweb_html('account.report_invoice', inv.ids)[0]
        return html.decode() if isinstance(html, bytes) else str(html)

    def test_1_factura_de_venta_ml_muestra_el_envio(self):
        html = self._html(self._factura('SHIP-E450-A'))
        self.assertIn('Envío ML', html)
        self.assertIn('SHIP-E450-A', html)

    def test_2_el_envio_va_despues_del_bloque_de_informacion(self):
        html = self._html(self._factura('SHIP-E450-B'))
        i, j = html.find('id="informations"'), html.find('name="meli_shipping"')
        self.assertGreaterEqual(i, 0)
        self.assertGreater(j, i)

    def test_3_factura_sin_envio_ml_no_cambia(self):
        self.assertNotIn('Envío ML', self._html(self._factura(False)))

    def test_4_sobrevive_a_la_copia_de_l10n_ar(self):
        """El template se hereda del reporte base; en la copia primary de l10n_ar tiene que seguir estando."""
        tmpl = self.env.ref('meli_oerp.report_invoice_document_meli_shipping')
        self.assertEqual(tmpl.inherit_id, self.env.ref('account.report_invoice_document'))
        ar = self.env.ref('l10n_ar.report_invoice_document', raise_if_not_found=False)
        if not ar:
            self.skipTest('l10n_ar no instalado')
        if hasattr(ar, '_get_combined_arch'):
            from lxml import etree
            arch = etree.tostring(ar._get_combined_arch(), encoding='unicode')
        else:
            arch = ar.read_combined()['arch']
        self.assertIn('name="meli_shipping"', arch)
