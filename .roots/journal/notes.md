# meli_oerp - Notes

> Ideas y notas que podrían convertirse en features.

---

## Ideas pendientes

### Validación de campos ML antes de publicar (2026-04-30) `[19.0.tecnolosys]`

Agregar una validación pre-publish que verifique campos obligatorios de ML (título, precio, stock, categoría) antes de intentar publicar, evitando errores de API.

**Estado:** Nueva

---

### SKU rules — mejoras pendientes (2026-05-02) `[16.0.shoppy]`

Tres mejoras identificadas para las reglas de SKU:

1. **Implementar `resolve_to_sku()`** — actualmente retorna `None`, nunca ejecuta
2. **Regex en BD** — las reglas tipo `regex` existen en el modelo pero `map_to_sku()` solo busca `type='map'`; las regex de BD no se aplican automáticamente
3. **Campo `barcode`** — existe en el modelo pero no se usa en la lógica de búsqueda de productos

**Estado:** Nueva → ver `../meli_oerp_stock/.roots/tasks/todo.md` para tracking

---

### Wizard Import Sales — contadores resumen (2026-05-02) `[16.0.shoppy]`

Agregar contadores de resumen (X importadas, Y incompletas, Z errores) al wizard de importación.

**Estado:** Nueva

---

### Parsear `metadata.item_id` de charges_details (2026-05-02) `[16.0.shoppy]`

Para descuentos per-item, parsear `metadata.item_id` de charges_details si ML lo provee.

**Estado:** Nueva

---
