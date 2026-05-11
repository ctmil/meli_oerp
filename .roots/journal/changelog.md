# meli_oerp - Changelog

> Historial de versiones y cambios orientado al cliente.

---

## Versión 26.28
2026-05-08

**Cambios:**

1. **Cupón ML — control de descuento en factura:** El campo `coupon_amount` de MercadoLibre es un costo que ML financia al comprador — el vendedor cobra el precio completo. La lógica anterior aplicaba ese monto como descuento en las líneas del SO siempre, y calculaba el porcentaje sobre el precio base sin IVA (incorrecto). Cambios:
   - Nuevo campo de configuración `meli_coupon_discount_on_invoice` (Boolean, default=False):
     - **Desactivado (default):** factura por precio de venta completo. Si hubo descuentos incorrectos previos, se limpian automáticamente al reimportar la orden.
     - **Activado:** aplica el cupón como descuento porcentual usando el precio bruto **con IVA** como denominador (corrección del bug de cálculo).

2. **Reparar entrega — notificación de resultado (UX):** El método `meli_repair_missing_pickings()` ahora retorna una notificación Odoo con el resultado (`success` si reparó, `warning` si no encontró movimientos huérfanos).

3. **Advertencias ML — renderizado de causas anidadas:** Los errores de la API ML que devuelven `causes` como lista ahora se renderizan como alertas HTML individuales en el chatter, mostrando el detalle de cada causa aunque el mensaje principal sea un string simple.

4. **Compatibilidad Odoo 19 — `qty_done` → `quantity`:** En Odoo 19 el campo `qty_done` de `stock.move.line` fue renombrado a `quantity`. La detección ahora es automática via `hasattr`, sin hardcodear el nombre del campo.

5. **Compatibilidad Odoo 19 — view_mode f-string:** Fix en `cron_execution.py`: la variable `view_mode_tree` no se expandía en el string de la acción de ventana de CRONs.

---

## Versión 26.27
2026-05-07

**Cambios:**

1. **Protección de billing child en `_commercial_sync_from_company`:** Los contactos hijos de tipo `invoice` (billing child) cuyo padre tiene órdenes ML (`meli_buyer` o `meli_order_id`) ahora están protegidos de la sincronización fiscal automática de Odoo. Sin esta protección, Odoo sobreescribía los datos fiscales del hijo con los del padre comercial, eliminando el CUIT y tipo de responsabilidad AFIP.

2. **Propagación de `partner_invoice_id` en sub-órdenes pack:** Al confirmar una orden con sub-órdenes (packs ML), si el billing child resuelto es diferente del partner padre del buyer, se propaga `partner_invoice_id` a todas las sub-órdenes para que facturen al mismo billing child.

3. **Context flags en `_assign_picking()`:** Al llamar `_assign_picking()` durante la confirmación de la orden, se activan los flags `tracking_disable=True`, `mail_notrack=True` y `meli_skip_stock_update=True` para evitar triggers innecesarios de notificaciones y actualizaciones de stock en cada asignación individual.

---

## Versión 26.26
2026-05-05

**Cambios:**

1. **Descuento de vendedor con cupones (fix):** Cuando ML reporta un `seller_discount` grande (precio de lista vs. precio pagado) y hay un cupón, el descuento se capea al monto del cupón solo si la diferencia produciría un monto por debajo del total del SO. Resuelve el error "amount doesn't match" en órdenes con descuentos de lista + cupón.

2. **Reparación de pickings huérfanos:** Nuevo método `meli_repair_missing_pickings()`. Detecta stock moves en órdenes confirmadas sin picking asignado y los asigna a un picking existente (o crea uno). Se llama automáticamente si `confirm_ml()` produce una orden sin picking. También disponible como acción en el wizard de operaciones.

3. **API billing_info v2:** Migración al endpoint `/orders/billing-info/{SITE_ID}/{BILLING_INFO_ID}` con `x-version: 2`. La respuesta v2 se normaliza al formato legacy (claves UPPERCASE) para transparencia. Fallback automático al endpoint viejo.

4. **CSRF webhooks (fix crítico):** Los endpoints `/meli_notify` ahora tienen `csrf=False`. Sin este fix todas las notificaciones ML eran rechazadas con HTTP 400.

---

## Versión 16.0.26.25
2026-05-02 · `[16.0.shoppy]`

**Cambios:**

1. **Nombre de venta con info de envío:** El nombre del pedido de venta ahora muestra el número de seguimiento o ID de envío junto al número de orden ML, facilitando la identificación rápida.

2. **Tabla de mapeo de transportistas:** Nueva pantalla en MercadoLibre > Mapeo de Transportistas donde se pueden asignar los métodos de envío de ML a transportistas existentes en Odoo, evitando la creación de duplicados.

3. **Descuentos de cupón aplicados correctamente:** Los cupones y descuentos de MercadoLibre ahora se reflejan como descuento porcentual en las líneas del pedido de venta, asegurando que la factura refleje el monto real pagado por el cliente.

4. **Fechas de envío detalladas:** Se incorporaron las fechas reales de cada etapa del envío (preparación, despacho, entrega, etc.) además de las fechas estimadas, visibles en la ficha del envío.

5. **Etiqueta de envío visible en albarán:** La etiqueta PDF y su vista previa ahora se muestran directamente en el albarán (stock.picking).

6. **Nombre de impresora en configuración:** Se puede indicar el nombre de la impresora destino para etiquetas ZPL en la configuración de la cuenta ML.

---

## Versión 19.0.26.22
2026-04-30 · `[19.0.tecnolosys]`

**Cambios:**

1. **Publicación de productos:** Permalink API ahora incluye access_token para acceso directo desde el backend de Odoo.

---
