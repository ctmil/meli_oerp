# -*- coding: utf-8 -*-
"""26.332 (caso-K01 cliente B, ticket id caso-K06 / portal #caso-K05) -- cambios de producto de MercadoLibre.

Payloads REALES de la cuenta MLM de cliente B (GET de solo lectura, 28-oct-2026), recortados en
tests/data/meli_change_cliente_b.json. Red mockeada: `_meli_change_get` sirve el JSON por path.
Casos:
  - 2000553234638327 (reclamo 5759242653, orden original 2000214454182585): cambio VENCIDO.
  - 2000237645213616 (original 2000495284482240): FULL, return ENTREGADO.
  - 2000122963381564 (original 2000324725753585): return ENTREGADO; las 10 originales de cliente B son FULL,
    asi que el caso NO-FULL es VARIANTE de este payload con logistic_type=cross_docking (marcado en el test).
  - 2000301642313281: el GET del return dio 429 => no se decide a ciegas.
"""
import json
import os
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from ..models import change as C

_FX = json.load(open(os.path.join(os.path.dirname(__file__), "data", "meli_change_cliente_b.json")))["cases"]


class _FakeMeli:
    access_token = "TEST"

    def need_login(self):
        return False


@tagged("post_install", "-at_install", "meli_26332")
class TestCambiosProductoPuro(TransactionCase):
    """Funciones puras contra los 10 casos reales."""

    def test_tag_change_no_confunde_no_add_tag_change(self):
        for oid, c in _FX.items():
            self.assertTrue(C.meli_change_has_tag(c["new_order"]["tags"]), oid)
            self.assertTrue(C.meli_change_has_tag(str(c["new_order"]["tags"])), oid)
            # la ORIGINAL trae 'no_add_tag_change' y NO es un cambio
            self.assertFalse(C.meli_change_has_tag(c["orig_order"]["tags"]), oid)
            self.assertFalse(C.meli_change_has_tag(str(c["orig_order"]["tags"])), oid)

    def test_vinculo_resuelto_en_los_10(self):
        for oid, c in _FX.items():
            link = C.meli_change_find_link(oid, c["changes"])
            self.assertTrue(link, oid)
            self.assertEqual(link["orig_order_id"], str(c["orig_order"]["id"]), oid)
        link = C.meli_change_find_link("2000706551143353", _FX["2000706551143353"]["changes"])
        self.assertEqual((link["claim_id"], link["type"], link["return_id"]), ("5545233832", "replace", "164015208"))
        self.assertEqual(C.meli_change_outcome(link), "closed")

    def test_resultado_vs_plata_de_ml(self):
        """Exitoso => ML cancela la ORIGINAL y la nueva queda paid; vencido => al reves."""
        for oid, c in _FX.items():
            out = C.meli_change_outcome(C.meli_change_find_link(oid, c["changes"]))
            if out == "delivered":
                self.assertEqual(c["orig_order"]["status"], "cancelled", oid)
            elif out == "closed":
                self.assertEqual(c["orig_order"]["status"], "paid", oid)
                self.assertEqual(c["new_order"]["status"], "cancelled", oid)

    def test_return_429_es_desconocido_no_negativo(self):
        ret = _FX["2000393090469383"]["returns"]
        self.assertIsNone(C.meli_change_return_status(ret))
        self.assertIsNone(C.meli_change_return_is_total(ret, "2000090263827142"))

    def test_return_total(self):
        c = _FX["2000042362327525"]
        self.assertEqual(C.meli_change_return_status(c["returns"]), "delivered")
        self.assertTrue(C.meli_change_return_is_total(c["returns"], "2000947363495130", {"MLM1111022880": 1}))
        self.assertFalse(C.meli_change_return_is_total(c["returns"], "2000947363495130",
                                                       {"MLM1111022880": 1, "MLM999": 1}))


