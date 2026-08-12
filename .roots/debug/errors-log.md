# meli_oerp - Errors Log

> Registro de errores encontrados.

---

## Errores Activos

*Ninguno actualmente*

---

## Errores Resueltos

### ERROR-005: Descuento de cupón ML calculado con denominador sin IVA — factura por menos de lo pagado `[17.0.elvimarta]`

**Reportado:** 2026-05-08
**Severidad:** Alta — la factura quedaba por debajo del monto pagado por el comprador
**Estado:** Resuelto

**Síntomas:**
En órdenes con `coupon_amount > 0` donde `meli_coupon_discount_on_invoice = True`, la factura mostraba un monto menor al esperado. El pago de ML no alcanzaba para cubrir la factura completa, quedando con residual.

**Ejemplo (caso Elvimarta):**
```
coupon_amount = 1480
Cálculo incorrecto: discount_pct = 1480 / sum(price_unit × qty) = 1480 / 48925 = 3.02%
Factura = 48925 × (1 - 3.02%) × 1.21 = $57,412  ← menos de lo que pagó ML

Cálculo correcto: discount_pct = 1480 / sum(price_unit × qty × (1 + IVA)) = 1480 / 59200 = 2.5%
Factura = 48925 × (1 - 2.5%) × 1.21 = $57,720  ← correcto
```

**Causa raíz:**
El denominador para calcular el % de descuento usaba el precio base sin IVA. Como el cupón de ML es un monto bruto (con IVA), aplicar ese porcentaje sobre el precio neto generaba un descuento mayor al real.

**Resolución:** Ver [fixes-log.md](./fixes-log.md) → FIX-010

---

### ERROR-006: Odoo 19 — xpath `//field[@name='locked']` no encontrado en orders_view `[19.0.scoremx]`

**Reportado:** 2026-05-08
**Severidad:** Crítica — ParseError fatal en carga del módulo
**Estado:** Resuelto
**Detalle completo:** `.roots/19.0.scoremx/meli_oerp/debug/errors-log.md → ERROR-002`

**Síntomas:**
```
ParseError: while parsing meli_oerp/views/orders_view.xml:75
El elemento '<xpath expr="//field[@name='locked']">' no puede ser localizado en la vista padre
```
El campo `locked` no existe en la vista base de `sale.order` en Odoo 19.

**Resolución:** Ver [fixes-log.md](./fixes-log.md) → FIX-011

---

### ERROR-004: Seller discount capping incorrecto con cupones `[19.0.keleb]`

**Reportado:** 2026-05-05
**Severidad:** Alta — órdenes con cupón grandes bloqueadas en `confirm_ml`
**Estado:** Resuelto

**Síntomas:**
`confirm_ml` rechaza la orden con "amount doesn't match" cuando hay un cupón de ML. El `seller_discount` reportado por el endpoint `/amounts` es el descuento de lista completo (precio catálogo - precio pagado), no solo el cupón.

**Resolución:** Ver [fixes-log.md](./fixes-log.md) → FIX-007

---

### ERROR-003: billing_info endpoint deprecated por ML `[19.0.keleb]`

**Reportado:** 2026-04-10
**Severidad:** Alta — datos fiscales del comprador no llegaban desde ML
**Estado:** Resuelto

**Síntomas:**
ML deprecó el endpoint `/orders/{id}/billing_info` (03/2026). La respuesta es vacía o devuelve 404. Sin datos fiscales el partner queda como Consumidor Final genérico.

**Nuevo endpoint:** `/orders/billing-info/{SITE_ID}/{BILLING_INFO_ID}` con header `x-version: 2`. La estructura de campos cambió de UPPERCASE flat a nested.

**Resolución:** Ver [fixes-log.md](./fixes-log.md) → FIX-008

---

### ERROR-002: CSRF rechazaba todas las notificaciones ML `[19.0.keleb]`

**Reportado:** 2026-04-10
**Severidad:** Crítica — sin notificaciones ML el sistema queda en polling puro
**Estado:** Resuelto

