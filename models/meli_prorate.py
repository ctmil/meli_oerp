# -*- coding: utf-8 -*-
"""Reglas puras (sin Odoo) de importes de carrito / descuento del vendedor.

Vienen de prod Shoppy 502 (26.235, 3fb82c5a: #603 F5b + #595) y se portan en 26.386 sobre el diseño del
source (26.229/26.249/26.318: prorrateo del pack por bruto, nunca negativo, type=discount excluido).
Se testean aislado (`tests/test_26386_carrito_595.py`).
"""


def bounded_order_discount(seller_discount, coupon_amount):
    """[F5b] Descuento del vendedor que se permite restar en UNA orden, acotado al cupón de la orden.

    En 502 `discount_seller_amount` superaba al cupón en la gran mayoría de las órdenes (medido 5-oct:
    4.782 de 4.817). Sin cupón no se descuenta nada (precio pleno, lo seguro); con cupón nunca más
    que el cupón. Sólo se aplica con el parámetro `meli_oerp.seller_discount_cap_coupon` (opt-in).
    """
    seller = max(float(seller_discount or 0.0), 0.0)
    coupon = max(float(coupon_amount or 0.0), 0.0)
    if coupon <= 0.0:
        return 0.0
    return min(seller, coupon)


def pack_line_fits(amount_total, paid_amount, line_amount, tolerance=1.1):
    """[#595] ¿Entra esta línea del carrito en lo que pagó el comprador?

    El guard anterior (`amount_total < paid - cupón`) restaba el cupón del CARRITO al margen disponible:
    el último ítem más barato que el cupón no se creaba nunca y sin aviso (cepillo 3.699 < cupón 7.019,80
    en ML 2000014963729457). La línea entra si, sumada, no pasa lo pagado.
    """
    return (float(amount_total or 0.0) + float(line_amount or 0.0)) <= (float(paid_amount or 0.0) + tolerance)
