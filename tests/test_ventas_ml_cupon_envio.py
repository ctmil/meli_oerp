# -*- coding: utf-8 -*-
"""26.229 -- ventas ML: cupon del vendedor, envio del comprador,
cupon + descuento del vendedor, cancelacion de pack, lineas sobre venta confirmada.

Los numeros son los de casos reales de produccion (montos). No hay red: la config de cuenta se simula.
"""
from odoo.tests import common, tagged


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


@tagged('post_install', '-at_install', 'meli', 'meli_26229')
class TestVentasMLCuponEnvio(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({'name': 'Comprador ML'})
        cls.product = cls.env['product.product'].create({'name': 'Refaccion', 'taxes_id': [(5, 0, 0)]})
        cls.tax_field = 'tax_ids' if 'tax_ids' in cls.env['sale.order.line']._fields else 'tax_id'

    # ---------------------------------------------------------------- helpers
    def _cfg(self, shipping='always'):
        return _FakeAccountConfig(
            mercadolibre_order_total_config='paid_amount',
            mercadolibre_including_shipping_cost=shipping,
            company_id=self.company,
        )

    def _so(self, lines, paid, disc=0.0, coupon=0.0, ship=0.0, **extra):
        so = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1.0,
                'price_unit': price,
                self.tax_field: [(5, 0, 0)],
            }) for price in lines],
        })
        vals = {
            'meli_total_amount': sum(lines),
            'meli_paid_amount': paid,
            'meli_discount_seller_amount': disc,
            'meli_coupon_amount': coupon,
            'meli_shipping_amount': ship,
        }
        vals.update(extra)
        so.write(vals)
        return so

    def _morder(self, so, order_id, status='paid', pay_ship=0.0, pay_status='approved', **extra):
        vals = {'order_id': order_id, 'name': 'MO %s' % order_id, 'status': status, 'sale_order': so.id}
        vals.update(extra)
        mo = self.env['mercadolibre.orders'].create(vals)
        if pay_ship or pay_status:
            self.env['mercadolibre.payments'].create({
                'order_id': mo.id,
                'payment_id': 'P' + order_id,
                'status': pay_status,
                'shipping_amount': pay_ship,
            })
        so.meli_orders = [(4, mo.id)]
        return mo

    # ------------------------------------------- 1. cupon a cargo del vendedor
    def test_1_unit_price_net_of_seller_coupon(self):
        """ML 2000000000000001: 5.324 con cupon 266,20 del vendedor -> la linea nace en 5.057,80."""
        mo = self.env['mercadolibre.orders'].create({'order_id': '2000000000000001', 'name': 'x',
                                                      'discount_seller_amount': 266.20})
        item = {'unit_price': 5324.0, 'quantity': 1}
        res = mo._set_product_unit_price(self.product, item, config=self.company)
        self.assertAlmostEqual(res['price_unit'], 5057.80, places=2)

    def test_1_empty_recordset_had_no_discount(self):
        """La causa: el import llamaba al metodo sobre el recordset VACIO (self) -> sin descuento."""
        empty = self.env['mercadolibre.orders']
        res = empty._set_product_unit_price(self.product, {'unit_price': 5324.0, 'quantity': 1}, config=self.company)
        self.assertAlmostEqual(res['price_unit'], 5324.0, places=2)

    def test_1_discount_prorated_between_items(self):
        """Orden con 2 items (300 y 100): el descuento de 40 se reparte 30/10, no 40 en cada uno."""
        mo = self.env['mercadolibre.orders'].create({'order_id': 'T-PRO', 'name': 'x',
                                                      'discount_seller_amount': 40.0})
        a = mo._set_product_unit_price(self.product, {'unit_price': 300.0, 'quantity': 1}, config=self.company, items_total=400.0)
        b = mo._set_product_unit_price(self.product, {'unit_price': 50.0, 'quantity': 2}, config=self.company, items_total=400.0)
        self.assertAlmostEqual(a['price_unit'], 270.0, places=2)
        self.assertAlmostEqual(b['price_unit'], 45.0, places=2)
        # una orden de un solo item: todo el descuento (como antes)
        c = mo._set_product_unit_price(self.product, {'unit_price': 400.0, 'quantity': 1}, config=self.company, items_total=400.0)
        self.assertAlmostEqual(c['price_unit'], 360.0, places=2)

    def test_1_discount_never_makes_price_negative(self):
        """Backstop del incidente de 26.131: un descuento mayor que el bruto del item (p. ej. el de un
        pack entero) no se aplica; la linea queda a precio pleno, nunca negativa."""
        mo = self.env['mercadolibre.orders'].create({'order_id': 'T-PACKDISC', 'name': 'x',
                                                      'discount_seller_amount': 50170.70})
        with self.assertLogs('odoo.addons.meli_oerp.models.orders', level='WARNING') as cm:
            res = mo._set_product_unit_price(self.product, {'unit_price': 3200.0, 'quantity': 1}, config=self.company)
        self.assertAlmostEqual(res['price_unit'], 3200.0, places=2)
        self.assertTrue(any('NO se aplica' in m for m in cm.output))

    def test_1_so_with_seller_coupon_invoices_paid_amount(self):
        """Con la linea en 5.057,80, el importe a facturar es lo pagado (5.057,80) y confirma."""
        so = self._so([5057.80], paid=5057.80, disc=266.20, coupon=266.20, meli_total_amount=5324.0)
        self._morder(so, '2000000000000001')
        self.assertAlmostEqual(so.meli_amount_to_invoice(config=self._cfg()), 5057.80, places=2)
        ready, reason = so.meli_confirm_ready(config=self._cfg())
        self.assertTrue(ready, reason)

    # ------------------------------------------- 4. envio pagado por el comprador
    def test_4_buyer_shipping_from_payments(self):
        """ML 2000000000000002: 152 + 85 de envio = 237; la venta no tenia meli_shipping_amount."""
        so = self._so([152.0], paid=237.0, ship=0.0)
        self._morder(so, '2000000000000002', pay_ship=85.0)
        self.assertAlmostEqual(so._meli_so_buyer_shipping(), 85.0, places=2)
        ready, reason = so.meli_confirm_ready(config=self._cfg())
        self.assertTrue(ready, reason)

    def test_4_without_shipping_anywhere_still_incomplete(self):
        """Control: si ni la venta ni el pago traen envio, la diferencia sigue marcandose."""
        so = self._so([152.0], paid=237.0, ship=0.0)
        self._morder(so, 'T-NOSHIP', pay_ship=0.0)
        ready, reason = so.meli_confirm_ready(config=self._cfg())
        self.assertFalse(ready)

    def test_4_other_cases_of_the_capture(self):
        for oid, prod, ship in (('2000000000000010', 254.0, 89.0), ('2000000000000011', 594.0, 35.0),
                                ('2000000000000012', 212.0, 89.0), ('2000000000000013', 1359.0, 62.41),
                                ('2000000000000014', 407.0, 57.58)):
            so = self._so([prod], paid=prod + ship)
            self._morder(so, oid, pay_ship=ship)
            ready, reason = so.meli_confirm_ready(config=self._cfg())
            self.assertTrue(ready, "%s: %s" % (oid, reason))

    # ------------------------------------------- 7. cupon + descuento del vendedor
    def test_7_coupon_plus_seller_discount(self):
        """ML 2000000000000003: linea 339 (399,99 - 60,99), pagado 388,18 (339 + 49,18 de envio),
        cupon 16,95. El calculo de siempre da 371,23; el bueno es 388,18 (con envio, modo always)."""
        so = self._so([339.0], paid=388.18, disc=60.99, coupon=16.95, meli_total_amount=399.99)
        self._morder(so, '2000000000000003', pay_ship=49.18)
        self.assertAlmostEqual(so._meli_amount_to_invoice_legacy(config=self._cfg()), 371.23, places=2)
        self.assertAlmostEqual(so.meli_amount_to_invoice(config=self._cfg()), 388.18, places=2)
        ready, reason = so.meli_confirm_ready(config=self._cfg())
        self.assertTrue(ready, reason)
        # modo never: el envio se resta -> 339
        self.assertAlmostEqual(so.meli_amount_to_invoice(config=self._cfg('never')), 339.0, places=2)

    def test_7_without_discount_in_line_is_unchanged(self):
        """Sin evidencia de que el descuento este en la linea (venta == total de ML), el default
        'coupon' de la flota no cambia: mismo numero que el calculo de siempre."""
        so = self._so([399.99], paid=388.18, disc=60.99, coupon=16.95)
        self._morder(so, 'T-NOEVID', pay_ship=49.18)
        self.assertAlmostEqual(so.meli_amount_to_invoice(config=self._cfg()),
                               so._meli_amount_to_invoice_legacy(config=self._cfg()), places=2)

    def test_7_legacy_that_fits_is_untouched(self):
        """Si el calculo de siempre ya cuadra, no se cambia (pagado 1.000, venta 1.000)."""
        so = self._so([1000.0], paid=1000.0)
        self._morder(so, 'T-OK')
        self.assertAlmostEqual(so.meli_amount_to_invoice(config=self._cfg()), 1000.0, places=2)

    def test_7_nothing_fits_returns_legacy(self):
        """Si ninguna interpretacion cuadra, devuelve el calculo de siempre (el control marca conflicto)."""
        so = self._so([500.0], paid=1000.0, disc=10.0)
        self._morder(so, 'T-CONFLICT')
        self.assertAlmostEqual(so.meli_amount_to_invoice(config=self._cfg()),
                               so._meli_amount_to_invoice_legacy(config=self._cfg()), places=2)

    # ------------------------------------------- 3. cancelacion de pack
    def _pack(self, s1, s2):
        so = self._so([100.0, 200.0], paid=300.0, meli_status='paid')
        so.action_confirm()
        self._morder(so, 'T-P1', status=s1, pack_id='2000000000000005')
        self._morder(so, 'T-P2', status=s2, pack_id='2000000000000005')
        return so

    def test_3_pack_all_cancelled_marks_sale(self):
        so = self._pack('cancelled', 'cancelled')
        order_json = {'id': 'T-P2', 'status': 'cancelled', 'status_detail': '',
                      'cancel_detail': {'code': 'buyer_cancel_express', 'description': 'x', 'requested_by': 'buyer',
                                        'date': '2026-10-13T19:18:35.000-04:00'},
                      'date_created': '2026-10-13T10:00:00.000-04:00', 'date_closed': '2026-10-13T10:00:00.000-04:00'}
        self.assertTrue(so._meli_pack_sync_cancelled(order_json=order_json))
        self.assertEqual(so.meli_status, 'cancelled')
        self.assertEqual(so.meli_cancel_reason_code, 'buyer_cancel_express')

    def test_3_pack_partially_cancelled_untouched(self):
        so = self._pack('cancelled', 'paid')
        self.assertFalse(so._meli_pack_sync_cancelled(order_json={'status': 'cancelled'}))
        self.assertEqual(so.meli_status, 'paid')

    def test_3_single_order_untouched(self):
        so = self._so([100.0], paid=100.0, meli_status='paid')
        self._morder(so, 'T-S1', status='cancelled')
        self.assertFalse(so._meli_pack_sync_cancelled(order_json={'status': 'cancelled'}))
