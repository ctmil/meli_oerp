# -*- coding: utf-8 -*-
"""Cancelaciones de MercadoLibre decididas con una FOTO FRESCA de ML (modo `por_estado_ml`).

MODULO PURO: no importa nada de Odoo ni hace red. Todo lo que hay aca se prueba con
una tabla de casos sin levantar un servidor (tests/test_cancel_decision_pure.py).

Indicacion de diseno de FCA (29-sep-2026, frente 431 TusRefacciones):
    "basar el mapeo de cada tipo de cancelacion a parametros que veas son fundamentales,
     consultando los status actualizados de la orden y pagos y envios de meli ANTES de
     accionar".
Decisiones tomadas el mismo dia (PLAN-2026-09-28-431-...):
    a) la NC va por el monto REINTEGRADO;
    b) envio en transito => ESPERAR el retorno (no devolver al cancelar);
    c) v1 SIN claims/returns: orden + pagos + envio.

Dos funciones:
    build_cancel_context(order_jsons, shipment_json, shipment_expected)
        -> normaliza la foto (dict). Si viene incompleta, ctx["ok"] = False y NO se acciona.
    meli_cancel_decide(ctx, odoo_state, config)
        -> dict con la decision: mercaderia, factura, monto NC, accion sobre la venta y texto.
"""

# ---------------------------------------------------------------- clases de ENVIO --
SHIP_NOT_SHIPPED = "not_shipped"   # nunca salio del deposito
SHIP_IN_TRANSIT = "in_transit"     # esta en el correo (ida o vuelta)
SHIP_RETURNED = "returned"         # volvio al vendedor
SHIP_DELIVERED = "delivered"       # entregado al comprador
SHIP_FULFILLMENT = "fulfillment"   # FULL: el stock lo gestiona ML
SHIP_NONE = "no_shipment"          # la orden no tiene envio de ML (acordar con el vendedor)
SHIP_UNKNOWN = "unknown"

# ---------------------------------------------------------------- clases de PAGO --
PAY_REFUNDED = "refunded"          # hubo reintegro (total o parcial)
PAY_APPROVED = "approved"          # cobrado y SIN reintegro (tipico pack_splitted)
PAY_NEVER = "never_credited"       # nunca se acredito (cancelled / rejected / sin pagos)
PAY_UNKNOWN = "unknown"            # in_mediation, charged_back, pending, in_process...

# ---------------------------------------------------------------- acciones --------
# mercaderia
GOODS_RETURN = "return"            # crear la devolucion (segun mercadolibre_return_mode)
GOODS_WAIT = "wait"                # esperar el retorno: no se devuelve, la venta queda abierta
GOODS_NONE = "none"                # no se toca el stock
GOODS_CONFIG = "config"            # comportamiento configurado (legacy)
# factura
INV_NONE = "none"                  # no hay nada que hacer
INV_CREDIT_NOTE = "credit_note"    # NC total (idempotente, meli_oerp_accounting 26.153+)
INV_MANUAL = "manual"              # no se toca + aviso
INV_CONFIG = "config"              # comportamiento configurado (mercadolibre_invoice_cancel_mode)
# venta
SO_CANCEL = "cancel"
SO_HOLD = "hold"                   # no se cancela (esperando retorno / accion manual)
SO_SKIP = "skip"                   # ML ya no dice "cancelled": no se acciona nada

# Substatus de /shipments que indican el recorrido de VUELTA. Los nombres los define ML y
# cambian sin avisar: un substatus nuevo cae en la clase por STATUS, y si tampoco se
# reconoce el status, en SHIP_UNKNOWN => comportamiento configurado (nunca una accion nueva).
RETURNED_SUBSTATUS = frozenset([
    "returned", "returned_to_warehouse", "returned_to_sender", "returned_to_hub",
    "delivered_to_seller",
])
RETURNING_SUBSTATUS = frozenset([
    "returning_to_sender", "returning_to_hub", "returning_to_warehouse", "return_to_sender",
    "in_return",
])
NOT_SHIPPED_STATUS = frozenset(["pending", "handling", "ready_to_ship"])
IN_TRANSIT_STATUS = frozenset(["shipped", "not_delivered"])

PAY_OK_STATUS = frozenset(["approved", "authorized"])
PAY_DEAD_STATUS = frozenset(["cancelled", "rejected"])


def _f(value):
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _payment_refunded(pay):
    """Monto reintegrado de UN pago. `transaction_amount_refunded` es el dato; si el pago
    viene `refunded` sin ese campo, se toma el monto entero (reintegro total)."""
    refunded = _f(pay.get("transaction_amount_refunded"))
    if not refunded and (pay.get("status") == "refunded"):
        refunded = _f(pay.get("total_paid_amount")) or _f(pay.get("transaction_amount"))
    return refunded


