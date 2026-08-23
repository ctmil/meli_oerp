# PLAN 2026-08-23 — #494 SHOPPY (502): cancelar la venta en Odoo cuando ML cancela el pedido

**Quién lo pidió:** FCA, fin de semana 23/24-ago, via sesión madre. Compromiso escrito con el
cliente en el ticket #494 (msg 255159, 21-ago): *"el lunes 25/8 les confirmamos por aca la fecha
de instalacion o, si todavia no la tenemos, en que esta"*.
**Sobre qué:** `meli_oerp` rama **16.0** (tip `6e63ae77`, == origin/16.0). Branch de trabajo
`claude/494-cancelar-venta-al-cancelar-ml`. Cliente SHOPPY/TheFaraway (acct 502), Odoo 16.0,
server propio `https://odoo.tfw.com.ar`, repo `ctmil/shoppy` rama `main`.
**Lock:** `sync-lock.sh acquire meli_oerp` tomado como `meli-keeper-494`. `meli_oerp_accounting`
y `meli_oerp_multiple` están LOCKED por `meli-keeper-524` → **NO se tocan en esta tanda**.

## Criterio acordado con el cliente (citado del hilo, no inventado)
- 19-ago (nuestro, msg del hilo): *"que el conector cancele la venta en Odoo cuando MercadoLibre
  cancela el pago, en vez de dejarla viva y que siga el circuito hasta la factura"*.
- 21-ago (nuestro): *"La parte tecnica es que el conector cancele la venta en Odoo cuando
  MercadoLibre cancela el pedido, en vez de dejarla viva y que siga el circuito hasta la factura."*
- 21-ago (Gonzalo, último mensaje): *"ahora nos ocupamos nosotros de auditar estos pedidos y
  realizar las nc que correspondan. Aguardamos nos confirmen la fecha de instalación"*.
⇒ La mitad **fiscal** (las 96 facturas ya emitidas) es del cliente. Lo nuestro es que **no se
sigan generando casos nuevos** y que los que queden **sean listables por ellos**.

## Diagnóstico read-only PREVIO (hecho antes de escribir nada) — corrige la premisa
La premisa recibida ("el código NO existe, es desarrollo desde cero") es **falsa**. Verificado
contra los objetos de git, no contra el directorio:
- `sale.order.meli_cancel_with_detail()` existe desde `fcf7fc6a` (**25-feb-2026**, v26.15).
- Banner `meli_cancel_pending_banner` ("cancelado en ML pero NO cancelado en Odoo") desde
  `af6290df` (**15-abr-2026**, 26.21).
- Cron `orders_resync_status` + `cron_meli_orders_status` (30 min) desde `98905227`
  (**8-jul-2026**, #475). Dispatcher multi-cuenta en `meli_oerp_multiple`.
- Política configurable `mercadolibre_invoice_cancel_mode` (manual/draft/cancel/credit_note,
  **default `manual`**) + `_meli_cancel_invoices()` con protección CAE en `meli_oerp_accounting`.
- El worktree 16.0 está **limpio** (`diff -rq` contra el clone de `6e63ae77` = 0 diferencias).
- **Está instalado en prod de Shoppy desde el 19-ago** (`meli_oerp` 26.93 · `accounting` 26.46).

## Por qué entonces el número sigue creciendo (hipótesis con la evidencia del código)
Las 96 facturas del listado del 21-ago son todas de pedidos **ya facturados** cuando ML cancela.
Con `mercadolibre_invoice_cancel_mode='manual'` (el default, y no hay evidencia de que Shoppy lo
haya cambiado), `_meli_cancel_invoices()` retorna sin hacer nada, `meli_cancel_with_detail()`
detecta factura `posted` sin resolver y **NO cancela la venta** — por diseño. Postea aviso y sale.
⇒ Lo que falta para que el número deje de crecer NO es código nuevo: es una **decisión de
configuración fiscal del cliente**. Eso se pregunta, no se decide acá.

## Qué SÍ voy a corregir (defectos reales del código, acotados, sin tocar la política fiscal)
1. [ ] **FIX 1 — la cancelación no resuelta queda fuera de la cola PARA SIEMPRE.**
   `orders_resync_status` escribe `order.status='cancelled'` y el dominio del barrido excluye
   `("status","not in",("cancelled","invalid"))`. Si `meli_cancel_with_detail()` abortó por
   factura publicada, esa venta **no se vuelve a mirar nunca**. Patrón exacto de la memoria
   `meli-estado-de-error-saca-la-publicacion-de-la-cola-para-siempre`.
   → Barrido local de re-intento **sin costo de API** al final del cron: órdenes ML con
   `status='cancelled'` y `sale_order.state != 'cancel'` vuelven a pasar por
   `meli_cancel_with_detail()`. Idempotente. Cuando el cliente emite la NC, la venta se cancela
   sola en el ciclo siguiente.
2. [ ] **FIX 2 — paridad de estado.** `update_order_status()` setea
   `sorder.meli_status='cancelled'`; `orders_resync_status()` **no**. Sin eso el campo (stored)
   sólo se refresca como efecto lateral del compute no-almacenado `_meli_status_brief`, o sea
   al abrir el registro. El banner y cualquier filtro por `meli_status` quedan mintiendo.
3. [ ] **FIX 3 — que el cliente pueda LISTARLAS él.** Campo stored+indexado
   `meli_cancel_pending` en `sale.order` (True = ML canceló y Odoo no está cancelada) + filtro
   en la vista de búsqueda. Es lo que Gonzalo pidió hacer por su cuenta; hoy se lo armamos a
   mano en CSV tres veces (10/8, 19/8, 21/8) y el número cambiaba con el criterio.

## Qué NO voy a hacer (y por qué)
- **NO** cambiar el default de `mercadolibre_invoice_cancel_mode`. Es plata y AFIP; la decide el
  cliente. Nace apagado y sigue apagado.
- **NO** tocar `meli_oerp_accounting` ni `meli_oerp_multiple` (LOCKED por `meli-keeper-524`).
- **NO** construir el "período de gracia antes de facturar" que evitaría los 48 `pack_splitted`
  + 28 `buyer_cancel_express`: requiere medir el **lag entre facturación y cancelación** en la
  instancia, y esta sesión tiene prohibido tocarla. Sin ese dato sería un número inventado
  (regla `sin-precision-en-uno-no-se-masifica`). Queda propuesto, no implementado.
- **NO** tocar el punto ciego `shipment_status='delivered'` del dominio (las 9 `mediations` de
  Shoppy pueden caer ahí): mismo motivo, hace falta medirlo primero.
- **NO** deployar, NO tocar la instancia, NO contestar el ticket.

## Criterio de terminado
- Branch `claude/494-cancelar-venta-al-cancelar-ml` desde `6e63ae77`, pusheado a `ctmil/meli_oerp`.
- `py_compile` OK, XML parseando, manifest bumpeado, migración si hace falta.
- `.roots` del módulo al día (changelog + fixes-log + migrations).
- Informe con: criterio citado, diseño, SHA, bordes cubiertos y NO cubiertos, y la **pregunta de
  configuración** que hay que hacerle al cliente antes de dar fecha.

## Avance
- 23-ago 13:00 — diagnóstico read-only cerrado; premisa corregida; lock tomado; plan escrito.
