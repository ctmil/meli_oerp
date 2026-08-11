# meli_oerp - TODO

> Backlog y tareas pendientes.

---

## Alta Prioridad

- [ ] **CAPACITACIONES ACTUALIZADAS DEL SUITE — arrancar por PUBLICACION MASIVA DE PRODUCTOS** `[todas las versiones]`
      Pedido por **Mario Vidales (Tus Refacciones MX, cuenta 431)** en la call del **11-ago-2026**, y
      registrado en el **ticket #547**. FCA: *"me pide las capacitaciones actualizadas de todo el modulo
      de meli, pero particularmente para la publicacion de productos masivamente, **lo que todos quieren
      ya**"* ⇒ **NO es de un cliente: es material de suite**, se hace una vez contra la version actual y
      sirve para todos. **Orden: publicacion masiva primero**, despues el resto del modulo.
      Sin fecha comprometida con el cliente todavia (asi se lo dijimos). Pendiente: definir formato
      (video / doc / ambos — existe el skill `video` con storyboard + TTS + subtitulos) y alcance por version.
      Insumo pedido a Mario en el #547: volumen de la tanda, si es catalogo nuevo o productos ya en Odoo,
      si llevan variantes / fichas de catalogo, y quien la va a hacer.

- [ ] **Guardar `sale.order.meli_stock_location_id` ("Deposito ML (origen)")** `[18.0 · meli_oerp_multiple]`
      Hoy es `compute` con **`store=False`** ⇒ **no se puede filtrar ni agrupar por deposito en la lista
      de ventas**. Pedido implicito de Tus Refacciones (431) al querer reportar por deposito; ofrecido en
      el **ticket #546**. Al almacenarlo hay que resolver el recompute (depende de
      `meli_orders.order_items.meli_stock_node_id` / `..._store_id`).

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
