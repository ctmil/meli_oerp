# meli_oerp - Changelog

> Historial de versiones y cambios orientado al cliente.

---


## Versión 18.0.26.57 — el IMPORT ML→Odoo trae las medidas del paquete y demás campos de la pestaña "MELI Plantilla" [#424 Deco/KPI]
3 jul 2026

**Cambios:**

1. **Al importar un producto desde MercadoLibre ya se completan los campos de la pestaña "MercadoLibre / Plantilla".**
   Antes, al traer un item de ML, la sección **"Dimensiones del paquete (Vendedor – Mercado Envíos)"**
   (Alto/Ancho/Largo/Peso del paquete) y los campos **Marca**, **Modelo** y **Género** quedaban vacíos —
   había que cargarlos a mano para poder **re-publicar** (Mercado Envíos exige las medidas del paquete).
   Ahora el import lee esos datos del propio item de ML y los rellena automáticamente. Si ML no informa un
   dato, **no se pisa** lo que hayas cargado a mano (es idempotente).
2. **Nuevo botón "Traer medidas" y acción masiva** para los productos **ya importados** sin estos datos:
   en la ficha del producto (pestaña MELI Plantilla) y como acción sobre la lista de productos, relee el
   item de ML de cada producto con publicación y completa los campos faltantes. Procesa de a lotes de forma
   segura: si un producto falla, el resto continúa.


## Versión 18.0.26.56 — no rotar el token de MercadoLibre en bases de prueba (neutralizadas)
1 jul 2026

**Cambios:**

1. **Las copias de prueba (staging/duplicados en Odoo.sh) ya no desconectan a producción.** Al duplicar
   la base para un entorno de test, Odoo la marca como *neutralizada*. Hasta ahora el conector seguía
   intentando **renovar el token** de MercadoLibre desde esa copia; como el token de renovación es rotativo
   (un solo uso), cada renovación desde el test **invalidaba la sesión de producción** (y viceversa),
   causando cortes intermitentes de conexión (401). Ahora una base neutralizada **nunca renueva el token**:
   el entorno de prueba sigue leyendo con el token vigente hasta que expira y luego queda desconectado
   (esperado en test), sin afectar a producción. _(Producción sin cambios de comportamiento.)_

## Versión 26.55 — cupón ML: respeta la preferencia de facturación (modo de cupón configurable) [#433]
30 jun 2026

**Cambios:**

