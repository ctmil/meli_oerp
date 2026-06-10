# meli_oerp - Migrations

> Registro de migraciones de datos, campos y esquemas.

---

## 2026-06-10 — Forward-port tanda fixes meli jun-2026 (16.0 → 18.0)

Origen: shoppy `ctmil/main` (Odoo 16.0), rango `2e5289a..fa5eb40`. Bump 18.0.26.31 → **18.0.26.39**.

Portado tal cual (Python, version-agnóstico):
- `versions.py` `ml_datetime`: guard año<1970 → `None` (descarta placeholders de ML que rompían el write).
- `orders.py` `_ensure_payment_shipping_amounts` (re-consulta MP de pagos aprobados con shipping_amount=0) + chequeo final en `shipment._update_sale_order_shipping_info` con `invalidate_recordset`.
- `orders.py` `meli_fix_team`: respeta team/vendedor manuales; asigna seller_team sin compañía (`company.id in user_id.company_ids.ids`).
- `shipment.py` carrier mapeado: no sobreescribe `product_id`; usa el producto efectivo del carrier.
- `shipment.py` modos etiqueta PDF / ZPL (zip) / ZPL (txt: extrae el zip con `io`+`zipfile`) + `response_type=zpl2`.
- `shipment.py`/`orders.py` campos de fecha de `shipping_option` (estimated_buffering_date, estimated_schedule_limit, estimated_pay_before, pickup_promise_from/to, desired_promised_delivery); `handling_limit_status` usa `estimated_buffering_date` como fallback.
- `orders.py` gate `mercadolibre_set_fiscal_position` (campo vive en meli_oerp_multiple).

Adaptaciones de versión 18:
- Modifiers: el commit `28b86e3` (python→attrs) **NO se portó** — en 18 `attrs` está eliminado y python es la sintaxis nativa. Las vistas tocadas en este módulo ya estaban en python.
- `filename="..."` en campos binarios: form de orders_view, list+form de shipment_view.
- Inserción de campos en shipment_view: la vista de lista del destino ya usa **`<list>`** (no `<tree>`); campos agregados respetando `<list>`.

Notas:
- `versions.py` y `orders_view.xml` ya eran pure-LF en el destino 18.0; se preservó su convención (resto del módulo es CRLF).

---
