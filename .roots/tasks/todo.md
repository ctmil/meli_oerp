# meli_oerp - TODO

> Backlog y tareas pendientes.

---

## Alta Prioridad

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
