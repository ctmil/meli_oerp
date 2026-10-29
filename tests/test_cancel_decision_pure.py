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


class TestCancelReturnReasons(unittest.TestCase):
    """26.221 (un cliente): que motivos de cancelacion devuelven stock automaticamente."""

    def test_default(self):
        for raw in (None, "", "   "):
            self.assertTrue(cd.cancel_return_allowed("buyer_cancel_express", raw))
            self.assertTrue(cd.cancel_return_allowed("fraud", raw))
            for code in ("pack_splitted", "shipment_not_delivered", "mediations", "buyer_regretted"):
                self.assertFalse(cd.cancel_return_allowed(code, raw), code)

    def test_sin_motivo_no_devuelve(self):
        self.assertFalse(cd.cancel_return_allowed("", None))
        self.assertFalse(cd.cancel_return_allowed(None, "buyer_cancel_express,fraud"))
        self.assertTrue(cd.cancel_return_allowed(None, "*"))

    def test_todos(self):
        for code in ("pack_splitted", "mediations", "cualquiera", ""):
            self.assertTrue(cd.cancel_return_allowed(code, "*"))
        self.assertTrue(cd.cancel_return_allowed("pack_splitted", "fraud, *"))

    def test_lista_configurada(self):
        raw = " Fraud ;pack_splitted\nmediations "
        self.assertEqual(cd.parse_cancel_return_reasons(raw),
                         frozenset(["fraud", "pack_splitted", "mediations"]))
        self.assertTrue(cd.cancel_return_allowed("PACK_SPLITTED", raw))
        self.assertFalse(cd.cancel_return_allowed("buyer_cancel_express", raw))



class TestClassifyCancelReason624(unittest.TestCase):
    """26.278 (#caso-K04): tabla A-F MEDIDA sobre 16 cancelaciones reales etiquetadas por la clienta
    (texto del panel de ML) — status_detail del pago tal como lo devolvio GET /orders/{id}."""

    MEDIDO = [
        # (caso, cancel_detail.code, payments[].status_detail, clase esperada)
        ("A comprador", "buyer_cancel_express", ["bpp_refunded"], cd.REASON_RETURN),
        ("B paquete cancelado por ML", "shipment_not_delivered", ["bpp_refunded"], cd.REASON_RETURN),
        ("C pack dividido", "pack_splitted", ["by_admin"], cd.REASON_PACK_SPLIT),
        ("D devolucion finalizada", "mediations", ["bpp_refunded"], cd.REASON_RETURN_REVIEW),
        ("D descartamos el producto", "mediations", ["bpp_covered"], cd.REASON_COVERED),
        ("E te dimos el dinero", "mediations", ["bpp_covered"], cd.REASON_COVERED),
        ("F paquete no entregado, te reembolsamos", "shipment_not_delivered", ["bpp_covered"], cd.REASON_COVERED),
    ]

    def test_tabla_medida(self):
        for caso, code, details, esperado in self.MEDIDO:
            self.assertEqual(cd.classify_cancel_reason(code, details), esperado, caso)

    def test_ambiguo_sin_dato_de_pago_es_revision(self):
        for code in ("mediations", "shipment_not_delivered"):
            self.assertEqual(cd.classify_cancel_reason(code, None), cd.REASON_REVIEW)
            self.assertEqual(cd.classify_cancel_reason(code, ["", None]), cd.REASON_REVIEW)

    def test_cubierto_gana_aunque_haya_otro_pago(self):
        self.assertEqual(cd.classify_cancel_reason("mediations", ["bpp_refunded", "bpp_covered"]),
                         cd.REASON_COVERED)

    def test_mayusculas_y_espacios(self):
        self.assertEqual(cd.classify_cancel_reason(" Mediations ", [" BPP_COVERED "]), cd.REASON_COVERED)

    def test_otros_motivos_quedan_como_siempre(self):
        for code in ("buyer_regretted", "fraud", "seller_cancelled", "", None):
            self.assertEqual(cd.classify_cancel_reason(code, ["bpp_covered"]), cd.REASON_DEFAULT)

    def test_parametros(self):
        self.assertTrue(cd.cancel_policy_enabled(" By_Reason "))
        for raw in (None, "", "legacy", "1"):
            self.assertFalse(cd.cancel_policy_enabled(raw))
        for raw in ("1", "true", "Si", "on"):
            self.assertTrue(cd.param_is_true(raw))
        for raw in (None, "", "0", "false", "no"):
            self.assertFalse(cd.param_is_true(raw))


class TestLegacyCancelGuard26335(unittest.TestCase):
    """26.335: guarda de entrega / cobro del modo legacy (legacy_cancel_block_reason)."""
    G = staticmethod(cd.legacy_cancel_block_reason)

    def test_envio_entregado_retiene(self):
        self.assertIn("ENTREGADO", self.G({"id": "48242125959", "status": "delivered"}, []))

    def test_envio_entregado_y_vuelto_no_retiene(self):
        self.assertEqual(self.G({"status": "delivered", "substatus": "returned_to_sender"}, []), "")

    def test_envio_cancelado_o_sin_envio_no_retiene(self):
        self.assertEqual(self.G({"status": "cancelled"}, []), "")
        self.assertEqual(self.G(None, None), "")
        self.assertEqual(self.G({"status": "ready_to_ship"}, []), "")

    def test_pago_aprobado_sin_reintegro_retiene(self):
        self.assertIn("acreditado", self.G(None, [{"id": "1", "status": "approved", "refunded": 0.0}]))

    def test_pago_aprobado_con_reintegro_parcial_no_retiene(self):
        self.assertEqual(self.G(None, [{"status": "approved", "refunded": 50.0}]), "")

    def test_pago_cubierto_por_ml_retiene(self):
        self.assertIn("bpp_covered", self.G(None, [{"status": "refunded", "status_detail": "bpp_covered",
                                                     "refunded": 200.0}]))

    def test_pago_reintegrado_o_muerto_no_retiene(self):
        self.assertEqual(self.G(None, [{"status": "refunded", "status_detail": "bpp_refunded", "refunded": 200.0}]), "")
        self.assertEqual(self.G(None, [{"status": "cancelled"}, {"status": "rejected"}]), "")

    def test_pago_local_viejo_no_retiene(self):
        self.assertEqual(self.G(None, [{"status": "approved", "refunded": 0.0, "fresh": False}]), "")

    def test_entregado_gana_aunque_el_pago_este_reintegrado(self):
        self.assertIn("ENTREGADO", self.G({"status": "delivered"}, [{"status": "refunded", "refunded": 230.0}]))

if __name__ == "__main__":
    unittest.main(verbosity=2)
