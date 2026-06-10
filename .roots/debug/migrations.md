# meli_oerp - Migrations

> Registro de migraciones de datos, campos y esquemas.

---

## 2026-06-10 — Forward-port tanda fixes meli jun-2026 (16.0 → 19.0)

Origen: shoppy `ctmil/main` (16.0), rango `2e5289a..fa5eb40`. Versión `19.0.26.31` → `19.0.26.39`.

**Portado tal cual (Python, version-agnóstico):**
- `versions.py` `ml_datetime`: guard año < 1970 → devuelve None (descarta fechas placeholder
  ML año 0001 que rompían el write con ValueError de formato).
- `orders.py`:
  - `_compute_so_handling_limit_status`: depende también de `estimated_buffering_date`;
    fallback `estimated_handling_limit or estimated_buffering_date`.
  - `meli_fix_team`: team/vendedor seteados a mano no se pisan (team sin compañía válido en
    cualquiera; seller_team sin compañía ahora SÍ se asigna; user válido si company en company_ids).
  - Gate fiscal: `mercadolibre_set_fiscal_position` (si False, `fiscal_position_id=False`).
  - Nuevo `_ensure_payment_shipping_amounts(meli, config)`: re-consulta MP los pagos aprobados con
    shipping_amount=0 (usa `requests` + `urlencode`, ya importados).
- `shipment.py`:
  - import `io`, `zipfile`.
  - Modos etiqueta `zpl_txt` además de `zpl` (response_type zpl2; extrae ZPL plano del zip en
    modo txt; `.zip`/`.zpl` según `PK` magic).
  - 6 campos `Datetime` nuevos (estimated_buffering_date, estimated_schedule_limit,
    estimated_pay_before, pickup_promise_from/to, desired_promised_delivery) + parseo desde
    `shipping_option` (buffering, estimated_schedule_limit, pickup_promise, desired_promised_delivery,
    pay_before).
  - `_compute_handling_limit_status`: idem buffering fallback.
  - Carrier mapping: respeta el producto del carrier mapeado (solo asigna si el carrier no tiene
    producto); usa el producto efectivo del carrier para la línea de envío.
  - Chequeo final shipping_amount antes de calcular la línea (`_ensure_payment_shipping_amounts` +
    `invalidate_recordset`).
- Vistas (`orders_view.xml`, `shipment_view.xml`): `filename="..."` en pdf_file + campos de fecha
  nuevos. version-agnóstico; la vista destino ya usa `<list>`.

**Adaptación 19.0:** ninguna sintaxis hubo que cambiar respecto del Python/XML del origen. El commit
16.0 `28b86e3` (modifiers v17→attrs) NO se porta (en 19 `attrs` está eliminado; las vistas tocadas
acá no usan modifiers). No se tocó `view_mode` (esta tanda no lo modificó).

**API verificada en 19:** `invalidate_recordset`, `with_user`/`with_company`, `requests`/`urlencode`
disponibles; sin `name_get()` ni APIs deprecadas en la tanda.

**Modifiers (nota de versión):** sintaxis nativa python `invisible="<expr>"` (NO attrs). El commit
16.0 `28b86e3` (python→attrs) NO se porta a 19.

---