1. **El cupón de MercadoLibre vuelve a respetar la configuración del cliente.** Una corrección previa
   (#399) forzaba el descuento del cupón sobre el producto cuando el comprador pagaba el envío completo,
   incluso con la opción de facturar-con-descuento **desactivada** — pisando la preferencia del vendedor
   (regresión #433). Ahora el tratamiento del cupón depende **solo** del modo declarado en la cuenta.

2. **Modo de facturación del cupón (tri-estado).** La antigua casilla pasa a un selector con tres modos:
   - **Precio pleno** (por defecto, equivale a la casilla desactivada): la factura se emite por el precio
     completo. Correcto cuando MercadoLibre reembolsa el cupón al vendedor (el ingreso gravado es el precio
     pleno). *Ni el producto ni el envío llevan el descuento del cupón.*
   - **Descuento en producto** (equivale a la casilla activada): el cupón se refleja como % de descuento
     sobre las líneas de producto.
   - **Línea de descuento separada** (opcional, avanzado): el cupón se imputa como línea(s) de descuento
     aparte, una por grupo de impuesto, sin tocar producto ni envío. *Requiere validación fiscal previa.*

   En todos los modos el total facturado sigue cuadrando con lo que corresponde cobrar. La migración deja a
   cada cuenta en el modo equivalente a su configuración anterior (desactivada → Precio pleno; activada →
   Descuento en producto).

---

## Versión 26.54 — alta automática de productos inexistentes al importar órdenes (sin frenar por permisos)
30 jun 2026

**Cambios:**

1. **Productos nuevos al importar una orden:** cuando llega una orden de MercadoLibre cuyo producto aún no
   existe en Odoo y la cuenta tiene activada *"Crear producto desde la orden"*, el sistema lo da de alta
   automáticamente. Si el cron operaba a nombre del *Vendedor ML* (sin permiso para crear productos), esa
   alta fallaba con un error de acceso y la orden quedaba sin importar. Ahora la creación y el vínculo del
   producto corren con **privilegios de sistema** (es parte de la integración automática), de modo que la
   orden se importa completa. Con la opción **desactivada** el comportamiento no cambia: el producto no se
   crea y la incidencia se registra en el log sin abortar el resto de la importación.

---

## Versión 26.46
15 jun 2026

**Cambios:**

1. **Host API ML de rescate (reverse proxy):** Nuevo campo de configuración (solo administrador técnico) **"Host API ML (rescate)"** que permite rutear las llamadas a MercadoLibre — y el OAuth — por un reverse proxy externo cuando la IP del servidor está bloqueada por ML. Vacío = directo a `api.mercadolibre.com` (comportamiento por defecto, sin cambios). Pensado para incidentes de IP bloqueada.

---

## Versión 26.41
11 jun 2026

**Cambios:**

1. **Devoluciones — Sin duplicar al cancelar:** Corregido el chequeo de devoluciones ya existentes (busca por `origin_returned_move_id` sobre los movimientos del picking, no al revés) y eliminada una doble llamada interna en la cancelación, que generaban pickings de devolución (IN) duplicados por cada ciclo de cron.

2. **AFIP — Códigos de responsabilidad ampliados:** El mapeo de tipo de contribuyente de ML reconoce más variantes (`RESPONSABLE INSCRIPTO`, `IVA EXENTO`, `EXENTO`, `SUJETO EXENTO`).

3. **Envíos — Línea de envío con costo en factura:** Cuando el envío tiene costo real, se restaura `qty_to_invoice` en la línea para que aparezca en la factura (el conector factura al pago, no a la entrega).

---

## Versión 26.40
10 jun 2026

**Cambios:**

1. **Envíos — Flete del comprador en órdenes pack/ME2:** En ventas tipo pack (varios ítems en un carrito), el costo de envío a cargo del comprador no viene en el pago (`payment.shipping_amount=0`) ni en la orden — vive en el envío (`/shipments/{id}/costs → receiver.cost`). Ahora el conector lo captura (`mercadolibre.shipment.shipping_receiver_cost`) y lo usa como precio de la línea de envío cuando el pago no lo trae, de modo que la factura cierra con lo que pagó el comprador (producto + envío).

---

## Versión 26.39
10 jun 2026

**Cambios (tanda fixes meli jun-2026):**

1. **Mapeo de transportistas — respeta el producto del carrier:** La línea de envío del pedido ahora usa el producto del transportista mapeado en su tabla de mapeo (antes lo pisaba con un servicio de envío autogenerado). `shipment.py _update_sale_order_shipping_info`.
2. **Etiqueta de envío — modos PDF / ZPL (zip) / ZPL (txt):** Nuevo modo `zpl_txt` que extrae el contenido ZPL del zip que entrega ML y lo guarda como `.zpl` plano (listo para impresora). Además **fix del nombre de descarga**: los binarios de etiqueta ahora llevan `filename=`, así la descarga muestra `Shipment_<id>.pdf/.zpl` en vez del tamaño (`"1.10 Kb"`).
3. **Equipo / vendedor:** `meli_fix_team` ya no resetea el equipo ni el vendedor cuando fueron seteados a mano; asigna `seller_team` aunque la cuenta no tenga compañía (guard company-less).
4. **Posición fiscal configurable:** El sistema respeta el flag `mercadolibre_set_fiscal_position` (default True). En False deja en blanco la posición fiscal de la venta. `orders.py`.
5. **Fechas placeholder de ML descartadas:** `ml_datetime` descarta las fechas placeholder de ML (año < 1970) que rompían el `write` del envío con `ValueError '1-01-01 00:00:00'`. `versions.py`.
6. **Costo de envío en la primera importación:** `_ensure_payment_shipping_amounts` completa el `shipping_amount` del pago antes de calcular la línea de envío, evitando que el envío quede en 0 en la primera importación de la orden. `orders.py`.
7. **Fechas del envío desde `shipping_option`:** Se incorporan buffering_date, schedule_limit, pay_before, pickup_promise (from/to) y desired_promised_delivery a la ficha del envío.

---

## Versión 26.29
2026-05-13

**Cambios:**

1. **Stock — Priorización por movimiento de stock:** Cuando ocurre un movimiento de stock para un producto publicado en ML, `meli_update_boms()` ahora resetea `meli_stock_update = NULL` vía SQL directo. El cron ordena por `meli_stock_update ASC NULLS FIRST` — con NULL, el producto sube al frente del queue en el primer ciclo siguiente (5-10 min). Antes, un producto synced con qty=0 quedaba al fondo de la cola y podía tardar 30+ minutos en reactivarse.

2. **Stock — `meli_stock_diagnostic()` como red de seguridad:** Nueva función que corre al final de cada ciclo de `meli_update_remote_stock`. Detecta y corrige automáticamente:
   - Items `status=paused` en ML con `virtual_available > 0` → reactiva vía `product_post_stock()`
   - Items `status=active` con `available_quantity=0` pero Odoo tiene stock → push corrección
   - `meli_available_quantity` stale cuando ML tiene qty>0 → sincroniza desde ML (SQL directo)
   - Drift de cantidades (Odoo ≠ ML) → log WARNING `MELI_STOCK_DIAG`

3. **Stock — Skip fulfillment en cron:** Productos con `meli_shipping_logistic_type='fulfillment'` ya no generan llamadas a ML API innecesarias en el cron de stock (ML no permite modificar stock de almacenes fulfillment vía API). El cron ahora hace `continue` directamente con `meli_stock_error="fulfillment"`.

4. **Órdenes — Fix `seller_discount` sobreestimado con cupón:** `amounts.seller` del endpoint `/orders/{id}/discounts` contiene el descuento total de precio de lista (precio original − precio de venta), no la contribución real del vendedor al cupón. Para evitar que `meli_amount_to_invoice` devuelva un valor menor al correcto, el descuento del vendedor se capea al `coupon_amount` cuando `(paid - seller_discount) < amount_total`.

5. **Webhooks ML — CSRF desactivado en `/meli_notify`:** Los endpoints de webhook de ML (`/meli_notify`, `/meli_notify/<login_id>`) ahora tienen `csrf=False` en el decorator. Sin este flag, Odoo rechazaba los POST de ML con 400 "No CSRF validation token provided".

6. **Billing info — Migración a API v2:** El endpoint legacy `/orders/{order_id}/billing_info` fue deprecado por ML en Q1 2026. Migrado al nuevo endpoint `/orders/billing-info/{SITE_ID}/{BILLING_INFO_ID}` con header `x-version: 2`. Incluye normalizador de formato para el nuevo schema anidado (antes UPPERCASE flat, ahora `identification.type`, `name`, `address.street_name`).

7. **Compatibilidad Odoo 19 — `_sql_constraints` obsoletos eliminados:** 23 warnings de startup eliminados. Odoo 19 emite `DeprecationWarning` por cada clase con `_sql_constraints`. Todos los modelos ya tenían `UniqueIndex`/`Constraint` como atributos de clase — el atributo era redundante.

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
