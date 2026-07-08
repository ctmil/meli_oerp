# meli_oerp - Migrations

> Registro de migraciones de datos, campos y esquemas.

---

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
