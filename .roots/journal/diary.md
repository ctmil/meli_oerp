# meli_oerp - Development Diary

> Reflexiones diarias sobre el desarrollo.

---

**2026-07-16** `[19.0.26.78]` — dimensiones del producto (float+unidad) + IVA/impuesto interno desde ML [#424/#474 Deco/KPI]

Pedido en call con Deco/KPI. Campos nuevos en product.template y product.product (pestaña MELI Plantilla):
- `meli_product_{width,height,length}` (Float) + `*_unit` (Char) ← atributos WIDTH/HEIGHT/LENGTH. Parser `_meli_parse_dimension` (value_struct {number,unit} o value_name "1.2 m"/"70 cm"/coma decimal → (float, unidad)). NO se normaliza: se guarda el número y la unidad tal cual (por eso el campo de unidad).
- `meli_vat` / `meli_import_duty` (Char) ← VALUE_ADDED_TAX / IMPORT_DUTY (los DOS atributos que hacían fallar la publicación en #474). Van al `_MELI_IMPORT_ATTR_MAP` + overwrite (ML autoritativo).
Poblado en `_meli_import_template_attributes` (nuevo pase de dims tras el loop de Char, escribe template+variante). Como `meli_oerp_multiple.product_meli_get_product` NO encadena a la base, se agregó ahí la llamada a `_meli_import_template_attributes` (antes solo "Traer medidas" llenaba estos campos en multi-cuenta). Verificado el parser con los valores reales de Deco. Bump 26.77→26.78. Backport 16/17/18 pendiente en la misma tanda.

---

**2026-07-15** `[19.0.26.77]` — "Traer medidas": la acción de lista tragaba el resultado + backfill mudo [#485 Deco/KPI]

El cliente reportó "aparece la opción pero no hace nada" al usar la acción masiva desde la vista Lista. **Corría bien**: el log de prod (Deco, 13/7 12:43) muestra `MELI backfill plantilla: finished 2342/2342 (ok=2342, errors=2)` — escribió el reclamo a las 12:43:21, mientras el proceso todavía corría (terminó 12:43:51). Dos causas independientes, ambas de feedback:
- `action_meli_backfill_template_fields` (models/product.py) terminaba en `return True`: todo el resultado iba al log, cero notificación. Ahora devuelve un `display_notification` **sticky** (el proceso dura minutos; un toast que se desvanece es justo lo que dejaba la duda) con actualizados / omitidos / errores. Casos "sin cuentas ML logueadas" y "ningún producto vinculado" también avisan.
- **El server action de la lista descartaba el retorno**: `views/product_view.xml` tenía `records.filtered(...).action_meli_backfill_template_fields()` sin asignar a `action` → en `ir.actions.server` state=code, sin `action = ...` el dict devuelto **no llega al cliente**. Con solo arreglar el método, el camino que usó el cliente (lista) hubiera seguido mudo. Además se quitó el `.filtered(...)` previo: el método ya filtra, y necesita VER los no-vinculados para poder reportarlos (si no, `omitted` daba 0 siempre desde la lista).
Contadores nuevos: `skipped` (link en template pero no en variante) + `unlinked` (seleccionados sin vínculo ML); en el log van separados, en pantalla se suman como "omitidos". Sin cambio de schema. Bump 26.76→26.77 (solo 19.0: sesión de cliente; backport 16/17/18 = deuda).

---

**2026-07-10** `[19.0.26.70]` — orders_resync_status: dominio in-flight + order asc [#475]

Refinado el barrido de re-sync de estado para que cubra la ventana DE VERDAD (en sellers de alto volumen el limit=100/desc cubría ~10% y justo las órdenes NUEVAS que el sweep normal date_desc ya cubre). Cambios en `orders_resync_status` (models/orders.py): (a) dominio suma `("shipment_status", "not in", ("delivered",))` — la cancelación del comprador es pre-entrega; delivered (~73% en Score/WodPro) no es cancelable por esa vía → excluirla concentra el barrido en las in-flight (empty/pending/ready_to_ship/not_delivered/shipped = todas las no-entregadas, no se pierde ninguna cancelable) y hace la ventana entera cubrible (medido prod 30d: Score 1107 / WodPro 482 in-flight vs 4784 "abiertas"). (b) `order="date_created asc"` (más viejas primero = at-risk; si el limit trunca, trunca las nuevas ya cubiertas). (c) defaults days 7→15, limit 100→500 (en prod se fijan por CONFIG). `shipment_status` = Char related indexado (models/orders.py). Bump 26.69→26.70, 4 versiones idénticas. meli_oerp_multiple no cambia (dispatcher igual). Nota: source venía de 26.65→26.69 por trabajo concurrente (post_title 26.69 unpushed encima).

---

## 2026

**2026-07-08** `[19.0.26.65]` — `orders_resync_status` acepta `account=None` (multi-cuenta) [#475]

El re-sync de estado de #475 (26.62) era mono-cuenta: `orders_resync_status` derivaba `company` de `self.env.user.company_id` y consultaba con un único token. Se agregó param opcional `account` (mercadolibre.account): cuando viene (lo pasa el dispatcher de meli_oerp_multiple) el dominio suma `("connection_account","=",account.id)` y `company` se deriva de `config.company_id` (connection_configuration) en vez del user del cron. Retrocompat total: sin `account`, idéntico al histórico (config=res.company sin `company_id` → cae a env.user.company_id). Log final ahora incluye `cuenta=`. Bump 26.64→26.65, 4 versiones. El dispatcher vive en meli_oerp_multiple (no requiere ir.cron nuevo: reutiliza `ir_cron_module_cron_meli_orders_status`). Caso Score/WODPRO (co1 361 + co3 499 mismo Odoo).

---

**2026-07-08** `[19.0.26.63]` — Import de medidas del paquete: fill-empty → OVERWRITE (ML autoritativo) [#424 Deco/KPI]

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
