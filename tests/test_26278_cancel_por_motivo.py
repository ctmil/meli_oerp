# -*- coding: utf-8 -*-
"""26.278 (#624) -- politica de cancelacion por MOTIVO (meli_oerp.cancel_reason_policy=by_reason).

Casos A-F tal como los especifico la clienta y como se MIDIERON en sus ventas reales (22-oct-2026):
el codigo de ML no separa B/F ni D/E; los separa payments[].status_detail (bpp_covered = ML le
pago la venta al vendedor). La tabla pura esta en tests/test_cancel_decision_pure.py.

La red se mockea en sale.order._meli_cancel_fetch (unico GET). Se mide lo que queda en Odoo:
estado de la venta, devoluciones, marca de venta cubierta, actividad y filtro de pendientes.
"""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

ORDER_ID = "2000099990001"


class _FakeMeli:
    access_token = "TEST"
    needlogin_state = False


def _oj(code, details=None, oid=ORDER_ID, pack_id=None):
    pays = [{"id": 1, "status": "refunded", "status_detail": d, "transaction_amount": 200.0,
             "total_paid_amount": 200.0, "transaction_amount_refunded": 200.0} for d in (details or [])]
    return {"id": int(oid), "status": "cancelled", "pack_id": pack_id,
            "cancel_detail": {"code": code, "requested_by": "meli"}, "payments": pays}


