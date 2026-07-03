# meli_oerp - TODO

> Backlog y tareas pendientes.

---

## Alta Prioridad

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

---
