# -*- coding: utf-8 -*-
"""Tabla de casos de la decision de cancelacion `por_estado_ml` — SIN Odoo.

Correr:  python3 meli_oerp/tests/test_cancel_decision_pure.py   (desde la raiz de addons)
(`python3 -m unittest tests/...` NO: importaria tests/__init__.py, que importa odoo).

NO esta en tests/__init__.py a proposito: carga models/cancel_decision.py por ruta para no
importar el paquete del modulo (que importa odoo). Los casos de integracion con Odoo estan en
tests/test_cancel_por_estado_ml.py.
"""
import importlib.util
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "meli_cancel_decision", os.path.join(_HERE, "..", "models", "cancel_decision.py"))
cd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cd)


def order(status="cancelled", payments=None, code="buyer_regretted", pack_id=None, oid=2000001):
    return {"id": oid, "status": status, "pack_id": pack_id,
            "cancel_detail": {"code": code, "requested_by": "buyer"},
            "payments": payments if payments is not None else []}


def pay(status, amount=230.0, refunded=0.0, pid=1):
    return {"id": pid, "status": status, "transaction_amount": amount, "total_paid_amount": amount,
            "transaction_amount_refunded": refunded}


def ship(status, substatus=None, logistic="cross_docking", shipped=False, sid=4000001):
    return {"id": sid, "status": status, "substatus": substatus, "logistic_type": logistic,
            "status_history": {"date_shipped": "2026-09-20T10:00:00Z" if shipped else None}}


REFUND = [pay("refunded", 230.0, 230.0)]
APPROVED = [pay("approved", 230.0, 0.0)]
DEAD = [pay("cancelled", 230.0, 0.0)]
PARTIAL = [pay("approved", 230.0, 100.0)]
MEDIATION = [pay("in_mediation", 230.0, 0.0)]

CFG = {"return_mode": "done", "invoice_cancel_mode": "manual", "tolerance": 1.0}

ODOO_OUT_DONE_POSTED = {"out_done": True, "posted_total": 230.0, "has_posted": True, "has_draft": False}
ODOO_OUT_DONE_NOINV = {"out_done": True, "posted_total": 0.0, "has_posted": False, "has_draft": False}
ODOO_NOT_DELIVERED = {"out_done": False, "posted_total": 0.0, "has_posted": False, "has_draft": False}
ODOO_DRAFT_INV = {"out_done": False, "posted_total": 0.0, "has_posted": False, "has_draft": True}

# (nombre, pagos, envio, odoo_state, config) -> (goods, invoice, cancel_drafts, nc_amount, so, waiting)
TABLE = [
    ("01 nunca salio, reintegrado, OUT done + factura",
     REFUND, ship("ready_to_ship"), ODOO_OUT_DONE_POSTED, CFG,
     ("return", "credit_note", False, 230.0, "cancel", False)),
    ("02 nunca salio, reintegrado, sin entregar ni facturar",
     REFUND, ship("handling"), ODOO_NOT_DELIVERED, CFG,
     ("none", "none", False, 0.0, "cancel", False)),
    ("03 en transito (shipped), reintegrado => ESPERAR, NC igual",
     REFUND, ship("shipped", shipped=True), ODOO_OUT_DONE_POSTED, CFG,
     ("wait", "credit_note", False, 230.0, "hold", True)),
    ("04 volviendo al vendedor => ESPERAR",
     REFUND, ship("not_delivered", "returning_to_sender", shipped=True), ODOO_OUT_DONE_NOINV, CFG,
     ("wait", "none", False, 0.0, "hold", True)),
    ("05 volvio (returned) => devolucion + NC",
     REFUND, ship("not_delivered", "returned", shipped=True), ODOO_OUT_DONE_POSTED, CFG,
     ("return", "credit_note", False, 230.0, "cancel", False)),
    ("06 entregado sin devolucion fisica => sin stock, NC por lo reintegrado",
     REFUND, ship("delivered", shipped=True), ODOO_OUT_DONE_POSTED, CFG,
     ("none", "credit_note", False, 230.0, "cancel", False)),
    ("07 FULL => ML gestiona el stock",
     REFUND, ship("shipped", logistic="fulfillment", shipped=True), ODOO_OUT_DONE_POSTED, CFG,
     ("none", "credit_note", False, 230.0, "cancel", False)),
    ("08 pack_splitted: aprobado sin reintegro, facturado => manual, venta abierta",
     APPROVED, ship("ready_to_ship"), ODOO_OUT_DONE_POSTED, CFG,
     ("none", "manual", False, 0.0, "hold", False)),
    ("09 pack_splitted: aprobado sin reintegro, nada hecho => se cancela la venta",
     APPROVED, ship("ready_to_ship"), ODOO_NOT_DELIVERED, CFG,
     ("none", "none", False, 0.0, "cancel", False)),
    ("10 nunca acreditado, factura borrador => cancelar borrador",
     DEAD, ship("pending"), ODOO_DRAFT_INV, CFG,
     ("none", "none", True, 0.0, "cancel", False)),
    ("11 nunca acreditado, factura publicada => NC total",
     DEAD, ship("cancelled"), ODOO_OUT_DONE_POSTED, CFG,
     ("return", "credit_note", False, 230.0, "cancel", False)),
    ("12 sin pagos (paid 0) y sin envio => mercaderia segun config",
     [], None, ODOO_NOT_DELIVERED, CFG,
     ("config", "none", False, 0.0, "cancel", False)),
    ("13 reintegro PARCIAL => factura manual + aviso, venta abierta",
     PARTIAL, ship("ready_to_ship"), ODOO_OUT_DONE_POSTED, CFG,
     ("return", "manual", False, 100.0, "hold", False)),
    ("14 pago en mediacion => factura segun config",
     MEDIATION, ship("delivered", shipped=True), ODOO_OUT_DONE_POSTED, CFG,
     ("none", "config", False, 0.0, "cancel", False)),
    ("15 envio con estado desconocido => mercaderia segun config",
     REFUND, ship("weird_new_status"), ODOO_OUT_DONE_NOINV, CFG,
     ("config", "none", False, 0.0, "cancel", False)),
    ("16 envio cancelado DESPUES de despachado => desconocido => config",
     REFUND, ship("cancelled", shipped=True), ODOO_OUT_DONE_NOINV, CFG,
     ("config", "none", False, 0.0, "cancel", False)),
    ("17 nunca salio pero return_mode=none => sin devolucion",
     REFUND, ship("ready_to_ship"), ODOO_OUT_DONE_NOINV, dict(CFG, return_mode="none"),
     ("none", "none", False, 0.0, "cancel", False)),
    ("18 reintegro 229.50 sobre 230 (tolerancia 1) => NC total",
     [pay("refunded", 230.0, 229.5)], ship("ready_to_ship"), ODOO_OUT_DONE_POSTED, CFG,
     ("return", "credit_note", False, 230.0, "cancel", False)),
    ("19 factura YA revertida (posted_total 0) + reintegro => nada que facturar, se cancela",
     REFUND, ship("ready_to_ship"), dict(ODOO_OUT_DONE_NOINV, reversed=True), CFG,
     ("return", "none", False, 0.0, "cancel", False)),
    ("20 refunded sin transaction_amount_refunded => toma el monto entero",
     [{"id": 9, "status": "refunded", "transaction_amount": 230.0}], ship("ready_to_ship"),
     ODOO_OUT_DONE_POSTED, CFG,
     ("return", "credit_note", False, 230.0, "cancel", False)),
]


