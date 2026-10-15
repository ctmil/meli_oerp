# -*- coding: utf-8 -*-
"""[26.231] Linea de envio de una venta ML y estado de facturacion.

El producto de envio es un SERVICIO con "facturar cantidades entregadas" y entrega manual:
nadie le pone cantidad entregada. Antes del fix:
- envio $0 => el pedido facturado decia "Nada para facturar";
- envio con precio => la factura salia SIN el envio y el pedido quedaba mal.
"""
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


def _sales_user(env):
    """En 19 el usuario de AccountTestInvoicingCommon no trae permisos de Ventas."""
    gfield = 'group_ids' if 'group_ids' in env.user._fields else 'groups_id'
    env.user.write({gfield: [(4, env.ref('sales_team.group_sale_manager').id)]})


@tagged('post_install', '-at_install', 'meli_462e1')
class TestMeli462EnvioFacturacion(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _sales_user(cls.env)
        Product = cls.env['product.product']
        # producto vendido: servicio con politica "entregadas" (sin stock => la entrega se simula
        # con qty_delivered, igual que la valida el albaran)
        cls.prod = Product.create({'name': 'Mochila 462', 'type': 'service',
                                   'invoice_policy': 'delivery', 'list_price': 1000.0})
        # producto de envio: como "MEL Distribution" en un cliente
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


@tagged('post_install', '-at_install', 'meli_462e1')
class TestMeli462PackItemFaltante(AccountTestInvoicingCommon):
    """Pack con un item sin producto en Odoo: el aviso lo nombra y no se repite cada ciclo."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _sales_user(cls.env)

    def _pack_order(self):
        prod = self.env['product.product'].create({'name': 'Panos cian', 'type': 'service',
                                                   'invoice_policy': 'order', 'list_price': 100.0})
        MO = self.env['mercadolibre.orders'].sudo()
        mo1 = MO.create({'name': 'MO 1', 'order_id': '4629001', 'pack_id': '4629000', 'status': 'paid',
                         'order_items': [(0, 0, {'order_item_id': 'MLA111', 'seller_sku': 'SKU_cian',
                                                 'order_item_title': 'Panos cian', 'quantity': 1,
                                                 'unit_price': '100.0', 'product_id': prod.id})]})
        mo2 = MO.create({'name': 'MO 2', 'order_id': '4629002', 'pack_id': '4629000', 'status': 'paid',
                         'order_items': [(0, 0, {'order_item_id': 'MLA222', 'seller_sku': 'SKU_amariillo',
                                                 'order_item_title': 'Panos amarillo', 'quantity': 1,
                                                 'unit_price': '100.0'})]})
        so = self.env['sale.order'].create({
            'partner_id': self.partner_a.id,
            'meli_order_id': '4629001,4629002',
            'meli_orders': [(6, 0, (mo1 | mo2).ids)],
            'meli_status': 'paid',
            'meli_paid_amount': 200.0, 'meli_total_amount': 200.0,
            'order_line': [(0, 0, {'product_id': prod.id, 'product_uom_qty': 1, 'price_unit': 100.0,
                                   'tax_id' if 'tax_id' in self.env['sale.order.line']._fields else 'tax_ids': [(5, 0, 0)]})],
        })
        return so

    def test_aviso_nombra_item_sin_producto(self):
        so = self._pack_order()
        self.assertIn('MLA222', so._meli_items_without_product())
        self.assertNotIn('MLA111', so._meli_items_without_product())
        ready, reason = so.meli_confirm_ready()
        self.assertFalse(ready)
        self.assertIn('SKU_amariillo', reason)

    def test_aviso_una_sola_vez(self):
        so = self._pack_order()
        for _i in range(3):
            so.confirm_ml()  # (con meli_oerp_stock instalado confirm_ml no devuelve el resultado)
            # en prod cada ciclo agrega mensajes de seguimiento (el total sube y baja): 4 por ciclo
            for _j in range(5):
                so.message_post(body="seguimiento %s-%s" % (_i, _j))
        n = self.env['mail.message'].search_count([
            ('model', '=', 'sale.order'), ('res_id', '=', so.id), ('body', 'ilike', 'Condition not met')])
        self.assertEqual(n, 1, "el mismo motivo se postea una sola vez (antes: en cada ciclo)")
