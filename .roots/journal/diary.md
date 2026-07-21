# meli_oerp - Development Diary

> Reflexiones diarias sobre el desarrollo.

---

**2026-07-21** `[17.0.26.84]` — backport: _meli_import_template_attributes escribe a TODAS las variantes de la publicacion [#424 Deco/KPI]

Reporte cliente: "Traer medidas solo toma la primera variante". El metodo ahora arma ml_prod_vals y los escribe a todas las variantes con el mismo meli_id (overwrite dims/paquete/impuestos, fill-empty por-variante marca/modelo/genero). Backport de 19.0. Bump ->26.84.

---

**2026-07-16** `[17.0.26.81]` — backport dims del producto + IVA/impuesto interno (import+publish) [#424/#474 Deco/KPI]

Backport de 19.0 (26.78 import + 26.79 publish). Campos meli_product_{width,height,length}+*_unit y meli_vat/meli_import_duty en product.template/product.product; parser _meli_parse_dimension; poblado en _meli_import_template_attributes (+ llamada agregada en meli_oerp_multiple.product_meli_get_product, que no encadena a la base); publish envia WIDTH/HEIGHT/LENGTH + VALUE_ADDED_TAX/IMPORT_DUTY en el builder de atributos del body. Bump oerp ->26.81, multiple ->26.78.

---

**2026-07-15** `[17.0.26.80]` — backport #485: "Traer medidas" avisa + la acción de lista tragaba el retorno [Deco/KPI]

Backport de 19.0 (`33133d7b`). Dos causas de feedback, ambas presentes IDÉNTICAS en las 4 versiones:
- `action_meli_backfill_template_fields` (models/product.py) terminaba en `return True`: el resultado iba solo al log. Ahora devuelve `display_notification` **sticky** (el proceso dura minutos sobre miles de productos) con actualizados/omitidos/errores; también avisa "sin cuentas ML logueadas" y "ningún producto vinculado".
- `views/product_view.xml`: el `ir.actions.server` de la vista Lista llamaba al método **sin asignar a `action`** → en state=code el dict devuelto NO llega al cliente. **La acción masiva estaba muda en TODAS las versiones**, no solo en la del cliente que lo reportó. Se quitó además el `.filtered(...)` previo (el método ya filtra y necesita ver los no-vinculados para contarlos).
Contadores `skipped`/`unlinked` separados en el log, sumados como "omitidos" en pantalla. Sin cambio de schema. Verificado end-to-end en la prod de Deco (19.0, 26.77): productos vinculados → aviso `success`; sin vínculo → `warning`.

---

**2026-07-10** `[17.0.26.70]` — orders_resync_status: dominio in-flight + order asc [#475]

Refinado el barrido de re-sync de estado para que cubra la ventana DE VERDAD (en sellers de alto volumen el limit=100/desc cubría ~10% y justo las órdenes NUEVAS que el sweep normal date_desc ya cubre). Cambios en `orders_resync_status` (models/orders.py): (a) dominio suma `("shipment_status", "not in", ("delivered",))` — la cancelación del comprador es pre-entrega; delivered (~73% en Score/WodPro) no es cancelable por esa vía → excluirla concentra el barrido en las in-flight (empty/pending/ready_to_ship/not_delivered/shipped = todas las no-entregadas, no se pierde ninguna cancelable) y hace la ventana entera cubrible (medido prod 30d: Score 1107 / WodPro 482 in-flight vs 4784 "abiertas"). (b) `order="date_created asc"` (más viejas primero = at-risk; si el limit trunca, trunca las nuevas ya cubiertas). (c) defaults days 7→15, limit 100→500 (en prod se fijan por CONFIG). `shipment_status` = Char related indexado (models/orders.py). Bump 26.69→26.70, 4 versiones idénticas. meli_oerp_multiple no cambia (dispatcher igual). Nota: source venía de 26.65→26.69 por trabajo concurrente (post_title 26.69 unpushed encima).

---

**2026-07-08** `[17.0.26.65]` — `orders_resync_status` acepta `account=None` (multi-cuenta) [#475]

El re-sync de estado de #475 (26.62) era mono-cuenta: `orders_resync_status` derivaba `company` de `self.env.user.company_id` y consultaba con un único token. Se agregó param opcional `account` (mercadolibre.account): cuando viene (lo pasa el dispatcher de meli_oerp_multiple) el dominio suma `("connection_account","=",account.id)` y `company` se deriva de `config.company_id` (connection_configuration) en vez del user del cron. Retrocompat total: sin `account`, idéntico al histórico. Log final incluye `cuenta=`. Bump 26.64→26.65, 4 versiones. Dispatcher en meli_oerp_multiple (reutiliza `ir_cron_module_cron_meli_orders_status`, sin cron nuevo). Caso Score/WODPRO (co1 361 + co3 499 mismo Odoo).

---

## 2026

**2026-07-08** `[17.0.26.63]` — Import de medidas del paquete: fill-empty → OVERWRITE (ML autoritativo) [#424 Deco/KPI]

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
