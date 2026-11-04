# -*- coding: utf-8 -*-
"""157 (Hito Fusion, Smarttrack #5121) — una venta CANCELADA en ML que en Odoo sigue en
sale/done no debe recuperar el albaran por la "reparacion de entregas".

Caso: la cancelacion de ML no se pudo aplicar en Odoo (_meli_action_cancel "NO quedo
cancelada"; banner meli_cancel_pending_banner) y la entrega quedo cancelada/borrada con los
stock.move huerfanos (picking_id NULL). `meli_repair_missing_pickings` (boton y la
auto-reparacion de `meli_oerp_update`) les hacia `_assign_picking()` y RE-CREABA el albaran:
mercaderia reservada y lista para despachar en una venta que ML ya no cobra.

Sin red: la venta no tiene `meli_orders`, asi que meli_oerp_update no llama a ML.
"""
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

ORPHAN_STATES = ['confirmed', 'waiting', 'partially_available', 'assigned']


@tagged("post_install", "-at_install", "meli", "meli_cancel", "meli_157_cancel_guard")
class TestCancelGuardRepair(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Comprador 157 cancel guard"})
        Product = cls.env["product.product"]
        vals = {"name": "Producto 157 cancel guard", "type": "consu", "list_price": 100.0}
        if "is_storable" not in Product._fields:
            vals["type"] = "product"
        else:
            vals["is_storable"] = True
        cls.product = Product.create(vals)
        cls._n = 0

    def _sale_with_orphan_moves(self, meli_status):
        """Venta ML confirmada cuya entrega desaparecio dejando los moves sin picking."""
        type(self)._n += 1
        so = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "meli_order_id": "2000015700%05d" % self._n,
            "meli_status": "paid",
            "order_line": [(0, 0, {"product_id": self.product.id, "product_uom_qty": 1.0,
                                   "price_unit": 100.0})],
        })
        so.action_confirm()
        self.assertEqual(so.state, "sale")
        pickings = so.picking_ids
        self.assertTrue(pickings, "precondicion: action_confirm crea la entrega")
        cr = self.env.cr
        cr.execute("UPDATE stock_move SET picking_id = NULL WHERE picking_id IN %s", (tuple(pickings.ids),))
        cr.execute("DELETE FROM stock_move_line WHERE picking_id IN %s", (tuple(pickings.ids),))
        cr.execute("DELETE FROM stock_picking WHERE id IN %s", (tuple(pickings.ids),))
        self.env.invalidate_all() if hasattr(self.env, "invalidate_all") else self.env.cache.invalidate()
        so.write({"meli_status": meli_status})
        self.assertFalse(so.picking_ids, "precondicion: la venta quedo sin entrega")
        self.assertTrue(self._orphans(so), "precondicion: quedan moves huerfanos")
        return so

    def _orphans(self, so):
        return self.env["stock.move"].search([
            ("picking_id", "=", False), ("state", "in", ORPHAN_STATES),
            ("sale_line_id.order_id", "=", so.id),
        ])

    # ------------------------------------------------------------ el caso
    def test_01_repair_no_recrea_entrega_de_venta_cancelada_en_ml(self):
        so = self._sale_with_orphan_moves("cancelled")
        res = so.meli_repair_missing_pickings()
        self.assertFalse(so.picking_ids, "venta cancelada en ML: no se re-crea el albaran")
        self.assertTrue(self._orphans(so), "los moves siguen huerfanos (se resuelven por el flujo de cancelacion)")
        self.assertEqual(res["params"]["type"], "warning")

    def test_02_auto_repair_de_meli_oerp_update_no_recrea_entrega(self):
        so = self._sale_with_orphan_moves("cancelled")
        so.meli_oerp_update()
        self.assertFalse(so.picking_ids, "la auto-reparacion de meli_oerp_update respeta la cancelacion de ML")

    # --------------------------------------------------- controles positivos
    def test_03_control_repair_si_repara_venta_pagada(self):
        so = self._sale_with_orphan_moves("paid")
        res = so.meli_repair_missing_pickings()
        self.assertTrue(so.picking_ids, "control: venta pagada con moves huerfanos SI se repara")
        self.assertFalse(self._orphans(so))
        self.assertEqual(res["params"]["type"], "success")

    def test_04_control_auto_repair_si_repara_venta_pagada(self):
        so = self._sale_with_orphan_moves("paid")
        so.meli_oerp_update()
        self.assertTrue(so.picking_ids, "control: la auto-reparacion sigue andando para ventas vivas")

    def test_05_lote_mixto_repara_solo_la_viva(self):
        viva = self._sale_with_orphan_moves("paid")
        cancelada = self._sale_with_orphan_moves("cancelled")
        (viva | cancelada).meli_repair_missing_pickings()
        self.assertTrue(viva.picking_ids)
        self.assertFalse(cancelada.picking_ids)
