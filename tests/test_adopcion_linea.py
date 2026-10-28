# -*- coding: utf-8 -*-
"""26.250 -- la sincronizacion ADOPTA la linea del mismo producto sin vinculo ML.

Mecanismo medido en ventas reales: el usuario cancela y vuelve a confirmar la venta a mano; la
linea que queda la crea el usuario y NO tiene `meli_order_item_id`. La sincronizacion siguiente
no la encontraba por (item, variacion, venta), el monto no cuadraba (descuento del vendedor) y
agregaba otra linea del mismo producto ⇒ producto duplicado y un abastecimiento nuevo.
Variante: la sincronizacion cae entre "cotizacion" y "confirmar" (venta en borrador) y crea la
segunda linea antes de que el usuario confirme.
"""
from odoo.tests import tagged

from .test_import_cupon_linea import TestImportCuponLinea, _order_json

ROUTES = [('/items/', {'id': 'MLM000TEST'})]


@tagged('post_install', '-at_install', 'meli', 'meli_26250')
class TestAdopcionLinea(TestImportCuponLinea):

    # no re-ejecutar los tests heredados
    test_1_new_order_seller_coupon_line_is_net = None
    test_1_coupon_only_in_payments_still_fetches_discounts = None
    test_1_pack_member_coupon_only_in_payments_does_not_fetch = None
    test_6_resync_does_not_add_line_to_confirmed_sale = None

    def _import(self, oid, unit=959.99, paid=911.99):
        oj = _order_json(oid=oid, unit=unit, paid=paid, coupon=0)
        self._run(oj, ROUTES)
        so = self.env['sale.order'].search([('meli_order_id', '=', str(oid))], limit=1)
        self.assertTrue(so, "no se creo la venta")
        return so, oj

    def _product_lines(self, so):
        return so.order_line.filtered(lambda l: not l.is_delivery and not l.display_type and l.product_id == self.product)

    def _cancel_and_requote_by_hand(self, so, price):
        """Lo que hace el usuario: cancelar, volver a cotizacion, rehacer la linea a mano."""
        so.with_context(disable_cancel_warning=True)._action_cancel()
        so.action_draft()
        self._product_lines(so).unlink()
        self.env['sale.order.line'].create({'order_id': so.id, 'product_id': self.product.id,
                                            'product_uom_qty': 1, 'price_unit': price})
        self.assertFalse(self._product_lines(so).meli_order_item_id)

    def _notes(self, so):
        return so.message_ids.filtered(lambda m: 'no tiene una' in (m.body or '') and 'MLM000TEST' in (m.body or ''))

    def test_a_reconfirmed_by_hand_resync_adopts_line(self):
        """Cancelada y reconfirmada a mano: el re-sync NO agrega otra linea, vincula la del usuario."""
        oid = 2000696554923115
        so, oj = self._import(oid)
        self._cancel_and_requote_by_hand(so, 959.99)
        so.action_confirm()
        self.assertEqual(so.state, 'sale')
        self._run(oj, ROUTES)
        lines = self._product_lines(so)
        self.assertEqual(len(lines), 1, "el re-sync agrego una linea a la venta reconfirmada")
        self.assertEqual(lines.meli_order_item_id, 'MLM000TEST')
        self.assertFalse(self._notes(so), "no corresponde aviso: la linea se adopto")

    def test_b_resync_between_quotation_and_confirm(self):
        """La sincronizacion cae con la venta en cotizacion: adopta y re-precia la linea, no crea otra."""
        oid = 2000015138026200
        so, oj = self._import(oid)
        self._cancel_and_requote_by_hand(so, 959.99)
        self.assertEqual(so.state, 'draft')
        self._run(oj, ROUTES)
        lines = self._product_lines(so)
        self.assertEqual(len(lines), 1, "la sincronizacion en cotizacion creo una segunda linea")
        self.assertEqual(lines.meli_order_item_id, 'MLM000TEST')
        so.action_confirm()
        self._run(oj, ROUTES)
        self.assertEqual(len(self._product_lines(so)), 1)

    def test_c_confirmed_without_candidate_posts_one_note(self):
        """Venta confirmada sin ninguna linea del producto: no se agrega linea y queda UNA nota de control."""
        oid = 2000323771537355
        so, oj = self._import(oid)
        other = self.env['product.product'].create({'name': 'Otro', 'taxes_id': [(5, 0, 0)]})
        self._cancel_and_requote_by_hand(so, 959.99)
        self._product_lines(so).write({'product_id': other.id})
        so.action_confirm()
        n = len(so.order_line)
        with self.assertLogs('odoo.addons.meli_oerp.models.orders', level='WARNING') as cm:
            self._run(oj, ROUTES)
            self._run(oj, ROUTES)
        self.assertTrue(any('NO se agrega' in m for m in cm.output))
        self.assertEqual(len(so.order_line), n, "se agrego una linea a la venta confirmada")
        self.assertEqual(len(self._notes(so)), 1, "la nota de control tiene que quedar una sola vez")

    def test_d_two_unlinked_candidates_adopts_one_never_creates(self):
        oid = 2000340553973742
        so, oj = self._import(oid)
        self._cancel_and_requote_by_hand(so, 959.99)
        self.env['sale.order.line'].create({'order_id': so.id, 'product_id': self.product.id,
                                            'product_uom_qty': 2, 'price_unit': 959.99})
        with self.assertLogs('odoo.addons.meli_oerp.models.orders', level='WARNING'):
            line = self.env['mercadolibre.orders']._meli_adopt_unlinked_sale_line(
                so, {'product_id': self.product.id, 'product_uom_qty': 1, 'meli_order_item_id': 'MLM000TEST',
                     'meli_order_item_variation_id': False})
        self.assertEqual(len(line), 1)
        self.assertEqual(line.product_uom_qty, 1, "debe adoptar la de la misma cantidad")
        self.assertEqual(len(self._product_lines(so).filtered('meli_order_item_id')), 1)
        self.assertEqual(len(self._product_lines(so)), 2)


