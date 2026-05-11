# meli_oerp - Fixes Log

> Historial de correcciones implementadas.

---

### 2026-05-08 — FIX-011: Odoo 19 — orders_view xpath `locked` eliminado `[19.0.scoremx]`

**Commit:** `400f4f2`
**Resuelve:** ERROR-006
**Archivos:** `meli_oerp/views/orders_view.xml`

El xpath `//field[@name='locked']` fallaba porque `locked` no existe en Odoo 19.
`<field name="picking_ids" invisible="1"/>` se movió directamente dentro del primer `button_box` xpath, eliminando el xpath separado que dependía del campo eliminado.

**Patrón:** Antes de usar xpath por nombre de campo, verificar que el campo sigue existiendo en la vista base de la versión de Odoo objetivo.

---

### 2026-05-08 — FIX-010: Cupón ML — denominador correcto (con IVA) + control `meli_coupon_discount_on_invoice` `[17.0.elvimarta]`

**Commit:** (v26.28)
**Resuelve:** ERROR-005
**Archivos:** `meli_oerp/models/orders.py`, `meli_oerp_accounting/models/company.py`

**Fix:**
1. El cálculo del % de descuento ahora usa el precio bruto con IVA como denominador:
   ```python
   tax_pct = sum(t.amount for t in line.tax_id if t.amount_type == 'percent' and not t.price_include)
   total_gross += line.price_unit * line.product_uom_qty * (1.0 + tax_pct / 100.0)
   discount_pct = round(coupon_amount / total_gross * 100.0, 6)
   ```
2. El descuento solo se aplica si `config.meli_coupon_discount_on_invoice = True` (campo nuevo en `res.company`).
3. Cuando `meli_coupon_discount_on_invoice = False` (default): si la orden tenía descuentos incorrectos del bug anterior, se detectan y limpian (compara contra `pct_bug` y `pct_ok` con tolerancia 0.01).

---

### 2026-05-05 — FIX-009: CSRF fix en /meli_notify `[19.0.keleb]`

**Commit:** pending
**Resuelve:** ERROR-002
**Archivos:** `meli_oerp/controllers/main.py`, `meli_oerp_multiple/controllers/main.py`

Agregado `csrf=False` y `methods=['POST']` a ambas rutas de notificación ML. Sin este fix Odoo 17 rechazaba todos los POST externos con 400.
El módulo multiple también valida `application_id` vs `client_id` y `user_id` contra los vendedores autorizados de la cuenta.

---

### 2026-05-05 — FIX-008: Migración a billing_info v2 `[19.0.keleb]`

**Commit:** pending
**Resuelve:** ERROR-003
**Archivos:** `meli_oerp/models/orders.py`

Nuevo endpoint `/orders/billing-info/{SITE_ID}/{BILLING_INFO_ID}` con header `x-version: 2`.
La respuesta v2 tiene estructura nested distinta a v1. Se implementó un normalizador que convierte el response v2 al formato legacy UPPERCASE flat, transparente para el código existente.
El método `_get_billing_info_extra_headers()` agrega el header `x-version: 2` al SDK.
Fallback automático al endpoint legacy si el v2 falla.
Mapeo de `INVOICE_TYPE` para MLA derivado del `doc_type` cuando el campo no viene en v2 (CUIT → Factura A, DNI → Factura B).

---

### 2026-05-05 — FIX-007: Seller discount capping para cupones `[19.0.keleb]`

**Commit:** `bf2931f`, refinado en `c73eb35`
**Resuelve:** ERROR-004
**Archivos:** `meli_oerp/models/orders.py`

Lógica: cap el `seller_discount` al monto del cupón **solo si** `(paid_amount - seller_discount) < amount_total`.
Si la condición es falsa, el descuento es legítimo (no es un descuento de lista) y no se capea.
Ejemplo: paid=$57,960, discount=$24,038, total=$54,725 → `(57,960 - 24,038) = $33,922 < $54,725` → cap a coupon=$5,288 → invoice=$55,289 ≈ total ✓

---

### 2026-05-05 — FIX-006b: meli_repair_missing_pickings `[cross-client]`

**Commit:** (parte de 26.26)
**Archivos:** `meli_oerp/models/orders.py`

Nuevo método `meli_repair_missing_pickings()`. Detecta stock moves en `state in ('confirmed','assigned','partially_available')` sin `picking_id`. Los asigna a un picking existente vía `_assign_picking()` o crea uno nuevo. Retorna `{repaired: N, skipped: M}`.
Llamado automáticamente si `confirm_ml()` detecta que la orden confirmada tiene 0 pickings.

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
