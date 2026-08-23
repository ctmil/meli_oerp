# meli_oerp - Migrations

> Registro de migraciones de datos, campos y esquemas.

---

## 23 ago 2026 - flag buscable de cancelacion pendiente (v16.0.26.95) [#494 Shoppy]

- **Campo NUEVO stored+index -> requiere `-u meli_oerp`** (el bump 26.95 lo dispara):
  `sale.order.meli_cancel_pending` (Boolean, compute+store+index) = `meli_status == 'cancelled'
  AND state != 'cancel'`.
- **Migracion `migrations/16.0.26.95/post-migrate.py` (post, idempotente), en dos pasos:**
  1. Propaga `meli_status = 'cancelled'` a la venta **desde `mercadolibre_orders.status`**.
     ⚠️ Motivo: `sale_order.meli_status` es un campo **almacenado** que en la practica solo se
     reescribe como efecto lateral del compute **NO almacenado** `_meli_status_brief`, o sea recien
     cuando alguien **abre** la venta. La verdad vive en el pedido de ML. Sin este paso el filtro
     nuevo arrancaria mostrando **de menos**, que es peor que no tenerlo.
     **Acotado a `'cancelled'`**: no toca ningun otro estado.
  2. Siembra `meli_cancel_pending` con la definicion exacta del compute.
- **Campo de configuracion nuevo:** `res.company.mercadolibre_cron_orders_redrain_days` (Integer,
  default **90**, `0` = desactivado). Ventana del re-intento LOCAL. No consume API.
- **Vistas tocadas:** `views/orders_view.xml` (filtro "Cancelado en ML, vivo en Odoo" en las dos
  vistas de busqueda de `sale.order`) y `views/company_view.xml` (el campo nuevo).
- **Efecto esperado en el primer arranque post-deploy:** el WARNING
  `#494: N venta(s) canceladas en MercadoLibre siguen VIVAS en Odoo` con el backlog historico
  completo. **Es el numero real, no una regresion.** En Shoppy (502) se esperan del orden de 96.
- **Sin borrado ni reescritura de facturas.** La migracion NO toca `account_move`.

---

## 28 jul 2026 - sello de movimientos de stock: create_date -> GREATEST(date, write_date, create_date) (v16.0.26.88) [OrgVit 475]

- **Sin migracion de datos ni de esquema.** Codigo puro en `models/product.py` y `models/company.py`.
  No crea columnas. El bump dispara `-u meli_oerp`.
- **Cambio de SEMANTICA de un campo YA existente (leer antes de deployar):**
  `product_product.meli_stock_moves_update` pasa a calcularse con
  `GREATEST(date si state='done', write_date, create_date)` y a ser **monotono**.
  - Los valores viejos **no se reescriben**: no hay backfill. Se van corrigiendo solos a medida que
    cada producto pasa por `process_meli_stock_moves_update()`.
  - **Efecto esperado en el primer ciclo post-deploy:** en instalaciones con drift acumulado, muchos
    bindings van a pasar de `updated` a `update` de golpe (el sello nuevo es >= al viejo y ademas entra
    la red de seguridad por antiguedad de `meli_oerp_multiple`). **Es el comportamiento buscado**, pero
    hay que vigilar el tamano de la primera tanda: con `meli_cron_stock_top_commit` bajo (25 en OrgVit)
    y el cron cada 10 min, drena solo pero puede tardar horas en catalogos grandes.
    Si hace falta escalonarlo, subir `mercadolibre_stock_resync_days` los primeros dias y bajarlo despues.
- **Sin cambios de vistas** en este modulo.

## 19 jul 2026 — comprador + zona del receiver buscables en sale.order (v16.0.26.83) [#404 Deco/KPI]

- **Campos nuevos stored/related → requieren `-u meli_oerp`** (el bump 26.83 lo dispara en Odoo.sh):
  - `sale.order.meli_buyer_nickname` / `meli_buyer_id` (Char, computed+store+index desde `meli_buyer`):
    se **recomputan** en el upgrade a partir del comprador ya vinculado (retroactivos, sin script).
  - `sale.order.meli_receiver_state/city/neighborhood/zip_code` (Char, related+store+index desde
    `meli_shipment`): **backfillean** en el upgrade desde el envío existente. Provincia/Localidad/CP
    quedan pobladas para el histórico; el **Barrio** (receiver_neighborhood) solo aparece en envíos
    **re-fetcheados** post-deploy (los históricos no lo tenían guardado → vacíos hasta re-consultar el envío).
  - `mercadolibre.shipment.receiver_neighborhood` / `receiver_municipality` (Char): columnas nuevas,
    sin backfill (se llenan al re-consultar/procesar cada envío desde `receiver_address.neighborhood/municipality`).