@tagged('post_install', '-at_install', 'meli', 'meli_26250')
class TestCarritoCancelacion(TestImportCuponLinea):
    """26.250 -- cancelacion en carritos: carrito de UNA orden y carrito PARCIAL."""

    test_1_new_order_seller_coupon_line_is_net = None
    test_1_coupon_only_in_payments_still_fetches_discounts = None
    test_1_pack_member_coupon_only_in_payments_does_not_fetch = None
    test_6_resync_does_not_add_line_to_confirmed_sale = None

    def _cart(self, statuses, pack='2000460463933812'):
        so = self.env['sale.order'].create({
            'partner_id': self.contact.id, 'company_id': self.company.id,
            'order_line': [(0, 0, {'product_id': self.product.id, 'product_uom_qty': 1, 'price_unit': 100.0})]})
        so.write({'meli_order_id': pack, 'meli_status': 'paid'})
        so.action_confirm()
        for i, st in enumerate(statuses):
            mo = self.env['mercadolibre.orders'].create({
                'order_id': '%s%d' % (pack[:-1], i + 5), 'name': 'MO %d' % i, 'status': st,
                'sale_order': so.id, 'pack_id': pack})
            so.meli_orders = [(4, mo.id)]
        return so

    _CANCEL_JSON = {'id': 'X', 'status': 'cancelled', 'status_detail': '',
                    'cancel_detail': {'code': 'mediations', 'description': 'Mediations cancel the order',
                                      'requested_by': 'meli', 'date': '2026-09-29T13:45:59.000-04:00'}}

    def _notes(self, so):
        return so.message_ids.filtered(lambda m: 'siguen vigentes' in (m.body or ''))

    def test_e_single_order_cart_takes_cancelled(self):
        """Carrito con UNA orden ML cancelada: la venta toma meli_status=cancelled (26.229 lo salteaba)."""
        so = self._cart(['cancelled'])
        self.assertTrue(so._meli_pack_sync_cancelled(order_json=self._CANCEL_JSON))
        self.assertEqual(so.meli_status, 'cancelled')
        self.assertEqual(so.meli_cancel_reason_code, 'mediations')

    def test_f_single_order_sale_untouched(self):
        """Venta comun (meli_order_id = id de su orden): no la toca este camino."""
        so = self._cart(['cancelled'])
        so.meli_order_id = so._meli_sale_ml_orders().order_id
        self.assertFalse(so._meli_pack_sync_cancelled(order_json=self._CANCEL_JSON))

    def test_g_partial_cart_is_not_cancelled(self):
        so = self._cart(['cancelled', 'paid'])
        res = so.meli_cancel_with_detail("Orden cancelada por MercadoLibre.", order_json=self._CANCEL_JSON)
        self.assertFalse(res)
        self.assertEqual(so.state, 'sale', "se cancelo la venta entera de un carrito con una orden viva")
        so.meli_cancel_with_detail("Orden cancelada por MercadoLibre.", order_json=self._CANCEL_JSON)
        self.assertEqual(len(self._notes(so)), 1)

    def test_h_full_cart_still_cancels(self):
        so = self._cart(['cancelled', 'cancelled'])
        so.meli_cancel_with_detail("Orden cancelada por MercadoLibre.", order_json=self._CANCEL_JSON)
        self.assertEqual(so.state, 'cancel')
        self.assertFalse(self._notes(so))

    def test_i_manual_action_ignores_partial(self):
        so = self._cart(['cancelled', 'paid'])
        so.meli_status = 'cancelled'
        so.action_meli_cancel_process_held()
        self.assertEqual(so.state, 'cancel')
