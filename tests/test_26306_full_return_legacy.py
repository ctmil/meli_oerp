# -*- coding: utf-8 -*-
"""26.306 (#607) -- `meli_oerp.cancel_return_full=1` habilita la devolucion de envios FULL
tambien en el modo legacy, SIN la politica por motivo (`cancel_reason_policy=by_reason`).

Sin el parametro: identico a antes (FULL sin devolucion). Con el parametro siguen mandando
`cancel_return_reasons` (motivos), `pack_splitted` (nunca devuelve en legacy) y el chequeo de
"ya devuelta" (no se duplica, tampoco con by_reason prendido). Red mockeada como en meli_26278.
"""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from .test_26278_cancel_por_motivo import _FakeMeli, _oj


@tagged("post_install", "-at_install", "meli_26306")
class TestFullReturnLegacy(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.co = cls.env.company
        cls.wh = cls.env["stock.warehouse"].search([("company_id", "=", cls.co.id)], limit=1)
        cls.cust = cls.env["res.partner"].create({"name": "Comprador ML 607"})
        cls.co.mercadolibre_return_mode = "done"
        cls.co.mercadolibre_invoice_cancel_mode = "manual"
        cls.co.mercadolibre_cancel_mode = "legacy"
        if "mercadolibre_cancel_auto_from" in cls.co._fields:
            cls.co.mercadolibre_cancel_auto_from = False
        if "mercadolibre_notification_mode" in cls.co._fields:
            cls.co.mercadolibre_notification_mode = "internal_note"
        cls.ICP = cls.env["ir.config_parameter"].sudo()
        cls.ICP.set_param("meli_oerp.cancel_reason_policy", "")
        cls.ICP.set_param("meli_oerp.cancel_return_full", "")
        cls.ICP.set_param("meli_oerp.cancel_return_reasons", "buyer_cancel_express,fraud")
        cls.SO = cls.env["sale.order"]

    def setUp(self):
        super().setUp()
        self.photo = None
        test = self

        def fake_fetch(so_self, meli, path):
            if path.startswith("/orders/") and test.photo is not None:
                return test.photo
            return {"error": "not_found", "status": 404}

        p = patch.object(type(self.SO), "_meli_cancel_fetch", fake_fetch)
        p.start()
        self.addCleanup(p.stop)

    # -------------------------------------------------------------- helpers --
    def _prod(self):
        Product = self.env["product.product"]
        pvals = {"name": "P-607", "list_price": 100.0, "invoice_policy": "order"}
        if "is_storable" in Product._fields:
            pvals.update(type="consu", is_storable=True)
        elif "detailed_type" in Product._fields:
            pvals.update(detailed_type="product")
        else:
            pvals.update(type="product")
        prod = Product.create(pvals)
        self.env["stock.quant"]._update_available_quantity(prod, self.wh.lot_stock_id, 50)
        return prod

    def _mkso(self, oid="2000099960701", logistic="fulfillment"):
        prod = self._prod()
        vals = {"partner_id": self.cust.id, "meli_order_id": oid, "meli_status": "cancelled",
                "order_line": [(0, 0, {"product_id": prod.id, "product_uom_qty": 2, "price_unit": 100})]}
        if logistic:
            vals["meli_shipment_logistic_type"] = logistic
        so = self.SO.create(vals)
        so.action_confirm()
        for pk in so.picking_ids:
            so._meli_validate_picking(pk)
        return so, prod

    def _cancel(self, so, order_json=None):
        return so.with_context(meli_cancel_ctx_nocache=True).meli_cancel_with_detail(
            "Orden cancelada por MercadoLibre. Motivo: test", order_json=order_json, meli=_FakeMeli())

    def _qty(self, prod):
        return prod.with_context(location=self.wh.lot_stock_id.id).qty_available

    def _returns(self, so):
        moves = self.env["stock.move"].search([
            ("origin_returned_move_id", "in", so.picking_ids.mapped("move_ids").ids)])
        return moves.mapped("picking_id")

    def _out(self, so):
        return so.picking_ids.filtered(lambda p: p.picking_type_code == "outgoing" and p.state == "done")

    # ------------------------------------------------------------ casos --
    def test_01_full_legacy_sin_parametro_no_devuelve(self):
        so, prod = self._mkso()
        self.assertTrue(self._cancel(so, _oj("buyer_cancel_express", ["bpp_refunded"])))
        self.assertEqual(so.state, "cancel")
        self.assertFalse(self._returns(so), "sin cancel_return_full: FULL sigue sin devolucion (como antes)")
        self.assertEqual(self._qty(prod), 48)

    def test_02_full_legacy_con_parametro_devuelve_en_hecho(self):
        self.ICP.set_param("meli_oerp.cancel_return_full", "1")
        so, prod = self._mkso()
        out = self._out(so)
        self.assertTrue(self._cancel(so, _oj("buyer_cancel_express", ["bpp_refunded"])))
        self.assertEqual(so.state, "cancel")
        rets = self._returns(so)
        self.assertEqual(rets.mapped("state"), ["done"], "la devolucion FULL nace validada (return_mode=done)")
        self.assertEqual(rets.location_dest_id, out.location_id, "vuelve a la ubicacion de origen (MLF/Existencias)")
        self.assertEqual(self._qty(prod), 50)
        self.assertFalse(so.meli_cancel_return_skipped)

    def test_03_full_legacy_con_parametro_no_duplica(self):
        self.ICP.set_param("meli_oerp.cancel_return_full", "1")
        so, prod = self._mkso()
        self._cancel(so, _oj("buyer_cancel_express", ["bpp_refunded"]))
        so._meli_return_done_pickings()
        self._cancel(so, _oj("buyer_cancel_express", ["bpp_refunded"]))
        self.assertEqual(len(self._returns(so)), 1)
        self.assertEqual(self._qty(prod), 50)

    def test_04_full_legacy_con_parametro_motivo_fuera_de_lista(self):
        self.ICP.set_param("meli_oerp.cancel_return_full", "1")
        so, prod = self._mkso()
        self.assertTrue(self._cancel(so, _oj("mediations", ["bpp_refunded"])))
        self.assertEqual(so.state, "cancel")
        self.assertFalse(self._returns(so), "cancel_return_reasons sigue mandando")
        self.assertTrue(so.meli_cancel_return_skipped)

    def test_05_full_legacy_con_parametro_pack_splitted_sin_devolucion(self):
        self.ICP.set_param("meli_oerp.cancel_return_full", "1")
        self.ICP.set_param("meli_oerp.cancel_return_reasons", "buyer_cancel_express,fraud,pack_splitted")
        so, prod = self._mkso()
        self.assertFalse(self._cancel(so, _oj("pack_splitted", ["bpp_refunded"])))
        self.assertNotEqual(so.state, "cancel", "pack_splitted con salida hecha queda retenida, como antes")
        self.assertFalse(self._returns(so))
        self.assertEqual(self._qty(prod), 48)

    def test_06_by_reason_con_parametro_una_sola_devolucion(self):
        self.ICP.set_param("meli_oerp.cancel_reason_policy", "by_reason")
        self.ICP.set_param("meli_oerp.cancel_return_full", "1")
        so, prod = self._mkso()
        self.assertTrue(self._cancel(so, _oj("buyer_cancel_express", ["bpp_refunded"])))
        self._cancel(so, _oj("buyer_cancel_express", ["bpp_refunded"]))
        rets = self._returns(so)
        self.assertEqual(rets.mapped("state"), ["done"])
        self.assertEqual(len(rets), 1)
        self.assertEqual(self._qty(prod), 50)

    def test_07_no_full_sin_parametro_sin_cambios(self):
        so, prod = self._mkso(logistic="cross_docking")
        self.assertTrue(self._cancel(so, _oj("buyer_cancel_express", ["bpp_refunded"])))
        self.assertEqual(self._returns(so).mapped("state"), ["done"])
        self.assertEqual(self._qty(prod), 50)
