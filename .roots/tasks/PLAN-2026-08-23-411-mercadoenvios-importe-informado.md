# PLAN 2026-08-23 — #411 SHOPPY (502) · linea de MercadoEnvios con el importe que ML informa

**Rol:** meli-keeper. **Quien lo pidio:** FCA (resolver este fin de semana).
**Cliente:** 502 SHOPPY / TheFaraway (AR), Odoo **16.0**, VPS propio `odoo.tfw.com.ar`.
**Modulo:** `meli_oerp` **16.0** (manifest 16.0.26.94; instalado en prod 16.0.26.93).
**Branch previsto:** `claude/411-mercadoenvios-importe-informado` desde `16.0` (`6e63ae77`).

## Que (criterio del cliente, CITADO)
Gonzalo Shoppy, ticket #411, mensaje del **20-ago-2026 19:51:28**:

> "si, confirmamos que queremos que el conector cargue la linea de envio con el importe
> correspondiente siempre que MercadoLibre informe que el comprador pago el envio, incluso si el
> calculo interno de MercadoLibre no lo devuelve en el momento de creacion de la venta."

Eso es el contrato. Es **cambio de criterio**, no bug: por eso va **configurable y OFF por default**.

## Por que (diagnostico medido hoy, read-only XMLRPC contra prod)
Caso testigo `ML 2000017997353696` (SO 223681, 18-ago 15:41):
- `paid_amount` 95.071,89 · `total_amount` 90.111,35 · `shipping_cost` = `shipping_receiver_cost` =
  `payments_shipment_amount` = **4.960,54** · `shipping_seller_cost` 16.790,54 · `cross_docking`.
- SO: `amount_untaxed` 74.472,19 · `amount_total` 90.111,35 (= 74.472,19 x 1,21) · carrier `MercadoEnvios`.
  Linea de envio `is_delivery` en **0,00**.
- **`meli_discount_seller_amount` = 62.205,93** y `meli_coupon_amount` = 0.
- Config efectiva (`mercadolibre.configuration` id 1, company SHOPPY S.R.L.):
  `mercadolibre_order_total_config = paid_amount` · `mercadolibre_including_shipping_cost = always` ·
  `mercadolibre_use_payment_shipping_amount = True` · `mercadolibre_tax_included = tax_excluded` ·
  `meli_coupon_invoice_mode = full` · `mercadolibre_protect_invoiced_orders = True`.

**Cadena exacta del cero** (no es "ML no devolvio el importe": el importe SI estaba):
1. `orders.py::meli_amount_to_invoice` con `total_config='paid_amount'` devuelve
   `paid_amount - seller_discount` = 95.071,89 - 62.205,93 = **32.865,96**.
   El cap contra la sobre-deduccion (`_coupon_cap`) **solo se aplica si `coupon_amount > 0`**; aca es 0,
   asi que no capea.
2. `shipment.py::_update_sale_order_shipping_info`:
   `shipment_amount_cond_fix = (sorder.amount_total - received_amount) > 1.0 and delivery_price > 0`
   -> 90.111,35 - 32.865,96 = 57.245,39 -> **True** -> `delivery_price = 0.0` +
   `set_delivery_line(sorder, 0.0, "Defined by MELI")`.
3. Cada corrida del cron re-aplica el cero mientras la venta no este facturada.

O sea: la valvula interna (pensada para no facturar flete cuando la venta supera lo cobrable) se
dispara por un `discount_seller_amount` espurio y **pisa el importe que ML si informo**.

## Sobre que se toca (molde que YA existe — no se inventa camino paralelo)
- `meli_oerp/16.0/models/shipment.py::_update_sale_order_shipping_info` (bloque `del_price` /
  `shipment_amount_cond_fix` / `delivery_price <= 0`).
