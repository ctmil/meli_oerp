# -*- coding: utf-8 -*-
"""[#462 Matices, 26.231] Linea de envio de una venta ML y estado de facturacion.

El producto de envio es un SERVICIO con "facturar cantidades entregadas" y entrega manual:
nadie le pone cantidad entregada. Antes del fix:
- envio $0 => el pedido facturado decia "Nada para facturar";
- envio con precio => la factura salia SIN el envio y el pedido quedaba mal.
"""
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged('post_install', '-at_install', 'meli_462e1')
class TestMeli462EnvioFacturacion(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Product = cls.env['product.product']
        # producto vendido: servicio con politica "entregadas" (sin stock => la entrega se simula
        # con qty_delivered, igual que la valida el albaran)
        cls.prod = Product.create({'name': 'Mochila 462', 'type': 'service',
                                   'invoice_policy': 'delivery', 'list_price': 1000.0})
        # producto de envio: como "MEL Distribution" en Matices
        cls.ship = Product.create({'name': 'MEL Distribution 462', 'type': 'service',
                                   'invoice_policy': 'delivery', 'list_price': 1.0})

    def _ml_order(self, ref, ship_price, ml=True):
        so = self.env['sale.order'].create({
            'partner_id': self.partner_a.id,
            'meli_order_id': ref if ml else False,
            'order_line': [
                (0, 0, {'product_id': self.prod.id, 'product_uom_qty': 1, 'price_unit': 1000.0}),
                (0, 0, {'product_id': self.ship.id, 'product_uom_qty': 1, 'price_unit': ship_price,
                        'is_delivery': True}),
            ],
        })
        so.action_confirm()
        return so

    def _lines(self, so):
        pl = so.order_line.filtered(lambda l: l.product_id == self.prod)
        sl = so.order_line.filtered(lambda l: l.product_id == self.ship)
        return pl, sl

    def test_envio_gratis_facturado_no_queda_nada_para_facturar(self):
        so = self._ml_order('4620001', 0.0)
        pl, sl = self._lines(so)
        self.assertEqual(so.invoice_status, 'no', "sin entregar no hay nada para facturar")
        pl.qty_delivered = 1
        self.assertEqual(so.invoice_status, 'to invoice')
        inv = so._create_invoices()
        self.assertNotIn(self.ship, inv.invoice_line_ids.product_id, "el envio $0 no va a la factura")
        self.assertEqual(sl.qty_to_invoice, 0.0)
        self.assertEqual(so.invoice_status, 'invoiced',
                         "producto facturado + envio $0 => 'Facturado' (antes: 'Nada para facturar')")

    def test_envio_con_precio_entra_en_la_factura(self):
        so = self._ml_order('4620002', 500.0)
        pl, sl = self._lines(so)
        self.assertEqual(sl.qty_to_invoice, 1.0)
        self.assertEqual(so.invoice_status, 'no',
                         "el envio solo no se factura: sin producto entregado el pedido no esta 'A facturar'")
        pl.qty_delivered = 1
        self.assertEqual(so.invoice_status, 'to invoice')
        inv = so._create_invoices()
        self.assertIn(self.ship, inv.invoice_line_ids.product_id, "el envio con precio va a la factura")
        self.assertAlmostEqual(sum(inv.invoice_line_ids.mapped('price_subtotal')), 1500.0, places=2)
        self.assertEqual(sl.qty_to_invoice, 0.0)
        self.assertEqual(so.invoice_status, 'invoiced', "antes: 'A facturar' estando facturado")

    def test_venta_no_ml_sin_cambios(self):
        so = self._ml_order('x', 500.0, ml=False)
        pl, sl = self._lines(so)
        pl.qty_delivered = 1
        self.assertEqual(sl.qty_to_invoice, 0.0, "fuera de ML el envio sigue la politica del producto")
