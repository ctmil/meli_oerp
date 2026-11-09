# -*- coding: utf-8 -*-
"""26.386 — port a la flota de lo que prod Shoppy 502 (26.235/26.239, 3fb82c5a) tenía y el source no:
  * #595: la línea de la sub-orden del carrito entra si cabe en lo PAGADO (no en `pagado - cupón`), y
    nunca para una sub-orden cancelada por ML;
  * #603 F5b: tope del descuento del vendedor al cupón de la orden, como parámetro opt-in
    `meli_oerp.seller_discount_cap_coupon` (default apagado: la flota no cambia).
Números de la base de 502.
"""
import inspect

from odoo.tests import common, tagged


@tagged('post_install', '-at_install', 'meli', 'meli_f5b', 'meli_26386')
class TestCarrito595YTopeCupon(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from odoo.addons.meli_oerp.models import meli_prorate
        cls.mp = meli_prorate
        cls.ICP = cls.env['ir.config_parameter'].sudo()
        P = cls.env['product.product']
        cls.partner = cls.env['res.partner'].create({'name': 'Comprador 26386'})
        cls.p1 = P.create({'name': '26386 item 1', 'type': 'consu', 'taxes_id': [(6, 0, [])]})
        cls.p2 = P.create({'name': '26386 item 2', 'type': 'consu', 'taxes_id': [(6, 0, [])]})

    def _tax_field(self):
        return 'tax_ids' if 'tax_ids' in self.env['sale.order.line']._fields else 'tax_id'

    def _set(self, key, value):
        # Odoo 16-19: set_param · Odoo 20: set_str ('' = sin valor)
        if hasattr(self.ICP, 'set_param'):
            self.ICP.set_param(key, value)
        else:
            self.ICP.set_str(key, value or '')

    # ---- #595 (puro) ----
    def test_595_cepillo_mas_barato_que_el_cupon_entra(self):
        # ML 2000014963729457: 66.499 + cepillo 3.699 = 70.198 pagado; cupón del carrito 7.019,80.
        self.assertTrue(self.mp.pack_line_fits(66499.00, 70198.00, 3699.00))
        # el guard viejo lo dejaba afuera: 66.499 < 70.198 - 7.019,80 es False
        self.assertFalse(66499.00 < (70198.00 - 7019.80))

    def test_595_linea_que_no_cabe_no_entra(self):
        self.assertFalse(self.mp.pack_line_fits(66499.00, 66499.00, 3699.00))

    def test_595_shipment_usa_el_guard_nuevo(self):
        from odoo.addons.meli_oerp.models import shipment
        src = inspect.getsource(shipment)
        self.assertIn("meli_prorate.pack_line_fits(", src)
        self.assertIn("mOrder.status in ('cancelled', 'invalid')", src)
        self.assertNotIn("sorder_pack.amount_total<(sorder_pack.meli_paid_amount-(sorder_pack.meli_discount_seller_amount or sorder_pack.meli_coupon_amount))", src)

    # ---- tope al cupón ----
    def test_tope_puro(self):
        self.assertEqual(self.mp.bounded_order_discount(132462.50, 4291.32), 4291.32)
        self.assertEqual(self.mp.bounded_order_discount(2500.00, 0.0), 0.0)
        self.assertEqual(self.mp.bounded_order_discount(1000.00, 4291.32), 1000.00)

    def _order(self, oid, items, coupon, seller_discount):
        o = self.env['mercadolibre.orders'].create({
            'order_id': oid, 'coupon_amount': coupon, 'discount_seller_amount': seller_discount})
        for iid, price, qty in items:
            self.env['mercadolibre.order_items'].create({
                'order_id': o.id, 'order_item_id': iid, 'order_item_variation_id': '',
                'unit_price': str(price), 'quantity': qty})
        return o

    def _so_total(self, o, items, prods):
        gross = sum(p * q for _i, p, q in items)
        lines = []
        for (iid, price, qty), prod in zip(items, prods):
            item = {'item': {'id': iid, 'variation_id': None}, 'unit_price': price, 'quantity': qty}
            pu = o._set_product_unit_price(prod, item, config=self.env.company, items_total=gross)['price_unit']
            self.assertGreaterEqual(pu, 0.0)
            lines.append((0, 0, {'product_id': prod.id, 'product_uom_qty': qty, 'price_unit': pu, self._tax_field(): [(6, 0, [])]}))
        return self.env['sale.order'].create({'partner_id': self.partner.id, 'order_line': lines}).amount_total

    def test_tope_apagado_no_cambia_la_flota(self):
        self._set('meli_oerp.seller_discount_cap_coupon', '')
        o = self._order('26386-A', [('MLA1', 12012.00, 1)], 1201.21, 2500.00)
        o._meli_apply_seller_coupon_mode(config=self.env.company)
        self.assertAlmostEqual(o.discount_seller_amount, 2500.00, places=2)

    def test_tope_prendido_caso_f5b_01_oct(self):
        """Orden de 2 ítems con discount_seller_amount (132.462,50) MAYOR que la orden y cupón 4.291,32:
        la venta = ítems - cupón (prod 502 F5b); sin tope el source factura a precio pleno."""
        self._set('meli_oerp.seller_discount_cap_coupon', '1')
        items = [('MLA1', 12012.00, 1), ('MLA2', 15450.60, 2)]
        o = self._order('26386-B', items, 4291.32, 132462.50)
        o._meli_apply_seller_coupon_mode(config=self.env.company)
        self.assertAlmostEqual(o.discount_seller_amount, 4291.32, places=2)
        self.assertAlmostEqual(self._so_total(o, items, [self.p1, self.p2]), 42913.20 - 4291.32, delta=0.02)

    def test_tope_prendido_sin_cupon_precio_pleno(self):
        self._set('meli_oerp.seller_discount_cap_coupon', 'true')
        items = [('MLS1', 9999.00, 1)]
        o = self._order('26386-C', items, 0.0, 2500.00)
        o._meli_apply_seller_coupon_mode(config=self.env.company)
        self.assertEqual(o.discount_seller_amount, 0.0)
        self.assertAlmostEqual(self._so_total(o, items, [self.p1]), 9999.00, places=2)

    def test_tope_por_compania(self):
        self._set('meli_oerp.seller_discount_cap_coupon', '')
        self._set('meli_oerp.seller_discount_cap_coupon.company_%s' % self.env.company.id, 'on')
        self.assertTrue(self.env['mercadolibre.orders']._meli_seller_discount_cap_coupon(company=self.env.company))

    def test_collected_sigue_mandando(self):
        self._set('meli_oerp.seller_discount_cap_coupon', '1')
        self._set('meli_oerp.seller_coupon_mode', 'collected')
        o = self._order('26386-D', [('MLD1', 5000.00, 1)], 500.00, 800.00)
        o._meli_apply_seller_coupon_mode(config=self.env.company)
        self.assertEqual(o.discount_seller_amount, 0.0)
