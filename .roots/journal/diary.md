# meli_oerp - Development Diary

> Reflexiones diarias sobre el desarrollo.

---

## 2026

**2026-07-08** `[16.0.26.63]` — Import de medidas del paquete: fill-empty → OVERWRITE (ML autoritativo) [#424 Deco/KPI]

`_meli_import_template_attributes` (models/product.py) escribía cada campo mapeado cuando ML traía valor, pero para las dimensiones del paquete no alcanzaba: filas legacy tenían el WIDTH/HEIGHT del *producto* (ej. '100 cm' = 1 m convertido) en `meli_seller_package_*`, y el import/backfill las conservaba porque el mapeo NO toca el atributo bare WIDTH/HEIGHT/LENGTH (sólo `SELLER_PACKAGE_*` + fallback catalog `PACKAGE_*`). Se dividió la semántica de escritura:
- `_MELI_IMPORT_OVERWRITE_FIELDS` (las 4 dims del paquete) → **OVERWRITE** con `SELLER_PACKAGE_*` (ML es fuente autoritativa del paquete). `PACKAGE_*` sólo como fallback si no hay `SELLER_PACKAGE_*`; nunca pisa con vacío (`if not val: continue`).
- brand/model/gender → **fill-empty** (no pisar carga manual).
El backfill "Traer medidas" usa el mismo helper → corrige los ya importados. Sin cambio de schema (sin migración). Bumps 26.62→26.63, 4 versiones.

---

**2026-05-02** `[16.0.shoppy]` — Sesión intensiva de features, fixes y estabilización.

Sesión larga cubriendo múltiples áreas del módulo:

### Features implementados
1. **Tracking number en nombre de venta** — `ML 123456 | MEL46856273568FMXDF01`
2. **Carrier mapping** — Tabla `meli_oerp.carrier.mapping` con 18 carriers AR precargados, filtro de archivados
3. **Cupón/descuento** — Captura desde `charges_details`, aplica `line.discount` proporcional
4. **Fechas de envío** — 8 campos nuevos de `status_history` + fallback `shipping_option`
5. **Printer name config** — Campo destino impresión ZPL en configuración cuenta
6. **Import Sales wizard** — Botones rápidos de fecha (Selection+onchange), estado "Incompleto", pestaña "Ventas procesadas"
7. **Etiqueta en albarán** — PDF con filename + preview imagen

### Fixes aplicados
1. `order.meli_shipment` → `order.shipment` (AttributeError en mercadolibre.orders)
2. Doble descuento cupón eliminado (solo vía `line.discount`)
3. `action_create_mercadolibre_account` restaurado (upgrade error BD)
4. Odoo 16 syntax: `invisible="not X"` → `attrs`, `column_invisible` → `invisible`, `</list>` → `</tree>`
5. Auditlog `copy.deepcopy` — sanitización de recordsets antes de `sale.order.create()`
6. `coupon_amount` re-activado desde `charges_details` post-merge 26.25

### Pendientes para próxima sesión
- Pestaña "Ventas procesadas" en wizard: las `import_lines` se pierden al recrear el wizard transient
- Validar descuento cupón en órdenes multi-item reales
- Reiniciar Odoo para que SDK tome `extra_headers` (billing-info v2)
- Fix auditlog en el módulo externo (ya preparado en `exereview/`)

---

**2026-04-30** `[19.0.tecnolosys]` — Fix de permalink API y bootstrap de .roots/

Se corrigió el permalink de la API de MercadoLibre para incluir el `access_token` directamente en la URL del item. Esto permite que el link funcione desde el backend de Odoo sin necesidad de autenticación adicional. Se inicializó la estructura `.roots/` para documentación persistente del proyecto.

---