@tagged("post_install", "-at_install", "meli_26332")
class TestCambiosProducto(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.co = cls.env.company
        cls.wh = cls.env["stock.warehouse"].search([("company_id", "=", cls.co.id)], limit=1)
        cls.cust = cls.env["res.partner"].create({"name": "Comprador ML 26332"})
        cls.co.mercadolibre_return_mode = "done"
        if "mercadolibre_notification_mode" in cls.co._fields:
            cls.co.mercadolibre_notification_mode = "internal_note"
        cls.ICP = cls.env["ir.config_parameter"].sudo()
        cls.ICP.set_param("meli_oerp.cancel_return_full", "")
        cls.SO = cls.env["sale.order"]
        cls.MO = cls.env["mercadolibre.orders"]

    def setUp(self):
        super().setUp()
        self.fail_returns = set()
        test = self

        def fake_get(meli, path):
            for oid, c in _FX.items():
                buyer = str(c["new_order"]["buyer_id"])
                if path.endswith("player_user_id=%s" % buyer):
                    return c["claims_search"]
                for cid, cj in c["changes"].items():
                    if path == "/post-purchase/v1/claims/%s/changes" % cid:
                        return cj
                    if path == "/post-purchase/v2/claims/%s/returns" % cid:
                        if cid in test.fail_returns:
                            return {"_http_error": 429}
                        return c["returns"]
            return {"_http_error": 404}

        p = patch.object(type(self.MO), "_meli_change_get", staticmethod(fake_get))
        p.start()
        self.addCleanup(p.stop)

    # ------------------------------------------------------------- helpers --
    def _prod(self, sku):
        Product = self.env["product.product"]
        pvals = {"name": sku, "default_code": sku, "list_price": 100.0, "invoice_policy": "order"}
        if "is_storable" in Product._fields:
            pvals.update(type="consu", is_storable=True)
        elif "detailed_type" in Product._fields:
            pvals.update(detailed_type="product")
        else:
            pvals.update(type="product")
        prod = Product.create(pvals)
        self.env["stock.quant"]._update_available_quantity(prod, self.wh.lot_stock_id, 10)
        return prod

    def _venta(self, oj, state, deliver=True):
        """Venta + orden ML como las deja la importacion (state 'sale' o 'cancel', OUT done)."""
        buyer = self.env["mercadolibre.buyers"].search([("buyer_id", "=", str(oj["buyer_id"]))], limit=1) or \
            self.env["mercadolibre.buyers"].create({"name": "B %s" % oj["buyer_id"], "buyer_id": str(oj["buyer_id"])})
        it = oj["items"][0]
        prod = self.env["product.product"].search([("default_code", "=", it["sku"])], limit=1) or self._prod(it["sku"])
        vals = {"partner_id": self.cust.id, "meli_order_id": str(oj["id"]),
                "order_line": [(0, 0, {"product_id": prod.id, "product_uom_qty": it["quantity"],
                                       "price_unit": it["unit_price"]})]}
        if oj.get("logistic_type"):
            vals["meli_shipment_logistic_type"] = oj["logistic_type"]
        so = self.SO.create(vals)
        so.action_confirm()
        if deliver:
            for pk in so.picking_ids:
                so._meli_validate_picking(pk)
        mo = self.MO.create({"name": "Orden %s" % oj["id"], "order_id": str(oj["id"]), "pack_id": str(oj.get("pack_id") or ""),
                             "status": oj["status"] if oj["status"] in ("paid", "cancelled") else False,
                             "tags": str(oj["tags"]), "buyer": buyer.id, "sale_order": so.id,
                             "company_id": self.co.id})
        self.env["mercadolibre.order_items"].create({"order_id": mo.id, "order_item_id": it["item_id"],
                                                    "quantity": it["quantity"], "product_id": prod.id})
        if state == "cancel":
            so.with_context(disable_cancel_warning=True)._action_cancel()
        return so, mo, prod

    def _par(self, oid, orig_state, new_state, orig_logistic=None):
        c = _FX[oid]
        oj = dict(c["orig_order"], logistic_type=orig_logistic) if orig_logistic else c["orig_order"]
        orig_so, orig_mo, prod = self._venta(oj, orig_state)
        new_so, new_mo, _ = self._venta(c["new_order"], new_state)
        return orig_so, new_so, new_mo, prod

    def _returns(self, so):
        return self.env["stock.move"].search([
            ("origin_returned_move_id", "in", so.picking_ids.mapped("move_ids").ids),
            ("state", "!=", "cancel")]).mapped("picking_id")

    def _msgs(self, so, needle):
        return self.env["mail.message"].search_count([("model", "=", "sale.order"), ("res_id", "=", so.id),
                                                      ("body", "ilike", needle)])

    def _amounts(self, *sos):
        return [(s.amount_total, tuple(s.order_line.mapped("price_unit"))) for s in sos]

    # --------------------------------------------------------------- casos --
    def test_01_caso_5582489788_vencido(self):
        """orden 2000214454182585 -> 2000553234638327 (vencido): vincula, no mueve stock, no toca importes."""
        orig_so, new_so, new_mo, prod = self._par("2000706551143353", "sale", "cancel")
        before = self._amounts(orig_so, new_so)
        n = new_mo.meli_change_sync(meli=_FakeMeli())
        self.assertEqual(n, 1)
        self.assertEqual(new_mo.meli_change_state, "closed")
        self.assertEqual(new_mo.meli_change_claim_id, "5545233832")
        self.assertEqual(new_mo.meli_change_origin_order_id, "2000459505421451")
        self.assertEqual(new_mo.meli_change_return_id, "164015208")
        self.assertEqual(new_so.meli_change_origin_sale_id, orig_so)
        self.assertIn(new_so, orig_so.meli_change_replacement_ids)
        self.assertFalse(self._returns(orig_so))
        self.assertEqual(orig_so.state, "sale")
        self.assertEqual(self._amounts(orig_so, new_so), before)
        self.assertEqual(self._msgs(orig_so, "5545233832"), 2)  # vinculo + vencido

    def test_02_full_entregado_sin_parametro_respeta_full(self):
        orig_so, new_so, new_mo, prod = self._par("2000042362327525", "cancel", "sale")
        before = self._amounts(orig_so, new_so)
        new_mo.meli_change_sync(meli=_FakeMeli())
        self.assertEqual(new_mo.meli_change_state, "done")
        self.assertEqual(new_mo.meli_change_return_status, "delivered")
        self.assertFalse(self._returns(orig_so), "FULL sin cancel_return_full: no hay reingreso (politica vigente)")
        self.assertEqual(self._msgs(orig_so, "No se registró reingreso"), 1)
        self.assertEqual(self._amounts(orig_so, new_so), before)

    def test_03_full_entregado_con_parametro_reingresa_y_es_idempotente(self):
        self.ICP.set_param("meli_oerp.cancel_return_full", "1")
        orig_so, new_so, new_mo, prod = self._par("2000042362327525", "cancel", "sale")
        before = self._amounts(orig_so, new_so)
        new_mo.meli_change_sync(meli=_FakeMeli())
        rets = self._returns(orig_so)
        self.assertEqual(len(rets), 1)
        self.assertEqual(rets.state, "done")
        self.assertEqual(self._msgs(orig_so, "Reingreso del artículo"), 1)
        # re-sync: ya no es candidato, y forzado tampoco duplica
        self.assertNotIn(new_mo, self.MO._meli_change_candidates())
        new_mo.meli_change_state = "linked"
        new_mo.meli_change_sync(meli=_FakeMeli())
        self.assertEqual(len(self._returns(orig_so)), 1)
        self.assertEqual(self._msgs(orig_so, "Reingreso del artículo"), 1)
        self.assertEqual(self._msgs(orig_so, "el comprador cambió el artículo"), 1)
        self.assertEqual(self._amounts(orig_so, new_so), before)

    def test_04_no_full_entregado_reingresa(self):
        # VARIANTE: payload real, logistica de la original cambiada a no-FULL (cliente B no tiene un caso asi).
        orig_so, new_so, new_mo, prod = self._par("2000020658320246", "cancel", "sale", orig_logistic="cross_docking")
        self.assertFalse(orig_so.is_meli_order_fulfillment())
        new_mo.meli_change_sync(meli=_FakeMeli())
        rets = self._returns(orig_so)
        self.assertEqual(len(rets), 1)
        self.assertEqual(rets.state, "done")
        self.assertEqual(new_mo.meli_change_state, "done")

    def test_05_return_429_no_decide(self):
        self.ICP.set_param("meli_oerp.cancel_return_full", "1")
        orig_so, new_so, new_mo, prod = self._par("2000393090469383", "cancel", "sale")
        new_mo.meli_change_sync(meli=_FakeMeli())
        self.assertEqual(new_mo.meli_change_state, "linked")
        self.assertFalse(self._returns(orig_so))
        self.assertIn(new_mo, self.MO._meli_change_candidates())

    def test_06_original_no_es_candidata_y_cron_procesa(self):
        orig_so, new_so, new_mo, prod = self._par("2000706551143353", "sale", "cancel")
        orig_mo = self.MO.search([("order_id", "=", "2000459505421451")])
        cands = self.MO._meli_change_candidates()
        self.assertIn(new_mo, cands)
        self.assertNotIn(orig_mo, cands)
        with patch.object(type(self.MO), "_meli_change_meli", lambda s: _FakeMeli()):
            self.MO.cron_meli_change_sync()
        self.assertEqual(new_mo.meli_change_state, "closed")
