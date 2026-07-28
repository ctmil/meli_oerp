# meli_oerp - TODO

> Backlog y tareas pendientes.

---

## Alta Prioridad

- [ ] **🔴 Stock: invariante de cola congelado + doble definición de "disponible"** — análisis de producto 28-jul-2026 (caso OrgVit 475, MLM). Causa raíz: `_meli_stock_moves_update()` usa `max(stock_move.create_date)` (`models/product.py:5241-5269`), que **se congela**; combinado con `meli_stock_moves_update > stock_update` (`meli_oerp_multiple/models/connection_binding.py:2078-2086`) el binding queda `updated` para siempre y **ningún cron lo vuelve a tocar**. Todo cambio de stock que no crea una fila nueva de `stock_move` (validar un move viejo, reservar/desreservar, cancelar) queda invisible. Plan de fixes **F1..F8** con prioridad y versión (26.87 / 26.88 / 26.90) en → **`.roots/debug/2026-07-28-stock-queue-invariant-y-kits.md`**. Incluye: verificar el `available_quantity` devuelto por ML (F7), diagnóstico que mide con `stock_quant` en vez de `_meli_available_quantity()` (F2), sobre-promesa de stock en publicaciones que comparten producto/componente (F4), `conn_id` duplicados con productos distintos (F5), backoff de reactivación (F8), test `[4d]` con falso OK (F6). **Afecta a toda la flota.**

- [ ] **Notificación de mensajes post-venta del comprador** (indicador de mensajes NO leídos en la orden ML) — pedido SEBA/Deco, ticket #499. Verificado: `GET /messages/unread?role=seller&tag=post_sale` devuelve total + resources `/packs/{pack_id}/sellers/{seller_id}` con count (Deco total=3). **Versión mínima (en curso):** campo `meli_unread_messages` (Integer) en `mercadolibre.orders` (match por `pack_id`/`order_id`) + related en `sale.order` + método refresh + cron + botón manual + link a ML. Fase 2 = leer/responder desde la orden en Odoo. Deco-first para que lo prueben. [rel #424.2]

- [x] **IMPORT trae campos de la pestaña MELI Plantilla** (`product.template`) — HECHO 3-jul-2026 (26.58 import + 26.59 fix backfill + 26.60 multi-cuenta real, 4 versiones, sin push). Backfill: BUG A `meli_id` en variante no template (ValueError) + BUG B token por cuenta dueña (evita 403) + BUG C multi-cuenta usa `mercadolibre.account` no `res.company` → hooks overridables `_meli_backfill_get_accounts`/`_meli_backfill_list_ids` en base, override en `meli_oerp_multiple` 26.60. Detalle: mapeo inverso ML→Odoo en `_meli_import_template_attributes` (llamado en `product_meli_get_product`, cubre crear+actualizar) → `meli_seller_package_*` (+fallback catalog `PACKAGE_*`), `meli_brand`/`meli_model`/`meli_gender`. Idempotente. + **backfill** `action_meli_backfill_template_fields` (botón form + acción de lista, savepoint por producto). Char + backfill hechos; dimensiones estructuradas value/uom para MRP = FASE 2 pendiente. Spec: workspace `.roots/state/meli-product-import-template-fields.md`. [Deco/KPI, rel #424]

- [ ] **Wizard "Ventas procesadas"** `[16.0.shoppy]`: las import_lines transient se pierden al recrear wizard. Opciones: modelo persistente para resultados, o computed field desde mercadolibre.orders filtrando por timestamp
- [ ] Validar descuento de cupón en órdenes multi-item reales (proporcional por precio)
- [ ] Reiniciar Odoo para que SDK tome `extra_headers` (billing-info v2 endpoint)
- [ ] Aplicar fix de auditlog (`exereview/auditlog/models/rule.py`) al módulo en servidor

---

## Media Prioridad

- [ ] Parsear `metadata.item_id` de charges_details para descuentos per-item si ML lo provee
- [ ] Agregar fechas estimadas de envío al stock.picking (related desde shipment)
- [x] Producteca: resolver `connection_monitor` column missing — RESUELTO 2026-06-27: faltaba la **definición** del campo en `meli_oerp_multiple` (regresión `0be207d`); agregado `connection_monitor = fields.Boolean(default=True)` en `mercadolibre.account` (v26.52, 16-19). El `-u` crea la columna; no hace falta ALTER manual. Ver `meli_oerp_multiple/*/.roots/debug/fixes-log.md`.
- [ ] Agregar validación pre-publish de campos ML obligatorios (título, precio, stock, categoría)

---

## Ideas / Backlog

- [ ] SKU rules: implementar `resolve_to_sku()` (actualmente retorna None)
- [ ] SKU rules: hacer que las regex de BD se apliquen en el flujo de resolución (hoy solo funciona type=map)
- [ ] SKU rules: usar campo `barcode` en la lógica de búsqueda de productos
- [ ] Wizard Import Sales: agregar contadores de resumen (X importadas, Y incompletas, Z errores)
- [ ] **(IMPORTANTE) Compatibilidades de vehículos ML** (autopartes): modelar + UI + push por API
  (`POST /items/{id}/compatibilities`), integrar al batch REFATODO. Sin esto las autopartes quedan
  `under_review/incomplete_compatibilities`. Ver **`design/meli-vehicle-compatibilities.md`**. Clientes:
  Koreautos (521, caso testigo C6536), Tus Refacciones MX (431, ¿repo con algo? re-verificar).

---