**Síntomas:**
Las notificaciones de MercadoLibre (órdenes, preguntas, items, envíos) llegaban a Odoo con HTTP 400. Log: `CSRF token validation failed for route /meli_notify`.

**Causa:** Las rutas `/meli_notify` no tenían `csrf=False`. Odoo 17 valida CSRF en POST por defecto.

**Resolución:** Ver [fixes-log.md](./fixes-log.md) → FIX-009

---

### ERROR-001: Permalink API sin access_token `[19.0.tecnolosys]`

**Reportado:** 2026-04-30
**Severidad:** Media
**Estado:** Resuelto
**Origen:** 19.0.tecnolosys

**Síntomas:**
Links de permalink de items ML no eran accesibles directamente desde el backend de Odoo.

**Contexto:**
La URL se construía sin token de autenticación:
`https://api.mercadolibre.com/items/{meli_id}?include_attributes=all`

**Análisis:**
La API de ML requiere `access_token` como query param para acceso directo sin sesión del browser.

**Resolución:** Ver [fixes-log.md](./fixes-log.md) → FIX-001

---

### ERROR-005: Publicaciones ML no se reactivan al reabastecer stock

**Reportado:** 12 Mayo 2026
**Severidad:** Alta
**Estado:** Resuelto

**Síntomas:**
Cuando ML auto-pausa una publicación (`status=paused, sub_status=out_of_stock`), al
reabastecer el stock en Odoo la publicación no se reactiva automáticamente. Puede
tardar 30+ minutos o no activarse.

**Causa raíz:**
`meli_update_boms()` actualizaba `meli_stock_moves_update` (timestamp del movimiento)
pero no tocaba `meli_stock_update` (timestamp del último sync con ML). El cron ordena
por `meli_stock_update ASC NULLS FIRST` — un producto synced recientemente con qty=0
quedaba al fondo de la cola.

**Solución:**
`meli_update_boms()` ahora también resetea `meli_stock_update = NULL` vía SQL directo.
Con NULL, el cron (NULLS FIRST) procesa el producto en el primer ciclo siguiente.

---

### ERROR-006: Endpoint billing_info v1 deprecado por ML (Q1 2026)

**Reportado:** 10 Abril 2026
**Severidad:** Alta
**Estado:** Resuelto

**Síntomas:**
Emisión de facturas falló porque el endpoint `/orders/{order_id}/billing_info` quedó
deprecado. ML migró a `/orders/billing-info/{SITE_ID}/{BILLING_INFO_ID}` con header
`x-version: 2`.

**Causa raíz:**
El código seguía llamando al endpoint legacy sin el nuevo path y sin el header requerido.
El formato de respuesta también cambió radicalmente (UPPERCASE flat → JSON anidado).

**Solución:**
Migrado al endpoint v2 con normalizador de claves para mantener compatibilidad con el
código consumidor sin tocar 100+ líneas de procesamiento.

---

### ERROR-007: Webhooks ML rechazados con 400 CSRF

**Reportado:** 10 Abril 2026
**Severidad:** Alta
**Estado:** Resuelto

**Síntomas:**
```
werkzeug: POST /odoo/meli_notify/keleb 400
odoo.http: No CSRF validation token provided for path '/odoo/meli_notify/keleb'
```

**Causa raíz:**
Los decorators de route de `/meli_notify` y `/meli_notify/<login_id>` no tenían
`csrf=False`. Odoo rechazaba los POST externos de ML.

**Solución:**
Agregado `csrf=False` a ambos decorators. La validación de origen se hace via
`application_id` y `user_id` en el handler.

---

## ERROR-011 — `stock_inventory_action_done` está roto (defecto DORMIDO, no activo) · 18.0 · 12-ago-2026
**Dónde:** `meli_oerp/18.0/models/versions.py:527-543` (`stock_inventory_action_done`).
**Qué:** la función recibe el parámetro `stock`, pero en la línea 537 usa **`_stock`**, que **no está
definido en su ámbito** ni existe como global del módulo (única aparición en todo el archivo).
Si se ejecuta, muere con `NameError` antes de escribir el quant.

