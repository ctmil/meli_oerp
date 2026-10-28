# -*- coding: utf-8 -*-
"""Flete que paga el COMPRADOR según /shipments/{id}/costs — sin dependencias de Odoo.

`receiver.cost` es el costo del envío del lado del comprador, pero NO dice quién lo paga:
cuando el vendedor subsidia el envío gratis, ML lo informa en `receiver.cost_details`
(`sender_id` = el vendedor, `amount` = lo que cubre). Tomar `receiver.cost` bruto cobraba
al comprador un flete que pagó el vendedor (un cliente, 1-oct-2026: SO <n> +2.335,09 con
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



# [#caso-K02/#caso-K21/#caso-K22, 27-oct-2026] Quien COBRA el flete de un pack/ME2 no se lee en /costs: ML pone
# receiver.cost_details a nombre del VENDEDOR por el monto entero tanto si el vendedor lo cobro como si no
# (medido: caso-K02 no-pack con el flete DENTRO del pago, 200.640, tambien lo trae). Lo que si lo dice es la plata:
# cuando el vendedor cobra el flete, MercadoPago le acredita un pago APARTE con
# description="marketplace_shipment" y external_reference=<id del envio> (caso-K02: 102.089 y 8.692; cliente F caso-K21:
# 1.299,8 y 4.999). Si el flete lo cobro ML y no el vendedor (Full Super MLM, caso-K22), ese pago no existe para el
# vendedor. El pago de la ORDEN trae shipping_amount 0 en los tres casos: no sirve para decidir.
SHIPMENT_PAYMENT_DESCRIPTION = 'marketplace_shipment'


def receiver_gross_cost(rcosts):
    """receiver.cost de /shipments/{id}/costs tal cual viene (>= 0)."""
    receiver = (isinstance(rcosts, dict) and rcosts.get('receiver')) or {}
    if not isinstance(receiver, dict):
        return 0.0
    return max(float(receiver.get('cost') or 0.0), 0.0)


def seller_collected_shipping(search_json, shipment_id):
    """Flete del envio que COBRO el vendedor segun /v1/payments/search?external_reference=<envio>
    (consultado con el token del vendedor: sólo devuelve sus cobros).

    Devuelve la suma de los pagos approved con description=marketplace_shipment y
    external_reference == shipment_id (>= 0), o None si la respuesta no permite decidir
    (sin 'results'): el llamador NO asume nada en ese caso."""
    if not isinstance(search_json, dict) or not isinstance(search_json.get('results'), list):
        return None
    total = 0.0
    for pay in search_json['results']:
        if not isinstance(pay, dict):
            continue
        if pay.get('status') != 'approved':
            continue
        if pay.get('description') != SHIPMENT_PAYMENT_DESCRIPTION:
            continue
        if str(pay.get('external_reference') or '') != str(shipment_id):
            continue
        total += float(pay.get('transaction_amount') or 0.0)
    return round(max(total, 0.0), 2)


def pack_receiver_cost(rcosts, collected, previous=None):
    """Valor de mercadolibre.shipment.shipping_receiver_cost (fallback pack/ME2 de la linea de envio).

    - receiver.cost 0 -> 0 (no hay flete del lado del comprador).
    - collected conocido (>= 0) -> collected: lo que el vendedor efectivamente cobro.
    - collected None (la consulta a MP fallo) -> NO se asume: queda lo que habia (`previous`);
      si el envio es nuevo, el criterio anterior (receiver_buyer_cost)."""
    if receiver_gross_cost(rcosts) <= 0.0:
        return 0.0
    if collected is None:
        if previous is not None:
            return max(float(previous or 0.0), 0.0)
        return receiver_buyer_cost(rcosts)
    return max(float(collected), 0.0)


def buyer_shipping_amount(use_payment, payment_shipping, option_cost, receiver_cost):
    """Mismo criterio que mercadolibre.shipment._meli_buyer_shipping_amount, sin Odoo (para tests)."""
    amount = float((payment_shipping if use_payment else option_cost) or 0.0)
    if not amount and receiver_cost:
        amount = float(receiver_cost)
    return max(amount, 0.0)

def shipping_missing_in_paid(buyer, paid, total, coupon, payment_shipping, n_orders):
    """Flete del comprador que hay que SUMAR a meli_paid_amount para llegar a lo cobrable.

    UN SOLO criterio para la linea de envio y para el importe a facturar (un caso + un caso): el
    `buyer` que entra aca es el MISMO numero que lleva la linea de envio
    (mercadolibre.shipment._meli_buyer_shipping_amount). Todo a nivel VENTA, sin red.

    - buyer <= 0 (el comprador no paga envio / subsidiado) -> 0.
    - in_paid = paid - total + |cupon| = lo que paid_amount trae POR ENCIMA de los items.
    - Pago SIN shipping_amount (un caso, ME2): se suma si in_paid no cubre el flete.
    - Pago CON shipping_amount (un cliente, ME1): hasta un caso se asumia que paid_amount
      ya lo traia. Medido 7-oct en un cliente: paid == total (3.138.200) y el pago trae 205.570 de
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
