# meli_oerp - Patterns

> Patrones de código y convenciones.

---

## PAT-001: Descuentos ML siempre vía `line.discount`, nunca restando del unit_price `[16.0.shoppy]`

**Aplica a:** Modelos (orders.py)
**Razón:** Restar el descuento del unit_price y además aplicar line.discount genera doble descuento.

### Ejemplo correcto

```python
# Calcular descuento proporcional y aplicarlo en la línea
if subtotal > 0:
    discount_pct = (coupon_amount / subtotal) * 100
    order_line.discount = discount_pct
```

### Anti-patrón

```python
# NO: restar cupón del precio unitario
unit_price = unit_price - (coupon_amount / qty)  # incorrecto si también se usa line.discount
```

---

## PAT-002: Capturar cupones desde `charges_details`, no desde `order.coupon` `[16.0.shoppy]`

**Aplica a:** Modelos (orders.py)
**Razón:** El campo `coupon` en el JSON de la orden ML puede estar ausente. Los cupones siempre llegan en `charges_details` del pago con `type=coupon`.

### Ejemplo correcto

```python
for charge in payment.get('charges_details', []):
    if charge.get('type') == 'coupon':
        coupon_amount = abs(charge.get('amounts', {}).get('original', 0))
```

---
