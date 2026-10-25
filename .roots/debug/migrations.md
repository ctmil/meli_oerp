# meli_oerp - Migrations

> Registro de migraciones de datos, campos y esquemas.

---

### 20.0.26.301 — reglas de Odoo 20 (`test_lint`) aplicadas (24-oct-2026, F8b, rama `claude/lint-20.0` desde 20.0 4ceb33de)
Vara: `.roots/scripts/odoo-lint.sh` del workspace (pylint con las opciones de `test_lint/test_pylint.py` + `test_lint` del core
20 corrido de verdad). Varas de error: **175 → 57**; lo que queda está justificado regla por regla en
`.roots/docs/compat-20-backport.md` del workspace (bugs latentes `undefined-variable`, parámetros `context` de métodos
públicos y `shipment.update` = cambios de API del suite entero; licencia = decisión de FCA). Sube a 301 porque cambian vistas.
`-u` c+e 0 WARNING / 0 ERROR; tests 84, 0 failed, 0 error (igual que 26.300).
- **Íconos:** 40 botones `icon="fa-*"` ⇒ Material Symbols con el mapeo oficial (`odoo-bin upgrade_code` 19.5-00). En 20 un
  `fa-*` en `icon=` se pinta con la fuente Material ⇒ salía roto sin error.
- **Firmas:** `stock.move._action_assign(force_qty=False)` (con `mrp` arriba en el MRO era `TypeError`), `meli.warning.copy(default=None)`;
  borrado `sale.order.action_done` (sin padre desde 17) y `grid.row.col.name_get` (no se llama desde 17).
- **SQL:** 3 consultas con datos de ML ahora parametrizadas (mismo SQL para valores válidos); 5 concatenaciones de constantes
  con `# pylint: disable=sql-injection` + motivo.
- **Índices:** `btree_not_null` en 17 many2one (inversos de o2m / saltos de `depends`). En 20 el `-u` los crea (verificado).
- Manifest sin `demo_xml`/`active`/`installable`; `_()` en 2 excepciones; código muerto tras `return` fuera; docstring RST;
  `tests/__init__` importa los 6 tests puros (Odoo no los ejecuta: no son `odoo.tests.TestCase`).

### 20.0.26.300 — PORT 19.0 → 20.0, 2.ª pasada (24-oct-2026, F3: runtime que `-i/-u` no ve)
El piloto (01d5a6f3) instalaba limpio, pero el diff de registry 19 vs 20 y una prueba en shell mostraron rupturas EN RUNTIME
(no fallan al instalar). Mismo build (sin cambio de features). `-u` c+e 0 WARNING / 0 ERROR; tests del módulo en 20 con el suite
instalado: **84, 0 failed, 0 error** (`test_26278` ahora corre porque accounting está instalado).
- **Binary/Image 20** (se leen como `BinaryValue` crudo; escribir `bytes` ⇒ `TypeError`): `versions.get_image_full` devuelve
  base64 como en 19 (`b64_of_binary`) y `set_image_full` escribe str base64 (`b64_for_binary_write`) ⇒ importación de fotos de
  ML y subida de imágenes siguen con el contrato de 19. Colector de imágenes (`image_variant_1920`/`image_1920` directos) pasa
  por `b64_of_binary`. Miniatura de video: `.decode()`. Etiquetas: `pdf_file`/`pdfimage_file` se escriben como str base64, la
  lectura del PDF es `bytes(...)`, y `_get_shipment` entrega base64 al reporte. Smoke en shell 20: ida/vuelta de imagen,
  `get_first_image_to_publish`, PDF de etiqueta OK.
- **`ir.attachment.datas`** (ignorado en 20 ⇒ adjunto vacío): CSV de `product_post` con `'raw'`.
- **`mrp.bom(.line).product_uom_id` → `uom_id`:** `_meli_kit_components` (explosión de kits en la confirmación de stock) y la
  creación de BOM kit. Sin esto el `except` devolvía `None` y el kit se trataba como producto simple EN SILENCIO. Smoke: kit
  2×comp, qty 3 ⇒ `[('comp20', 6.0)]`.
- **`uom.uom.rounding` eliminado** ⇒ `comp.uom_id.compare(free, qty)` en el chequeo de faltantes de componentes.