- `meli_oerp/16.0/models/versions.py::set_delivery_line` + `_meli_guard_delivery_write` (#493) —
  se REUSAN, no se esquivan.
- `orders.py::_payments_shipment_amount` y `_ensure_payment_shipping_amounts` — fuente del importe.
- `ml_product_price_conversion` — el neteo de IVA sigue pasando por ahi (Shoppy es `tax_excluded`).

## Diseno (5 lineas)
1. Flag nuevo `mercadolibre_force_shipping_from_ml` (bool, **default False**) en `res.company` +
   `mercadolibre.configuration` (`meli_oerp_multiple`), leido con el patron `in config._fields`.
2. Helper `_ml_informed_shipping_amount(order, shipment)` = `payments_shipment_amount` or
   `shipping_receiver_cost` or `shipping_cost` (bruto ML, en ese orden = "lo que ML informa").
3. Con el flag ON y monto informado > 0: `shipment_amount_cond_fix` **no** pone el precio en 0, y al
   final se garantiza `price_unit = conv(monto)` y `qty_to_invoice = qty` via `set_delivery_line`.
4. Se respetan SIEMPRE: `_meli_guard_delivery_write` (venta ya facturada, #493),
   `including_shipping_cost == 'never'`, y el modo cupon `product_discount` (#391/#399).
5. Sin flag o con monto informado 0 (envio gratis/bonificado) el comportamiento es **identico** a hoy.

## Criterio de terminado
- Patch escrito y revisado sobre `meli_oerp` 16.0 con manifest bumpeado.
- Casos de borde cubiertos y declarados: envio pago · envio gratis · envio ya facturado · pedido que
  agrupa varias ventas (pack).
- Branch `claude/411-...` + commit + push del branch. **Merge y deploy NO** (los confirma FCA).
- `.roots` del modulo al dia (changelog/fixes-log).

## Limites
NO deployar · NO escribir en la instancia del cliente · NO contestar tickets · NO mezclar con #494 ni #524.

## Bitacora
- 23-ago 15:00 — leido el #411 entero por OCAPI (cuenta master), criterio citado arriba.
- 23-ago 15:10 — medido en prod (read-only): config efectiva + caso testigo + cadena del cero.
- 23-ago 15:20 — plan escrito. Pendiente: medicion de impacto, patch, branch.
- 23-ago — 🔴 **BLOQUEO: no puedo correr git en `meli_oerp/`.** Esta sesion esta aislada en el worktree
  `.claude/worktrees/agent-a2505c3dcaa056d80` y el guard rechaza toda operacion git fuera de el
  (probado con `git -C`, con `cd &&`). Los archivos SI son escribibles, pero escribir codigo en el
  checkout compartido de la rama de deploy `16.0` **sin poder branchear ni commitear** es exactamente
  lo que prohiben `git-flow-branch-per-task-deploy-from-git` y `git-index-compartido-entre-sesiones`.
  ⇒ Se entrega el cambio como **patch revisado** + este plan; el branch/commit/push lo tiene que hacer
  una sesion no aislada.

## Cierre — 23-ago
- [x] Diseno implementado: flag `mercadolibre_force_shipping_from_ml` (default **False**) +
      `versions.meli_informed_shipping_amount()` + la valvula `shipment_amount_cond_fix` que no corre
      cuando el importe informado esta validado. Manifests bumpeados (`meli_oerp` 26.95,
      `meli_oerp_multiple` 26.103).
- [x] Patch verificado: `patch -p1` limpio sobre los checkouts reales de 16.0, sin fuzz, **CRLF de
      `shipment.py` preservado**, los 4 .py compilan y el XML parsea.
- [x] Probado contra datos REALES de produccion (XMLRPC read-only, sin escribir nada): 7 fixtures de
      la instancia de Shoppy + 3 packs sinteticos + flag apagado + config sin el campo + pedido
      cancelado. **0 fallos.** Evidencia en `.roots/evidence/411/`.
- [x] Impacto medido: de 4.742 ordenes ML con la linea de envio en 0 desde el 1-ago, **4.703 quedan
      intactas** (envio gratis) y 39 tienen flete informado; la regla acierta en 36 y descarta 3.
- [ ] 🔴 **Branch/commit/push: NO se pudo** (guard de aislamiento del worktree). Ver
      `.roots/evidence/411/HANDOFF.md`.
- [ ] Encender el flag en la cuenta de Shoppy — requiere OK de FCA (write en la instancia).
- [ ] Decidir si se corrigen las 26 ventas viejas `done` sin facturar (corrida aparte).
- [ ] `.roots` del modulo (changelog/fixes-log) — pendiente hasta que exista el commit.