def build_cancel_context(order_jsons, shipment_json=None, shipment_expected=None):
    """Normaliza la foto fresca de ML.

    :param order_jsons: lista de respuestas de GET /orders/{id} (una por orden de la
        venta; un pack puede tener varias). Una respuesta con "error" o sin "id"/"status"
        vuelve la foto INCOMPLETA.
    :param shipment_json: respuesta de GET /shipments/{id}, o None si la orden no tiene envio.
    :param shipment_expected: id del envio que se esperaba leer (None = la orden no tiene
        envio de ML). Si se esperaba y no vino, la foto es INCOMPLETA.
    :return: dict. ctx["ok"] False => NO se acciona; ctx["missing"] dice por que.
    """
    ctx = {
        "ok": False, "missing": "",
        "order_ids": [], "status": "", "statuses": [],
        "cancel_code": "", "requested_by": "", "pack_id": "",
        "payments": [], "paid_amount": 0.0, "refunded_amount": 0.0,
        "shipment": None,
    }
    if not order_jsons:
        ctx["missing"] = "sin respuesta de /orders"
        return ctx
    for oj in order_jsons:
        if not isinstance(oj, dict) or oj.get("error") or not oj.get("id") or not oj.get("status"):
            ctx["missing"] = "respuesta de /orders incompleta o con error: %s" % (
                (isinstance(oj, dict) and (oj.get("message") or oj.get("error"))) or "sin id/status")
            return ctx
        if "payments" not in oj:
            ctx["missing"] = "la orden %s vino sin 'payments'" % oj.get("id")
            return ctx
        ctx["order_ids"].append(str(oj["id"]))
        ctx["statuses"].append(oj["status"])
        cd = oj.get("cancel_detail") or {}
        ctx["cancel_code"] = ctx["cancel_code"] or (cd.get("code") or "")
        ctx["requested_by"] = ctx["requested_by"] or (cd.get("requested_by") or "")
        ctx["pack_id"] = ctx["pack_id"] or str(oj.get("pack_id") or "")
        for pay in (oj.get("payments") or []):
            p = {
                "id": str(pay.get("id") or ""),
                "status": pay.get("status") or "",
                "status_detail": pay.get("status_detail") or "",
                "amount": _f(pay.get("total_paid_amount")) or _f(pay.get("transaction_amount")),
                "refunded": _payment_refunded(pay),
            }
            ctx["payments"].append(p)
            if p["status"] not in PAY_DEAD_STATUS:
                ctx["paid_amount"] += p["amount"]
            ctx["refunded_amount"] += p["refunded"]
    statuses = set(ctx["statuses"])
    ctx["status"] = statuses.pop() if len(statuses) == 1 else "mixed(%s)" % ",".join(sorted(set(ctx["statuses"])))

    if shipment_expected:
        sj = shipment_json
        if not isinstance(sj, dict) or sj.get("error") or not sj.get("status"):
            ctx["missing"] = "respuesta de /shipments/%s incompleta o con error: %s" % (
                shipment_expected, (isinstance(sj, dict) and (sj.get("message") or sj.get("error"))) or "sin status")
            return ctx
        logistic = sj.get("logistic_type") or ((sj.get("logistic") or {}).get("type")) or ""
        history = sj.get("status_history") or {}
        ctx["shipment"] = {
            "id": str(sj.get("id") or shipment_expected),
            "status": sj.get("status") or "",
            "substatus": sj.get("substatus") or "",
            "logistic_type": logistic,
            "shipped": bool(history.get("date_shipped")),
        }
    ctx["refunded_amount"] = round(ctx["refunded_amount"], 2)
    ctx["paid_amount"] = round(ctx["paid_amount"], 2)
    ctx["ok"] = True
    return ctx


def classify_shipment(ship):
    if not ship:
        return SHIP_NONE
    if (ship.get("logistic_type") or "") == "fulfillment":
        return SHIP_FULFILLMENT
    st = ship.get("status") or ""
    sub = ship.get("substatus") or ""
    if sub in RETURNED_SUBSTATUS:
        return SHIP_RETURNED
    if st == "delivered":
        return SHIP_DELIVERED
    if sub in RETURNING_SUBSTATUS or st in IN_TRANSIT_STATUS:
        return SHIP_IN_TRANSIT
    if st in NOT_SHIPPED_STATUS:
        return SHIP_NOT_SHIPPED
    if st == "cancelled":
        # Un envio cancelado DESPUES de despachado no dice donde esta la mercaderia.
        return SHIP_UNKNOWN if ship.get("shipped") else SHIP_NOT_SHIPPED
    return SHIP_UNKNOWN