class TestCancelDecisionTable(unittest.TestCase):

    def test_table(self):
        for name, pays, sj, ostate, cfg, expected in TABLE:
            with self.subTest(name):
                ctx = cd.build_cancel_context([order(payments=pays)], sj, sj and sj["id"])
                self.assertTrue(ctx["ok"], ctx["missing"])
                d = cd.meli_cancel_decide(ctx, ostate, cfg)
                got = (d["goods"], d["invoice"], d["cancel_drafts"], d["nc_amount"], d["so"], d["waiting_return"])
                self.assertEqual(got, expected, "%s\n%s" % (name, d["text"]))
                self.assertIn("fila:", d["text"])

    def test_not_cancelled_anymore_skips(self):
        ctx = cd.build_cancel_context([order(status="paid", payments=APPROVED)], ship("ready_to_ship"), 4000001)
        d = cd.meli_cancel_decide(ctx, ODOO_OUT_DONE_POSTED, CFG)
        self.assertEqual((d["goods"], d["invoice"], d["so"]), ("none", "none", "skip"))

    def test_incomplete_photo_is_not_ok(self):
        # /orders con error
        ctx = cd.build_cancel_context([{"error": "not_found", "message": "Order not found", "status": 404}], None, None)
        self.assertFalse(ctx["ok"])
        # /orders sin payments
        ctx = cd.build_cancel_context([{"id": 1, "status": "cancelled"}], None, None)
        self.assertFalse(ctx["ok"])
        # se esperaba envio y /shipments fallo (request_exception del cliente HTTP)
        ctx = cd.build_cancel_context([order(payments=REFUND)],
                                      {"error": "get error", "status": 0, "cause": "request_exception"}, 4000001)
        self.assertFalse(ctx["ok"])
        self.assertIn("shipments", ctx["missing"])
        # se esperaba envio y no vino nada
        ctx = cd.build_cancel_context([order(payments=REFUND)], None, 4000001)
        self.assertFalse(ctx["ok"])
        # sin ordenes
        self.assertFalse(cd.build_cancel_context([], None, None)["ok"])

    def test_pack_aggregates_payments_and_status(self):
        o1 = order(payments=[pay("refunded", 100.0, 100.0, pid=1)], oid=1, pack_id=77)
        o2 = order(payments=[pay("refunded", 130.0, 130.0, pid=2)], oid=2, pack_id=77)
        ctx = cd.build_cancel_context([o1, o2], ship("ready_to_ship"), 4000001)
        self.assertEqual(ctx["refunded_amount"], 230.0)
        self.assertEqual(ctx["pack_id"], "77")
        d = cd.meli_cancel_decide(ctx, ODOO_OUT_DONE_POSTED, CFG)
        self.assertEqual((d["invoice"], d["nc_amount"]), ("credit_note", 230.0))
        # una sola orden del pack cancelada => status mixed => no se acciona
        o3 = order(status="paid", payments=APPROVED, oid=3, pack_id=77)
        ctx = cd.build_cancel_context([o1, o3], ship("ready_to_ship"), 4000001)
        self.assertTrue(ctx["status"].startswith("mixed"))
        self.assertEqual(cd.meli_cancel_decide(ctx, ODOO_OUT_DONE_POSTED, CFG)["so"], "skip")

    def test_new_logistic_shape(self):
        sj = {"id": 5, "status": "shipped", "logistic": {"type": "fulfillment"}}
        ctx = cd.build_cancel_context([order(payments=REFUND)], sj, 5)
        self.assertEqual(cd.classify_shipment(ctx["shipment"]), cd.SHIP_FULFILLMENT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
