# meli_oerp - Migrations

> Registro de migraciones de datos, campos y esquemas.

---

## 10 jul 2026 — humanización de errores de publicación (v19.0.26.71) [#532]

- **Sin migración de datos ni de esquema.** Cambio de código puro en `models/warning.py`
  (patrones regex + presentación del wizard `meli.warning`, que es TransientModel). No crea columnas,
  no requiere backfill, no toca vistas. Convergencia byte-idéntica 16/17/18/19.

## 9 jul 2026 — BUG-009 `date_order` + BUG-007 cancelación en `update_order_status` (v19.0.26.68)

- **Sin migración de datos ni de esquema.** Cambio de código puro en `models/orders.py`: `date_order`
  y `meli_status` son campos **ya existentes** de `sale.order` → el bump 26.68 no crea columnas ni
  requiere backfill. Los pedidos ya importados conservan su `date_order` histórico; el nuevo valor
  (fecha real de ML) aplica a las órdenes procesadas de aquí en más.
- **Convergencia:** inserción byte-idéntica en 16/17/18/19 (anchors `prepare_sale_order_vals` y
  `update_order_status` convergidos). Promoción desde el cliente Dannok (`0eff11d`).

## 8 jul 2026 — Feature surtido multi-almacén (captura depósito ML) + fixes de migración (v19.0.26.66)

- **Feature (16≡17≡18≡19, byte-idéntico):** 2 campos Char nuevos en `mercadolibre.order_items`
  (`meli_stock_node_id`, `meli_stock_store_id`, `index=True`) + captura en `orders.py`
  (armado de `order_item_fields`, guardado condicionado a que los `_fields` existan). Sin migración
  de datos: el ORM crea las columnas en el `-u` del bump 19.0.26.66. Anchors idénticos en las 4 versiones.
- **Adaptación v19.0:** `type='tree'`→`list` en `views/claims_view.xml` (Odoo 18/19 removió `tree`); quitado `numbercall` de `data/claims_cron.xml` (Odoo 17 removió el campo de `ir.cron`).

## 2026-06-15 — Promoción http_proxy (Deco→source) + sources-align 16/17/18/19 (v26.46)

- Feature `mercadolibre_http_proxy` desarrollado en 19.0 (merge atento sobre el source) y **forward-port/backport idéntico** a 16/17/18 (los anchors de `get_new_instance`, `company.py` y `res_config_settings.*` estaban convergidos entre versiones → edición byte-idéntica). Sin diferencias de sintaxis por versión (`groups=`/`<setting>` válidos en 16-19; no toca grupos de `res.users`).
- **Schema:** columna `mercadolibre_http_proxy` en `res_company`, la añade el ORM al upgradear (bump 26.46, sin migración manual). Campo vacío por default → comportamiento idéntico al previo.
- `sources-align.sh meli` → CONVERGIDO en las 4 versiones tras la promoción.

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
