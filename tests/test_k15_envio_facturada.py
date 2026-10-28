# -*- coding: utf-8 -*-
"""26.305 (#caso-K15 cliente E, 25-oct-2026): re-sincronizar una venta YA FACTURADA no toca el envio.

En el fork de cliente E (meli_oerp 19.0.26.86, anterior al guard del #caso-K24) el re-sync de la venta
ML 2000306520094807 (FA-B 00006-00000160 pagada, $46.308,31) llevo la linea de envio de
$3.353,98 a $0: el bloque "envio con cupon" calculaba el residual lo-cobrable - producto (< 0)
y la escritura directa `delivery_line.price_unit = 0.0` no tenia guard.

El source ya lo cubre (`_meli_guard_delivery_write`, versions.py, desde 26.94): este test lo deja
fijado para que no vuelva. Cubre los dos caminos: set_delivery_line y el chequeo que usan las
escrituras directas de shipment.py.
"""
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.meli_oerp.models.versions import set_delivery_line, _meli_guard_delivery_write
from odoo.tests import tagged


def _sales_user(env):
    gfield = 'group_ids' if 'group_ids' in env.user._fields else 'groups_id'
    env.user.write({gfield: [(4, env.ref('sales_team.group_sale_manager').id)]})


@tagged('post_install', '-at_install', 'meli_K15_envio')
class TestMeliK15EnvioFacturada(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _sales_user(cls.env)
        Product = cls.env['product.product']
        cls.prod = Product.create({'name': 'Cortina K15', 'type': 'service',
                                   'invoice_policy': 'order', 'taxes_id': [(5, 0, 0)]})
        cls.ship = Product.create({'name': 'Andreani K15', 'type': 'service',
                                   'invoice_policy': 'order', 'taxes_id': [(5, 0, 0)]})
        co = cls.env.company
        if 'mercadolibre_protect_invoiced_orders' in co._fields:
            co.mercadolibre_protect_invoiced_orders = True

    def _venta(self, ref):
        tf = 'tax_ids' if 'tax_ids' in self.env['sale.order.line']._fields else 'tax_id'
        so = self.env['sale.order'].create({
            'partner_id': self.partner_a.id,
            'meli_order_id': ref,
            'order_line': [
                (0, 0, {'product_id': self.prod.id, 'product_uom_qty': 1, 'price_unit': 42249.99, tf: [(5, 0, 0)]}),
                (0, 0, {'product_id': self.ship.id, 'product_uom_qty': 1, 'price_unit': 3353.98,
                        'is_delivery': True, tf: [(5, 0, 0)]}),
            ],
        })
        so.action_confirm()
        return so, so.order_line.filtered('is_delivery')

    def test_venta_facturada_no_baja_el_envio(self):
        so, dl = self._venta('2000088450301419')
        inv = so._create_invoices()
        inv.action_post()
        self.assertEqual(inv.state, 'posted')
        self.assertTrue(_meli_guard_delivery_write(so, dl, 0.0),
                        "con factura posteada el guard tiene que frenar la escritura del envio")
        set_delivery_line(so, 0.0, "Defined by MELI")
        self.assertAlmostEqual(dl.price_unit, 3353.98, places=2, msg="el envio NO se baja a 0")
        self.assertAlmostEqual(so.amount_total, inv.amount_total, places=2,
                               msg="la venta queda igual a su factura")

    def test_venta_sin_factura_si_se_actualiza(self):
        so, dl = self._venta('2000393321610933')
        self.assertFalse(_meli_guard_delivery_write(so, dl, 0.0), "sin factura el guard no interviene")
        self.assertFalse(_meli_guard_delivery_write(so, dl, 3353.98), "sin cambio de precio no hay nada que frenar")


@tagged('post_install', '-at_install', 'meli_K15_envio')
class TestMeliK15EnvioResync(AccountTestInvoicingCommon):
    """Escenario 9593 por el camino real: shipment._update_sale_order_shipping_info sobre venta facturada,
    con cupon 7.000 y lo-cobrable (31.271,33) por debajo del producto => residual del envio < 0."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        gfield = 'group_ids' if 'group_ids' in cls.env.user._fields else 'groups_id'
        cls.env.user.write({gfield: [(4, cls.env.ref('sales_team.group_sale_manager').id)]})
        P = cls.env['product.product']
        cls.prod = P.create({'name': 'Cortina', 'type': 'service', 'invoice_policy': 'order', 'taxes_id': [(5, 0, 0)]})
        cls.ship = P.create({'name': 'Andreani Estandar K15', 'default_code': 'Andreani Estandar K15',
                             'type': 'service', 'invoice_policy': 'order', 'taxes_id': [(5, 0, 0)]})
        cls.carrier = cls.env['delivery.carrier'].create({'name': 'Andreani Estandar K15', 'product_id': cls.ship.id})
        co = cls.env.company
        for f, v in (('mercadolibre_order_total_config', 'paid_amount'), ('mercadolibre_including_shipping_cost', 'always'),
                     ('meli_coupon_discount_on_invoice', True)):
            if f in co._fields:
                co[f] = v

    def test_resync_no_baja_envio_de_venta_facturada(self):
        from unittest.mock import patch
        tf = 'tax_ids' if 'tax_ids' in self.env['sale.order.line']._fields else 'tax_id'
        so = self.env['sale.order'].create({
            'partner_id': self.partner_a.id, 'carrier_id': self.carrier.id,
            'order_line': [(0, 0, {'product_id': self.prod.id, 'product_uom_qty': 1, 'price_unit': 34917.35, tf: [(5, 0, 0)]}),
                           (0, 0, {'product_id': self.ship.id, 'product_uom_qty': 1, 'price_unit': 3353.98,
                                   'is_delivery': True, tf: [(5, 0, 0)]})]})
        so.action_confirm()
        inv = so._create_invoices()
        inv.action_post()
        so.meli_coupon_amount = 7000.0
        mo = self.env['mercadolibre.orders'].create({'order_id': '2000088450301419', 'name': '2000088450301419', 'sale_order': so.id})
        self.env['mercadolibre.payments'].create({
            'order_id': mo.id, 'payment_id': '180592010042', 'status': 'approved', 'currency_id': self.env.company.currency_id.name,
            'transaction_amount': 34917.35, 'total_paid_amount': 31271.33, 'coupon_amount': 7000.0, 'shipping_amount': 3353.98})
        so.meli_orders = [(6, 0, [mo.id])]
        sh = self.env['mercadolibre.shipment'].create({
            'sale_order': so.id, 'tracking_method': 'Andreani Estandar K15', 'mode': 'me2',
            'shipping_cost': 3353.98, 'shipping_seller_cost': 13847.5, 'shipping_list_cost': 13847.5})
        SO = type(so)
        with patch.object(SO, 'meli_amount_to_invoice', lambda self, meli=None, config=None: 31271.33, create=True), \
             patch.object(type(mo), '_ensure_payment_shipping_amounts', lambda self, meli=None, config=None: None, create=True):
            sh._update_sale_order_shipping_info(mo, meli=None, config=self.env.company)
        dl = so.order_line.filtered('is_delivery')
        self.assertAlmostEqual(sum(dl.mapped('price_unit')), 3353.98, places=2,
                               msg="re-sync de venta facturada: el envio NO se baja a 0 (ML 2000088450301419)")
        self.assertAlmostEqual(so.amount_total, inv.amount_total, places=2)
