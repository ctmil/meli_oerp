# -*- coding: utf-8 -*-
"""26.354 (153 BA Vending, 2-nov-2026): cancelación de ML con FACTURA PUBLICADA => actividad SIEMPRE.

Hasta 26.353 el pack_splitted con factura publicada dejaba sólo chatter si
`meli_oerp.cancel_reason_policy` no estaba en by_reason (el default, y BA no lo tiene): el aviso se
perdió y la gemela se facturó encima. Igual en el camino legacy genérico (cualquier motivo, factura
publicada que no vuelve a borrador). Ahora: actividad 'Revisar cancelación de MercadoLibre' UNA vez,
la venta no se cancela y NUNCA se crea nota de crédito automática.

Casos reales (original cancelada por pack_splitted -> gemela): 2000019270134014 -> 2000019281411680,
2000019276075288 -> 2000019289037380, 2000019281735806 -> 2000019289046854 (ítem MLA2512253164, 68.890).

Correr:  odoo-bin ... --test-enable --test-tags /meli_oerp:TestCancelActividadFactura --stop-after-init
"""
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

ITEM = "MLA2512253164"
AMOUNT = 68890.0
CASES = [
    ("2000019270134014", "2000019281411680", "202800992"),
    ("2000019276075288", "2000019289037380", "47381496"),
    ("2000019281735806", "2000019289046854", "166078168"),
]
REVIEW = "Revisar cancelación de MercadoLibre"


class _FakeMeli:
    access_token = "TEST"
    needlogin_state = False


@tagged("post_install", "-at_install", "meli_26354")
class TestCancelActividadFactura(TransactionCase):

    def setUp(self):
        super().setUp()
        self.SO = self.env["sale.order"]
        co = self.env.company
        if not self.env["account.journal"].search([("type", "=", "sale"), ("company_id", "=", co.id)], limit=1):
            self.skipTest("sin diario de ventas en esta base")
        co.mercadolibre_return_mode = "done"
        co.mercadolibre_invoice_cancel_mode = "manual"
        co.mercadolibre_cancel_mode = "legacy"
        if "mercadolibre_cancel_auto_from" in co._fields:
            co.mercadolibre_cancel_auto_from = False
        if "mercadolibre_notification_mode" in co._fields:
            co.mercadolibre_notification_mode = "internal_note"
        # El default de BA: el parámetro de la política por motivo NO está seteado.
        self.env["ir.config_parameter"].sudo().search(
            [("key", "=", "meli_oerp.cancel_reason_policy")]).unlink()
        self.assertFalse(self.SO._meli_cancel_policy_on())
        Product = self.env["product.product"]
        pvals = {"name": "Nescafé 1 kg", "list_price": AMOUNT, "invoice_policy": "order"}
        pvals["detailed_type" if "detailed_type" in Product._fields else "type"] = "service"
        self.product = Product.create(pvals)

        p = patch.object(type(self.SO), "_meli_cancel_fetch",
                         lambda s, meli, path: {"error": "not_found", "status": 404})
        p.start()
        self.addCleanup(p.stop)

    def _so(self, oid, status, partner):
        tax_f = "tax_id" if "tax_id" in self.env["sale.order.line"]._fields else "tax_ids"
        so = self.SO.create({
            "partner_id": partner.id, "meli_order_id": oid, "meli_status": status,
            "order_line": [(0, 0, {"product_id": self.product.id, "product_uom_qty": 1,
                                   "price_unit": AMOUNT, tax_f: [(6, 0, [])]})]})
        so.action_confirm()
        return so

    def _mo(self, so, oid, buyer, status, date, tags):
        mo = self.env["mercadolibre.orders"].create({
            "order_id": oid, "pack_id": "P" + oid, "status": status, "buyer": buyer.id,
            "date_created": date, "sale_order": so.id, "tags": tags})
        self.env["mercadolibre.order_items"].create({"order_id": mo.id, "order_item_id": ITEM})
        so.meli_orders = [(6, 0, mo.ids)]

    def _pair(self, orig_id, twin_id, bid):
        buyer = self.env["mercadolibre.buyers"].create({"name": "Comprador %s" % bid, "buyer_id": bid})
        partner = self.env["res.partner"].create({"name": "Comprador ML %s" % bid})
        orig = self._so(orig_id, "cancelled", partner)
        self._mo(orig, orig_id, buyer, "cancelled", "2026-11-01 15:00:00", "['paid']")
        inv = orig._create_invoices()
        inv.action_post()
        twin = self._so(twin_id, "paid", partner)
        self._mo(twin, twin_id, buyer, "paid", "2026-11-01 19:53:30", "['splitted_order', 'paid']")
        return orig, inv, twin

    def _cancel(self, so, code):
        oj = {"id": int(so.meli_order_id), "status": "cancelled",
              "cancel_detail": {"group": "internal", "code": code, "requested_by": "meli"}}
        def no_draft(move_self, *a, **k):
            # Factura con CAE (o sin meli_oerp_accounting): no vuelve a borrador.
            raise UserError("factura con CAE: no vuelve a borrador")
        with patch.object(type(self.env["account.move"]), "button_draft", no_draft):
            return so.with_context(meli_cancel_ctx_nocache=True).meli_cancel_with_detail(
                "Orden cancelada por MercadoLibre. Motivo: internal / %s / meli" % code,
                order_json=oj, meli=_FakeMeli())

    def _review(self, so):
        return so.activity_ids.filtered(lambda a: a.summary == REVIEW)

    def _refunds(self):
        return self.env["account.move"].search_count([("move_type", "=", "out_refund")])

    def test_pack_splitted_con_factura_actividad_sin_politica(self):
        refunds0 = self._refunds()
        for orig_id, twin_id, bid in CASES:
            orig, inv, twin = self._pair(orig_id, twin_id, bid)
            self.assertFalse(self._cancel(orig, "pack_splitted"))
            self.assertNotEqual(orig.state, "cancel")
            act = self._review(orig)
            self.assertEqual(len(act), 1, orig_id)
            self.assertIn(inv.name, act.note)
            self.assertIn(twin.name, act.note, "nombra la gemela")
            self.assertIn(twin.name, orig.meli_cancel_decision)
            # Reproceso del cron: una sola actividad.
            self._cancel(orig, "pack_splitted")
            self.assertEqual(len(self._review(orig)), 1)
            self.assertEqual(inv.state, "posted")
        self.assertEqual(self._refunds(), refunds0, "nunca nota de crédito automática")

    def test_pack_splitted_sin_factura_ni_salida_cancela_sin_actividad(self):
        buyer = self.env["mercadolibre.buyers"].create({"name": "C", "buyer_id": "1"})
        partner = self.env["res.partner"].create({"name": "C"})
        so = self._so(CASES[0][0], "cancelled", partner)
        self._mo(so, CASES[0][0], buyer, "cancelled", "2026-11-01 15:00:00", "['paid']")
        self.assertTrue(self._cancel(so, "pack_splitted"))
        self.assertEqual(so.state, "cancel")
        self.assertFalse(self._review(so))

    def test_otro_motivo_con_factura_publicada_actividad(self):
        partner = self.env["res.partner"].create({"name": "Comprador recurrente"})
        so = self._so("2000019299999999", "cancelled", partner)
        inv = so._create_invoices()
        inv.action_post()
        self.assertFalse(self._cancel(so, "buyer_cancel_express"))
        self.assertNotEqual(so.state, "cancel")
        act = self._review(so)
        self.assertEqual(len(act), 1)
        self.assertIn(inv.name, act.note)
