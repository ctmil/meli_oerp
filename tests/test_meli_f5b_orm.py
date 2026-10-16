# -*- coding: utf-8 -*-
"""[#603 F5b, Shoppy 502] Precio de linea con cupon: ORM real de Odoo (tag `meli_f5b`).

Regla del suite: un importe de nivel orden/carrito NUNCA se aplica entero a cada linea. Se
acota al cupon de la orden y se prorratea entre sus items al centavo. Numeros de la base de 502.
"""
from odoo.tests import common, tagged


@tagged('post_install', '-at_install', 'meli', 'meli_f5b')
class TestMeliF5bPrecioConCupon(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({'name': 'Comprador F5b'})
        P = cls.env['product.product']
        cls.p1 = P.create({'name': 'F5b item 1', 'type': 'consu', 'taxes_id': [(6, 0, [])]})
        cls.p2 = P.create({'name': 'F5b item 2', 'type': 'consu', 'taxes_id': [(6, 0, [])]})

    def _order(self, oid, items, coupon, seller_discount):
        o = self.env['mercadolibre.orders'].create({
            'order_id': oid, 'coupon_amount': coupon, 'discount_seller_amount': seller_discount,
        })
        for iid, price, qty in items:
            self.env['mercadolibre.order_items'].create({
                'order_id': o.id, 'order_item_id': iid, 'order_item_variation_id': '',
                'unit_price': str(price), 'quantity': qty,
            })
        return o

    def _so(self, lines):
        so = self.env['sale.order'].create({'partner_id': self.partner.id, 'order_line': [
            (0, 0, {'product_id': p.id, 'product_uom_qty': q, 'price_unit': pu, 'tax_id': [(6, 0, [])]})
            for p, q, pu in lines]})
        return so

    def test_orden_con_cupon_de_dos_lineas_prorratea_y_no_deja_negativos(self):
        """Una orden, 2 items (uno x2). discount_seller_amount (132.462,50) es MAYOR que la orden:
        antes cada linea restaba ese importe entero => precios negativos (cancelacion 01-oct)."""
        o = self._order('F5B-1', [('MLA1', 12012.00, 1), ('MLA2', 15450.60, 2)], 4291.32, 132462.50)
        prices = []
        for (iid, price, qty), prod in zip([('MLA1', 12012.00, 1), ('MLA2', 15450.60, 2)], [self.p1, self.p2]):
            item = {'item': {'id': iid, 'variation_id': None}, 'unit_price': price, 'quantity': qty}
            pu = o._set_product_unit_price(prod, item, config=self.company)['price_unit']
            self.assertGreaterEqual(pu, 0.0, "ninguna linea negativa")
            self.assertLessEqual(pu, price, "nunca mas caro que el precio de ML")
            prices.append((prod, qty, pu))
        so = self._so(prices)
        # total de la venta = items - cupon de la orden (no menos): 42.913,20 - 4.291,32
        self.assertAlmostEqual(so.amount_total, 42913.20 - 4291.32, delta=0.02)

    def test_carrito_descuento_del_pack_repetido_en_cada_suborden(self):
        """Escenario del 26.131: cada sub-orden del carrito trae el descuento del PACK entero
        (50.170,70) y su propio cupon prorrateado por ML. Camino de shipment.py: Item = registro."""
        m1 = self._order('F5B-C1', [('MLC1', 12012.00, 1)], 1201.21, 50170.70)
        m2 = self._order('F5B-C2', [('MLC2', 30901.20, 1)], 3090.11, 50170.70)
        lines = []
        for m, prod in ((m1, self.p1), (m2, self.p2)):
            pu = m._set_product_unit_price(prod, m.order_items[0], config=self.company)['price_unit']
            self.assertGreaterEqual(pu, 0.0)
            self.assertAlmostEqual(pu, float(m.order_items[0].unit_price) - m.coupon_amount, places=2)
            lines.append((prod, 1, pu))
        so = self._so(lines)
        self.assertAlmostEqual(so.amount_total, 42913.20 - 4291.32, places=2)

    def test_sin_cupon_factura_a_precio_pleno(self):
        o = self._order('F5B-3', [('MLS1', 9999.00, 1)], 0.0, 2500.00)
        item = {'item': {'id': 'MLS1', 'variation_id': None}, 'unit_price': 9999.00, 'quantity': 1}
        self.assertAlmostEqual(o._set_product_unit_price(self.p1, item, config=self.company)['price_unit'], 9999.00, places=2)
