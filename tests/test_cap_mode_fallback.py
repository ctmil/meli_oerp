# -*- coding: utf-8 -*-
"""[#504/#520 Dannok] El tope del descuento de vendedor se resuelve por la compania
cuando la configuracion que recibe el flujo es la de una CUENTA ML sin ese campo.

Con `meli_oerp_multiple`, `meli_amount_to_invoice` recibe una `mercadolibre.configuration`
(modelo de la cuenta) que NO tiene `meli_seller_discount_cap_mode`. Antes el chequeo
`in config._fields` daba False y el modo caia a "coupon" en silencio: la opcion puesta en
la compania no movia nada.

La config de cuenta se simula con un objeto que se comporta como un record en lo que usa
el calculo (`_fields`, acceso por atributo y por clave, `company_id`): asi el test no
depende de instalar meli_oerp_multiple (y todo lo que arrastra) para probar la regla.

Numeros del caso real (venta ML 2000018486811198, SO 28789): total 60.793,78, pagado
60.793,78, descuento de vendedor 4.096,22, sin cupon registrado en la venta.
  - modo "coupon" (default)          -> 56.697,56 (la venta no confirma)
  - modo "never_below_total"         -> 60.793,78
"""
from odoo.tests import common, tagged

TOTAL = 60793.78
DISCOUNT = 4096.22
SHORT = 56697.56


class _FakeAccountConfig:
    """Una `mercadolibre.configuration` de cuenta, reducida a lo que lee el calculo."""

    def __init__(self, **vals):
        self._vals = dict(vals)
        self._fields = dict.fromkeys(self._vals)

    def __bool__(self):
        return True

    def __getattr__(self, name):
        vals = self.__dict__.get("_vals", {})
        if name in vals:
            return vals[name]
        raise AttributeError(name)

    def __getitem__(self, name):
        return self._vals[name]


@tagged('post_install', '-at_install', 'meli', 'meli_504')
class TestSellerDiscountCapModeFallback(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({'name': '#504 Comprador ML'})
        cls.product = cls.env['product.product'].create({
            'name': '#504 Producto',
            'list_price': TOTAL,
        })
        tax_field = 'tax_ids' if 'tax_ids' in cls.env['sale.order.line']._fields else 'tax_id'
        cls.order = cls.env['sale.order'].create({
            'partner_id': cls.partner.id,
            'company_id': cls.company.id,
            'order_line': [(0, 0, {
                'product_id': cls.product.id,
                'product_uom_qty': 1.0,
                'price_unit': TOTAL,
                tax_field: [(5, 0, 0)],
            })],
        })
        cls.order.write({
            'meli_total_amount': TOTAL,
            'meli_paid_amount': TOTAL,
            'meli_discount_seller_amount': DISCOUNT,
            'meli_coupon_amount': 0.0,
            'meli_shipping_amount': 0.0,
        })

    def _account_config(self, with_company=True):
        vals = {
            'mercadolibre_order_total_config': 'paid_amount',
            'mercadolibre_including_shipping_cost': 'always',
        }
        if with_company:
            vals['company_id'] = self.company
        return _FakeAccountConfig(**vals)

    def test_00_fixture(self):
        self.assertAlmostEqual(self.order.amount_total, TOTAL, places=2)
        self.assertNotIn('meli_seller_discount_cap_mode', self._account_config()._fields)

    def test_01_control_default_is_coupon(self):
        """Sin nada seteado: 'coupon', y el calculo es el de siempre (queda corto)."""
        self.company.meli_seller_discount_cap_mode = 'coupon'
        cfg = self._account_config()
        self.assertEqual(
            self.order._meli_order_setting('meli_seller_discount_cap_mode', 'coupon', config=cfg),
            'coupon')
        self.assertAlmostEqual(self.order.meli_amount_to_invoice(config=cfg), SHORT, places=2)

    def test_02_account_config_without_field_uses_company(self):
        """Config de CUENTA sin el campo + compania en never_below_total -> never_below_total."""
        self.company.meli_seller_discount_cap_mode = 'never_below_total'
        cfg = self._account_config()
        self.assertEqual(
            self.order._meli_order_setting('meli_seller_discount_cap_mode', 'coupon', config=cfg),
            'never_below_total')
        self.assertAlmostEqual(self.order.meli_amount_to_invoice(config=cfg), TOTAL, places=2)

    def test_03_account_config_without_company_uses_order_company(self):
        """Config de cuenta sin company_id: se resuelve por la compania de la venta."""
        self.company.meli_seller_discount_cap_mode = 'never_below_total'
        cfg = self._account_config(with_company=False)
        self.assertAlmostEqual(self.order.meli_amount_to_invoice(config=cfg), TOTAL, places=2)

    def test_04_company_as_config_unchanged(self):
        """Sin meli_oerp_multiple (config = compania): el comportamiento de c79ee06b sigue igual."""
        self.company.write({
            'mercadolibre_order_total_config': 'paid_amount',
            'meli_seller_discount_cap_mode': 'never_below_total',
        })
        self.assertAlmostEqual(self.order.meli_amount_to_invoice(config=self.company), TOTAL, places=2)
        self.company.meli_seller_discount_cap_mode = 'coupon'
        self.assertAlmostEqual(self.order.meli_amount_to_invoice(config=self.company), SHORT, places=2)

    def test_05_account_value_wins_over_company(self):
        """Si algun dia la cuenta tiene el campo con valor, manda la cuenta (lo mas especifico)."""
        self.company.meli_seller_discount_cap_mode = 'never_below_total'
        cfg = self._account_config()
        cfg._vals['meli_seller_discount_cap_mode'] = 'coupon'
        cfg._fields['meli_seller_discount_cap_mode'] = None
        self.assertAlmostEqual(self.order.meli_amount_to_invoice(config=cfg), SHORT, places=2)
