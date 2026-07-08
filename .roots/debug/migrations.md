# meli_oerp - Migrations

> Registro de migraciones de datos, campos y esquemas.

---

## 8 jul 2026 — Feature surtido multi-almacén (captura depósito ML) + fixes de migración (v17.0.26.66)

- **Feature (16≡17≡18≡19, byte-idéntico):** 2 campos Char nuevos en `mercadolibre.order_items`
  (`meli_stock_node_id`, `meli_stock_store_id`, `index=True`) + captura en `orders.py`
  (armado de `order_item_fields`, guardado condicionado a que los `_fields` existan). Sin migración
  de datos: el ORM crea las columnas en el `-u` del bump 17.0.26.66. Anchors idénticos en las 4 versiones.
- **Adaptación v17.0:** quitado `numbercall` de `data/claims_cron.xml` (Odoo 17 removió el campo de `ir.cron`).

## 2026-06-15 — Promoción http_proxy (Deco→source) + sources-align 16/17/18/19 (v26.46)

- Feature `mercadolibre_http_proxy` desarrollado en 19.0 (merge atento sobre el source) y **forward-port/backport idéntico** a 16/17/18 (los anchors de `get_new_instance`, `company.py` y `res_config_settings.*` estaban convergidos entre versiones → edición byte-idéntica). Sin diferencias de sintaxis por versión (`groups=`/`<setting>` válidos en 16-19; no toca grupos de `res.users`).
- **Schema:** columna `mercadolibre_http_proxy` en `res_company`, la añade el ORM al upgradear (bump 26.46, sin migración manual). Campo vacío por default → comportamiento idéntico al previo.
- `sources-align.sh meli` → CONVERGIDO en las 4 versiones tras la promoción.

---

## 2026-06-10 — Forward-port tanda fixes meli jun-2026 (16.0 → 17.0)

Origen: shoppy `ctmil/main` (Odoo 16.0), rango `2e5289a..fa5eb40`. Bump 17.0.26.31 → **17.0.26.39**.

Portado tal cual (Python, version-agnóstico):
- `versions.py` `ml_datetime`: guard año < 1970 → `None` (descarta placeholders de ML que rompían el write).
- `orders.py` `_ensure_payment_shipping_amounts` (re-consulta MP de pagos aprobados con shipping_amount=0) + chequeo final en `shipment._update_sale_order_shipping_info` con `invalidate_recordset`.
- `orders.py` `meli_fix_team`: respeta team/vendedor manuales; asigna seller_team sin compañía (`company.id in user_id.company_ids.ids`).
- `shipment.py` carrier mapeado: no sobreescribe `product_id`; usa el producto efectivo del carrier.
- `shipment.py` modos etiqueta PDF / ZPL (zip) / ZPL (txt: extrae el zip con `io`+`zipfile`) + `response_type=zpl2`.
- `shipment.py`/`orders.py` campos de fecha de `shipping_option` (estimated_buffering_date, estimated_schedule_limit, estimated_pay_before, pickup_promise_from/to, desired_promised_delivery); `handling_limit_status` usa `estimated_buffering_date` como fallback.
- `orders.py` gate `mercadolibre_set_fiscal_position` (campo vive en meli_oerp_multiple).

Adaptaciones de versión 17:
- **Modifiers en sintaxis nativa python `invisible="<expr>"` (NO attrs).** El commit 16.0 `28b86e3` (python→attrs) **NO se porta** — en 17 los modifiers van como `invisible="<expr>"`. Las vistas tocadas en este módulo ya estaban en python.
- `filename="..."` en campos binarios: form de orders_view, list/form de shipment_view.

---