def classify_payments(ctx):
    pays = ctx.get("payments") or []
    if ctx.get("refunded_amount", 0.0) > 0.0:
        return PAY_REFUNDED
    if not pays:
        return PAY_NEVER
    statuses = set(p.get("status") or "" for p in pays)
    if statuses <= PAY_DEAD_STATUS:
        return PAY_NEVER
    if statuses & PAY_OK_STATUS and statuses <= (PAY_OK_STATUS | PAY_DEAD_STATUS):
        return PAY_APPROVED
    return PAY_UNKNOWN


def _money(v):
    return ("%.2f" % _f(v))


GOODS_TEXT = {
    SHIP_NOT_SHIPPED: "el envío nunca salió",
    SHIP_IN_TRANSIT: "el envío está en tránsito",
    SHIP_RETURNED: "el envío volvió al vendedor",
    SHIP_DELIVERED: "el envío fue entregado (sin devolución física informada)",
    SHIP_FULFILLMENT: "envío FULL (el stock lo gestiona MercadoLibre)",
    SHIP_NONE: "la orden no tiene envío de MercadoLibre",
    SHIP_UNKNOWN: "estado de envío no reconocido",
}
PAY_TEXT = {
    PAY_REFUNDED: "pago reintegrado",
    PAY_APPROVED: "pago acreditado SIN reintegro",
    PAY_NEVER: "pago nunca acreditado",
    PAY_UNKNOWN: "estado de pago no reconocido",
}


def meli_cancel_decide(ctx, odoo_state, config):
    """Decide que hacer con una venta que ML informa cancelada. FUNCION PURA.

    :param ctx: foto de build_cancel_context() con ctx["ok"] True.
    :param odoo_state: dict con lo que hay en Odoo:
        out_done (bool)            -- hay una entrega (OUT) en 'done'
        posted_total (float)       -- total de facturas de cliente publicadas SIN revertir
        has_posted (bool)          -- hay facturas publicadas sin revertir
        has_draft (bool)           -- hay facturas en borrador
        reversed (bool)            -- hay facturas ya revertidas por NC publicada
    :param config: dict: return_mode ('none'|'draft'|'done'), invoice_cancel_mode, tolerance.
    :return: dict con claves goods, invoice, cancel_drafts, nc_amount, so, waiting_return,
        row_ship, row_pay, text.
    """
    tol = _f(config.get("tolerance")) or 1.0
    return_mode = config.get("return_mode") or "done"
    out_done = bool(odoo_state.get("out_done"))
    posted_total = _f(odoo_state.get("posted_total"))
    has_posted = bool(odoo_state.get("has_posted"))
    has_draft = bool(odoo_state.get("has_draft"))

    ship_class = classify_shipment(ctx.get("shipment"))
    pay_class = classify_payments(ctx)
    d = {
        "goods": GOODS_NONE, "invoice": INV_NONE, "cancel_drafts": False, "nc_amount": 0.0,
        "so": SO_CANCEL, "waiting_return": False,
        "row_ship": ship_class, "row_pay": pay_class, "notes": [],
    }

    # 0. La foto dice que ya NO esta cancelada (ML la revirtio, o el disparador era viejo).
    if ctx.get("status") != "cancelled":
        d.update(goods=GOODS_NONE, invoice=INV_NONE, so=SO_SKIP)
        d["notes"].append("MercadoLibre informa la orden como '%s', no como cancelada: no se acciona nada"
                          % (ctx.get("status") or "-"))
        d["text"] = _text(ctx, d)
        return d

    # 1. MERCADERIA, por la clase de envio.
    if ship_class == SHIP_FULFILLMENT:
        d["goods"] = GOODS_NONE
    elif ship_class in (SHIP_NOT_SHIPPED, SHIP_RETURNED):
        d["goods"] = GOODS_RETURN if out_done else GOODS_NONE
    elif ship_class == SHIP_IN_TRANSIT:
        d["goods"] = GOODS_WAIT
    elif ship_class == SHIP_DELIVERED:
        d["goods"] = GOODS_NONE
        if out_done:
            d["notes"].append("si la mercadería vuelve por un reclamo, la devolución se gestiona a mano")
    else:  # SHIP_NONE / SHIP_UNKNOWN
        d["goods"] = GOODS_CONFIG
    if d["goods"] == GOODS_RETURN and return_mode == "none":
        d["goods"] = GOODS_NONE
        d["notes"].append("no se crea la devolución por configuración ('No crear devolución')")

    # 2. FACTURA, por la clase de pago.
    if pay_class == PAY_APPROVED:
        # Cobrado y sin reintegro: tipico pack_splitted (ML recreo la venta con otro numero).
        # Nunca NC automatica ni devolucion: la mercaderia y la plata siguen con la gemela.
        d["goods"] = GOODS_NONE
        d["invoice"] = INV_MANUAL if (has_posted or has_draft) else INV_NONE
        d["notes"].append("el pago sigue acreditado sin reintegro%s: revisar a mano (buscar la venta gemela)"
                          % (ctx.get("pack_id") and " (pack %s)" % ctx["pack_id"] or ""))
        if out_done or has_posted:
            d["so"] = SO_HOLD
    elif pay_class == PAY_REFUNDED:
        refunded = _f(ctx.get("refunded_amount"))
        d["cancel_drafts"] = has_draft
        if has_posted:
            if refunded + tol >= posted_total:
                d["invoice"] = INV_CREDIT_NOTE
                d["nc_amount"] = round(posted_total, 2)
            else:
                # El core solo revierte la factura ENTERA (account.move.reversal); una NC
                # parcial automatica exigiria editar lineas de un borrador fiscal. v1: a mano.
                d["invoice"] = INV_MANUAL
                d["nc_amount"] = round(refunded, 2)
                d["notes"].append("reintegro PARCIAL %s de %s facturado: la nota de crédito parcial se hace a mano"
                                  % (_money(refunded), _money(posted_total)))
    elif pay_class == PAY_NEVER:
        d["cancel_drafts"] = has_draft
        if has_posted:
            d["invoice"] = INV_CREDIT_NOTE
            d["nc_amount"] = round(posted_total, 2)
    else:  # PAY_UNKNOWN
        d["invoice"] = INV_CONFIG if (has_posted or has_draft) else INV_NONE
        d["notes"].append("estado de pago no reconocido (%s): se aplica la acción configurada"
                          % ",".join(sorted(set(p.get("status") or "-" for p in ctx.get("payments") or []))))

    # 3. VENTA.
    if d["goods"] == GOODS_WAIT:
        d["so"] = SO_HOLD
        d["waiting_return"] = True
    if d["invoice"] == INV_MANUAL and has_posted:
        d["so"] = SO_HOLD

    d["text"] = _text(ctx, d)
    return d