### 20.0.26.300 — PORT 19.0 → 20.0 (24-oct-2026, agente migrador-20, rama `claude/port-20.0` desde origin/19.0 a30d1752)
Core 20 medido: odoo 632c2d6c · enterprise f6513ecb. `-i` y `-u` en `meli20_test` (community) y `meli20e_test`
(+enterprise, `web_enterprise`): **0 WARNING / 0 ERROR**. Mismas features que 19.0.26.300 ⇒ mismo build.
Cambios (sólo lo que 20 exige; sin refactor):
- **Seguridad:** 20 eliminó `ir.model.access` e `ir.rule` ⇒ un solo modelo `ir.access` (`operation` 'crud' + `domain`).
  `security/ir.model.access.csv` → `security/ir.access.csv` (66 filas, perms 1/0 → letras `crud`; `model_id` por nombre de
  modelo). Los 3 `ir.rule` multi-company (orders/shipment/questions) → filas **sin grupo** = restricción, mismo dominio.
  El `ir.rule` duplicado de questions en `data/parameters_data.xml` se borró.
- **`ir.config_parameter`:** `get_param/set_param` ya no existen ⇒ `get_str(key, default)` / `set_str` (get_param(k) ≡
  get_str(k, False)). 21 llamadas (models, `__init__` hook y tests).
- **`res.partner.company_type`:** eliminado del core (is_company pasa a compute de has_vat+commercial_partner). La importación
  de compradores lo escribe y compara ⇒ se restituye en `models/res_partner.py` con la definición de base 19 (compute/inverse
  sobre is_company). Verificado en shell: company→is_company True; person con VAT → False.
- **Devoluciones:** el wizard `stock.return.picking` **no existe** en 20 ⇒ `_meli_return_done_pickings` usa
  `picking._create_return()` + `action_return_all()` cuando el wizard falta (mismo guard de cantidad entregada). Smoke en shell:
  picking 3 u. done → devolución draft con 3 u. y `origin_returned_move_id` (lo que el resto del flujo busca).
- **Imágenes de variante:** website_sale 20 sacó `product.image.product_variant_id` y `product.product.product_variant_image_ids`
  (las imágenes de variante cuelgan de `attribute_value_ids`). Se restituyen ambos campos en `models/product_image.py`
  (definición de website_sale 19) para las fotos por variación de ML. ⚠️ El sitio web 20 NO muestra esas imágenes por variante
  (usa attribute_value_ids): mapear eso es feature, no port — abierto.
- **Video:** `html_editor.tools.get_video_embed_code/get_video_thumbnail` eliminados ⇒ import con fallback (embed False) en
  `mercadolibre.image`; la constraint de video_url sólo valida embed si los helpers existen.
- **Controller:** `content_disposition` vive en `odoo.http.stream` (odoo.http es paquete; `web.controllers.main` vacío).
- **`_sql_constraints`:** en 20 su sola presencia (aun `[]`) da WARNING ⇒ se quitaron los 3 (claim, attribute_mapping x2); queda
  el `UniqueIndex`.
- **Vistas:** kanban `product.image` (sin `name` en la card ni `div.card` literal → ancla `image_1920/..`); lista de plantillas
  sin `virtual_available` (ancla `qty_available`); `t-esc`/`t-raw` prohibidos en arch y no compilados por QWeb 20 → `t-out`
  (banner kanban + 2 reportes); `ir.actions.report.report_file` eliminado → borrado.
- Sin scripts de migración nuevos. Las carpetas `migrations/19.0.*` no aplican a una instalación 20 nueva; una base 19→20
  de un cliente es otro frente (upgrade de Odoo + mapeo de ACL a ir.access lo hace el upgrade oficial).
- Tests del módulo en 20 (community): 102 tests, 0 failed, 1 error = `setUpClass` de `test_26278_cancel_por_motivo`, que usa
  `res.company.mercadolibre_invoice_cancel_mode` (campo de meli_oerp_accounting, no instalado): dependencia cruzada
  preexistente en 19, no del port.

