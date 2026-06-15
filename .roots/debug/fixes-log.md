# meli_oerp - Fixes Log

> Historial de correcciones implementadas.

---

### 15 jun 2026 — feat(meli_util): host API de rescate (reverse proxy) — PROMOVIDO desde cliente Deco (v26.46)

**Archivos:** `models/company.py`, `models/meli_util.py`, `models/res_config_settings.py`, `views/res_config_settings.xml`

- **Qué:** campo `mercadolibre_http_proxy` (Char 512, `base.group_system`) en `res.company`; `get_new_instance()` ahora rutea `api_host = company.mercadolibre_http_proxy or "https://api.mercadolibre.com"` y construye config por-host cuando hay proxy (SDK: `_meli_sdk.Configuration(host=...)`; noSDK: `MeliConfiguration(host=...)`). El OAuth ya va por `_abs_url("/oauth/token")`, así que tambien se rutea. Vacío = directo (sin cambio de comportamiento).
- **Origen:** feature nacido en el cliente Deco (incidente de IP de Odoo.sh bloqueada por ML). Promovido al source para no re-conflictuar en cada sync.
- **Merge atento (no copia):** el source ya había divergido en la zona OAuth/noSDK (tiene `_abs_url`, authorize/refresh por `_abs_url`). Solo se injertó el ruteo de host en `get_new_instance`; el resto del source se preservó.
- **Sanitización:** el dominio real del proxy del cliente (`proxy.moldeointeractive.com`) NO entra al source — reemplazado por `proxy.example.com` ficticio en help/placeholder. Campo vacío por default.
- **Retry (DECISIÓN PENDIENTE, no resuelta acá):** Deco usa `requests.Session()` sin auto-retry (`retries=False`, rationale "los 429 agravan el rate-limit") mientras el source usa `LoggingRetry` (backoff 413/429/503). Se **preservó el `LoggingRetry` del source** para el path por defecto (cambio de amplio alcance); cuando el proxy ESTÁ activo se usa `retries=False` (scoped, conservador). La unificación global queda a decisión del usuario (Deco `7c676f0` 2026-05-20 es posterior al `LoggingRetry` del source `a71004cb` 2026-02-25).

---

### 13 jun 2026 — fix(orders/returns): guard cantidad-cero en devolución FULL — evita bucle de error del cron (v26.45)

**Archivos:** `meli_oerp/models/orders.py` (`_meli_return_done_pickings`)

- **Síntoma:** en órdenes **FULL** canceladas por MeLi, el cron logueaba en bucle (~cada 5 min) `Error creating return for picking FULL/OUT/NNNN: Especifique al menos una cantidad diferente a cero` y posteaba el aviso repetido en el chatter de la orden.
- **Causa:** el wizard `stock.return.picking` calcula `quantity=0` en `product_return_moves` (el stock FULL vive en el fulfillment de ML); `action_create_returns()` lanza UserError y, sin guard, el cron reintenta indefinidamente.
- **Fix:** antes de `action_create_returns()`, si `sum(product_return_moves.quantity)==0` → omitir la devolución con `_logger.info` y `continue` (no-fatal). Detectado por smoke-test en prod (Dannok).

---


### 11 jun 2026 — fix(payment_term): no forzar el término de pago (respetar el del tercero) (v42)

**Archivos:** `meli_oerp/models/orders.py`, `meli_oerp/models/shipment.py`

- **Síntoma:** órdenes importadas de MeLi quedaban en *Pago inmediato* al confirmar, pisando el término del tercero (p.ej. **crédito**) → rompía el despacho sin validar pago (caso TYL Colombia).
- **Causa:** `payment_term_id` de la orden y `property_payment_term_id` del comprador se seteaban siempre desde `mercadolibre_payment_term`; vacío escribía `False`, borrando el término propio.
- **Fix:** sólo setear el término si está configurado; si no, **no sobrescribir**. Acompaña `meli_oerp_multiple` (campo opcional).

---

### 10 jun 2026 — Tanda fixes meli jun-2026 (v26.39)

**Archivos:** `meli_oerp/models/shipment.py`, `meli_oerp/models/orders.py`, `meli_oerp/models/versions.py`, `meli_oerp/views/orders_view.xml`, `meli_oerp/views/shipment_view.xml`

1. **Carrier mapeado pisado por servicio autogenerado** — *Síntoma:* la línea de envío del SO usaba un producto de servicio creado al vuelo aunque el transportista estuviera mapeado. *Causa:* `_update_sale_order_shipping_info` sobreescribía `product_id` con el autogenerado. *Fix:* usa el producto efectivo del carrier mapeado; solo asigna producto si el carrier no tiene uno. `shipment.py`.

2. **Nombre de descarga de la etiqueta = tamaño ("1.10 Kb")** — *Síntoma:* al descargar la guía, el navegador mostraba el tamaño en vez de un nombre. *Causa:* los campos binarios de etiqueta no declaraban `filename=`. *Fix:* `filename="pdf_filename"` (PDF/ZPL) y el del preview en `orders_view.xml` y `shipment_view.xml`. Además nuevo modo `zpl_txt` (extrae el ZPL plano del zip de ML con `io`+`zipfile`, response_type `zpl2`). `shipment.py`.

3. **`meli_fix_team` reseteaba equipo/vendedor manuales** — *Síntoma:* equipo y vendedor seteados a mano se perdían al re-procesar. *Causa:* el método los reasignaba siempre y exigía compañía para `seller_team`. *Fix:* respeta team/seller seteados a mano; asigna `seller_team` aunque la cuenta no tenga compañía; user válido si `company in user.company_ids`. `orders.py`.

