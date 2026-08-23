# -*- coding: utf-8 -*-
"""[#494] Cancelacion de la venta en Odoo cuando MercadoLibre cancela el pedido.

Cubre los bordes que importan porque tocan plata y stock:
  1. venta en BORRADOR                      -> se cancela
  2. venta CONFIRMADA sin entregar          -> se cancela y libera la reserva
  3. venta ENTREGADA (picking done)         -> se cancela y queda la devolucion
  4. venta FACTURADA (factura publicada)    -> NO se cancela, avisa y queda listable
  5. factura publicada + pago conciliado    -> NO se cancela, avisa y queda listable

Los casos 4 y 5 son deliberadamente NO automaticos: una factura emitida se reversa
con nota de credito y esa es una decision del cliente, no del conector. Lo que si se
exige es que el caso quede VISIBLE (flag buscable + WARNING) y que vuelva a intentarse
solo cuando la factura se resuelva (re-drain), en vez de caer en un limbo.
"""
from odoo.tests import common, tagged


@tagged('post_install', '-at_install', 'meli', 'meli_cancel')
class TestMeliCancelOnMlCancel(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': '#494 Comprador ML'})
        cls.product = cls.env['product.product'].create({
            'name': '#494 Producto ML',
            'type': 'product',
            'invoice_policy': 'order',
            'list_price': 1000.0,
        })

    def _new_ml_order(self, meli_status='paid'):
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1.0,
                'price_unit': 1000.0,
            })],
        })
        order.write({
            'meli_order_id': '2000099900000001',
            'meli_status': meli_status,
        })
        return order

    # ------------------------------------------------------------------
    # El flag buscable (lo que el cliente usa para auditar por su cuenta)
    # ------------------------------------------------------------------
    def test_flag_off_when_not_cancelled_in_ml(self):
        order = self._new_ml_order(meli_status='paid')
        self.assertFalse(order.meli_cancel_pending)

    def test_flag_on_when_ml_cancelled_and_odoo_alive(self):
        order = self._new_ml_order(meli_status='paid')
        order.meli_status = 'cancelled'
        self.assertTrue(
            order.meli_cancel_pending,
            "ML cancelo y la venta sigue viva: tiene que ser listable",
        )

    def test_flag_off_once_odoo_is_cancelled(self):
        order = self._new_ml_order(meli_status='cancelled')
        order.action_cancel()
        self.assertEqual(order.state, 'cancel')
        self.assertFalse(
            order.meli_cancel_pending,
            "Ya cancelada en Odoo: sale del listado de pendientes",
        )

    def test_flag_is_searchable(self):
        """store=True: tiene que poder buscarse por dominio, no solo leerse."""
        order = self._new_ml_order(meli_status='cancelled')
        found = self.env['sale.order'].search([
            ('meli_cancel_pending', '=', True), ('id', '=', order.id),
        ])
        self.assertEqual(found, order)

    # ------------------------------------------------------------------
    # Borde 1 - venta en borrador
    # ------------------------------------------------------------------
    def test_cancel_draft_order(self):
        order = self._new_ml_order(meli_status='cancelled')
        self.assertEqual(order.state, 'draft')
        order.meli_cancel_with_detail("Orden cancelada por MercadoLibre. Motivo: test")
        self.assertEqual(order.state, 'cancel')
        self.assertFalse(order.meli_cancel_pending)

    # ------------------------------------------------------------------
    # Borde 2 - confirmada, sin entregar
    # ------------------------------------------------------------------
    def test_cancel_confirmed_not_delivered(self):
        order = self._new_ml_order(meli_status='cancelled')
        order.action_confirm()
        self.assertEqual(order.state, 'sale')
        order.meli_cancel_with_detail("Orden cancelada por MercadoLibre. Motivo: test")
        self.assertEqual(order.state, 'cancel')
        self.assertTrue(
            all(p.state == 'cancel' for p in order.picking_ids),
            "Cancelar la venta tiene que liberar la reserva de stock",
        )

    # ------------------------------------------------------------------
    # Borde 3 - entregada (picking validado)
    # ------------------------------------------------------------------
    def test_cancel_delivered_creates_return(self):
        order = self._new_ml_order(meli_status='cancelled')
        order.action_confirm()
        picking = order.picking_ids[:1]
        if not picking:
            self.skipTest("Sin picking: la configuracion de stock del entorno no lo genera")
        self.env['stock.quant']._update_available_quantity(
            self.product, picking.location_id, 1.0)
        picking.action_assign()
        for move in picking.move_ids:
            for line in move.move_line_ids:
                if 'qty_done' in line._fields:
                    line.qty_done = line.reserved_uom_qty or 1.0
                else:
                    line.quantity = 1.0
        picking.button_validate()
        self.assertEqual(picking.state, 'done')

        pickings_before = len(order.picking_ids)
        order.meli_cancel_with_detail("Orden cancelada por MercadoLibre. Motivo: test")
        self.assertGreater(
            len(order.picking_ids), pickings_before,
            "Entregada: tiene que quedar una devolucion, no desaparecer el movimiento",
        )
        self.assertEqual(order.state, 'cancel')

    # ------------------------------------------------------------------
    # Borde 4 - facturada (factura PUBLICADA): NO se cancela sola
    # ------------------------------------------------------------------
    def test_posted_invoice_blocks_automatic_cancel(self):
        order = self._new_ml_order(meli_status='cancelled')
        order.action_confirm()
        invoice = order._create_invoices()
        if not invoice:
            self.skipTest("El entorno no permite crear la factura de venta")
        invoice.action_post()
        self.assertEqual(invoice.state, 'posted')

        order.meli_cancel_with_detail("Orden cancelada por MercadoLibre. Motivo: test")

        self.assertNotEqual(
            order.state, 'cancel',
            "Una venta con factura publicada NO se cancela sola: eso es una nota de "
            "credito, y la decide el cliente",
        )
        self.assertTrue(
            order.meli_cancel_pending,
            "Si no se pudo cancelar, tiene que quedar LISTABLE - no en un limbo",
        )
        self.assertTrue(
            order.message_ids.filtered(
                lambda m: 'REQUERIDA' in (m.body or '') or 'pendiente' in (m.body or '')
            ),
            "Tiene que quedar el aviso visible en el chatter",
        )

    # ------------------------------------------------------------------
    # Borde 5 - factura publicada Y conciliada con un pago
    # ------------------------------------------------------------------
    def test_reconciled_payment_blocks_automatic_cancel(self):
        order = self._new_ml_order(meli_status='cancelled')
        order.action_confirm()
        invoice = order._create_invoices()
        if not invoice:
            self.skipTest("El entorno no permite crear la factura de venta")
        invoice.action_post()

        journal = self.env['account.journal'].search(
            [('type', 'in', ('bank', 'cash')), ('company_id', '=', invoice.company_id.id)],
            limit=1)
        if not journal:
            self.skipTest("Sin diario de banco/efectivo en el entorno")
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner.id,
            'amount': invoice.amount_total,
            'journal_id': journal.id,
        })
        payment.action_post()
        (payment.move_id.line_ids + invoice.line_ids).filtered(
            lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
        ).reconcile()
        self.assertNotEqual(invoice.payment_state, 'not_paid')

        order.meli_cancel_with_detail("Orden cancelada por MercadoLibre. Motivo: test")

        self.assertNotEqual(
            order.state, 'cancel',
            "Con el pago conciliado, menos todavia: no se toca sola",
        )
        self.assertTrue(order.meli_cancel_pending)

    # ------------------------------------------------------------------
    # Re-drain: el caso trabado NO sale de la cola para siempre
    # ------------------------------------------------------------------
    def test_redrain_retries_and_cancels_once_invoice_is_resolved(self):
        order = self._new_ml_order(meli_status='cancelled')
        order.action_confirm()
        invoice = order._create_invoices()
        if not invoice:
            self.skipTest("El entorno no permite crear la factura de venta")
        invoice.action_post()

        ml_order = self.env['mercadolibre.orders'].create({
            'order_id': '2000099900000001',
            'status': 'cancelled',
            'sale_order': order.id,
        })

        # 1a pasada: la factura publicada bloquea -> queda pendiente, NO cancelada.
        res = self.env['mercadolibre.orders']._orders_redrain_pending_cancels()
        self.assertNotEqual(order.state, 'cancel')
        self.assertGreaterEqual(res.get('pending', 0), 1)

        # El cliente resuelve la factura (aca: la revierte; en la vida real, nota de credito).
        invoice.button_draft()
        invoice.button_cancel()

        # 2a pasada: el mismo pedido VUELVE a intentarse y ahora si se cancela.
        res2 = self.env['mercadolibre.orders']._orders_redrain_pending_cancels()
        self.assertEqual(
            order.state, 'cancel',
            "Resuelta la factura, el re-drain tiene que cancelar la venta sin que "
            "nadie se acuerde de volver",
        )
        self.assertGreaterEqual(res2.get('cancelled', 0), 1)
        self.assertFalse(order.meli_cancel_pending)
        self.assertTrue(ml_order.exists())