**Por qué no está causando daño hoy:** su único llamador
(`meli_oerp/18.0/models/product.py:4948`) está detrás de **`if (1==2 and ...)`** — condición imposible
por construcción, o sea desactivado a propósito. Nunca corre.
Los otros dos llamadores (`meli_oerp_stock/18.0/models/product.py:532`,
`meli_oerp_multiple/18.0/models/product.py:1852`) invocan `self.env['stock.inventory']`, **modelo que
no existe desde Odoo 15**. También muertos.

**Por qué se registra igual:** es la ÚNICA vía del suite que escribe cantidades de inventario
(`stock_inv_model = "stock.quant"` + `inventory_quantity` + `_apply_inventory()`). El día que alguien
reactive ese `1==2` para volver a sincronizar stock por ajuste, **revienta en la primera corrida**.
Arreglo trivial (`_stock` → `stock`), pero conviene decidir a la vez si ese camino debe existir.

**Cómo salió a la luz:** midiendo el stock negativo de **DT TEC (533)** para descartar que fuera
nuestro. Se descartó — y con motivo verificable, no por confianza.
Plan: `.roots/tasks/PLAN-2026-08-12-533-dttec-triage.md`.

## ERROR-012 — 🔴 FLOTA: `UpdateProductType` fuerza `invoice_policy='order'` en Odoo 18 · 12-ago-2026
**Severidad: alta.** Le pisa al cliente una decisión de negocio en **cada importación de orden ML**, y
en silencio. Detectado en **DT TEC (533)**, pero afecta a **cualquier cliente en Odoo 18** con el suite.

**Cadena (verificada eslabón por eslabón, no inferida):**
1. **Core Odoo 18** — `addons/sale/models/product_template.py:169-171`:
   ```python
   @api.depends('type')
   def _compute_invoice_policy(self):
       self.filtered(lambda t: t.type == 'consu' or not t.invoice_policy).invoice_policy = 'order'
   ```
   `invoice_policy` es `compute=… store=True readonly=False precompute=True tracking=True`.
   ⇒ **cualquier `write` que toque `type` en un template `consu` fuerza `order`**, pisando al usuario.
2. **Nosotros** — `meli_oerp/models/versions.py:385-402`, `UpdateProductType()`:
   ```python
   if (prod and "type" in prod._fields and prod.type not in ['product']):
       prod.write( { 'type': 'consu' } )     # ← 402
   ```
3. **El guard es de Odoo ≤16.** Ahí almacenable era `'product'`; **en Odoo 18 ese valor no existe**, así
   que la condición **siempre** da verdadero y el `write` corre **en cada pasada aunque no cambie nada**.
4. **Llamadores:** `meli_oerp/models/orders.py:4171` (dentro de `orders_update_order_json` = **cada
   importación de orden ML**), `meli_oerp/models/product.py:2598`,
   `meli_oerp_multiple/models/connection_account.py:6735` y `:6745`.

**Prueba (audit trail, no razonamiento):** `invoice_policy` tiene `tracking=100` ⇒ `mail_tracking_value`.
El cambio del usuario aparece en **es_MX** ("Cantidad ordenada"→"Cantidades entregadas") y el revert con
etiquetas **en_US** (contexto de servidor, no de UI) **en el mismo segundo que se crea la SO de ML**:
SO `ML 2000014490513871` 15:12:44 → revert del template 20435 15:12:47. Ídem 04:12:36/38 y 23:12:43/47.
El write tocó **sólo** `invoice_policy`.

**Impacto real medido:** la clienta corrigió 5 productos a mano entre 14:55 y 15:12 UTC y el conector le
**pisó 3** en el día. Estaba peleando contra el bug en vivo sin saberlo.

**Fix propuesto (sin implementar):** corregir el guard para que refleje los valores de Odoo 17/18
(`'consu'`/`'combo'`/`is_storable`) y, sobre todo, **no escribir si no hay cambio** —
`if prod.type != 'consu': prod.write(...)`. Con eso el `_compute` no se dispara.
⚠️ Al tocarlo hay que revisar el **efecto colateral inverso**: productos que hoy quedan en `order` por
este camino y cuyos clientes ya se acostumbraron.