@tagged("post_install", "-at_install", "meli_26278")
class TestCancelPorMotivo(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.co = cls.env.company
        cls.wh = cls.env["stock.warehouse"].search([("company_id", "=", cls.co.id)], limit=1)
        cls.cust = cls.env["res.partner"].create({"name": "Comprador ML 624"})
        cls.co.mercadolibre_return_mode = "done"
        cls.co.mercadolibre_invoice_cancel_mode = "manual"
        cls.co.mercadolibre_cancel_mode = "legacy"
        if "mercadolibre_cancel_auto_from" in cls.co._fields:
            cls.co.mercadolibre_cancel_auto_from = False
        if "mercadolibre_notification_mode" in cls.co._fields:
            cls.co.mercadolibre_notification_mode = "internal_note"
        cls.ICP = cls.env["ir.config_parameter"].sudo()
        cls.ICP.set_param("meli_oerp.cancel_reason_policy", "by_reason")
        cls.ICP.set_param("meli_oerp.cancel_return_full", "")
        cls.SO = cls.env["sale.order"]

    def setUp(self):
        super().setUp()
        self.photo = None
        self.calls = []
        test = self

        def fake_fetch(so_self, meli, path):
            test.calls.append(path)
            if path.startswith("/orders/") and test.photo is not None:
                return test.photo
            return {"error": "not_found", "status": 404}

        p = patch.object(type(self.SO), "_meli_cancel_fetch", fake_fetch)
        p.start()
        self.addCleanup(p.stop)

    # -------------------------------------------------------------- helpers --
    def _prod(self):
        Product = self.env["product.product"]
        pvals = {"name": "P-624", "list_price": 100.0, "invoice_policy": "order"}
        if "is_storable" in Product._fields:
            pvals.update(type="consu", is_storable=True)
        elif "detailed_type" in Product._fields:
            pvals.update(detailed_type="product")
        else:
            pvals.update(type="product")
        prod = Product.create(pvals)
        self.env["stock.quant"]._update_available_quantity(prod, self.wh.lot_stock_id, 50)
        return prod

    def _mkso(self, prod=None, oid=ORDER_ID, deliver=True, logistic=None):
        prod = prod or self._prod()
        vals = {"partner_id": self.cust.id, "meli_order_id": oid, "meli_status": "cancelled",
                "order_line": [(0, 0, {"product_id": prod.id, "product_uom_qty": 2, "price_unit": 100})]}
        if logistic:
            vals["meli_shipment_logistic_type"] = logistic
        so = self.SO.create(vals)
        so.action_confirm()
        if deliver:
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

    def _review(self, so):
        return so.activity_ids.filtered(lambda a: a.summary == "Revisar cancelación de MercadoLibre")

    def _pending(self, so):
        return self.SO.search_count([("id", "=", so.id), ("meli_order_id", "!=", False),
                                     ("meli_status", "=", "cancelled"), ("state", "!=", "cancel"),
                                     ("meli_cancel_covered", "=", False)])

    # ---------------------------------------------------------------- A-F --
    def test_a_buyer_cancel_express_cancela_y_devuelve(self):
        so, prod = self._mkso()
        self.assertEqual(self._qty(prod), 48)
        self.assertTrue(self._cancel(so, _oj("buyer_cancel_express", ["bpp_refunded"])))
        self.assertEqual(so.state, "cancel")
        self.assertEqual(self._returns(so).mapped("state"), ["done"])
        self.assertEqual(self._qty(prod), 50)

    def test_b_shipment_not_delivered_reintegrado_cancela_y_devuelve(self):
        so, prod = self._mkso()
        self.assertTrue(self._cancel(so, _oj("shipment_not_delivered", ["bpp_refunded"])))
        self.assertEqual(so.state, "cancel")
        self.assertEqual(self._returns(so).mapped("state"), ["done"])
        self.assertEqual(self._qty(prod), 50)
        self.assertFalse(so.meli_cancel_return_skipped)

    def test_f_shipment_not_delivered_cubierto_es_venta_concretada(self):
        so, prod = self._mkso()
        self.assertFalse(self._cancel(so, _oj("shipment_not_delivered", ["bpp_covered"])))
        self.assertNotEqual(so.state, "cancel")
        self.assertTrue(so.meli_cancel_covered)
        self.assertFalse(self._returns(so))
        self.assertEqual(self._qty(prod), 48)
        self.assertEqual(self._pending(so), 0, "una venta cubierta no queda en 'Canceladas pendientes'")
        self.assertFalse(so.meli_cancel_pending_banner)

    def test_e_mediacion_cubierta_es_venta_concretada(self):
        so, prod = self._mkso()
        self.assertFalse(self._cancel(so, _oj("mediations", ["bpp_covered"])))
        self.assertNotEqual(so.state, "cancel")
        self.assertTrue(so.meli_cancel_covered)
        self.assertFalse(self._returns(so))

    def test_d_mediacion_reintegrada_cancela_y_devolucion_sin_validar_con_actividad(self):
        so, prod = self._mkso()
        self.assertTrue(self._cancel(so, _oj("mediations", ["bpp_refunded"])))
        self.assertEqual(so.state, "cancel")
        rets = self._returns(so)
        self.assertEqual(len(rets), 1)
        self.assertNotIn(rets.state, ("done", "cancel"), "la devolucion queda SIN validar y viva")
        self.assertEqual(self._qty(prod), 48, "sin validar: el stock todavia no volvio")
        self.assertEqual(len(self._review(so)), 1)
        self.assertTrue(so.meli_cancel_review_scheduled)

    def _pack_split(self, twin_deliver=True, with_twin=True):
        prod = self._prod()
        so, _ = self._mkso(prod=prod, oid="2000099990011")
        twin = self.SO
        MO = self.env["mercadolibre.orders"]
        buyer = self.env["mercadolibre.buyers"].create({"name": "Comprador 624", "buyer_id": "650423053"})
        mo1 = MO.create({"order_id": "2000099990011", "pack_id": "2000014788491255", "status": "cancelled",
                         "buyer": buyer.id, "date_created": "2026-08-31 05:08:18", "sale_order": so.id})
        self.env["mercadolibre.order_items"].create({"order_id": mo1.id, "order_item_id": "MLM1922940117"})
        if with_twin:
            twin, _ = self._mkso(prod=prod, oid="2000099990012", deliver=twin_deliver)
            twin.meli_status = "paid"
            mo2 = MO.create({"order_id": "2000099990012", "pack_id": "2000014788999259", "status": "paid",
                             "buyer": buyer.id, "date_created": "2026-08-31 07:33:25", "sale_order": twin.id})
            self.env["mercadolibre.order_items"].create({"order_id": mo2.id, "order_item_id": "MLM1922940117"})
        so.meli_orders = [(6, 0, mo1.ids)]
        return so, twin, prod

    def test_c_pack_splitted_gemela_con_salida_propia_devuelve(self):
        """26.288: la gemela trae su propia salida hecha => devolver la de la cancelada (si no, doble salida)."""
        so, twin, prod = self._pack_split(twin_deliver=True)
        self.assertEqual(so._meli_pack_splitted_twins(), twin)
        self.assertEqual(self._qty(prod), 46, "doble salida antes de procesar")
        self.assertTrue(self._cancel(so, _oj("pack_splitted", ["by_admin"], oid="2000099990011")))
        self.assertEqual(so.state, "cancel")
        self.assertEqual(self._returns(so).mapped("state"), ["done"])
        self.assertEqual(self._qty(prod), 48, "queda una sola salida: la de la gemela")
        self.assertIn(twin.name, so.meli_cancel_decision)
        twin_out = twin.picking_ids.filtered(lambda p: p.picking_type_code == "outgoing")
        self.assertIn(twin_out.name, so.meli_cancel_decision)

    def test_c_pack_splitted_gemela_sin_salida_no_devuelve(self):
        so, twin, prod = self._pack_split(twin_deliver=False)
        self.assertFalse(self._cancel(so, _oj("pack_splitted", ["by_admin"], oid="2000099990011")))
        self.assertNotEqual(so.state, "cancel")
        self.assertFalse(self._returns(so))
        self.assertIn(twin.name, so.meli_cancel_decision)
        self.assertEqual(len(self._review(so)), 1)

    def test_c_pack_splitted_sin_gemela_no_devuelve(self):
        so, twin, prod = self._pack_split(with_twin=False)
        self.assertFalse(self._cancel(so, _oj("pack_splitted", ["by_admin"], oid="2000099990011")))
        self.assertNotEqual(so.state, "cancel")
        self.assertFalse(self._returns(so))
        self.assertIn("no se encontró la venta gemela", so.meli_cancel_decision)
        self.assertEqual(len(self._review(so)), 1)

    # ------------------------------------------------- dato de pago y red --
    def test_ambiguo_sin_order_json_lee_la_foto_y_detecta_cubierta(self):
        so, prod = self._mkso()
        so.meli_cancel_reason_code = "mediations"
        self.photo = _oj("mediations", ["bpp_covered"])
        self.assertFalse(self._cancel(so))
        self.assertTrue(so.meli_cancel_covered)
        self.assertTrue(any(c.startswith("/orders/") for c in self.calls))
        # Segunda pasada del cron: corta sin red.
        self.calls[:] = []
        self.assertFalse(self._cancel(so))
        self.assertEqual(self.calls, [])

    def test_ambiguo_sin_foto_no_acciona(self):
        so, prod = self._mkso()
        so.meli_cancel_reason_code = "shipment_not_delivered"
        self.photo = None   # GET falla
        self.assertFalse(self._cancel(so))
        self.assertNotEqual(so.state, "cancel")
        self.assertFalse(so.meli_cancel_covered)
        self.assertFalse(self._returns(so))

    def test_ambiguo_sin_pagos_queda_en_revision(self):
        so, prod = self._mkso()
        self.assertFalse(self._cancel(so, _oj("mediations", [])))
        self.assertNotEqual(so.state, "cancel")
        self.assertFalse(self._returns(so))
        self.assertEqual(len(self._review(so)), 1)

    # ------------------------------------------------------------- FULL --
    def test_full_sin_parametro_no_devuelve(self):
        so, prod = self._mkso(logistic="fulfillment")
        self.assertTrue(self._cancel(so, _oj("buyer_cancel_express", ["bpp_refunded"])))
        self.assertEqual(so.state, "cancel")
        self.assertFalse(self._returns(so))

    def test_full_con_parametro_devuelve_a_la_ubicacion_de_origen(self):
        self.ICP.set_param("meli_oerp.cancel_return_full", "1")
        so, prod = self._mkso(logistic="fulfillment")
        self.assertTrue(self._cancel(so, _oj("buyer_cancel_express", ["bpp_refunded"])))
        rets = self._returns(so)
        self.assertEqual(rets.mapped("state"), ["done"])
        self.assertEqual(rets.location_dest_id, so.picking_ids.filtered(
            lambda p: p.picking_type_code == "outgoing").location_id)

    # ------------------------------------------------ politica apagada --
    def test_politica_apagada_comportamiento_de_siempre(self):
        self.ICP.set_param("meli_oerp.cancel_reason_policy", "")
        so, prod = self._mkso()
        self.assertTrue(self._cancel(so, _oj("mediations", ["bpp_covered"])))
        self.assertEqual(so.state, "cancel", "sin la politica, una mediacion cubierta se cancela como antes")
        self.assertFalse(so.meli_cancel_covered)
        self.assertFalse(self._returns(so), "mediations fuera de cancel_return_reasons: sin devolucion")
        self.assertTrue(so.meli_cancel_return_skipped)
