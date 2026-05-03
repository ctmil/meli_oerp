# meli_oerp - Fixes Log

> Historial de correcciones implementadas.

---

### 2026-05-02 — FIX-004: Fix upgrade error action_create_mercadolibre_account `[16.0.shoppy]`

**Commit:** `af33b78`
**Origen:** 16.0.shoppy
**Archivos:** meli_oerp_multiple/models/company.py

El método fue eliminado por merge upstream pero la BD aún tenía una vista que lo referenciaba como botón `type="object"`. Se restauró el método.

---

### 2026-05-02 — FIX-003: Fix coupon_amount no capturado desde charges_details `[16.0.shoppy]`

**Commit:** `4568192`, re-activado en `f46ebc4`
**Origen:** 16.0.shoppy
**Archivos:** orders.py

El `order.coupon_amount` quedaba en 0 porque el order JSON de ML no incluía el campo `coupon`. La info del cupón solo llegaba en `charges_details` del pago (type=coupon, name=coupon_rebate). Se activó la actualización de `order.coupon_amount` desde charges_details y se aplica `line.discount` proporcional a las líneas de venta.

---

### 2026-05-02 — FIX-002: Fix doble descuento de cupón `[16.0.shoppy]`

**Commit:** `97adc37`
**Origen:** 16.0.shoppy
**Archivos:** orders.py

`_set_product_unit_price` restaba el cupón del unit_price, y luego el código nuevo también aplicaba `line.discount`. Resultado: doble descuento. Se eliminó la resta de cupón de `_set_product_unit_price` — el descuento se aplica solo vía `line.discount` (proporcional, correcto).

---

### 2026-05-02 — FIX-001: Fix AttributeError meli_shipment en mercadolibre.orders `[16.0.shoppy]`

**Commit:** `322fa4e`
**Origen:** 16.0.shoppy
**Archivos:** orders.py

El código de tracking number en nombre de venta usaba `order.meli_shipment` pero el campo en `mercadolibre.orders` se llama `shipment` (Many2one). El campo `meli_shipment` es de `sale.order`. Corregido a `order.shipment`.

---

### 2026-04-30 — FIX-001: Permalink API con access_token `[19.0.tecnolosys]`

**Commit:** `e0d262a`
**Resuelve:** ERROR-001
**Origen:** 19.0.tecnolosys
**Archivos:** models/product.py

Se agregó `access_token` a la URL del permalink API. Ahora la URL se construye como:
`https://api.mercadolibre.com/items/{meli_id}?include_attributes=all&access_token={token}`
El token se obtiene directamente de `meli.access_token`.

---
