# PLAN 07-oct-2026 · meli_oerp · #158 Elvimarta — vaivén de la línea de envío (ENVIO-ME1)
**Quién / por qué:** meli-keeper, lanzado por soporte (client-158). Diagnóstico de cliente:
`partners/Argentina/elvimarta/.roots/tasks/PLAN-2026-10-07-158-621-alinear-248-y-facturacion-automatica.md` §2-§3a.
La línea de envío oscila (ML 2000015003762179: 72 cambios de total 12-15 sep) y Facturacion_Automatica
(de ellos) factura en un minuto con envío 0 ⇒ NC manual. Sigue: 5 casos 2-oct..7-oct.
**Sobre:** source `meli_oerp` 16.0/17.0/18.0/19.0 · ramas `claude/158-envio-vaiven-<serie>`.
⛔ Sin merge a ramas de deploy, sin deploy, sin staging (no hay staging-claim).

## Mecanismo (medido con `git show origin/<serie>:models/...`, 7-oct tras fetch exit 0)
Presente en origin/16.0, 17.0, 18.0, 19.0 (todas 26.166). Los dos escritores de la línea están en
`mercadolibre.shipment._update_sale_order_shipping_info`:
- `shipment_amount_cond_fix = (sorder.amount_total - received_amount) > 1` ⇒ línea a 0.
- "UPDATE PRICE": `abs(line.price_unit - delivery_price) > 1` ⇒ línea = flete del pago.
`amount_total` INCLUYE la línea actual ⇒ la decisión depende del estado que ella misma escribe:
con línea = flete ⇒ total > cobrable ⇒ 0; con línea = 0 ⇒ update ⇒ flete. Cada pasada invierte.
`received_amount = meli_amount_to_invoice()` = `meli_paid_amount` (modo paid_amount), que en estas
órdenes ME1 NO trae el envío: `meli_total_amount = meli_paid_amount = 3.138.200`, envío del pago 205.570.
Además `meli_confirm_ready` no acepta `amount_total = cobrable + envío` (sólo el inverso) ⇒ "Condition not met".

## Relación con #620 (T3LC 535, 26.180, SIN mergear, ramas claude/620-linea-envio-costo-comprador-*)
#620 ya saca la válvula (no baja a 0) y agrega `_meli_shipping_missing_in_paid` a `meli_amount_to_invoice`,
pero devuelve 0 **si el pago trae shipping_amount** — que es justamente Elvimarta. Con #620 solo: el vaivén
para, pero el cobrable queda sin envío ⇒ confirm/factura del módulo ven un descuadre igual al flete.
⇒ **Se apila sobre #620** (mismo mecanismo; dos ramas paralelas chocarían en las mismas líneas).

## Fix (mismo criterio para todos los caminos; sin red; todo a nivel VENTA)
1. `_meli_shipping_missing_in_paid`: si los pagos traen shipping_amount, sumar el flete SÓLO si ML
   muestra que paid_amount no lo incluye: `|paid - total + cupón| <= 1` (paid = ítems exactos) — firma
   Elvimarta. Flete del pago = suma de `payments_shipment_amount` de TODAS las órdenes ML de la venta
   (pack: nivel venta contra nivel venta; no el pago de una sola orden contra el total del pack).
2. ~~shipment.py contra total objetivo~~ **DESCARTADO tras leer #620 (21:05Z):** con #620 la válvula ya
   sólo loguea; `fix2` y el paso a 0 dependen del flete del comprador, no de la línea actual ⇒ ya no queda
   escritura auto-referida. Pasar `fix2` a total objetivo además ROMPE la creación de la línea cuando el
   carrier ya está puesto y no hay línea. shipment.py no se toca (salvo que el log #620 deja de dispararse
   en Elvimarta porque el cobrable ya trae el flete).
   Riesgo residual anotado (sin caso medido): el tope del descuento del vendedor en `meli_amount_to_invoice`
   compara contra `amount_total` con la línea incluida.
3. Bump 26.194 en las 4 series (max suite medido = 26.193 [542]; bus hasta 26.193).
4. Test puro (sin Odoo) del criterio + py_compile. roots: fixes-log + changelog por serie.

## Pasos
- [x] 1. sync-lock acquire meli_oerp
- [x] 2. worktrees claude/158-envio-vaiven-<serie> desde origin/claude/620-linea-envio-costo-comprador-<serie>
- [x] 3. fix 17.0 + test puro; port 16/18/19 (respetar EOL de cada archivo)
- [x] 4. py_compile + test; manifests 26.194; roots  — 15/15 tests OK por serie (9 nuevos), py_compile OK; EOL intacto (shipment.py CRLF no tocado)
- [ ] 5. commit + push sólo claude/158-envio-vaiven-*; ls-remote = local
- [ ] 6. sync-lock release; reservar 26.194 en el bus

## Terminado
4 ramas pusheadas, compiladas, test verde, versión 26.194 en las 4, lock liberado. Falta (OK FCA):
merge #620+#158 a origin/<serie>, staging con staging-claim (1 orden por caso), y para el cliente 158 el
pase en 19.0 (migración en curso) o 17.0.
