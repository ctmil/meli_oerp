# -*- coding: utf-8 -*-
"""Flete que paga el COMPRADOR según /shipments/{id}/costs — sin dependencias de Odoo.

`receiver.cost` es el costo del envío del lado del comprador, pero NO dice quién lo paga:
cuando el vendedor subsidia el envío gratis, ML lo informa en `receiver.cost_details`
(`sender_id` = el vendedor, `amount` = lo que cubre). Tomar `receiver.cost` bruto cobraba
al comprador un flete que pagó el vendedor (Olpa 462, 1-oct-2026: SO 6146 +2.335,09 con
el pago del comprador en shipping 0).
"""


def receiver_buyer_cost(rcosts):
    """Parte de receiver.cost que efectivamente paga el comprador (>= 0)."""
    receiver = (isinstance(rcosts, dict) and rcosts.get('receiver')) or {}
    if not isinstance(receiver, dict):
        return 0.0
    cost = float(receiver.get('cost') or 0.0)
    buyer_id = receiver.get('user_id')
    covered = 0.0
    for det in receiver.get('cost_details') or []:
        if not isinstance(det, dict):
            continue
        sender = det.get('sender_id')
        if buyer_id and sender and str(sender) == str(buyer_id):
            continue
        covered += float(det.get('amount') or 0.0)
    return max(cost - covered, 0.0)