def _text(ctx, d):
    ship = ctx.get("shipment") or {}
    pays = ctx.get("payments") or []
    foto = "ML: orden %s %s" % (",".join(ctx.get("order_ids") or []) or "-", ctx.get("status") or "-")
    if ctx.get("cancel_code"):
        foto += " (%s%s)" % (ctx["cancel_code"], ctx.get("requested_by") and ", por %s" % ctx["requested_by"] or "")
    if ship:
        foto += " · envío %s %s/%s%s" % (ship.get("id") or "-", ship.get("status") or "-", ship.get("substatus") or "-",
                                         ship.get("logistic_type") and " [%s]" % ship["logistic_type"] or "")
    else:
        foto += " · sin envío ML"
    if pays:
        foto += " · pagos " + ", ".join("%s %s%s" % (p.get("id") or "-", p.get("status") or "-",
                                                    p.get("refunded") and " reintegrado %s" % _money(p["refunded"]) or "")
                                       for p in pays)
    else:
        foto += " · sin pagos"
    goods_txt = {
        GOODS_RETURN: "devolución de la entrega",
        GOODS_WAIT: "ESPERAR el retorno (no se devuelve todavía)",
        GOODS_NONE: "sin movimiento de stock",
        GOODS_CONFIG: "mercadería según configuración",
    }[d["goods"]]
    inv_txt = {
        INV_NONE: "sin acción sobre factura",
        INV_CREDIT_NOTE: "nota de crédito por %s" % _money(d.get("nc_amount")),
        INV_MANUAL: "factura a gestionar a mano",
        INV_CONFIG: "factura según configuración",
    }[d["invoice"]]
    if d.get("cancel_drafts"):
        inv_txt += " + cancelar borradores"
    so_txt = {SO_CANCEL: "la venta se cancela", SO_HOLD: "la venta queda abierta", SO_SKIP: "no se acciona"}[d["so"]]
    fila = "%s + %s" % (GOODS_TEXT.get(d["row_ship"], d["row_ship"]), PAY_TEXT.get(d["row_pay"], d["row_pay"]))
    text = "%s ⇒ fila: %s ⇒ %s; %s; %s." % (foto, fila, goods_txt, inv_txt, so_txt)
    if d.get("notes"):
        text += " Nota: " + "; ".join(d["notes"]) + "."
    return text
