# -*- coding: utf-8 -*-
"""Reparto de importes de nivel AGREGADO (orden / carrito) entre las lineas que lo componen.

[#603 / #595 Shoppy 502, 5-oct-2026] Regla del suite: un importe de nivel agregado NUNCA se
aplica entero a un nivel mas fino. El 23-sep (26.131) el descuento del PACK completo se restaba
del precio de CADA linea y dejo 46 lineas con precio negativo; el 01-oct una cancelacion
re-sincronizada dejo [F04194AL] en -48.730,17 porque `discount_seller_amount` (132.462,50) era
mayor que la propia orden (73.499). Este modulo no importa nada de Odoo: se testea aislado
(`tests/test_meli_prorate.py`) y lo usan orders.py y shipment.py.
"""


def _to_cents(amount):
    return int(round(float(amount or 0.0) * 100))


def prorate_cents(weights, amount):
    """Reparte `amount` entre `weights` en forma proporcional, cuadrando AL CENTAVO.

    Garantias (son las que se prueban):
      * la suma de las partes == min(max(amount, 0), sum(weights)), exacto al centavo;
      * ninguna parte es negativa y ninguna supera su peso => ninguna linea queda negativa;
      * metodo del mayor resto: los centavos sobrantes van a las partes con mayor fraccion
        (desempate: mayor peso, luego menor indice), asi el resultado es determinista.

    :param weights: importes de cada linea (precio unitario * cantidad). Negativos cuentan 0.
    :param amount: importe agregado a repartir (cupon del carrito, descuento de la orden).
    :return: lista de floats (2 decimales), misma longitud que `weights`.
    """
    w = [max(_to_cents(x), 0) for x in weights]
    total = sum(w)
    a = min(max(_to_cents(amount), 0), total)
    if not w or total == 0 or a == 0:
        return [0.0 for _ in w]
    base = [a * wi // total for wi in w]
    rest = a - sum(base)
    order = sorted(range(len(w)), key=lambda i: (-(a * w[i] % total), -w[i], i))
    for i in order[:rest]:
        base[i] += 1
    return [b / 100.0 for b in base]


def bounded_order_discount(seller_discount, coupon_amount):
    """Descuento del vendedor que se permite bajar a las lineas de UNA orden.

    `discount_seller_amount` sale de /orders/<id>/discounts y en 502 NO es un cupon: medido
    5-oct sobre 4.817 ordenes desde el 1-ago, 4.782 lo tienen por encima del cupon y 1.822 por
    encima del total de la orden (incluye rebajas de precio de lista ya reflejadas en unit_price).
    Por eso se acota al cupon de la orden: sin cupon no se descuenta nada (factura a precio
    pleno, que es el comportamiento seguro) y con cupon nunca se descuenta mas que el cupon.
    """
    seller = max(float(seller_discount or 0.0), 0.0)
    coupon = max(float(coupon_amount or 0.0), 0.0)
    if coupon <= 0.0:
        return 0.0
    return min(seller, coupon)


def pack_line_fits(amount_total, paid_amount, line_amount, tolerance=1.1):
    """[#595] ¿Entra esta linea del carrito en lo que pago el comprador?

    El guard anterior (`amount_total < paid - cupon`) restaba el cupon del CARRITO al margen
    disponible: con un cupon del 10 %, el ultimo item mas barato que el cupon no se creaba nunca
    y sin aviso (cepillo 3.699 < cupon 7.019,80 en ML 2000014963729457). El cupon es costo del
    vendedor (fee) y la venta lleva el precio completo, asi que la comparacion correcta es contra
    lo pagado: la linea entra si, sumada, no pasa lo pagado. Si el usuario ya reemplazo el
    producto a mano, el reemplazo ocupa ese lugar y la linea original no se re-crea.
    """
    return (float(amount_total or 0.0) + float(line_amount or 0.0)) <= (float(paid_amount or 0.0) + tolerance)
