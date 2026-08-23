# meli_oerp - Fixes Log

> Historial de correcciones implementadas.

---

### 23 ago 2026 — el flete informado por ML se perdia: lo pisaba la valvula del cap de cobrable — v26.96 `[#411 Shoppy]`

Criterio del cliente, textual (ticket #411, 20-ago-2026): *"confirmamos que queremos que el conector
cargue la linea de envio con el importe correspondiente siempre que MercadoLibre informe que el
comprador pago el envio, incluso si el calculo interno de MercadoLibre no lo devuelva en el momento de
creacion de la venta."*

**El cero NO era falta de dato.** Medido contra la instancia (XMLRPC read-only, 0 escrituras): el
importe estaba (`payments_shipment_amount` 4.960,54). Lo pisaba la valvula `shipment_amount_cond_fix`
de `shipment.py`, que baja el flete a 0 cuando el total de la venta supera lo cobrable segun
`meli_amount_to_invoice` — y ese cobrable se derrumba porque resta un `discount_seller_amount` de
62.205,93 con `coupon_amount` en 0, que **no entra en el cap de `orders.py`**.
**No es un caso aislado:** 39 ventas desde el 1-ago, 36 de ellas cierran exacto.

- *Fix:* flag **`mercadolibre_force_shipping_from_ml`** (Boolean, **default False**, opt-in por cuenta),
  declarado con el MISMO default en `res.company` (`meli_oerp`) y en `mercadolibre.configuration`
  (`meli_oerp_multiple`), visible en la vista de la cuenta.
- `versions.meli_informed_shipping_amount(sorder, config)` devuelve el flete BRUTO informado por ML, o
  **0.0 = no forzar**. Suma sobre TODAS las `meli_orders` de la venta (packs).
- `shipment._update_sale_order_shipping_info` lo usa como `del_price` y, cuando esta validado, **no deja
  correr** la valvula `shipment_amount_cond_fix`.
- El importe pasa por `ml_product_price_conversion`: con `tax_included = tax_excluded` (como esta
  Shoppy) el bruto se netea del IVA igual que cualquier otra fuente de flete. **No se puentea el
  tratamiento impositivo.**

⚠️ **Lo que este fix NO hace, y hay que decirlo antes de prometerlo:**
1. **Sin encender el flag no cambia nada.** Instalar el modulo no alcanza.
2. **Las ventas viejas no se corrigen solas.** 26 ventas `done` sin facturar de agosto quedan con el
   envio en 0: el early-return para ventas `done`/locked **no se toco** (es deliberadamente
   conservador). Corregirlas es una corrida aparte.
3. **Las ya facturadas no se tocan** (guard #493).

---

### 23 ago 2026 — la cancelacion de ML que no se podia aplicar salia de la cola PARA SIEMPRE — v26.95 `[#494 Shoppy]`

`orders_resync_status` (el cron de re-sync de estado del #475) escribe `order.status = 'cancelled'` en
cuanto ML lo informa, y **su propio dominio de barrido excluye** `("status","not in",("cancelled","invalid"))`.
Si en esa misma pasada `meli_cancel_with_detail()` abortaba — el caso normal cuando ya hay factura
publicada sin resolver, que en Shoppy es el **100%** de los casos — la venta quedaba viva y el pedido
ML **no volvia a entrar al barrido nunca**. Mismo patron que
[[meli-estado-de-error-saca-la-publicacion-de-la-cola-para-siempre]].

El unico rastro eran (a) un aviso en el chatter con `once_key`, o sea **una sola vez**, y (b) el banner
del formulario, que exige abrir las ventas **de a una**. Con 96 ventas en esa situacion, eso no es
observabilidad.

- *Fix 1 (el limbo):* `mercadolibre.orders._orders_redrain_pending_cancels()`, segunda pasada **local**
  al final de cada ciclo del cron: busca en la base los pedidos ML `status='cancelled'` cuya venta sigue
  en `draft/sent/sale/done` y los vuelve a pasar por `meli_cancel_with_detail()`. **Cero llamadas a la
  API.** Idempotente: si la factura sigue publicada el helper vuelve a abortar sin efectos (los avisos
  ya estan protegidos por `once_key`). Ventana `mercadolibre_cron_orders_redrain_days` (default 90,
  `0` = off). El backlog que sigue trabado se emite como **WARNING**, no como info — que es exactamente
  el defecto que le costo meses a este mismo cliente en el #521.
- *Fix 2 (paridad de estado):* `update_order_status()` escribia `sorder.meli_status = 'cancelled'`;
  `orders_resync_status()` **no**. Como `meli_status` es stored y solo se refresca via el compute no
  almacenado `_meli_status_brief` (o sea al abrir el registro), el banner
  `meli_cancel_pending_banner` y cualquier filtro por `meli_status` **mentian** hasta que un humano
  entrara a la venta. Ahora las dos rutas lo escriben.
- *Fix 3 (que el cliente pueda auditarlo el):* campo `sale.order.meli_cancel_pending`
  (compute+store+index) + filtro **"Cancelado en ML, vivo en Odoo"** en las dos vistas de busqueda de
  ventas. Hasta ahora ese listado se armaba a mano en CSV (10/8, 19/8, 21/8) y **el numero cambiaba con
  el criterio de quien lo armaba** (72 -> 80 -> 96). Con el campo, el criterio es uno solo y esta en el
  codigo.
- ⚠️ *Lo que este fix NO hace, a proposito:* **no** cambia el default de
  `mercadolibre_invoice_cancel_mode` (sigue en `manual`) y **no** toca ninguna factura publicada. Que el
  numero deje de **crecer** depende de esa configuracion, que es una decision fiscal del cliente. Ver
  `.roots/tasks/PLAN-2026-08-23-494-cancelar-venta-al-cancelar-ml.md`.
- 🔎 *Punto ciego conocido, NO corregido (falta medirlo):* el dominio de `orders_resync_status` excluye
  `shipment_status = 'delivered'` con el argumento de que *"la cancelacion por el comprador es SIEMPRE
  pre-entrega"*. Eso **no vale para mediaciones**: en Shoppy hay 9 canceladas por `mediations` que
  pueden caer ahi y no ser re-consultadas nunca. Requiere medir en la instancia antes de tocar el
  dominio (costo de API).
- *Tests:* `tests/test_meli_cancel.py` (TransactionCase, tag `meli_cancel`) cubre los 5 bordes
  (borrador / confirmada / entregada / facturada / con pago conciliado) + el re-drain.
  ⚠️ **Escritos pero NO ejecutados** en esta sesion: no habia entorno Odoo 16 con base para correrlos.

---

### 10 ago 2026 — el guard de venta facturada tenia TRES bypass (y el aviso del chatter mentia) — v26.93 `[#493 Shoppy]`

El fix `de715a23` (26.89) puso el guard **dentro de `set_delivery_line`**, con un comentario que
afirmaba que ese era *"el unico lugar por el que pasan TODAS las reescrituras de la linea de envio"*.
**No era cierto.** Medido en prod de Shoppy: 51/51 ventas con el aviso tenian la linea en 0.00, y 32
quedaron por debajo de su factura por **$196.318,54** entre el 31/7 y el 6/8.

Los tres caminos que lo esquivaban:
1. `models/shipment.py` — tras llamar a `set_delivery_line()` (donde el guard aborta), el **mismo
   bloque** escribia `delivery_line.price_unit = 0.0` y `qty_to_invoice = 0` **directo sobre la linea**.
   Este era el culpable vivo.
2. `models/shipment.py` — `sorder._remove_delivery_line()` con `including_shipping_cost == "never"`:
   borra la linea entera, la reescritura mas destructiva, y era la unica sin guard.
3. `meli_oerp_multiple/models/versions.py` — copia de `set_delivery_line` sin guard (ver su fixes-log).

- *Fix:* el guard se extrajo a `versions.py::_meli_guard_delivery_write(sorder, line, price)` y lo
  consultan **los tres** caminos antes de escribir. No levanta: ante error deja pasar la escritura
  (comportamiento previo) y loguea.
- ⚠️ *Ojo con el `import *`:* `shipment.py` hace `from .versions import *`, que **no trae nombres con
  guion bajo** — el guard se importa explicito.
- *Por que importa el aviso falso:* mientras el bypass existia, el chatter decia "Cambio no aplicado"
  sobre un cambio que si se aplico. Es lo que el cliente nos marco el 5/8.

---

### 30 jul 2026 - fix(orders): Odoo 16/17 nunca ejecutaban el guard de devolucion -> bucle infinito en ventas ML canceladas (v16.0.26.90) [Just 148]

**Sintoma** (prod Just, cuenta 148, Odoo 16.0): desde que una orden ML se cancela DESPUES de facturada
y despachada, cada ciclo del cron (~5 min, 2 veces por ciclo) loguea
`ERROR ... Error creating return for picking MELI/OUT/00548: Por favor, especifique al menos una
cantidad que no sea cero` + `WARNING meli_cancel_with_detail: orden ML ... NO cancelada - factura
publicada sin resolver`. Medido: **1 picking el 28-jul -> 2 el 29-jul**, **199 -> 514 ERROR/dia**,
**407 -> 2047 mensajes** de spam en el chatter de 2 sale.order. Crece con cada cancelacion nueva.

**Causa raiz** (contrastada contra `addons/stock/wizard/stock_picking_return.py` de los 4 cores):
`_meli_return_done_pickings` bifurca por `hasattr` sobre `stock.return.picking`:

| Core | `action_create_returns_all` | `action_create_returns` | `create_returns` | Rama real | Guard 0-qty |
|------|------|------|------|------|------|
| 16.0 | no | no | si (184) | **3a** | **NO** |
| 17.0 | no | no | si (183) | **3a** | **NO** |
| 18.0 | si (186) | si (174) | no | 1a | si |
| 19.0 | si (221) | si (209) | no | 1a | si |

- La 2a rama (`action_create_returns` sin `_all`) es **codigo muerto en las 4 versiones**, y es
  justo donde vivia el guard de cantidad-cero del 13-jun-2026. **16.0/17.0 nunca lo ejecutaban.**
- Ademas, en el core **16.0** `product_return_moves` se llena en `@api.onchange('picking_id')`, y los
  onchange **no corren en `create()`** -> `ReturnWiz.create({})` deja el wizard VACIO -> `_create_returns()`
  tira UserError siempre. En **17.0** el mismo campo es `compute=..., store=True` (depends `picking_id`),
  o sea si se puebla. => **en 16.0 la devolucion automatica nunca funciono**; en 17.0 funcionaba pero sin guard.
- El `except` posteaba al chatter en CADA reintento, y `meli_cancel_with_detail` volvia a postear el aviso
  de "factura publicada sin resolver" en cada pasada. Como la orden nunca llega a cancelarse (la factura
  posted corta el flujo con un `return`), el cron reentra por siempre: 2 mensajes por ciclo.

**Fixes:**
- **F1** poblar las lineas cuando el wizard nace vacio y existe el onchange (`wiz._onchange_picking_id()`).
  No-op en 17.0+ (ya vienen por compute).
- **F2** mismo guard de cantidad-cero en la rama `create_returns` (la que toman 16.0/17.0). La rama muerta
  queda documentada como tal, sin cambiarle el comportamiento.
- **F3** avisos idempotentes: `meli_message_post(..., once_key=...)` nuevo en `models/versions.py`. Marca el
  body con un comentario HTML invisible `<!-- meli-once:<key> -->` y no repostea si ya esta en el chatter.
  Ojo con el escape por version: 16.0 **no** escapa el body en `message_post`; 17.0/18.0/19.0 hacen
  `escape(body)` salvo `Markup` -> el helper devuelve `markup_escape(body) + Markup(marker)`, asi el texto se
  ve igual en las 4 y la marca queda invisible. `html_sanitize` **conserva** los comentarios
  (`'comments': False` en el Cleaner, verificado en los 4 cores).

**Alcance:** bug del source, no del cliente — pega a **todo cliente 16.0/17.0** con una venta ML cancelada
despues del despacho. Caso de prueba real: picking `MELI/OUT/00548` (id 46749) y `MELI/OUT/00553` (id 47038),
SOs `ML 2000014232660469` / `ML 2000014243455389`.

### 28 jul 2026 - fix(stock): el sello de movimientos se congelaba, drift permanente e invisible (v16.0.26.88) [OrgVit 475]

**Causa raiz** (analisis completo en `.roots/debug/2026-07-28-stock-queue-invariant-y-kits.md`):
`_meli_stock_moves_update()` calculaba el campo con `MAX(stock_move.create_date)`. `create_date` es
cuando se creo la FILA, no cuando cambio el stock, y el maximo **se congela** en cuanto deja de crearse
movimientos nuevos. Como `stock_update` se sella en cada push, la condicion de cola
(`meli_stock_moves_update > stock_update`, en `mercadolibre.product._meli_stock_status`) deja de
cumplirse **para siempre**: el binding queda `updated`, fuera de la cola, sin error y sin log. Quedaban
invisibles todos los cambios que no crean fila nueva: validar un move creado dias antes (**209 en 60
dias** en una sola cuenta), reservar/desreservar, cancelar, editar cantidad.

**Fixes (F1 + F3 + H1):**
- **F1a** el sello ahora es `GREATEST(date si state='done', write_date, create_date)`. `date` solo en
  los `done` porque en los demas es una fecha PREVISTA (futura) y adelantaria el sello a un evento que
  no ocurrio. `write_date` es lo que capta validar/reservar/cancelar sobre movimientos ya existentes.
- **F1b** el campo es **monotono** (`_meli_write_moves_stamp`): nunca retrocede. Sin esto, un recomputo
  pisaba hacia atras el `NOW()` que escriben por SQL los hooks de cancel/unreserve
  (`meli_oerp_multiple/models/stock_move.py`) y **anulaba una entrada de cola pendiente**.
- **F1c** mismo criterio en los caminos batch (`_process_stock_update_orm_batch`) y
  `GREATEST(actual, NOW())` en `_process_stock_update_sql_only`. Nuevo helper
  `_meli_move_stamps_by_product()`: una sola query agregada en vez de iterar `stock_move_ids` en Python
  (en productos con miles de movimientos era carisimo).
- **F3** `meli_stock_diagnostic` **persiste** el `status` que ML acaba de devolver
  (`_meli_diag_persist_ml_status`). Antes lo leia, lo logueaba y lo tiraba: `meli_last_status` solo se
  refrescaba en el push, y las publicaciones que nunca entran a la cola nunca se pushean, con lo cual el
  campo quedaba congelado meses (**994 marcadas `paused` que en ML estaban activas** en una cuenta real),
  ensuciando el propio diagnostico con falsos "pausada con stock = perdida de ventas" y quemando ~100
  llamadas API cada 30 min. Costo: **0 llamadas extra**, la respuesta ya estaba en la mano.
- **H1** `product_post_stock` devolvia un dict vacio (= exito) **despues de tragarse la excepcion**: el
  llamador marcaba el binding como publicado. Ahora el error viaja en el `return`.

**Archivos:** `models/product.py`, `models/company.py`, `__manifest__.py`.
**Verificacion:** `ast.parse` OK en las 4 versiones. Convergencia 16=17=18=19 (16.0 conserva su
`_sql_constraints` propio; el resto byte-identico). Branch `claude/stock-queue-invariant-2687-<ver>`.
**Merge a la rama de deploy y deploy a clientes: NO - lo confirma FCA aparte.**
### 24 jul 2026 — fix(tz): `estimated_buffering_date` Datetime→Date, self-service deadline mostraba día anterior (v16.0.26.92 — escrito el 24-jul, landeado el 10-ago) `[#420 Shoppy]`

Diagnóstico en vivo (XMLRPC prod Shoppy): `estimated_buffering_date` era `fields.Datetime` poblado con
`ml_datetime(shipping_option.buffering.date)`. ML manda el buffering como **día-calendario a medianoche-UTC**
(`YYYY-MM-DD 00:00:00Z`) → se guardaba el timestamp y renderizaba **21:00 del día anterior** en AR (-03).
Semánticamente es un DÍA (deadline de despacho self_service), no un instante → el campo pasa a `fields.Date`.

**Cambios:**
- `models/versions.py`: nuevo helper `ml_date(datestr)` (hermano de `ml_datetime`, devuelve `'%Y-%m-%d'`).
- `models/shipment.py`: field `estimated_buffering_date` `fields.Datetime`→`fields.Date`; asignación del import
  `ml_datetime(so_buf["date"])`→`ml_date(...)`; compute `_compute_handling_limit_status` compara el buffering
  al **fin del día** (`datetime.combine(date, time.max)`) para no romper el `<` contra `now`.
- `models/orders.py::_compute_so_handling_limit_status` y
  `meli_oerp_stock/models/stock_location.py::_compute_picking_handling_limit_status`: misma corrección
  fin-de-día (en stock_location se amplió el import a `datetime, time`).
- Mirror `mercadolibre.bind_shipment` (meli_oerp_multiple): hereda el field de `mercadolibre.shipment`
  (herencia por prototipo) → pasa a Date automáticamente; **no** hay override propio que tocar.
- `views/shipment_view.xml`: `widget="date"` explícito (2 ocurrencias).
- **Migraciones de datos** (arreglan el histórico sin re-pull, cast timestamp→date vía `::date`):
  `meli_oerp/migrations/16.0.26.86/pre-migrate.py` (tabla `mercadolibre_shipment`) y
  `meli_oerp_multiple/migrations/16.0.26.82/pre-migrate.py` (tabla espejo `mercadolibre_bind_shipment`).

**Archivos:** `models/versions.py`, `models/shipment.py`, `models/orders.py`, `views/shipment_view.xml`,
`migrations/16.0.26.86/pre-migrate.py`, `__manifest__.py` (+ `meli_oerp_stock`, `meli_oerp_multiple`).
**Verificación:** `py_compile` + XML parse OK. Branch `claude/fix-buffering-date` (16.0, los 3 módulos).
Merge a deploy + promoción al 17/18/19 + deploy a prod: **NO** (pendiente, ver meli-promotions-pending).

### 19 jul 2026 — feat(promoción cliente→source): comprador + zona del receiver buscables en sale.order (v16.0.26.83) [#404 Deco]

Promoción cliente→source (grove meli) del feature implementado en Deco/KPI (cuenta 526, commit cliente
`09723b1`). Genérico, sin nada Deco-específico. `sale.order`: `meli_buyer_nickname`/`meli_buyer_id`
(computed+store+index desde `meli_buyer`) y `meli_receiver_state/city/neighborhood/zip_code`
(related+store+index desde `meli_shipment`); `mercadolibre.shipment` gana `receiver_neighborhood`/
`receiver_municipality` + parse; vistas search+form. Ver changelog 26.83 y migrations.

**Archivos:** `models/orders.py`, `models/shipment.py`, `views/orders_view.xml`, `__manifest__.py`.
**Verificación:** py_compile + xmllint OK. Convergencia 16≡17≡18≡19 (inserción byte-idéntica).
Branch `claude/meli-deco-receiver-fields-16.0` (push automático). Merge a deploy + push a prod: NO (a confirmar con el usuario).
### 20 jul 2026 — savepoints anti-`InFailedSqlTransaction` en import de categorías/productos (v16.0.26.83) `[#410 SOLSUN]`

Promoción cliente→source (SOLSUN 381, rama `claude/fix-odoo-server-error-VVNHH`, marcadores `# [solsun-local]`).
El source **no los tenía** (verificado leyendo el código pinneado en las 4 versiones). Patrón: `except`
desnudos atrapaban la excepción Python pero dejaban la transacción PG abortada → el SQL siguiente moría
con `InFailedSqlTransaction` en cascada; el savepoint aísla el fallo.

**Archivos:** `models/category.py`, `models/product.py`.

**Cambios:**
1. `category.py · import_category`: savepoints alrededor de `_get_attributes` y `get_search_chart_filters`
   en **ambos** call-sites (camino create **y** camino write; el fix original del cliente sólo cubría el
   create). Cierra la causa raíz del FK violation `meli_category` (#410 BUG 3) — complementario al fix de
   síntoma ya presente en el source (`eb68d899`).
2. `product.py`: savepoint alrededor de `_meli_set_category` (un fallo suyo tumbaba el resto de la sync).

**Convergencia:** inserción byte-idéntica 16≡17≡18≡19 (anchors idénticos). py_compile OK ×4.
Rama `claude/meli-solsun-savepoints-16.0`. Push del `claude/*` hecho; SIN merge a deploy.

---

### 14 jul 2026 — hardening(meli_util): forward-port firma extra_headers/**kwargs consistente en get/post/put/delete `[ERROR-008]`

**Propaga a 16.0** el hardening ya aplicado en 17.0 (26.78, ver su fixes-log). Convergencia horizontal del grove.

**Archivos:** `meli_oerp/models/meli_util.py` (v16.0.26.78)

**Cambios (idénticos a 17.0):**
1. `MeliApiNoSDK` y `MeliApiSDK`: TODAS las variantes (`get`, `get_mini`, `post`, `post_mini`, `put`,
   `put_mini`, `delete`) ahora aceptan `extra_headers=None` con misma firma/semántica (merge en headers
   finales, o delegación a `*_mini` en el caso SDK sin hook de headers por-llamada).
2. `**kwargs` agregado a todas esas variantes (ambas clases) como red de seguridad anti-`TypeError` por firma.
3. Fix real: `get_mini`/`post_mini`/`put_mini` de NoSDK no propagaban `extra_headers` al delegar; ahora sí.

**Verificación:** `python3 -m py_compile` OK. Sin deploy. Push lo confirma el usuario.

---

### 12 jul 2026 — BUG-018 (PROPUESTO, sin deploy): `KeyError('attributes')` en `fetchIVA`/`fetchImpuestoInterno` — item ML 404 sin `attributes` `[justdistribution]`

**Reportado:** prod JustDistribution — `meli_oerp_multiple.models.connection_notification: _process_notification_order >> 'attributes'` repetido ~637 veces/día, siempre precedido de `meli_oerp.models.orders: Warning adding sale.order. Normally a pack order.`
**Estado:** Diagnosticado + fix escrito en el source, **pendiente de validación del usuario antes de deploy**
**Archivo:** `models/orders.py` (`fetchIVA` línea ~2203, `fetchImpuestoInterno` línea ~2233)

**Causa raíz:** al procesar los `order_items` de una orden pack (`orders_update_order_json`), por cada
ítem se pide el detalle a `/items/{id}` con `include_attributes=all` y se llama `fetchIVA(rjson=rjson3)`,
que hace `for att in rjson['attributes']:` sin guardia. Confirmado en vivo (llamada read-only a la API
ML desde prod) que para el ítem `MLA1428496705` (variación de una orden pack real del log de hoy) la
API devuelve **404**: `{'error': 'get error', 'status': 404, 'cause': 'Not Found', 'message': '...Item
with id MLA1428496705 not found...'}` — un dict NO vacío (pasa el check `if rjson:`) pero sin key
`attributes` → `KeyError`. La excepción no está capturada en `orders_update_order_json`, sube sin
trap hasta el `except Exception` de `_process_notification_order` en `meli_oerp_multiple`, que marca
la notificación `FAILED` y la reintenta en el próximo ciclo del cron (~45s) — loop infinito para
notificaciones que referencian publicaciones eliminadas/vencidas de MercadoLibre. No bloquea ventas
(la SO/factura sigue su curso normal; el error es solo en el enriquecimiento de IVA/impuesto interno
del ítem para el log).

**Fix propuesto:** `rjson.get('attributes') or []` en ambas funciones (`fetchIVA` y
`fetchImpuestoInterno`, mismo patrón, la segunda no tiene caller activo hoy pero comparte el bug).
Sin cambio de comportamiento para el caso normal (ítem con attributes) — cuando faltan, el loop
simplemente no encuentra IVA/impuesto interno (igual que el `else` ya contemplado) en vez de crashear.

**Pendiente:**
- Validar con el usuario antes de deployar.
- Portar el mismo fix a `meli_oerp/17.0`, `18.0`, `19.0` (mismo código, mismas líneas).

---

### 12 jul 2026 — [C] backport meli_confirm_ready (BUG-015 visibilidad) + BUG-011 dedup nombre contacto
- **[C] BUG-015** (backport 19.0 `c04bddd2`): helper read-only `meli_confirm_ready` en `sale.order` y
  `mercadolibre.orders` (comparte la matemática de `confirm_ml`) para LISTAR ventas ML trabadas/incompletas.
  Alimenta la pestaña "Ventas incompletas" del wizard (meli_oerp_multiple). `models/orders.py`.
- **BUG-011** (dedup nombre): helper module-level `_meli_norm_name`; `buyer_full_name` y `billing_full_name`
  ya NO concatenan el apellido si ML lo manda == nombre (razón social repetida en compradores empresa sin
  persona de contacto). `models/orders.py`.

### 12 jul 2026 — align(horizontal 16≡17≡18≡19): backport returns-guard #339 + meli_util retries-noSDK + default billing_force_on_main (v16.0.26.75)

Convergencia horizontal (sesión flota, SIN push). Tres cambios que faltaban en esta versión:
- **[A] returns-guard `action_create_returns_all` (#339 D VIGI)** — backport del fix 18.0 `b2e9ab02` (2026-07-09).
  El guard cantidad-cero quedaba ciego en Odoo 18+ (`product_return_moves.quantity` nace en 0); el bloque es
  hasattr-safe (rama `action_create_returns_all` para 18+, `elif action_create_returns` para ≤17) → en 16.0 usa
  el `elif` como siempre. `models/orders.py`. Bump 26.73 → 26.74.
- **[B] meli_util `retries=False` en path noSDK con proxy** — backport del fix 19.0 `879c0fa5` (2026-06-18):
  completa el scoping ya decidido (retries=False SOLO con host de rescate activo; inerte sin proxy).
  `models/meli_util.py`. Bump 26.74 → 26.75.
- **default `mercadolibre_billing_force_on_main=True`** (Estrategia B unificada por defecto; informe Dannok
  BUG-012/013) — `models/company.py`. Solo afecta companies NUEVAS; clientes existentes conservan su valor.

### 11 jul 2026 — feat: IDs de atributo ML en errores de publicación resueltos a NOMBRE ES (v16.0.26.73) [#521 Koreautos]

**Archivos/funciones:** `models/warning.py::warning._meli_resolve_attribute_ids` (nuevo),
`models/warning.py::warning._format_meli_error`, `models/warning.py::MELI_PUBLISH_ERROR_PATTERNS`

Los errores de publicación de ML citan atributos por su ID crudo entre corchetes (`[PART_NUMBER]`,
`[BRAND,VEHICLE_TYPE]`), ilegible para el vendedor. Nuevo método `_meli_resolve_attribute_ids(text, cat_id=None)`
(100% defensivo, try/except → texto original) que, con regex `\[([A-Z0-9_]+(?:\s*,\s*[A-Z0-9_]+)*)\]`,
detecta esos códigos y les antepone el nombre real en español tomado de `mercadolibre.category.attribute`
(att_id → name, ES por locale). Scopea por `cat_id` si viene y hace fallback global. Listas `[A,B]` se
expanden legible ("Marca [BRAND], Tipo de vehículo [VEHICLE_TYPE]"). Código no resuelto → se deja crudo.
Se llama sobre el texto ya humanizado (`_hmess`/`ecodemess`) en las 3 ramas de `_format_meli_error`
(dict-cause, string, rcause).

**Acople:** las plantillas genéricas de atributos en `MELI_PUBLISH_ERROR_PATTERNS`
("atributo … ignored" / "attributes … required") ahora emiten el código ENTRE CORCHETES (antes comillas)
para que el resolver lo detecte tras la humanización.

**cat_id:** el flujo de publicación (`product.py ~4468/4471`) entrega al wizard sólo `context={"rjson": rjson}`
con el cuerpo de error de ML (error/message/status/cause), SIN `category_id` → la resolución es global en la
práctica (suficiente: BRAND→"Marca", PART_NUMBER→"Número de pieza" son estables entre categorías). Se dejó
el hook por si a futuro se pasa la categoría del producto.

Antes: `…atributo(s) obligatorio(s) 'PART_NUMBER'…`
Después: `…atributo(s) obligatorio(s) Número de pieza [PART_NUMBER]…`

---

### 10 jul 2026 — feat: humanización de errores de publicación ML + presentación amarillo/rojo pareja (v16.0.26.71) [#532 RPM Motos]

**Archivos/funciones:** `models/warning.py::MELI_PUBLISH_ERROR_PATTERNS`,
`models/warning.py::_meli_humanize_publish_message`, `models/warning.py::warning._format_meli_error`

**GAP 1 (traducción):** el framework de humanización (regex→español) existía pero le faltaban patrones
para errores que le salían a RPM Motos. Agregados a `MELI_PUBLISH_ERROR_PATTERNS`:
- `attributes are required` / `/decorations/build-title` → "Faltan atributos obligatorios de la
  categoría. Completá la ficha técnica del producto (marca, modelo, código universal, etc.)…".
- `body does not contains ... [family_name]` → "Falta el Nombre de la familia (Family Name)…"
  (+ variante genérica que lista la/s propiedad/es faltante/s).
- GTIN/EAN/UPC/código universal **requerido/faltante** (distinto del ya existente "invalid format").
- SELLER_SKU requerido; categoría inválida/requerida.
Orden verificado: los patrones específicos ganan sobre los genéricos (GTIN invalid-format antes que
GTIN-required; build-title antes que el genérico "attributes [X] are required").

**GAP 2 (presentación):** la rama `type(rmessage)==str` de `_format_meli_error` volcaba el string
CRUDO en inglés con ícono `fa-warning` amarillo fijo, sin respetar severidad. El error de build-title
llega justamente como `message` string (no lista `cause`) → se veía pobre. Ahora esa rama:
(1) humaniza el string vía `_meli_humanize_publish_message`, (2) elige severidad/ícono según el status
(`alert-danger`+`times-circle` rojo si error/400; `alert-warning`+`warning` amarillo si advertencia),
(3) agrega un título accionable en `<strong>` y (4) refleja el texto humanizado también en el `message`
plano del wizard. Queda parejo con la rama `cause`.

**Defensivo:** si ningún patrón matchea, se conserva el texto original de ML (nunca se pierde info).
`py_compile` OK. Convergido 16/17/18/19.

---

### 9 jul 2026 — fix: BUG-009 fecha real de ML en `date_order` + BUG-007 cancelación explícita en `update_order_status` (v16.0.26.68) — promoción Dannok `0eff11d`

**Archivos/funciones:** `models/orders.py::mercadolibre_orders.prepare_sale_order_vals`,
`models/orders.py::mercadolibre_orders.update_order_status`

**Origen:** ambos arreglos vivían solo en el repo del cliente Dannok/Delbre (commit `0eff11d`,
07-may) y el re-sync del grove 18.0 (26.27→26.44) los **sobreescribió** al reemplazar `orders.py`
entero (el diff de sync los reportó como "0 custom divergente" porque no eran customizaciones
marcadas). Re-aplicados en el cliente como 26.44.2 y **promovidos ahora al source** para las 4
versiones (16/17/18/19), de modo que un próximo re-sync ya no los pise.

**BUG-009 (`prepare_sale_order_vals`):** `meli_order_fields` ahora setea
`'date_order': ml_datetime(order_json["date_closed"]) or ml_datetime(order_json["date_created"])`
→ la SO refleja la fecha real de la operación en MercadoLibre, no el timestamp de importación en
Odoo. Corrige el síntoma "ventas entrando con delay / fecha que no coincide con ML".

**BUG-007 (`update_order_status`):** se reemplazó la llamada incondicional
`order.sale_order.confirm_ml(...)` por manejo explícito: si `order_json["status"] == "cancelled"` y
la SO no está cancelada → setea `meli_status='cancelled'` y llama `meli_cancel_with_detail(cancel_msg)`
(motivo desde `status_detail`); en cualquier otro estado → `confirm_ml(...)` como antes. Asegura que
las sub-órdenes de un pack disparen la cancelación aunque el path de update no llegue al chequeo. (El
método más nuevo `orders_resync_status` #475 ya tenía este manejo; este arreglo lo lleva también al
re-chequeo puntual `update_order_status`.)

**Verificación:** inserción byte-idéntica en las 4 versiones (anchors convergidos); `py_compile` OK.
Sin migración de datos (`date_order`/`meli_status` ya existen en `sale.order`).

### 8 jul 2026 — perf(backfill): resolucion de cuenta por FETCH DIRECTO por item — funciona en cuentas GRANDES (v16.0.26.64) [#424 Deco/KPI 526]

**Archivos/funciones:** `models/product.py`
- `product.template._meli_backfill_fetch_item(meli, meli_id)` (NUEVO helper, proxy-safe)
- `product.template.action_meli_backfill_template_fields` (reescrito: pre-scan → fetch directo)
- `product.template._meli_backfill_list_ids` (docstring: ahora fallback opcional, ya no lo usa el backfill)

**Problema (verificado prod Deco 526):** el backfill resolvía la cuenta ML dueña de cada ítem
**pre-escaneando la lista completa de ítems de cada cuenta** (`_meli_backfill_list_ids` →
`fetch_list_meli_ids` → `/users/<seller>/items/search` paginado) para armar el mapa
`meli_id→cuenta`. En cuentas GRANDES (DECO tiene **20.834 ítems**) ese pre-scan NO cubre todos los
ítems → muchos productos quedaban SIN resolver dueño → el botón "Traer medidas" no los corregía.
Confirmado: `MLA1685903163` no lo tocaba el backfill, pero un fetch DIRECTO del ítem sí lo corrige.

**Fix:** se eliminó el pre-scan. Ahora, por cada `product.template` a backfillear, se obtiene su
`meli_id` (de la variante vía `_meli_template_variant`) y se hace **fetch directo**
`GET /items/<meli_id>?include_attributes=all` **probando el token de cada cuenta ML logueada**
(las cuentas siguen viniendo del hook `_meli_backfill_get_accounts` — base=res.company,
meli_oerp_multiple=mercadolibre.account) hasta que una devuelve **HTTP 200** = la cuenta dueña (con
token ajeno da 403 access_denied y se prueba la siguiente). Es exactamente la corrección masiva que
se corrió a mano y funcionó. La cuenta que respondió OK se recuerda y se prueba primero (los ítems
de un mismo seller vienen en rachas); luego la compañía del propio producto. El fetch usa
`meli.get()` de la instancia `meli.util` del hook → **proxy-safe** (en clientes con el rescate proxy
rutea por su http_proxy; NO urllib crudo). `_meli_backfill_fetch_item` detecta éxito por
`status_code==200` + rjson dict con `id` y sin `error`.

**Se mantiene:** savepoint por producto (un ítem que falla no corta el lote), log de progreso cada 50,
y la semántica de overwrite del 26.63 (`_meli_import_template_attributes`: SELLER_PACKAGE_* pisa,
brand/model/gender fill-empty) INTACTA — se construye encima. Sin cambio de schema (sin migración).

**Alcance:** solo el backfill (helper nuevo + método). `meli_oerp_multiple` NO cambia: su override de
`_meli_backfill_get_accounts` sólo aporta la lista de cuentas, que el fetch directo consume igual.
`py_compile` OK + bloque byte-idéntico en 16/17/18/19.

---

### 8 jul 2026 — fix(backfill/import): dims del paquete pisan con ML SELLER_PACKAGE_* (v16.0.26.63) [#424 Deco/KPI 526, verificado prod Deco]

**Archivos/funciones:** `models/product.py::product.product._meli_import_template_attributes`

**BUG D (KPI vía WhatsApp, ej. `MLA1685903163` "Cortina 100x200"):** ML trae
`SELLER_PACKAGE_WIDTH='10 cm'` (paquete) y `WIDTH='1 m'` (producto), pero Odoo mostraba
`meli_seller_package_width='100 cm'` = el WIDTH del producto (1 m→100 cm), un valor **legacy** que un
proceso viejo metió en el campo del paquete. El import idempotente lo **preservaba** en vez de
corregirlo.

**Fix:** se dividió la semántica de escritura con `_MELI_IMPORT_OVERWRITE_FIELDS` (= las 4 dims del
paquete): dims del paquete → **OVERWRITE** con `SELLER_PACKAGE_*` siempre que ML traiga valor no-vacío
(ML es autoritativo del paquete); `PACKAGE_*` catalog sigue como fallback SOLO si no hay
`SELLER_PACKAGE_*`; ML vacío NUNCA borra; brand/model/gender siguen **fill-empty**. El backfill usa el
mismo helper → al re-correrlo corrige los ya importados. Sin cambio de schema.

**Commits:** 16 `f8b74fe2` · 17 `fe9ed470` · 18 `0347cf7e` · 19 `a56142de`. Deployado a Deco (patch
quirúrgico, prod `9340ed9`).

---

### 8 jul 2026 — feat(orders): cron dedicado de re-sync de estado para cancelaciones fuera de ventana (v16.0.26.62) [#475 ScoreMX]

**Archivos/funciones:**
- `models/orders.py::mercadolibre_orders.orders_resync_status` (NUEVO)
- `models/company.py::res_company.cron_meli_orders_status` (NUEVO) + campos `mercadolibre_cron_get_orders_status` (bool, default True), `mercadolibre_cron_orders_status_days` (int, default 7), `mercadolibre_cron_orders_status_limit` (int, default 100)
- `data/cron_jobs.xml`: `ir_cron_module_cron_meli_orders_status` (cada 30 min, activo)
- `views/company_view.xml`: los 3 campos en el grupo "Automatización ML a Odoo"

**Problema (#475, suite-wide 16/17/18/19):** el cron horario `cron_meli_orders → meli_query_orders → orders_query_recent → orders_query_iterate` consulta `/orders/search?seller=…&sort=date_desc` (orden por fecha de CREACIÓN). Sin `mercadolibre_filter_order_datetime` la paginación se desactiva (`orders_query_iterate`: `if orders_limit or not order_date_filter: offset_next = 0`) → sólo re-procesa las ~50 órdenes más nuevas por creación. Una orden vieja cancelada días después queda fuera de esa ventana → nunca se re-consulta → la cancelación no baja a Odoo hasta abrir la orden a mano (refresh puntual por ID). El banner `_compute_meli_cancel_pending_banner` ya detectaba el gap pero ningún cron lo resolvía.

**Fix:** cron dedicado que barre `mercadolibre.orders` con `sale_order` NO cancelada, `date_created` en los últimos N días y `status not in (cancelled, invalid)`, ordenado por fecha desc y **acotado por `limit`**. Por pedido hace **UN** `GET /orders/<id>`; si el estado NO cambió, no toca nada (idempotente, barato). Si cambió a `cancelled`, reusa `sale.order.meli_cancel_with_detail` (misma lógica del banner: devolución de albaranes, política de facturas, cancelación de la SO); otros cambios delegan a `orders_update_order` (resync por ID). **Rate-limit:** sólo candidatos recientes+abiertos, tope configurable (default 100), 1 GET por pedido salvo cambio real; respeta el retry/backoff de `meli.get`. Alineado 16≡17≡18≡19 (único delta entre versiones = estilo de `data/cron_jobs.xml` y line-endings preexistentes). Sin push.


### 5 jul 2026 — fix(stock): _fetch_meli_user_product_id devolvía la lista-string str(upids) (v16.0.26.61) [#425 Elvimarta/158] (A2)

**Archivos/funciones:** `models/product.py::product.product._fetch_meli_user_product_id`
- Cuando NO se pedía una variación específica y la publicación tenía variaciones, el método devolvía
  `str(upids)` (p.ej. `"['MLMU123']"`), que se persistía tal cual en `meli_user_product_id`. Eso rompía el
  push de stock por user-products (degradaba a modo standard → `not_modifiable` → estacionado (N1)); es la
  firma de los ~34 `no posted stock try` del reporte.
- Ahora devuelve el `user_product_id` sólo si es **inequívoco** (un único upid distinto entre las variaciones);
  si hay 0 o >1, cae al upid a nivel de item (si existe) o `None` — nunca fabrica un valor. La variación exacta
  (cuando se pide `meli_id_variation`) devuelve su propio upid como antes. Sin push.


### 3 jul 2026 — refactor(backfill): resolución de cuentas a hooks overridables (v16.0.26.60) [#424 Deco/KPI 526]

**Archivos:** `models/product.py` (`product.template`: nuevos hooks `_meli_backfill_get_accounts` + `_meli_backfill_list_ids`; `action_meli_backfill_template_fields` reescrito para usarlos).

- **Contexto:** el backfill 26.59 enumeraba credenciales desde `res.company`
  (`search([('mercadolibre_seller_id','!=',False)])`). En setups multi-cuenta (meli_oerp_multiple) las
  compañías tienen `mercadolibre_seller_id`/token = False (los tokens viven en `mercadolibre.account`), así
  que `meli_by_company` quedaba vacío → `return True` sin poblar nada (verificado en prod Deco: la query daba 0).
- **Fix (base):** se extrajo la parte "enumerar cuentas ML logueadas" y "listar los meli_ids de cada cuenta"
  a dos hooks overridables — `_meli_backfill_get_accounts()` (devuelve dicts `key`/`meli`/`company`/`source`)
  y `_meli_backfill_list_ids(account)` (usa `source.fetch_list_meli_ids`, misma firma en res.company y en
  mercadolibre.account). El loop (mapa `meli_id→cuenta`, fetch con el token correcto,
  `_meli_import_template_attributes`, savepoint por producto) quedó igual y reusable. La base conserva el
  comportamiento single-account (res.company) intacto.
- **Override multi-cuenta:** en `meli_oerp_multiple` (26.60). Ver su fixes-log.


### 3 jul 2026 — fix(backfill): action_meli_backfill_template_fields — meli_id en la variante + multi-cuenta (v16.0.26.59) [#424 Deco/KPI 526, verificado en prod Deco]

**Archivos:** `models/product.py` (`product.template.action_meli_backfill_template_fields` reescrito; helper `product.template._meli_template_variant`), `views/product_view.xml` (filtro del `ir.actions.server`).

- **BUG A — `meli_id` no existe en product.template (está en product.product/variante).** El backfill 26.58
  hacía `self.filtered(lambda t: t.meli_id)`, `self.search([('meli_id','!=',False)])` y `template.meli_id`
  sobre product.template → `ValueError: Invalid field product.template.meli_id`. El filtro del server action
  (`records.filtered(lambda t: t.meli_id)`) rompía igual. **Fix:** resolver la variante con la publicación
  vía `_meli_template_variant()` (`product_variant_ids.filtered("meli_id")[:1]`); el search sin `self` filtra
  por `[('product_variant_ids.meli_id','!=',False)]`; el filtro del server action pasó a
  `any(v.meli_id for v in t.product_variant_ids)`.
- **BUG B — multi-cuenta: usaba un solo token (`env.user.company_id`).** En Deco hay 3 cuentas ML
  (DECO/ECOMMARKET/DELTA), cada ítem pertenece a un seller distinto; leer `/items/<id>` con el token
  equivocado da **403 access_denied** (verificado; con el token del seller dueño devuelve 200 y trae los
  SELLER_PACKAGE_*). **Fix:** el token/cuenta se vive en `res.company` (`mercadolibre_seller_id` + tokens).
  El backfill ahora: (1) arma un `meli.util` por cada compañía ML-configurada logueada
  (`search([('mercadolibre_seller_id','!=',False)])`), (2) resuelve la compañía **dueña de cada ítem** con
  un mapa `meli_id→company` construido perezosamente por cuenta vía `company.fetch_list_meli_ids(meli=...)`
  (lista los items del propio seller — nunca pega a `/items` con el token ajeno), prefiriendo el
  `template.company_id` del producto, y (3) hace el fetch con el token de esa cuenta. Se agrupa por cuenta
  para no re-instanciar por ítem. Savepoint por producto + log de progreso se mantienen.
- **Alcance:** solo el backfill (método + filtro del server action). El mapeo `_meli_import_template_attributes`
  (import ML→Odoo) quedó intacto — verificado OK en prod Deco.
- **Deploy:** re-deploy a Deco (kpi-mas/Deco produccion) lo hace el coordinador.


### 3 jul 2026 — feat(import): ML→Odoo puebla los campos de la pestaña "MELI Plantilla" + backfill (v16.0.26.57) [#424 Deco/KPI 526, suite-wide]

**Archivos:** `models/product.py` (product.product: `_MELI_IMPORT_ATTR_MAP` / `_MELI_IMPORT_ATTR_FALLBACK`, `_meli_attr_value`, `_meli_import_template_attributes`; llamada en `product_meli_get_product` tras escribir meli_fields/tmpl_fields; product.template: `action_meli_backfill_template_fields`), `views/product_view.xml` (botón "Traer medidas" en la pestaña MELI Plantilla + `ir.actions.server` `action_meli_backfill_template_fields_server` como acción de lista).

- **Síntoma (Deco/KPI 526, #424):** al importar un item de ML los campos de la pestaña "MercadoLibre / Plantilla"
  del product.template quedaban vacíos — en particular `meli_seller_package_height/width/length/weight` (Char),
  y también `meli_brand`/`meli_model`/`meli_gender`. Solo se llenaban Categoría y Dominio. Dificultaba la re-publicación
  (Mercado Envíos exige las dimensiones del paquete).
- **Causa raíz:** existía el mapeo Odoo→ML (publish, construye atributos `SELLER_PACKAGE_*` y remapea catalog
  `PACKAGE_*`→`SELLER_PACKAGE_*`), pero **faltaba el inverso** ML→Odoo en el import. Solo había un fragmento parcial
  en la rama "sin variantes con SKU" de `product_meli_get_product`.
- **Fix:** helper `_meli_import_template_attributes(product_template, rjson)` que recorre `rjson['attributes']` y mapea
  `SELLER_PACKAGE_*`→`meli_seller_package_*` (con fallback a los catalog `PACKAGE_*`, misma relación que el publish, en
  sentido inverso), y `BRAND`/`MODEL`/`GENDER`→`meli_brand`/`meli_model`/`meli_gender`. Value extraído de forma robusta
  (`value_name` / `values[0].name` / `value_id`). Escribe en template y variante según exista el campo en cada uno
  (`meli_gender` solo en template). **Idempotente:** solo escribe si ML trae valor no-vacío (no pisa carga manual).
  Se llama en `product_meli_get_product` (cubre CREAR y ACTUALIZAR, ya que `product_template_update` delega ahí).
  Se eliminó el fragmento parcial duplicado.
- **Backfill:** `action_meli_backfill_template_fields` (product.template) relee cada item ML de los productos con
  `meli_id` y completa los faltantes; **savepoint por producto** (un item que falla no aborta el lote) + log de progreso.
  Expuesto como botón en el form y como `ir.actions.server` (acción de lista) sobre product.template.
- **Alcance:** solo los Char (`meli_seller_package_*` + brand/model/gender) + backfill. Las dimensiones estructuradas
  (value Float + uom por dimensión, para MRP) quedan para una FASE 2 aparte.
- **Deploy:** pendiente a Deco (kpi-mas/Deco produccion). El cambio es en `product.py`/`product_view.xml`, NO en los 8
  archivos del rescate proxy → port directo.


### 1 jul 2026 — fix(token): DB neutralizada no rota el refresh_token de ML (v16.0.26.56) [Deco/KPI 526, suite-wide]

**Archivos:** `models/meli_util.py` (`meli.util`: helpers `_meli_is_neutralized` + `_meli_log_neutralized_skip`; guard en `get_new_instance`), `models/company.py` (`res.company.get_meli_state` early no-op).

- **Síntoma (prod Deco 526, verificado):** cuentas ML flapean entre conectado/401. Staging (copia de la DB
  de prod en Odoo.sh) y prod se pelean por el mismo refresh_token de ML, que es rotativo (un solo uso): cada
  refresh del cron de staging invalida el access_token de prod, y viceversa.
- **Causa raíz:** el suite no distinguía la DB neutralizada. El cron "Get Meli State" (cada 10 min) y las
  refrescadas lazy pasan por `meli.util.get_new_instance`, que ante token vencido hace el POST
  `grant_type=refresh_token`. Ese POST **rota el token server-side en ML aunque no se persista** → le roba
  la sesión a producción.
- **Fix:** `_meli_is_neutralized()` lee `ir.config_parameter 'database.is_neutralized'` (parseo robusto
  '1'/'true'/'t'/'yes'; prod = False). En `get_new_instance` el disparador del refresh pasó a `elif` detrás
  de un `if self._meli_is_neutralized()` que NO hace el POST ni el write (needlogin_state queda True; el test
  sigue leyendo con el token vigente hasta que expire). El cron `res.company.get_meli_state` sale temprano
  (no-op) si is_neutralized. INFO una sola vez por proceso (flag de módulo, sin spam). NO se toca el OAuth
  inicial (authorize/callback). Prod (is_neutralized=False) idéntico al comportamiento actual.

### 30 jun 2026 — fix(perms): la creación on-the-fly de producto al importar una orden corre con sudo (v16.0.26.54) [Deco/KPI 526, suite-wide]

**Archivos:** `models/orders.py (`orders_update_order_json`)`

- **Síntoma (2º eslabón tras 26.53):** con el dispatcher ya en su=True, las órdenes con producto EXISTENTE
  importaban OK, pero las de producto INEXISTENTE seguían fallando: `Access Denied by ACLs: create, uid
  <vendedor>, model: product.template/product.product` →
  `productcreated = self.env['product.product'].create(prod_fields)`. La orden quedaba sin la línea
  (shipment: *"product not found in database"*) → cron `Imported N, failed M`.
- **Causa raíz:** `search_meli_product` (y el path equivalente en el base) ya hacían `.sudo()` en sus
  **lecturas** privilegiadas (`product_obj.sudo().search(...)` gated por `mercadolibre_update_product_company`),
  evidencia de que el método se diseñó para correr como el usuario-cron y auto-elevar sus ops privilegiadas;
  pero la **creación** del `product.product` y el **write** de binding (`meli_id`/`meli_pub`) quedaron SIN
  sudo. El su=True del dispatcher cubre la cadena vía el env del recordset, pero el chokepoint de creación de
  producto quedaba expuesto a los grupos del Vendedor ML (que NO incluyen creación de productos). El sudo
  parcial preexistente es el smoking gun: faltaba sudo-ear el create + el bind-write.
- **Fix (suite-wide, chokepoint puntual, NO sudo ciego):**
  - `product.product.create(...)` → `.sudo().create(...)` (alta on-the-fly = integración de sistema).
  - `product_related.write(prod_fields)` (bind meli_id) → `.sudo().write(...)`.
  - El gate de negocio sigue siendo `config.mercadolibre_create_product_from_order`: con la opción OFF NO se
    crea nada; el create-on-order es **opt-in por cuenta**. La atribución (salesperson/team) la fija
    `meli_fix_team()`. Constraints/computes NO se saltan (sudo sólo afecta ACL/reglas).
- **Diseño (creación on-the-fly):** se mantiene config-driven. Recomendación para clientes en fase de
  relevamiento de maestra (p.ej. Deco): considerar DESACTIVAR `mercadolibre_create_product_from_order` para
  no poblar el catálogo con productos sin SKU/costo; el fix garantiza que, con la opción en cualquiera de los
  dos estados, el cron no aborta la importación.

---

### 27 jun 2026 — fix(chatter): idempotencia en message_post anti-spam — PRODUCTO NO ENCONTRADO + Condition not met (v16.0.26.50) [#415 NipSkin/Inity 520]

**Archivos:** `models/orders.py`

- **Síntoma:** el chatter de ciertas órdenes se llenaba de mensajes repetidos en cada ciclo del cron. Dos
  casos: (1) "PRODUCTO NO ENCONTRADO" re-posteado por cada corrida cuando la publicación ML no tenía
  producto en Odoo; (2) "Condition not met: meli_paid_amount and amount_total doesn't match" re-posteado en
  cada intento de confirmación (típico en órdenes con amount_total=0 / sin líneas).
- **Causa:** los `meli_message_post(...)` no tenían guard de idempotencia; el cron reintenta la misma orden
  indefinidamente → un mensaje nuevo por ciclo.
- **Fix:** antes de postear se consulta un slice acotado de `message_ids` (performance):
  - PRODUCTO NO ENCONTRADO: postea sólo si no existe ya un mensaje con "PRODUCTO NO ENCONTRADO" **para ese
    ítem ML** (`_item_meli_id` en el body) en los últimos 50 mensajes.
  - Condition not met (paid_amount): postea sólo si no hay ya un "Condition not met" en los últimos ~5
    mensajes. La validación y el `return {'error': serror}` NO cambian (no se altera el control de flujo).
- **Versiones:** 16/17/18/19. El guard PRODUCTO es byte-idéntico en las 4. El guard "Condition not met"
  difiere por estructura: en 19.0 el serror viene de `meli_confirm_ready()` (refactor) y el guard va en
  `confirm_ml`; en 16/17/18 el serror se arma inline en `confirm_ml` (mismo guard, distinto anchor).
- Solo código Python, sin migración. Reportado por NipSkin/Inity (account 520, Odoo 19), tickets #414/#415.

---
### 25 jun 2026 — fix(category): cache RAM de meli_get_category devolvia ids huerfanos → FK violation meli_category (v26.48) [#410 Solsun]

**Archivos:** `models/category.py` (`meli_get_category`), `models/product.py` (`_meli_set_category`)

- **Síntoma:** al sincronizar/actualizar productos: `insert or update on table mercadolibre_product_template
  violates foreign key constraint ... Key (meli_category)=(1) is not present in table mercadolibre_category`,
  seguido de `InFailedSqlTransaction` en los productos siguientes de la misma corrida.
- **Causa:** `_CATEGORY_CACHE` (cache en RAM por `(db, category_id)`) guarda el **id de DB** de la
  `mercadolibre.category`. Si la transaccion que creo la categoria (via `import_category`) hace **rollback**,
  el id cacheado queda **huerfano** (nunca se committeo). La siguiente llamada para la misma categoria
  devolvia ese id desde RAM sin revalidar → `product.write({'meli_category': <id inexistente>})` → FK violation
  que aborta la transaccion de toda la sync. El `id=1` es consistente con la primera categoria creada en un
  worker que luego rollbackeo.
- **Fix (2 capas):**
  1. *Cache hit:* antes de devolver el id cacheado se valida con `.browse(id).exists()`; si no existe se
     descarta la entrada (`del`) y se recomputa. Ademas se **cachea solo lookups exitosos** (`if mlcatid:`) —
     un `mlcatid` vacio (login pendiente / categoria inexistente / fallo transitorio) ya no envenena llamadas
     posteriores.
  2. *Defensa-en-profundidad:* `_meli_set_category` solo escribe el FK si el id existe de verdad
     (`mlcatid and ...browse(mlcatid).exists()`).
- **Versiones:** 16/17/18/19 (bloque byte-identico, edicion identica). Solo codigo Python, sin migracion.

---

### 17 jun 2026 — fix(report): o.type → o.move_type en report_invoice_shipment (v26.47)

**Archivo:** `report/report_invoice_shipment_view.xml` (línea 36, activa — la línea 23 está comentada)

- **Síntoma:** QWebException al renderizar el reporte de factura+envío en Odoo 16+.
- **Causa:** `account.move` usa `move_type` desde Odoo 16 (el campo `type` no existe). El template activo `report_invoice_shipment` comparaba `o.type in ('in_invoice', 'in_refund')` → AttributeError / QWebException en render.
- **Fix:** `o.type` → `o.move_type` en la línea 36 del template activo. La línea 23 (mismo patrón) está dentro de un bloque XML comentado `<!--template...-->` — no se tocó.
- **Versiones:** roto y corregido en 16/17/18/19 (Odoo 16 también usa move_type, no type).
- **Validación:** xmllint OK en las 4 versiones.
- **Commits:** 16.0→36b45828 / 17.0→52ee5b06 / 18.0→0b930d0b / 19.0→be80600f

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


### 11 jun 2026 — fix(payment_term): no forzar el término de pago (respetar el del tercero) (v40)

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

### 24 jul 2026 — Backport: `sale.order.meli_unread_messages` no se materializaba, `-u meli_oerp` abortaba con ParseError (v16.0.26.86) [#499 Deco/KPI]

**Backport idéntico del fix verificado en 19.0** (commits `2b9e9ca9` + `8f175a74`). El bug es
byte-idéntico en 16/17/18/19: mismo `models/orders.py` (líneas 116-117: `meli_order_id` Char +
`meli_orders` Many2many) y mismo `models/sale_order.py` huérfano con los `related` rotos.

**Causa raíz:** `models/sale_order.py` (que define `class SaleOrder(models.Model): _inherit = "sale.order"`
con `meli_unread_messages`/`meli_messages_link` como `related`) **nunca fue importado** desde
`models/__init__.py` (no hay `from . import sale_order`) — código muerto desde el port inicial a 13.0.
La extensión de `sale.order` que Odoo **sí** carga es la clase `sale_order` de `models/orders.py`, donde
`meli_order_id` es `Char` (no `Many2one`) y el vínculo real a `mercadolibre.orders` es el Many2many
`meli_orders` — por eso el `related` nunca podía funcionar (un related no atraviesa un x2many). La vista
`orders_view.xml` (filtro `meli_unread_msgs`, domain `[('meli_unread_messages','>',0)]`) fallaba con
`ParseError: Unknown field "sale.order.meli_unread_messages"`.

**Fix:** en `models/orders.py` (clase activa) se agregaron los dos campos como **compute** (mismo patrón que
el `_meli_status_brief` ya existente: `morder = order.meli_orders and order.meli_orders[0]`):
`meli_unread_messages` (Integer, `store=True`, `_compute_meli_unread_messages`, depends
`meli_orders.meli_unread_messages`) y `meli_messages_link` (Char, sin store, `_compute_meli_messages_link`,
depends `meli_orders.meli_messages_link`). **Dos computes separados** (no uno compartido) porque difieren en
`store` — evita el warning "inconsistent store". Los campos destino `meli_unread_messages`/`meli_messages_link`
ya existen en `mercadolibre.orders` (misma `orders.py`, ~línea 5089). En `models/sale_order.py` (archivo muerto)
se quitaron las 2 líneas `related` rotas y se dejó una nota de por qué el archivo es inerte — **NO** se reactivó
el import (refactor fuera de alcance).

**Archivos:** `models/orders.py`, `models/sale_order.py`, `__manifest__.py` (.85 → .86).
**Verificación:** `py_compile` OK de los .py tocados. Instalación en instancia real: a cargo del usuario.
Branch `claude/fix-sale-order-meli-unread-16.0` (push automático). Merge a `16.0` / promoción a deploy: a
confirmar con el usuario.

---