**Clasificación F8** (A = la forma nueva ya funciona en 16–19 ⇒ candidato a backport para converger · B = sólo 20 ·
C = cambio de comportamiento/feature). Medido en `odoo/16.0–19.0` (read-only; ⚠️ `odoo/19.0` = master 19.1a): `ir.attachment.raw`
existe en 16–19; `fields.Binary` acepta str base64 al escribir en 16 (`convert_to_cache`); `t-out` existe en QWeb 16;
`uom.uom.compare` sólo en 19.1; `ir.config_parameter.get_str` y `odoo.http.stream` NO existen en 16–19. NADA aplicado atrás.
- B · `security/ir.access.csv` (ir.model.access/ir.rule no existen en 20; en 16–19 sí, y ir.access no).
- B · `get_param/set_param` → `get_str/set_str` (get_str no existe en 16–19; si se quiere una sola lógica: shim en versions.py).
- C · `res.partner.company_type` restituido (20 lo sacó; is_company pasa a compute). Decisión de producto.
- B · devolución sin wizard (`_create_return()` + `action_return_all()`); el código queda con guard y en 16–19 sigue el wizard.
- C · `product.image.product_variant_id` / `product_variant_image_ids` restituidos; el sitio 20 no muestra imágenes por variante.
- A · import con fallback de `get_video_embed_code/get_video_thumbnail` (inocuo en 16–19).
- B · `content_disposition` desde `odoo.http.stream` (no existe en 16–19; con try/except de import sería A).
- B · quitar `_sql_constraints` (queda `UniqueIndex`, que no existe en 16).
- B · ancla kanban `product.image` y lista de plantillas (`qty_available`): vistas distintas por serie, no medido en 16–18.
- A · `t-esc`/`t-raw` → `t-out` (banner kanban + 2 reportes).
- A · borrar `report_file` del reporte (verificar en 16–19 el nombre del archivo descargado antes de aplicar).
- A · `b64_of_binary` / `b64_for_binary_write` en `get_image_full`/`set_image_full`, colector de imágenes, `_get_shipment`,
  miniatura de video y `pdf_file`/`pdfimage_file` como str base64 (en 16–19 el Binary ya es base64 ⇒ los helpers son no-op).
- B · `bytes(shipment.pdf_file)` (en 16–19 `bytes()` daría el base64, no el PDF; con un helper `raw_of_binary` sería A).
- A · `ir.attachment` con `'raw'` en el CSV de product_post (raw existe en 16–19).
- B · `mrp.bom(.line).uom_id` (en 16–19 es `product_uom_id`).
- B · `uom.compare()` en vez de `rounding` (compare sólo desde 19.1).

### 19.0.26.282 — sin script de migración (20-oct-2026, #513 direcciones manuales)
- Campos nuevos, vacíos tras el `-u`: `sale.order.meli_partner_invoice_auto_id`, `sale.order.meli_partner_shipping_auto_id`
  (Many2one res.partner, copy=False, ondelete set null) y `res.partner.meli_address_sync_hash` (Char). Sin backfill: los
  pedidos viejos usan la regla de legado (sólo el valor por defecto se considera del conector) y adoptan el registro en la
  primera sincronización en que coinciden con ML.
### 19.0.26.221 — sin script de migración (13-oct-2026, #638 motivos)
- Campo nuevo `sale.order.meli_cancel_return_skipped` (Boolean, index, default False): lo crea el `-u`. **No se
  rellena hacia atrás**: las ventas canceladas sin devolución antes de 26.221 no quedan marcadas.
- Parámetro `meli_oerp.cancel_return_reasons` = `buyer_cancel_express,fraud` en `data/parameters_data.xml`
  (`noupdate=1`): se crea en el `-u` si no existe; si el cliente lo cambió, se respeta. Verificado en 19 borrando
  param + xmlid y corriendo `-u meli_oerp`.
### 19.0.26.171 — sin script (1-oct-2026, 431 E1-E4)
Campos nuevos: `mercadolibre_cancel_auto_from` (Datetime, vacío) en `res.company` (y gemelo en `mercadolibre.configuration`,
meli_oerp_multiple); `sale.order.meli_cancel_date` (Datetime) y `sale.order.meli_cancel_held` (Boolean). El ORM crea las
columnas vacías ⇒ comportamiento idéntico al anterior hasta cargar la fecha de corte. Sin backfill: para las ventas viejas la
fecha de cancelación se lee del texto de `meli_status_detail`.

### 19.0.26.170 — sin script (30-sep-2026, #645)
`mercadolibre_order_confirm_no_stock_mode` (Selection, default `confirm`) en `res.company` (meli_oerp) y en
`mercadolibre.configuration` (meli_oerp_multiple). El ORM crea la columna con el default ⇒ comportamiento idéntico al anterior.
## 5 oct 2026 — `sale.order.meli_handling_limit` almacenado (v19.0.26.188) [#431]

