# -*- coding: utf-8 -*-
"""[#504/#520] Descuento de vendedor y envio se deciden JUNTOS (opt-in never_below_total).

Caso (a) = PROD Dannok (420), SO 28789 / ML 2000018486811198, cuenta en paid_amount +
including_shipping_cost=never. Pagado = total + envio: el descuento ya esta en el precio y el
envio lo pago el comprador. 26.76.2 daba 56.697,56 y 26.158 daba 62.642,56; correcto 60.793,78.
"""
from odoo.tests import common, tagged

from .test_cap_mode_fallback import _FakeAccountConfig


@tagged('post_install', '-at_install', 'meli', 'meli_504')
class TestDiscountShippingJoint(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({'name': '#504b Comprador ML'})
        cls.product = cls.env['product.product'].create({'name': '#504b Producto'})
        cls.tax_field = 'tax_ids' if 'tax_ids' in cls.env['sale.order.line']._fields else 'tax_id'

    def _order(self, total, paid, disc=0.0, coupon=0.0, ship=0.0):
        so = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1.0,
                'price_unit': total,
                self.tax_field: [(5, 0, 0)],
            })],
        })
        so.write({
            'meli_total_amount': total,
            'meli_paid_amount': paid,
            'meli_discount_seller_amount': disc,
            'meli_coupon_amount': coupon,
            'meli_shipping_amount': ship,
        })
        self.assertAlmostEqual(so.amount_total, total, places=2)
        return so

    def _cfg(self, shipping='never'):
        return _FakeAccountConfig(
            mercadolibre_order_total_config='paid_amount',
            mercadolibre_including_shipping_cost=shipping,
            company_id=self.company,
        )

    def _opt_in(self, on=True):
        self.company.meli_seller_discount_cap_mode = 'never_below_total' if on else 'coupon'

    # (a) el caso real
    def test_a_dannok_so_28789(self):
        self._opt_in()
        so = self._order(60793.78, 66738.78, disc=4096.22, coupon=1627.08, ship=5945.0)
        self.assertAlmostEqual(so.meli_amount_to_invoice(config=self._cfg()), 60793.78, places=2)

    def test_a_without_opt_in_is_unchanged(self):
        """Sin opt-in: exactamente lo que daba 26.158 (no cambia nada para otros clientes)."""
        self._opt_in(False)
        so = self._order(60793.78, 66738.78, disc=4096.22, coupon=1627.08, ship=5945.0)
        self.assertAlmostEqual(so.meli_amount_to_invoice(config=self._cfg()), 62642.56, places=2)

    # (b) Tus Refacciones 431: envio absorbido por el vendedor
    def test_b_shipping_absorbed(self):
        for on in (True, False):
            self._opt_in(on)
            so = self._order(1000.0, 1000.0, ship=250.0)
            self.assertAlmostEqual(so.meli_amount_to_invoice(config=self._cfg()), 1000.0, places=2)

    # (c) el comprador pago el envio, sin descuento
    def test_c_buyer_paid_shipping(self):
        for on in (True, False):
            self._opt_in(on)
            so = self._order(1000.0, 1250.0, ship=250.0)
            self.assertAlmostEqual(so.meli_amount_to_invoice(config=self._cfg()), 1000.0, places=2)

    # (d) descuento legitimo NO reflejado en el precio: pagado - descuento = total
    def test_d_discount_not_reflected(self):
        self._opt_in()
        so = self._order(1000.0, 1100.0, disc=100.0, ship=250.0)
        self.assertAlmostEqual(so.meli_amount_to_invoice(config=self._cfg()), 1000.0, places=2)

    # (e) nada cuadra: igual que hoy (26.158), el control marca el conflicto
    def test_e_nothing_fits_keeps_current(self):
        self._opt_in()
        # candidatos 1500/1450/1400/1350 contra 1000: ninguno. 26.158 -> 1350.
        so = self._order(1000.0, 1500.0, disc=100.0, ship=50.0)
        self.assertAlmostEqual(so.meli_amount_to_invoice(config=self._cfg()), 1350.0, places=2)
        # pagado por debajo del total: 26.158 topa el descuento a 0 -> 900.
        so2 = self._order(1000.0, 900.0, disc=50.0)
        self.assertAlmostEqual(so2.meli_amount_to_invoice(config=self._cfg()), 900.0, places=2)
        ready, _reason = so.meli_confirm_ready(config=self._cfg())
        self.assertFalse(ready)

    # always: el envio no se empieza a restar
    def test_f_always_does_not_subtract_shipping(self):
        self._opt_in()
        so = self._order(1000.0, 1250.0, disc=80.0, ship=250.0)
        self.assertAlmostEqual(
            so.meli_amount_to_invoice(config=self._cfg('always')), 1250.0, places=2)
