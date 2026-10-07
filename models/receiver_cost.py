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


def shipping_missing_in_paid(buyer, paid, total, coupon, payment_shipping, n_orders):
    """Flete del comprador que hay que SUMAR a meli_paid_amount para llegar a lo cobrable.

    UN SOLO criterio para la linea de envio y para el importe a facturar (#620 + #158): el
    `buyer` que entra aca es el MISMO numero que lleva la linea de envio
    (mercadolibre.shipment._meli_buyer_shipping_amount). Todo a nivel VENTA, sin red.

    - buyer <= 0 (el comprador no paga envio / subsidiado) -> 0.
    - in_paid = paid - total + |cupon| = lo que paid_amount trae POR ENCIMA de los items.
    - Pago SIN shipping_amount (#620, ME2): se suma si in_paid no cubre el flete.
    - Pago CON shipping_amount (#158 Elvimarta, ME1): hasta #620 se asumia que paid_amount
      ya lo traia. Medido 7-oct en 158: paid == total (3.138.200) y el pago trae 205.570 de
      envio -> paid_amount NO lo incluye. Se suma SOLO con esa evidencia exacta
      (|in_paid| <= 1) y SOLO si la venta tiene UNA orden ML: en un pack la linea lleva el
      flete de una orden y paid/total son del pack — no se mezclan niveles.
    Nunca suma dos veces: si paid ya trae el flete, in_paid ~ flete y devuelve 0."""
    buyer = float(buyer or 0.0)
    if buyer <= 0.0:
        return 0.0
    in_paid = float(paid or 0.0) - float(total or 0.0) + abs(float(coupon or 0.0))
    if float(payment_shipping or 0.0) > 0.0:
        if int(n_orders or 0) != 1:
            return 0.0
        if abs(in_paid) > 1.0:
            return 0.0
        return buyer
    if in_paid >= buyer - 1.0:
        return 0.0
    return buyer