**Cómo salió a la luz:** midiendo `#537`/`#518` de DT TEC. La búsqueda previa concluyó *"el suite no
escribe `invoice_policy`"* — **literalmente cierto y prácticamente falso**: no lo escribimos, lo
**disparamos** vía `type`. Lección: buscar el campo por nombre **no alcanza** cuando es un `compute`
almacenado; hay que buscar también **sus `@api.depends`**.

**Relacionado:** `ERROR-011` (`stock_inventory_action_done` dormido).
Plan: `.roots/tasks/PLAN-2026-08-12-533-dttec-triage.md`.

### ERROR-012 · AMPLIACIÓN (12-ago, 2ª medición) — **son 4 sitios, no 1**, y hay 2 defectos más
La entrada original acotaba el fix a `UpdateProductType`. **Insuficiente.** Medido:

**a) Otros 3 sitios escriben el tipo SIN NINGÚN guard** (`ProductType()` = `{"type":"consu","is_storable":True}`):
`meli_oerp/models/product.py:2881` · `meli_oerp_multiple/models/product.py:1454` y `:1694`.
Los usos dentro de `create` (`orders.py:4120`, `connection_account.py:5640/5708`, `sale.py:823`) **sí** son
correctos: en creación no hay política previa que pisar.

**b) `UpdateProductType` tiene además un `UPDATE` SQL crudo** —
`UPDATE product_template SET type='consu', is_storable=True WHERE id=…` — que saltea compute, tracking
y constraints. Se elimina.

**c) Guard invertido:** `if (prod.is_storable): prod.write({'is_storable': True})` — sólo escribe `True`
cuando **ya** es `True`. ⇒ **el objetivo real de la función nunca se cumple**: un producto no-almacenable
jamás se corrige.

**¿Hace falta forzar `type` en 18? Hoy no.** El bit que importa es `is_storable`; todo bien físico nace
`consu`. En DT TEC, el **100%** de los templates ligados a publicaciones ML ya está `consu` + `is_storable`.
Queda un caso legítimo: un producto dado de alta como `service` que se publica — ahí el cambio de tipo es
real y el reset de política es consecuencia, no daño. Por eso el fix **preserva `invoice_policy`** alrededor
del write en vez de sólo evitarlo.

**Dos hechos que hay que decir juntos al planificar el deploy (medidos, no estimados):**
1. **Deployar NO mueve datos del cliente.** `_compute_invoice_policy` no se re-dispara al actualizar el
   módulo: la actualización del 27-jul escribió 4.226 productos y dejó **0 filas** de tracking en
   `invoice_policy`. (Vale desde el 06-abr-2026, que es donde arranca el tracking.)
2. **Y NO repara nada.** El compute **sólo asigna `'order'`, nunca `'delivery'`** ⇒ cero productos vuelven
   solos. Los que ya están mal hay que setearlos aparte, de común acuerdo con el cliente.

**Alcance real en DT TEC:** de **724** en `order` hoy, **674 son `service`** (normal) y **50 son bienes**
(el problema). Con rastro de revert automático: **9 templates**. Y esos 9 tuvieron **2.616 pedidos NO-ML**
en 2026 ⇒ **no pisamos productos ajenos a ML: pisamos productos de ML que el cliente vende mayormente
FUERA de ML**. Por eso le rompe mostrador y almacén, tal como dijo.
⚠️ Los otros 721 **no prueban decisión del cliente**: el core pone `order` en la **creación** de todo
`consu` (`precompute=True`) y crear **no deja tracking**.

**Escritor efectivo:** el **import de órdenes** (`orders.py:4171`), no el cron de productos — cada revert
coincide **al segundo** con la importación de una orden ML que contiene ese producto. ⇒ apagar el cron de
productos **no** protege al cliente; sólo el deploy.