- El related `meli_shipment.estimated_handling_limit` pasa a `store=True, index=True`.
- `migrations/19.0.26.188/pre-migrate.py`: crea la columna (`ADD COLUMN IF NOT EXISTS`) y la llena por SQL desde
  `mercadolibre_shipment` **antes** de cargar el modelo ⇒ Odoo no recomputa pedido por pedido.
- Los envíos viejos siguen sin fecha hasta que se re-sincronicen (sólo se consulta `/sla` para envíos por despachar).


### 19.0.26.164 — `migrations/19.0.26.164/post-migrate.py` (29-sep-2026, ola de cancelaciones integrada)
La siembra OLA3 (antes `19.0.26.149` → `19.0.26.162`) se renombra otra vez a **`19.0.26.164`**, el build de la ola integrada
(cancel-v2 26.162 + #585 26.163). Odoo corre las carpetas con `instalada < carpeta <= nueva`: con 26.164 corre desde una base
en 26.159 (origin) **y** desde una que ya haya quedado en 26.162/26.163 por un ensayo de las ramas sueltas. Idempotente.
#585 (26.163) no trae migración: sólo métodos y una `ir.actions.server` (la crea el `-u`).

### 19.0.26.162 — `migrations/19.0.26.162/post-migrate.py` (29-sep-2026)
Es la siembra OLA3 de `meli_cancel_reason_code` que estaba en `19.0.26.149`, **renombrada**: origin/19.0 ya estaba en 26.159, así que
una base en 26.150–26.159 nunca habría corrido una carpeta 26.149. Idempotente (sólo escribe filas vacías). Campos nuevos de 26.162
(`mercadolibre_cancel_mode`, `meli_cancel_waiting_return`, `meli_cancel_decision`) los crea el ORM con default; sin migración.


## 24 sep 2026 - motivo de cancelacion estructurado (v19.0.26.142) [#607 PetMarkt]

- **Campo NUEVO stored+index -> requiere `-u meli_oerp`** (el bump a 26.142 lo dispara):
  `sale.order.meli_cancel_reason_code` (Char, index) = el `cancel_detail.code` que informa ML.
- **Campo de configuracion nuevo (sin migracion de datos):**
  `res.company.mercadolibre_return_mode` (Selection `none`/`draft`/`done`, default **`done`**).
  Su GEMELO `mercadolibre.configuration.mercadolibre_return_mode` vive en `meli_oerp_multiple`
  con el MISMO default: si los defaults difieren, en multi-cuenta la opcion queda apagada sin
  que se note (bug del #453 / #587).
  ⚠️ **Cambia el comportamiento por defecto:** hasta 26.138 la devolucion se creaba y quedaba
  `assigned` (y la cancelacion de la orden la cancelaba). Desde 26.142 se crea Y SE VALIDA. Quien
  quiera el comportamiento viejo tiene que poner el modo en `draft` **explicitamente**.
- **Migracion `migrations/19.0.26.142/post-migrate.py` (post, idempotente):** siembra
  `meli_cancel_reason_code` parseando el texto de `meli_status_detail`, donde el codigo venia
  concatenado con el formato `" | <code>: <desc> (solicitado por: <x>, fecha: <y>)"`. Toma el
  ULTIMO `" | "` (el texto se appendea al final) y valida el token contra
  `^[A-Za-z0-9_.\-]{2,64}:\s`. Si `cancel_detail` venia sin `code`, no escribe nada.
  **Solo toca filas con el campo NULL o vacio; no toca `meli_status_detail`.**

---

## 28 jul 2026 - sello de movimientos de stock: create_date -> GREATEST(date, write_date, create_date) (v19.0.26.88) [OrgVit 475]

- **Sin migracion de datos ni de esquema.** Codigo puro en `models/product.py` y `models/company.py`.
  No crea columnas. El bump dispara `-u meli_oerp`.
- **Cambio de SEMANTICA de un campo YA existente (leer antes de deployar):**
  `product_product.meli_stock_moves_update` pasa a calcularse con
  `GREATEST(date si state='done', write_date, create_date)` y a ser **monotono**.
  - Los valores viejos **no se reescriben**: no hay backfill. Se van corrigiendo solos a medida que
    cada producto pasa por `process_meli_stock_moves_update()`.
  - **Efecto esperado en el primer ciclo post-deploy:** en instalaciones con drift acumulado, muchos
    bindings van a pasar de `updated` a `update` de golpe (el sello nuevo es >= al viejo y ademas entra
    la red de seguridad por antiguedad de `meli_oerp_multiple`). **Es el comportamiento buscado**, pero
    hay que vigilar el tamano de la primera tanda: con `meli_cron_stock_top_commit` bajo (25 en OrgVit)
    y el cron cada 10 min, drena solo pero puede tardar horas en catalogos grandes.
    Si hace falta escalonarlo, subir `mercadolibre_stock_resync_days` los primeros dias y bajarlo despues.
- **Sin cambios de vistas** en este modulo.

## 19 jul 2026 — comprador + zona del receiver buscables en sale.order (v19.0.26.83) [#404 Deco/KPI]

- **Campos nuevos stored/related → requieren `-u meli_oerp`** (el bump 26.83 lo dispara en Odoo.sh):
  - `sale.order.meli_buyer_nickname` / `meli_buyer_id` (Char, computed+store+index desde `meli_buyer`):
    se **recomputan** en el upgrade a partir del comprador ya vinculado (retroactivos, sin script).
  - `sale.order.meli_receiver_state/city/neighborhood/zip_code` (Char, related+store+index desde
    `meli_shipment`): **backfillean** en el upgrade desde el envío existente. Provincia/Localidad/CP
    quedan pobladas para el histórico; el **Barrio** (receiver_neighborhood) solo aparece en envíos
    **re-fetcheados** post-deploy (los históricos no lo tenían guardado → vacíos hasta re-consultar el envío).
  - `mercadolibre.shipment.receiver_neighborhood` / `receiver_municipality` (Char): columnas nuevas,
    sin backfill (se llenan al re-consultar/procesar cada envío desde `receiver_address.neighborhood/municipality`).
- **Sin script de migración** (el backfill lo hace el recompute/related del upgrade). Convergencia byte-idéntica 16/17/18/19.
## 20 jul 2026 — savepoints anti-`InFailedSqlTransaction` (v19.0.26.83) [#410 SOLSUN]

- **Sin migración de datos ni de esquema.** Cambio de código puro en `models/category.py` y
  `models/product.py` (savepoints ORM alrededor de llamadas frágiles). El bump 26.83 sólo dispara
  `-u meli_oerp`; no crea columnas ni requiere backfill. Convergencia byte-idéntica 16/17/18/19.

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

## 20.0 — build Odoo.sh (F7, 24-oct-2026): 0 WARNING / 0 ERROR en tests de la plataforma
Odoo.sh (dev build, demo, `--test-enable --log-level=test --test-tags /<suite>`) marcó el build 40514555 *failed*
y con 165 líneas W/E, todas emitidas DESDE TESTS (la instalación estaba limpia). Fix sin cambio de comportamiento:
tests: MP falso 503 en vez de ConnectionError (test_513/542/import_cupon; 431 y adopcion heredan) + mute del 'no account' de multiple cuando el suite está instalado; assertLogs en los WARNING esperados (525 diag full, cupon_envio backstop, 26278 x2, adopcion c/d); mute_logger de meli_util en test_452 (consulta /sites sin red).
Verificado: banco e+demo y c sin demo `0 failed, 0 error(s) of 236`, 0 líneas W/E; -u c/e limpio. Versión sin cambio (20.0.26.301: sin vistas/data).

---

## 20.0 — smoke de UI (F7b, 25-oct-2026): forms nuevos de `mercadolibre.category`
`odoo20-ui-smoke.mjs` abre en blanco los forms de modelos sin datos demo: `Categorías > Nuevo` rompía con
`ValueError: Compute method failed to assign ...meli_category_url` (y luego `meli_category_attributes`): `_get_category_url`
y `_get_attributes` sólo asignaban dentro del `if meli_category_id` (y `meli_father_category_id` sólo si `path_from_root>=2`).
Fix mínimo: asignar `False` al inicio de cada vuelta; con datos válidos el valor final es el mismo. NO es salto 19→20
(mismo código en 16–19) ⇒ **clase A, backport en la próxima release**. Build 26.303 (acompaña al suite: autofacturación toca vistas).
Abierto (pre-existente, igual en 19): abrir producto / compañía / forms ML sin cuenta conectada hace `GET /sites` a ML
(`res.company` site lookup) y meli_util loguea `WARNING ... Auth error status=403` en cada pantalla.
