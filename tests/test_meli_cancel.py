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
from unittest.mock import patch

from odoo.tests import common, tagged


@tagged('post_install', '-at_install', 'meli', 'meli_cancel')
class TestMeliCancelOnMlCancel(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        # El chatter es parte de lo que estos tests verifican: si la instancia tiene el
        # modo en "none", meli_message_post() sólo loguea y las aserciones de chatter
        # medirían la CONFIGURACION en vez del código. Se fija explícitamente.
        if 'mercadolibre_notification_mode' in cls.company._fields:
            cls.company.mercadolibre_notification_mode = 'notification'

        cls.partner = cls.env['res.partner'].create({'name': '#494 Comprador ML'})
        # Localizacion AR: sin responsabilidad AFIP en el partner, la factura no puede
        # calcular su tipo de documento y action_post() muere en el FIXTURE, antes de
        # llegar a una sola linea del codigo del #494.
        if 'l10n_ar_afip_responsibility_type_id' in cls.partner._fields:
            resp = cls.env.ref('l10n_ar.res_CF', raise_if_not_found=False)
            if not resp:
                resp = cls.env['l10n_ar.afip.responsibility.type'].search([], limit=1)
            if resp:
                cls.partner.l10n_ar_afip_responsibility_type_id = resp.id

        cls.product = cls.env['product.product'].create({
            'name': '#494 Producto ML',
            'type': 'product',
            'invoice_policy': 'order',
            'list_price': 1000.0,
        })

    # ------------------------------------------------------------------
    # Fixture: publicar la factura en instancias con localizacion latam
    # ------------------------------------------------------------------
    def _non_electronic_sale_journal(self, company):
        """Diario de ventas que NO factura electronicamente.

        POR QUE ESTO IMPORTA MAS QUE UN DETALLE DE FIXTURE. En una instancia con la
        localizacion AR de facturacion electronica (`l10n_ar_afipws_fe`), `action_post()`
        llama a `do_pyafipws_request_cae()`: PIDE UN CAE REAL A AFIP. En el server de test
        de Shoppy eso corta con "Not confirmed certificate for production", pero en una
        instancia con el certificado cargado un test emitiria un comprobante fiscal de
        verdad, y EL CAE NO SE DESHACE CON UN ROLLBACK. Un test nunca debe pasar por ahi.

        Se elige entonces un diario de venta de la compania SIN `afip_ws`, prefiriendo uno
        que no use documentos latam: lo que estos tests necesitan es una factura PUBLICADA,
        no un comprobante fiscal.
        """
        Journal = self.env['account.journal']
        journals = Journal.search([('type', '=', 'sale'), ('company_id', '=', company.id)])
        if 'afip_ws' in Journal._fields:
            journals = journals.filtered(lambda j: not j.afip_ws)
        if 'l10n_latam_use_documents' in Journal._fields:
            simple = journals.filtered(lambda j: not j.l10n_latam_use_documents)
            if simple:
                return simple[0]
        return journals[0] if journals else Journal

    def _create_posted_invoice(self, order):
        """Crea y PUBLICA la factura de la venta, sin tocar AFIP.

        POR QUE EXISTE. Tres de estos tests morian en el fixture, dentro de
        `action_post()`, y su ERROR se leia como si el codigo del #494 estuviera roto.
        Eran DOS muros encadenados, y el segundo solo aparecio al correr el primero:

        1. `l10n_latam_document_type_id`: con la localizacion latam instalada el diario lo
           exige y `action_post()` corta con "El diario requiere un tipo de documento".
        2. El diario por defecto de la compania es ELECTRONICO y `action_post()` dispara
           el pedido de CAE a AFIP.

        Un test que no llega al codigo no prueba nada. Este helper resuelve los dos y deja
        una factura realmente publicada, no un `state` escrito a mano.
        """
        invoice = order._create_invoices()
        if not invoice:
            self.skipTest("El entorno no permite crear la factura de venta")

        journal = self._non_electronic_sale_journal(invoice.company_id)
        if not journal:
            self.skipTest("Sin diario de ventas no electronico: el fixture no puede "
                          "publicar la factura sin pedirle un CAE real a AFIP")
        if invoice.journal_id != journal:
            invoice.journal_id = journal.id

        if 'l10n_latam_document_type_id' in invoice._fields:
            available = invoice.l10n_latam_available_document_type_ids
            if available and not invoice.l10n_latam_document_type_id:
                invoice.l10n_latam_document_type_id = available[0]

        invoice.action_post()
        self.assertEqual(
            invoice.state, 'posted',
            "El fixture tiene que dejar la factura PUBLICADA; si no, el test de abajo no "
            "estaria midiendo el caso que dice medir")
        return invoice

    def _deliver_order(self, order):
        """Entrega la venta validando TODA la cadena de albaranes.

        POR QUE. `order.picking_ids[:1]` sirve en un almacen de UN paso. En uno de 2 o 3
        pasos (el de Shoppy) la cadena es PICK -> PACK -> OUT y el primero es INTERNO:
        validarlo solo no deja la venta entregada, y `_meli_return_done_pickings()` -- que
        filtra por `picking_type_code == 'outgoing'` -- no encuentra nada que devolver. El
        test decia "venta ENTREGADA" y montaba otra cosa: su fallo no probaba un defecto
        del conector, probaba que el fixture no armaba el escenario.

        :return: los albaranes de SALIDA que quedaron en 'done'.
        """
        Quant = self.env['stock.quant']
        for _vuelta in range(6):
            pending = order.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel'))
            if not pending:
                break
            avanzo = False
            for picking in pending.sorted('id'):
                picking.action_assign()
                if picking.state != 'assigned':
                    for move in picking.move_ids:
                        Quant._update_available_quantity(
                            move.product_id, picking.location_id, move.product_uom_qty)
                    picking.action_assign()
                if picking.state != 'assigned':
                    continue
                for move in picking.move_ids:
                    for line in move.move_line_ids:
                        if 'qty_done' in line._fields:
                            line.qty_done = line.reserved_uom_qty or move.product_uom_qty
                        else:
                            line.quantity = move.product_uom_qty
                # skip_immediate/skip_backorder: button_validate() tambien puede devolver
                # el dict de un wizard en vez de validar -- el mismo modo de falla del #494.
                picking.with_context(skip_immediate=True, skip_backorder=True).button_validate()
                if picking.state == 'done':
                    avanzo = True
            if not avanzo:
                break
        return order.picking_ids.filtered(
            lambda p: p.state == 'done' and p.picking_type_code == 'outgoing')

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
        if not order.picking_ids:
            self.skipTest("Sin picking: la configuracion de stock del entorno no lo genera")

        entregados = self._deliver_order(order)
        if not entregados:
            self.skipTest(
                "El entorno no dejo ningun albaran de SALIDA en 'done': sin eso este test "
                "no monta el caso 'venta entregada' y no mediria nada")

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
        invoice = self._create_posted_invoice(order)

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
        invoice = self._create_posted_invoice(order)

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
        invoice = self._create_posted_invoice(order)

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

    # ------------------------------------------------------------------
    # El defecto que hacia que el codigo FINGIERA trabajar (#494)
    # ------------------------------------------------------------------
    def test_action_cancel_sin_el_contexto_devuelve_el_wizard_y_no_cancela(self):
        """Control NEGATIVO: reproduce el defecto contra el core, no contra nosotros.

        Es la prueba de que el instrumento mide algo real: sin
        `disable_cancel_warning`, `action_cancel()` de una venta confirmada devuelve un
        dict (la accion de ventana del wizard `sale.order.cancel`), NO lanza excepcion y
        deja la venta en 'sale'. Ese dict es lo que el conector se comia desde nov-2025.

        En Odoo 19 el core elimino el wizard y la clave: alli `action_cancel()` cancela
        igual. Por eso el test acepta las dos formas y afirma la INVARIANTE que importa:
        si volvio un dict, la venta NO puede estar cancelada.
        """
        order = self._new_ml_order(meli_status='cancelled')
        order.action_confirm()
        self.assertEqual(order.state, 'sale')

        res = order.action_cancel()
        if isinstance(res, dict):
            self.assertEqual(res.get('res_model'), 'sale.order.cancel')
            self.assertNotEqual(
                order.state, 'cancel',
                "Si action_cancel() devolvio el wizard, la venta NO se cancelo: dar eso "
                "por cancelado es exactamente el defecto del #494")
        else:
            self.assertEqual(order.state, 'cancel')

    def test_meli_action_cancel_cancela_de_verdad_y_lo_informa(self):
        """Control POSITIVO del helper: cancela y devuelve True, no un dict."""
        order = self._new_ml_order(meli_status='cancelled')
        order.action_confirm()
        self.assertEqual(order.state, 'sale')

        res = order._meli_action_cancel()
        self.assertIs(res, True, "El helper tiene que devolver un bool, no el wizard")
        self.assertEqual(order.state, 'cancel')

        # Idempotente: sobre una venta ya cancelada devuelve True sin romper.
        self.assertIs(order._meli_action_cancel(), True)

    def test_meli_cancel_with_detail_devuelve_true_cuando_cancela(self):
        order = self._new_ml_order(meli_status='cancelled')
        order.action_confirm()
        res = order.meli_cancel_with_detail("Orden cancelada por MercadoLibre. Motivo: test")
        self.assertIs(res, True)
        self.assertEqual(order.state, 'cancel')

    def test_el_chatter_no_afirma_una_cancelacion_que_no_ocurrio(self):
        """El corazon del #494: no fallaba, MENTIA.

        Se fuerza el peor caso (la cancelacion no se puede aplicar) y se exige que el
        chatter NO quede diciendo 'Orden cancelada por MercadoLibre' sobre una venta que
        sigue viva. Antes ese mensaje se posteaba pasara lo que pasara, y era la razon de
        que el defecto sobreviviera meses: dejaba rastro de haber hecho el trabajo.
        """
        order = self._new_ml_order(meli_status='cancelled')
        order.action_confirm()
        cancel_msg = "Orden cancelada por MercadoLibre. Motivo: test"

        with patch.object(type(order), '_meli_action_cancel', lambda self: False):
            res = order.meli_cancel_with_detail(cancel_msg)

        self.assertIs(res, False, "No cancelo: el metodo tiene que decirlo")
        self.assertNotEqual(order.state, 'cancel')

        bodies = [b for b in order.message_ids.mapped('body') if b]
        afirmaciones = [
            b for b in bodies
            if cancel_msg in b and 'NO pudo cancelarse' not in b
        ]
        self.assertFalse(
            afirmaciones,
            "El chatter afirma la cancelacion con la venta todavia en '%s': %s"
            % (order.state, afirmaciones))
        self.assertTrue(
            [b for b in bodies if 'NO pudo cancelarse' in b],
            "Tiene que quedar el aviso EXPLICITO de que no se pudo cancelar")