- **Sin script de migración** (el backfill lo hace el recompute/related del upgrade). Convergencia byte-idéntica 16/17/18/19.
## 20 jul 2026 — savepoints anti-`InFailedSqlTransaction` (v16.0.26.83) [#410 SOLSUN]

- **Sin migración de datos ni de esquema.** Cambio de código puro en `models/category.py` y
  `models/product.py` (savepoints ORM alrededor de llamadas frágiles). El bump 26.83 sólo dispara
  `-u meli_oerp`; no crea columnas ni requiere backfill. Convergencia byte-idéntica 16/17/18/19.

## 10 jul 2026 — humanización de errores de publicación (v16.0.26.71) [#532]

- **Sin migración de datos ni de esquema.** Cambio de código puro en `models/warning.py`
  (patrones regex + presentación del wizard `meli.warning`, que es TransientModel). No crea columnas,
  no requiere backfill, no toca vistas. Convergencia byte-idéntica 16/17/18/19.

## 9 jul 2026 — BUG-009 `date_order` + BUG-007 cancelación en `update_order_status` (v16.0.26.68)

- **Sin migración de datos ni de esquema.** Cambio de código puro en `models/orders.py`: `date_order`
  y `meli_status` son campos **ya existentes** de `sale.order` → el bump 26.68 no crea columnas ni
  requiere backfill. Los pedidos ya importados conservan su `date_order` histórico; el nuevo valor
  (fecha real de ML) aplica a las órdenes procesadas de aquí en más.
- **Salto de versión:** 26.67 fue un fix específico de Odoo 18/19 (`action_create_returns_all`) que
  no aplica a esta versión → 16.0 salta de 26.66 a **26.68**.
- **Convergencia:** inserción byte-idéntica en 16/17/18/19 (anchors `prepare_sale_order_vals` y
  `update_order_status` convergidos). Promoción desde el cliente Dannok (`0eff11d`).

## 8 jul 2026 — Feature surtido multi-almacén (captura depósito ML) + fixes de migración (v16.0.26.66)

- **Feature (16≡17≡18≡19, byte-idéntico):** 2 campos Char nuevos en `mercadolibre.order_items`
  (`meli_stock_node_id`, `meli_stock_store_id`, `index=True`) + captura en `orders.py`
  (armado de `order_item_fields`, guardado condicionado a que los `_fields` existan). Sin migración
  de datos: el ORM crea las columnas en el `-u` del bump 16.0.26.66. Anchors idénticos en las 4 versiones.
- **v16.0:** sin adaptaciones de migración (`type='tree'` y `numbercall` siguen válidos en ≤16 → no se tocan).

## 2026-06-15 — Promoción http_proxy (Deco→source) + sources-align 16/17/18/19 (v26.46)

- Feature `mercadolibre_http_proxy` desarrollado en 19.0 (merge atento sobre el source) y **forward-port/backport idéntico** a 16/17/18 (los anchors de `get_new_instance`, `company.py` y `res_config_settings.*` estaban convergidos entre versiones → edición byte-idéntica). Sin diferencias de sintaxis por versión (`groups=`/`<setting>` válidos en 16-19; no toca grupos de `res.users`).
- **Schema:** columna `mercadolibre_http_proxy` en `res_company`, la añade el ORM al upgradear (bump 26.46, sin migración manual). Campo vacío por default → comportamiento idéntico al previo.
- `sources-align.sh meli` → CONVERGIDO en las 4 versiones tras la promoción.

---

## 2026-06-10 — Port tanda fixes meli jun-2026 (16.0, desde shoppy)

Port EXACTO (sin adaptación de sintaxis, misma versión 16.0) desde `ctmil/shoppy`
rango `2e5289a..origin/main`. Version: `16.0.26.31` → `16.0.26.38`.

- **models/orders.py**: `_compute_so_handling_limit_status` ahora considera
  `estimated_buffering_date` como fallback; `meli_fix_team` respeta team/seller sin
  compañía y vendedor válido por `company_ids`; nuevo método
  `_ensure_payment_shipping_amounts` (re-consulta MP si shipping_amount=0).
- **models/shipment.py**: nuevos campos de fechas ML (buffering, schedule_limit,
  pay_before, pickup_promise, desired_promised_delivery); carrier mapeado respeta su
  producto; modo de impresión `zpl_txt` (extrae ZPL del zip); chequeo final de
  shipping_amount antes de la línea de envío.
- **models/versions.py**: `ml_datetime` descarta fechas placeholder (año < 1970 → None)
  que rompían el write en Odoo.
- **views/orders_view.xml**, **views/shipment_view.xml**: `filename=` en campos binarios
  pdf; nuevos campos de fechas en tree/form.

Divergencia detectada (no tocada): versions.py del source grove tiene un import extra
`from markupsafe import Markup` (línea 10) que NO existe en shoppy. Preexistente al
port; se preservó.

---