4. **Posición fiscal forzada siempre** — *Síntoma:* no se podía dejar la venta sin posición fiscal. *Causa:* `fiscal_position_id` se seteaba incondicionalmente. *Fix:* gate `mercadolibre_set_fiscal_position` (default True; en False → `fiscal_position_id=False`). El campo vive en `meli_oerp_multiple`. `orders.py`.

5. **`ValueError '1-01-01 00:00:00'` al escribir el shipment** — *Síntoma:* el `write` del envío reventaba con fechas año 0001. *Causa:* ML manda fechas placeholder (año < 1970) en algunos campos. *Fix:* `ml_datetime` descarta año < 1970 → devuelve `None`. `versions.py`.

6. **Envío en 0 en la primera importación** — *Síntoma:* la línea de envío quedaba en 0 al importar la orden por primera vez. *Causa:* el `shipping_amount` del pago aún no estaba completo al calcular la línea. *Fix:* `_ensure_payment_shipping_amounts` re-consulta MP los pagos aprobados con `shipping_amount=0` y completa el monto antes de calcular la línea (chequeo final + `invalidate_recordset`). `orders.py`.

7. **Fechas del envío incompletas** — *Fix (feature):* se parsean desde `shipping_option` los campos buffering_date, schedule_limit, pay_before, pickup_promise (from/to) y desired_promised_delivery. `shipment.py`/`orders.py`.

---

### 12 Mayo 2026 - fix(stock): reset meli_stock_update en moves para priorización en cron

**Commit:** `77ef170`
**Resuelve:** ERROR-005
**Archivos:** `meli_oerp/models/stock_move.py`

Cuando ocurre un stock move, `meli_update_boms()` (Step 3b) resetea `meli_stock_update = NULL`
para todos los productos ML afectados via SQL directo:

```python
self.env.cr.execute(
    "UPDATE product_product SET meli_stock_update = NULL WHERE id = ANY(%s)",
    (list(products_to_update),)
)
self.env['product.product'].invalidate_model(['meli_stock_update'])
```

Con `meli_stock_update = NULL`, el cron (ORDER BY `meli_stock_update ASC NULLS FIRST`)
procesa esos productos en el primer ciclo siguiente (5-10 min). Si ML tiene `status=paused`,
`product_post_stock()` llama `product_meli_status_active()` para reactivar.

---

### 12 Mayo 2026 - feat(stock): meli_stock_diagnostic() — red de seguridad post-cron

**Commit:** `6c7a8e2`
**Archivos:** `meli_oerp/models/company.py`

Nueva función que corre al final de cada ciclo de `meli_update_remote_stock`. Detecta:
- `status=paused` en ML + `virtual_available > 0` → `product_post_stock()` (reactiva)
- `status=active` + `ml_qty=0` pero Odoo tiene stock → push corrección
- `meli_available_quantity=0` + `ml_qty>0` + `status=active` → SQL update (sincroniza meli_qty desde ML)

Respeta `meli_update_stock_blocked`. Protegida con try/except para no romper el cron.

---

### 12 Mayo 2026 - fix(stock): fulfillment skip en cron de stock

**Commit:** `c3ec111`
**Archivos:** `meli_oerp/models/company.py`

Productos con `meli_shipping_logistic_type` conteniendo `'fulfillment'` ya no generan
API calls a ML (ML rechaza stock updates en almacenes fulfillment). Guard antes del loop:
`meli_stock_error="fulfillment"`, `continue`. Aplica en `meli_update_remote_stock` y
`meli_update_remote_stock_rt`.

---

### 10 Abril 2026 - fix(webhook): csrf=False en endpoints /meli_notify

**Resuelve:** ERROR-007
**Archivos:** `meli_oerp/controllers/main.py`, `meli_oerp_multiple/controllers/main.py`

Agregado `csrf=False` a los decorators de route de `/meli_notify` y `/meli_notify/<string:meli_login_id>`.

---

### 10 Abril 2026 - fix(billing_info): migración a endpoint v2 con normalizador de formato

**Resuelve:** ERROR-006
**Archivos:** `meli_oerp/models/orders.py`

Migrado de `/orders/{id}/billing_info` a `/orders/billing-info/{SITE_ID}/{BILLING_INFO_ID}`
con header `x-version: 2`. Agregado normalizador de claves para mapear el nuevo schema
anidado al formato esperado por el código consumidor.

---

### 05 Mayo 2026 - fix(orders): cap seller_discount condicional en meli_amount_to_invoice

**Resuelve:** ERROR-004
**Archivos:** `meli_oerp/models/orders.py`

`amounts.seller` de `/orders/{id}/discounts` tiene dos semánticas. El cap solo se aplica
cuando `(paid - seller_discount) < amount_total`:

```python
if _coupon_cap > 0 and self.amount_total > 0:
    _uncapped = (self.meli_paid_amount or 0.0) - seller_discount
    if _uncapped < self.amount_total:
        seller_discount = min(seller_discount, _coupon_cap)
```

---

### 05 Mayo 2026 - fix(odoo19): eliminar _sql_constraints obsoletos (23 warnings)

**Resuelve:** ERROR-003
**Archivos:** 8 modelos en meli_oerp, meli_oerp_multiple, meli_oerp_stock, odoo_connector_api

Eliminados `_sql_constraints = versions.sql_constraints_if_no_unique_index(...)` de 14 modelos.
Todos ya tenían `UniqueIndex`/`Constraint` como atributos de clase.

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
