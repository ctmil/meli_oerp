# meli_oerp — Documentación técnica

## Tanda jun-2026 (v26.39) — campos/modos/config de cara al usuario

- **Modo de impresión de etiqueta `zpl_txt`:** además de PDF y ZPL (zip), nuevo modo que extrae
  el contenido ZPL del zip que entrega ML y lo guarda como `.zpl` plano (listo para enviar a la
  impresora sin descomprimir). El selector de modo vive en la configuración de la cuenta
  (`meli_oerp_multiple`); el armado lo hace `shipment.py` (`response_type=zpl2`, `io`+`zipfile`).
- **Nombre de descarga de la etiqueta:** los campos binarios de etiqueta declaran `filename=`,
  por lo que la descarga ahora muestra `Shipment_<shipping_id>.pdf` / `.zpl` (antes mostraba el
  tamaño, p.ej. "1.10 Kb").
- **`mercadolibre_set_fiscal_position` (Boolean, default True):** controla si la importación de la
  orden setea la posición fiscal de la venta. En **False** deja la posición fiscal en blanco
  (campo en `meli_oerp_multiple`, consumido por `orders.py`).
- **Equipo/vendedor respetados:** si el equipo de ventas o el vendedor se setearon a mano, la
  importación ya no los pisa. El vendedor de ML (`seller_team`) se asigna aunque la cuenta no
  tenga compañía asociada.
- **Fechas del envío:** la ficha del envío muestra además buffering_date, schedule_limit,
  pay_before, pickup_promise (from/to) y desired_promised_delivery, tomadas de `shipping_option`.

---

## Surtido multi-almacén — depósito de origen por línea de orden (8 jul 2026, v19.0.26.66)

La orden de MercadoLibre trae, por ítem, el **depósito logístico de origen** desde el que ML surte
(`Item.stock = {"store_id": ..., "node_id": ...}`). Ahora se persiste en la línea de orden
(`mercadolibre.order_items`):

- **`meli_stock_node_id`** (ML Stock Node ID) — network node del depósito ML (ej. `MXP4397768091`).
- **`meli_stock_store_id`** (ML Stock Store ID) — store id del depósito ML.

Ambos indexados. Se cruzan con el mapeo Depósito ML→ubicación Odoo (`mercadolibre.account.stock_location`,
en meli_oerp_multiple) para rutear la venta al almacén correcto (ver meli_oerp_stock). Poblado
automático al procesar/actualizar la orden.

## Etiquetas de envío (guías ML): dónde se guardan y cómo ubicar el archivo en disco

> Versión Odoo **19.0**. Mismo modelo/campos/método en 16.0/17.0/18.0/19.0; sólo cambian
> los nº de línea del armado del filename (ver al pie).

### Modelo y campos

La etiqueta de la guía vive en el modelo **`mercadolibre.shipment`** (`models/shipment.py:415`):

| Campo | Tipo | Contenido |
|---|---|---|
| `pdf_file` | `Binary(attachment=True)` | la **etiqueta**: PDF **o ZPL2** (base64) |
| `pdf_filename` | `Char` | `Shipment_<shipping_id>.pdf` o `.zpl` |
| `pdfimage_file` | `Binary(attachment=True)` | **preview JPG** (si hay `pdf2image`) |
| `pdfimage_filename` | `Char` | nombre del preview |

(definidos en `shipment.py:529-532`)

Se llena en `_get_shipment_labels_data` (`shipment.py:185`) / al imprimir: se baja de
`https://api.mercadolibre.com/shipment_labels?...&response_type=pdf|zpl2`, se hace
`base64.b64encode(data)` y se asigna a `shipment.pdf_file`. **PDF y ZPL comparten `pdf_file`**;
los distingue la extensión del `pdf_filename`.

En `sale.order` NO se vuelve a guardar: son campos `related` (`models/orders.py:261-262`)
`meli_shipment_pdf_file` y `meli_shipment_pdf_filename` que apuntan al mismo
`mercadolibre.shipment` (vía `meli_shipment`). En este módulo `stock.picking` NO lleva el
related (si existe, sería en `meli_oerp_stock`).

### Nombres finales de los archivos

El nombre **lógico/de descarga** lo arma el código (`shipment.py` líneas PDF **1857** / ZPL **1876** /
preview jpg **1870**) a partir del `shipping_id` (campo `mercadolibre.shipment.shipping_id` = "Envio Id"
de ML, único e indexado — `shipment.py:423`):

| Archivo | Nombre final (campo `*_filename`) |
|---|---|
| PDF | `Shipment_<shipping_id>.pdf` |
| ZPL | `Shipment_<shipping_id>.zpl` |
| preview | `Shipment_<shipping_id>.jpg` |

> ⚠️ **Clave**: ese nombre vive en `pdf_filename` / `pdfimage_filename`. En **disco NO se llama así**:
> el archivo es `store_fname` = `xx/<sha1>` (sin extensión). Y el `ir_attachment.name` del attachment
> de campo es el nombre del campo (`pdf_file`), tampoco el nombre final. Para exportar/guardar el ZPL
> con nombre humano hay que usar `pdf_filename`.

### Cómo Odoo guarda un `Binary(attachment=True)`

NO se guarda en la columna de la tabla `mercadolibre_shipment`. Odoo crea un **`ir.attachment`** con
`res_model='mercadolibre.shipment'`, `res_id=<id>`, `res_field='pdf_file'`. Según el parámetro
`ir_attachment.location` (default **`file`**), los bytes van al **filestore**:

```
<data_dir>/filestore/<dbname>/<store_fname>
```

- `store_fname` (columna de `ir_attachment`) = ruta relativa tipo `ab/abcdef…` (sha1; los 2 primeros
  hex como subcarpeta). `checksum` = ese sha1; `file_size` = bytes.
- `data_dir` = directorio de datos de Odoo (`tools.config['data_dir']`, p.ej. `/var/lib/odoo` o
  `~/.local/share/Odoo`). Si `location='db'`, los bytes están en `ir_attachment.db_datas` (sin archivo).

### Técnica para encontrar el archivo en disco

**A) Vía ORM (odoo shell) — recomendado:**
```python
shipment = env['mercadolibre.shipment'].browse(SHIPMENT_ID)
att = env['ir.attachment'].sudo().search([
    ('res_model', '=', 'mercadolibre.shipment'),
    ('res_id',    '=', shipment.id),
    ('res_field', '=', 'pdf_file'),        # o 'pdfimage_file' para el preview
], limit=1)
print(att.store_fname)                      # ruta RELATIVA en el filestore
print(att._full_path(att.store_fname))      # ruta ABSOLUTA en disco
```
> Nota: hay que poner `res_field` explícito en el dominio — Odoo oculta por defecto los attachments
> de campo (`res_field IS NULL`). El `sudo()` evita problemas de permisos.

**B) Vía SQL (sin ORM) — buscar por `shipping_id` y traer nombre final + ruta juntos:**
```sql
SELECT s.id            AS shipment_id,
       s.shipping_id   AS envio_id,
       s.pdf_filename  AS nombre_final,   -- Shipment_<shipping_id>.zpl|pdf
       a.store_fname,                      -- ruta relativa en disco (hash)
       a.mimetype, a.file_size
FROM mercadolibre_shipment s
JOIN ir_attachment a
  ON a.res_model = 'mercadolibre.shipment'
 AND a.res_id    = s.id
 AND a.res_field = 'pdf_file'             -- o 'pdfimage_file' para el preview
WHERE s.shipping_id = 'ENVIO_ID';         -- o:  s.id = SHIPMENT_ID
```
Path en disco = `<data_dir>/filestore/<dbname>/<store_fname>`. El **nombre final** para guardar/exportar
es `nombre_final` (`pdf_filename`), NO el `store_fname`.

**C) Vía shell (ubicar `data_dir` y el archivo):**
```bash
grep -E "data_dir" /etc/odoo/odoo.conf          # o el .conf que use la instancia
ls -l <data_dir>/filestore/<dbname>/<store_fname>
# ZPL: el archivo es texto ZPL2 crudo → se puede enviar directo a la impresora:
cat <data_dir>/filestore/<dbname>/<store_fname> | lp -d <impresora_zpl>
```

### Método propuesto: devolver el path exacto (sobre todo ZPL)

Para que un servicio externo de impresión tome el ZPL directo del disco, agregar en
`mercadolibre.shipment` (`models/shipment.py`):

```python
def get_label_file(self, field='pdf_file'):
    """Ubicación + nombre FINAL del archivo de etiqueta en el filestore.
    field='pdf_file' (PDF o ZPL) | 'pdfimage_file' (preview JPG).
    Devuelve dict {'path','name','mimetype','size'} o {} si no está en disco
    (sin attachment, o guardado en DB con location='db')."""
    self.ensure_one()
    att = self.env['ir.attachment'].sudo().search([
        ('res_model', '=', self._name),
        ('res_id',    '=', self.id),
        ('res_field', '=', field),
    ], limit=1)
    if not att or not att.store_fname:
        return {}
    name = self.pdf_filename if field == 'pdf_file' else self.pdfimage_filename
    return {
        'path': att._full_path(att.store_fname),  # ruta absoluta en disco (hash)
        'name': name or att.name,                  # nombre FINAL: Shipment_<shipping_id>.zpl|pdf
        'mimetype': att.mimetype,
        'size': att.file_size,
    }
```

Uso:
```python
info = shipment.get_label_file()
# {'path': '/var/lib/odoo/filestore/<db>/ab/abcdef…', 'name': 'Shipment_43272588025.zpl', ...}
```
El servicio de impresión lee `info['path']` del disco y lo guarda/envía con `info['name']`.

> Este método aún **no existe** en el código (es propuesta). Si se implementa, va en el **source**
> `meli_oerp` para que baje a toda la flota por el sync (agente `sincronizacion-meli`).

---

### Nº de línea por versión (armado del filename en `shipment.py`)

El modelo (`L415`), los campos (`L529-532`), `shipping_id` (`L423`) y `_get_shipment_labels_data`
(`L185`) son **idénticos** en 16.0/17.0/18.0/19.0. Sólo cambian las líneas del armado del nombre:

| Versión | PDF `pdf_filename` | ZPL `pdf_filename` | preview jpg |
|---|---|---|---|
| **16.0** | 1860 | 1879 | 1873 |
| **17.0 / 18.0 / 19.0** | 1857 | 1876 | 1870 |

---

## Botón "Importar" (`product_meli_get_product`): qué trae de ML → Odoo (RPM #532, 11 jul 2026)

> Versión Odoo **19.0**. Referencia: botón en `views/product_view.xml:369`
> (`name='product_meli_get_product'`, `string="Importar"`, pestaña **MercadoLibre**, visible cuando
> `meli_id != False` y `meli_state != True`). Método: `models/product.py:2262`
> `def product_meli_get_product(self, context=None, meli_id=None, import_images=True)`.

Trazado completo de una llamada del botón sobre **un** `product.product` con `meli_id` seteado.
Cada apretón hace **1 GET `/items/{id}?include_attributes=all`** y, según ramas, GETs adicionales.

### Checklist de lo que trae (confirmado en el source)

| Dato | ¿Lo trae? | Cómo / dónde |
|---|---|---|
| **Título / family_name** | Sí | `meli_fields`/`tmpl_fields` (L2391-2465), respeta flags `mercadolibre_overwrite_variant/template` |
| **Descripción** | Sí (condicional) | Solo si `'descriptions' in rjson` → GET `/items/{id}/description` (L2320-2328) → `meli_description` + `description_sale` (este último solo si el template no tenía uno y `mercadolibre_overwrite_template`) |
| **Precio** | Sí | `_meli_set_product_price` (L2362-2384; pricelist o `lst_price`) |
| **Categoría ML** | Sí | `_meli_set_category` (L2353 → L1326): setea `meli_category` (modelo `mercadolibre.category`) y opcionalmente `public_categ_ids`. **NO** toca la `categ_id` interna de Odoo |
| **Ficha "Plantilla" curada** (marca/modelo/género + 4 dims de paquete) | Sí, **siempre** | `_meli_import_template_attributes` (L2468 → L1071): 7 campos Char desde `rjson['attributes']` (BRAND/MODEL/GENDER fill-empty; `SELLER_PACKAGE_*`/`PACKAGE_*` authoritative-overwrite) |
| **Ficha técnica como atributos Odoo** (`product.attribute`/`.value`/`attribute_line_ids`) | **Condicional y PARCIAL** | `_get_non_variant_attributes(rjson['attributes'])` (L2810-2812 → L1811). **Gateado por `company.mercadolibre_update_existings_variants`** Y solo para attrs ML que YA tengan un `product.attribute` mapeado (`meli_default_id_attribute`). Ver detalle y GAP abajo |
| **Variantes / combinaciones** | Condicional | `_get_variations` (L2571-2572 → L2027), también gateado por `mercadolibre_update_existings_variants`; matcheo SKU/barcode de variantes L2608-2692 |
| **Imágenes** | Sí (si `import_images=True`, default) | `_meli_set_images_x` (L2745-2751 → L1762). El bloque comentado `#TODO: traer las imagenes` de L2344-2350 es **código muerto viejo**; la llamada real está más abajo. Máx. resolución vía `_meli_best_picture_url` (ver abajo) |
| **Shipping / logistic_type / free_shipping** | Sí | L2500-2506 |
| **video_id, dimensiones, warranty, catalog_*, user_product_id** | Sí | L2341-2462 |
| **Stock local** | Condicional | Solo si `company.mercadolibre_update_local_stock` (L2753-2766) |

### Call-path confirmado de la creación de ATRIBUTOS (ficha técnica)

Hay **dos** mecanismos distintos, no equivalentes:

1. **`_meli_import_template_attributes` (SIEMPRE, L2468).** Solo llena **7 campos Char** de la
   pestaña "Plantilla" (`meli_brand`, `meli_model`, `meli_gender`,
   `meli_seller_package_{height,width,length,weight}`) mapeando por id de atributo ML
   (`_MELI_IMPORT_ATTR_MAP` L1019). **NO** crea `product.attribute` ni `attribute_line_ids`. Es solo
   metadata plana curada.

2. **`_get_non_variant_attributes(rjson['attributes'])` (CONDICIONAL y PARCIAL, L2810).** Materializa
   atributos Odoo, pero **solo los que YA están mapeados**. Por cada attr ML:
   - L1821: busca `mercadolibre.category.attribute` por `att_id`.
   - L1828: busca `product.attribute` con `meli_default_id_attribute` = ese id.
   - **L1831: `if (attribute and len(attribute)==1 and attribute.id):` — SOLO si existe un
     `product.attribute` PREVIAMENTE mapeado** crea/reusa `product.attribute.value` (L1845) y la
     `attribute_line_ids` del template (L1848-1875).
   - **Si NO hay `product.attribute` mapeado a ese attr ML → NO HACE NADA.** No crea `product.attribute`
     desde cero. → **Las specs arbitrarias de ML (TREADWEAR, WHEEL_CONSTRUCTION_TYPE, etc.) NO se
     importan como atributos** salvo que un admin haya pre-creado el `product.attribute` con su
     `meli_default_id_attribute`. En la práctica solo aterrizan atributos que definen variantes o los
     que alguien mapeó a mano.
   - **Gate adicional:** `if (company.mercadolibre_update_existings_variants and 'attributes' in rjson)`.
     Si el flag "Actualiza/agrega variantes" (`company.py:467`) está en False, ni esto corre.

> **CORRECCIÓN (11 jul, hallazgo empírico prod RPM):** la afirmación previa de que "la ficha técnica
> genérica no se importa por ningún path" era **INCORRECTA**. `_get_non_variant_attributes` **SÍ crea
> la ficha técnica completa como `attribute_line_ids`** (con `product.attribute.meli_default_id_attribute`
> seteado y `create_variant=no_variation`) cuando **se cumplen sus dos prerequisitos**: (a) el flag
> `mercadolibre_update_existings_variants` prendido, y (b) la **categoría ML del ítem tiene sus atributos
> mapeados** (ver "Prerequisito por categoría" abajo). Verificado en prod: los productos VIEJOS de RPM
> (neumáticos: 25-26 líneas; baterías: 15) tienen la ficha completa así importada. El problema del
> re-import que puebla 0 tiene otra causa — ver **"Diagnóstico del 0"** más abajo.

> **IMPORTANTE — RPM ejecuta el OVERRIDE de `meli_oerp_multiple`, no este método base.** Todo lo de
> arriba describe el `product_meli_get_product` de `meli_oerp`. Con `meli_oerp_multiple` instalado (RPM),
> el método que corre es el **override** `meli_oerp_multiple/models/product.py:1234`, que difiere en
> puntos clave. Ver la sección siguiente antes de diseñar cualquier bulk.

### Imágenes: resolución (bug CDN ML `-O` webp) — estado por versión

`_meli_set_images_x` (L1762) → por variante `_meli_set_image_xy` (L1656) baja la principal + las
adicionales como `product.image`.

- **19.0 — YA CORREGIDO (#532).** Tanto la imagen principal (L1699-1702) como las adicionales
  (L1717-1718) llaman a **`_meli_best_picture_url(pic_id, ...)` (L1624)**, que hace GET
  `/pictures/{id}` y elige la variación de **mayor área** (`max(variations, key=_area)`), devolviendo
  su `secure_url`. El docstring de la función deja explícito que el truco `-O→-F` en la URL **no
  sirve** (prefijo/formato distintos) y que la única fuente confiable es `/pictures/{id}`.
  → **RPM es 19.0: el re-import trae la imagen de máxima resolución nativa. No hay bug pendiente acá.**

- **16.0 / 17.0 / 18.0 — BUG PRESENTE (gap de alineación).** `_meli_best_picture_url` **no existe**.
  En `_meli_set_image_xy`:
  - Principal (17.0 L1666): `thumbnail_url = picture_hash[first_pic_id]['url']` → el `url` **chico**
    de `/items` (no secure, baja resolución).
  - Adicionales (17.0 L1681-1690): hace GET `/pictures/{id}` pero toma **`variations[0]['secure_url']`**
    (el **primer** elemento del array, que NO es necesariamente el de mayor área → suele caer en la
    `-O` webp ~500px), en vez del de máxima área.

  **Fix propuesto (NO aplicado aún — pendiente de sources-align):** forward-portar a 16/17/18 el
  método `_meli_best_picture_url` de 19.0 y reemplazar ambas asignaciones de `thumbnail_url` por
  `self._meli_best_picture_url(pic_id, meli=meli, fallback_url=<url actual>)`. Es un backport limpio
  desde 19.0 (misma firma de `_meli_set_image_xy`, mismas líneas base). Candidato para
  `sources-align` (convergencia 16≡17≡18≡19).

### GAP del path DIRECTO (`_process_meli_item_direct`) vs el botón "Importar"

RPM importó los ~15k por el path directo de **`meli_oerp_multiple`**
(`connection_account.py:5312 _process_meli_item_direct`, drains masivos). Ese path:

- **Item con variaciones** → delega en `_process_meli_item_variations` (L5340).
- **Producto ya existente** (match por SKU/barcode en dicts RAM) → `mercadolibre_bind_to(bind_only=True,
  fast_create=True)` (L5362). Este branch **solo crea/actualiza el registro de binding**
  (meli_id, título, sku, barcode, precio); **NO** llama a `product_meli_get_product`. → **Caso dominante
  de RPM.**
- **Producto nuevo** (no match, `force_dont_create=False`) → `create_meli_product(import_images=False)`
  (L5381). Este SÍ llama internamente a `product_meli_get_product(import_images=False)`
  (`connection_account.py:5561`) → trae descripción/categoría/atributos(si flag) pero **NO imágenes**.

**Lo que el botón "Importar" trae y el path directo NO** (por eso el re-import se justifica):

> Nota: en RPM el botón y el branch `create` corren el **override** de `meli_oerp_multiple` (ver sección
> siguiente), que difiere del base (no puebla Plantilla, descripción gateada, flag = cuenta). La columna
> "Botón" abajo refleja el **override** (lo que RPM ejecuta).

| | Botón (override multiple) | Directo (bind_only) | Directo (create) |
|---|---|---|---|
| meli_id + SKU + barcode + precio | Sí | **Sí** | Sí |
| Descripción (`meli_description`/`description_sale`) | Solo si `'descriptions' in rjson` (hoy casi nunca) | **No** | ídem botón |
| Categoría ML (`meli_category`) | Sí (si `meli_get_category` OK) | **No** | ídem botón |
| Ficha "Plantilla" (7 Char) | **No** (override no llama `_meli_import_template_attributes`) | **No** | **No** |
| Ficha técnica (atributos) | Sí, si flag CUENTA on **y** categoría mapeada | **No** | ídem botón (import_images=False) |
| Imágenes | Sí (default; máx. resol. #532) | **No** | **No** (`import_images=False`) |

→ Para los ~15k bindeados de RPM, el re-import es el único camino para traer **ficha técnica + categoría
ML** (y, con los fixes/backfill, descripción + Plantilla). Requiere el **workflow de 2 pasos** de abajo.

---

## OVERRIDE de `meli_oerp_multiple` + diagnóstico del re-import que puebla 0 (RPM #532, prod)

> **Esto es lo que RPM ejecuta realmente.** Con `meli_oerp_multiple` instalado, el
> `product.product.product_meli_get_product` que corre es el **override**
> `meli_oerp_multiple/models/product.py:1234` `def product_meli_get_product(self, meli_id=None,
> account=None, meli=None, rjson=None, import_images=True)` — firma y cuerpo **distintos** al base.

### Diferencias del override vs el base `meli_oerp` (las que importan)

1. **Flag de atributos = el de la CUENTA, no el de la compañía.** El override llama
   `_get_non_variant_attributes` en **L1724**:
   ```python
   if (config.mercadolibre_update_existings_variants and 'attributes' in rjson):
       product._get_non_variant_attributes(rjson['attributes'])
   ```
   con `config = account.configuration` (L1244) → lee
   **`connection_configuration.mercadolibre_update_existings_variants`**
   (`meli_oerp_multiple/models/connection_configuration.py:288`), **NO**
   `company.mercadolibre_update_existings_variants` (`meli_oerp/models/company.py:467`, que sí lee el
   base en su L2810). → **Toggle en `company` NO tiene efecto sobre el override.**

2. **El override NO llama a `_meli_import_template_attributes`.** (grep en
   `meli_oerp_multiple/models/product.py` = 0 hits.) El base lo invoca incondicionalmente (L2468) para
   poblar los 7 Char de "Plantilla" (`meli_brand`/`meli_model`/`meli_gender` + package dims). El override
   fue forkeado antes de esa feature y nunca la recibió. → **`meli_brand=False` etc. tras el re-import
   por la cuenta. DIVERGENCIA base↔override (gap de alineación).**

3. **Descripción gateada por `'descriptions' in rjson`** (override L1277, igual que el base). El
   `/items/{id}` moderno de ML **no** incluye la clave `descriptions` (se removió; la descripción vive
   solo en `/items/{id}/description`). → el `if` es False → **nunca** pega a `/description` → `desc=0`.
   Los productos viejos con descripción se importaron cuando ML aún mandaba la clave (o por otro path).

4. **Imágenes:** el override usa `_meli_set_images_x` (L1734) → `_meli_best_picture_url` (máx. resol.,
   19.0 OK). Con `import_images=False` no toca imágenes (correcto para el bulk).

5. **`_get_non_variant_attributes` y `_meli_set_category` son heredados del base** (`meli_oerp`), no
   redefinidos en multiple. Es decir la lógica de creación de líneas es la del base L1811 (gate L1831).

### Diagnóstico del "0" en MLA841410482 (Kit Pistón, single-variant) — call-path exacto

El fetch trae el ítem OK (12 atributos, status paused, sin error). Aun así attr_lines=0, desc=0,
meli_category=None, meli_brand=False. Causas, una por síntoma:

- **attr_lines=0 → DOS candados:**
  1. **Flag equivocado.** El coordinador seteó `company.mercadolibre_update_existings_variants=True`,
     pero el override lee `config.` (account.configuration). En la cuenta ese flag seguía en False →
     la línea L1724 no corrió. (Aun con el flag correcto, sigue el candado 2.)
  2. **Prerequisito por categoría.** `_get_non_variant_attributes` (base L1811) crea línea **solo si**
     (L1831) el `att['id']` del ítem existe en `mercadolibre.category.attribute` **y** hay un
     `product.attribute` con `meli_default_id_attribute` apuntándole. Si la **categoría del Kit Pistón**
     nunca tuvo "Importar atributos", esos `att_id` no están mapeados → cada attr se saltea (silencioso
     en el `try/except`). Los neumáticos funcionan porque ESA categoría sí fue mapeada.
     - Nota: el ítem es single-variant → `_get_variations` (override L1527, gate
       `len(variations)>0`) NO corre; toda la ficha depende de `_get_non_variant_attributes`.
- **meli_brand=False:** el override no llama `_meli_import_template_attributes` (diferencia 2). Nunca
  se puebla por la cuenta. (Sí lo poblaría el método base de `meli_oerp` solo, sin multiple.)
- **desc=0:** guard `'descriptions' in rjson` (diferencia 3) → no fetch de `/description`.
- **meli_category=None:** `_meli_set_category` (override L1309 → base `category.py:1326`) SÍ se invoca;
  escribe `meli_category` solo si `meli_get_category`→`import_category` (`category.py:306/341`) devuelve
  un `mercadolibre.category` válido. Si devolvió False (login/token/categoría no importable en ese
  contexto) queda None. **A verificar en prod** (a diferencia de los atributos, el path SÍ se ejecuta;
  probable causa: la categoría no está en el catálogo `mercadolibre.category` y `import_category` no la
  creó en esa corrida). No es un gate de flag.

### Prerequisito por categoría (paso 1 del workflow) — botón "Importar atributos"

`mercadolibre.category.get_attributes()` (`category.py:397`, botón `get_attributes` en
`views/category_view.xml:174`) por cada categoría:
- GET `/categories/{cat_id}/attributes` → crea/actualiza `mercadolibre.category.attribute` (por `att_id`).
- Si **`company.mercadolibre_product_attribute_creation != 'manual'`** (L455): crea/linkea el
  `product.attribute` con `meli_default_id_attribute` = la category.attribute, y `create_variant`
  calculado por `meli_default_create_variant` (da `no_variation` para los no-variante). **Este es el
  mapeo que habilita `_get_non_variant_attributes`.** Si el modo está en `manual`, el mapeo NO se crea
  y la ficha nunca aterriza aunque el flag de variantes esté prendido.

### Riesgo "barcode already defined" en re-import masivo

`product_meli_get_product` escribe barcode en tres lugares, **todos ya defensivos** (buscan
duplicados y **loguean error + saltean** en vez de abortar la transacción):

- Variantes con `default_code` match: L2644-2658.
- Variantes por `is_v_comb`: L2678-2692.
- Producto sin variantes con SKU: L2722-2738.

En los tres, si `product.product` con ese barcode ya existe (activo o archivado) → `_logger.error("Error
barcode already defined!")` y **no** escribe (no lanza). Es decir, el barcode ya definido **no aborta**
el import de ese producto; a lo sumo deja el barcode sin actualizar. **No hay un abort transaccional
por barcode** en este método (el `try/except: pass` de cada bloque lo blinda). Idempotencia: correr el
botón dos veces es seguro respecto de barcode.

> Riesgo real de bulk NO es barcode sino: (a) `mercadolibre_update_existings_variants=True` puede
> **crear variantes** sobre productos que hoy son mono-variante (reescribe `attribute_line_ids`,
> L2596) — evaluar si RPM quiere eso o solo ficha plana; (b) volumen de API (ver plan).

### Costo de API por producto (para pacing del bulk)

Por producto, el botón dispara como mínimo:
- **1×** GET `/items/{id}?include_attributes=all` (siempre).
- **1×** GET `/items/{id}/description` (si el item tiene descripción).
- **N×** GET `/pictures/{pic_id}` — **una por imagen** (principal + cada adicional), vía
  `_meli_best_picture_url`. Un item con 6 fotos = 6 GETs solo de pictures.
- Descarga binaria de cada imagen a máxima resolución (`urlopen`, ancho de banda, no cuenta rate ML
  pero sí tiempo).
- +1 GET `/pictures` por imagen adicional también en `_meli_remove_images_unsync` si
  `mercadolibre_remove_unsync_images` está on (L1379-1381 baja cada `url` para hashear bytes).

→ **Estimado real: 8-15 GETs ML por producto** con fotos. Para 15k = **120k-225k calls**. El proxy de
rescate 429 está **SIN configurar** → riesgo alto de rate-limit. Requiere pacing agresivo.

### GAPS documentados (NADA arreglado — solo anotado)

1. **[16/17/18] Imágenes en baja resolución** — `_meli_best_picture_url` no existe; principal usa el
   `url` chico de `/items`, adicionales toman `variations[0]` (suele ser `-O` webp). **Fix:**
   forward-portar `_meli_best_picture_url` de 19.0 (L1624) a 16/17/18 y sustituir las dos asignaciones
   de `thumbnail_url` en `_meli_set_image_xy`. Candidato **sources-align**. (19.0 = OK.)

2. **[DIVERGENCIA base↔multiple] El override de `meli_oerp_multiple` no llama
   `_meli_import_template_attributes`** → cuando el import corre por la cuenta (todo cliente con
   multiple), los 7 Char de "Plantilla" (`meli_brand`/`meli_model`/`meli_gender` + package dims) NO se
   pueblan. **Fix propuesto:** agregar la llamada `product._meli_import_template_attributes(
   product_template, rjson)` en el override (multiple product.py ~L1420, tras los `write`), igual que
   el base L2468. Candidato de convergencia base↔override + `sources-align` (las 4 versiones del
   override lo omiten idéntico).

3. **[base y override] Descripción condicionada a `'descriptions' in rjson`** (base L2320 / override
   L1277) — el `/items/{id}` moderno de ML **ya no** trae la clave `descriptions` → nunca se pega a
   `/items/{id}/description` → `meli_description`/`description_sale` quedan vacíos aunque exista
   descripción. **Fix propuesto:** pedir `/description` siempre que `meli_description` esté vacío (o
   quitar el guard `'descriptions' in rjson`, dejando solo el try/except). Afecta a todos los clientes.

4. **[base y override] `_get_non_variant_attributes` acoplado a `mercadolibre_update_existings_variants`**
   — el mismo flag que crea/pisa variantes controla si se trae la ficha técnica no-variante. En régimen
   Odoo→ML el help desaconseja prenderlo. **Fix propuesto:** separar la importación de atributos
   no-variante en su propio flag/condición, desacoplada de la creación de variantes.

5. **[correcto por diseño, documentar]** `_get_non_variant_attributes` (base L1811, gate L1831) solo
   crea líneas para attrs con `mercadolibre.category.attribute` + `product.attribute`
   (`meli_default_id_attribute`) mapeados. **No es bug:** es el prerequisito por categoría (paso 1 del
   workflow). Cobertura RPM: 1954 `product.attribute` mapeados / 2061 `mercadolibre.category.attribute`.
   El gap es operativo: hay que correr "Importar atributos" en las categorías aún sin mapear.

### WORKFLOW correcto para traer la ficha técnica a los ~15k (2 PASOS) — NO ejecutar sin confirmación

**Precondiciones (single-writer, como los drains previos):**
- **Pausar TODOS los crones meli** de la cuenta 532 (los ~9-10 que compiten por la fila `account`,
  incluido `[Cron Meli Process Get Products]` id=51) → evita 40001 y contención.
- Proxy 429 **sin configurar** → sin red de rescate: el pacing lo es todo.
- `company.mercadolibre_product_attribute_creation` **≠ `'manual'`** (si está en manual, el paso 1 crea
  `mercadolibre.category.attribute` pero NO el `product.attribute` mapeado → la ficha nunca aterriza).

**PASO 1 — mapear atributos por CATEGORÍA (prerequisito; una sola vez por categoría distinta).**
- **Relevar cuántas categorías distintas y cuáles sin mapear** (query, NO ejecutar acá — correr en
  prod con crones pausados):
  ```python
  # categorías ML distintas usadas por los productos de la cuenta
  cats = set(env['product.template'].search([('meli_id','!=',False)]).mapped('meli_category.meli_category_id'))
  # cuáles no tienen atributos importados aún (sin mercadolibre.category.attribute)
  sin_map = env['mercadolibre.category'].search([
      ('meli_category_id','in',list(cats)),
      ('meli_category_attribute_ids','=',False)])
  ```
  (o por SQL sobre `mercadolibre_category` / `mercadolibre_category_attribute`.) El universo de
  categorías de un catálogo de repuestos suele ser **decenas-pocos-cientos**, no 15k → paso barato.
- Para cada categoría sin mapear: `category.get_attributes()` (`category.py:397`) — 1 GET
  `/categories/{id}/attributes` por categoría. Crea `mercadolibre.category.attribute` + linkea
  `product.attribute` (`meli_default_id_attribute`, `create_variant=no_variation`).
- Verificar post: `product.attribute` con `meli_default_id_attribute` cubre los `att_id` que traen los
  ítems de esas categorías.

**PASO 2 — re-import por producto (ficha + desc + categoría), imágenes aparte.**
- Setear el flag que el override realmente lee: **`account.configuration.mercadolibre_update_existings_
  variants = True`** (connection_configuration, NO el de `company`). Para RPM (single-variant masivo)
  esto habilita `_get_non_variant_attributes` sin crear variantes espurias (los ítems no traen
  `variations` → `_get_variations` no corre). Restaurar el flag al terminar.
- Iterar `product.product` con `meli_id` en **lotes chicos (25-50)** llamando
  `product_meli_get_product(meli_id=…, account=account, meli=meli, import_images=False)` con **commit
  por lote** y **sleep** (1-2 s). Con `import_images=False` el costo baja a ~2 calls/producto
  (`/items` + `/items/description`).
- **Imágenes:** ya resueltas por el pase galería-por-link del 10-jul (`product.image` a `-F.jpg` desde
  el link guardado, sin API). NO re-bajar por este bulk salvo faltantes puntuales.
- **Plantilla (7 Char):** el override NO los puebla (gap #2). Hasta que se agregue la llamada, hacer un
  **backfill quirúrgico** aparte reutilizando `_meli_import_template_attributes(product_template, rjson)`
  con el `rjson` ya en RAM del paso 2 (barato, sin API extra), o esperar el fix del override.
- **Descripción:** si tras el paso 2 sigue vacía por el guard `'descriptions' in rjson` (gap #3),
  forzar el fetch de `/items/{id}/description` en el mismo lote (1 GET/producto ya contemplado).
- Idempotencia: barcode blindado (no aborta). Tandas reanudables por offset/últimoid, progreso en
  **tabla propia**, NO en JSON sobre la fila `account` (causa del 40001, ver
  `rpm-motos-import-maestro.md`).
- **Pacing Odoo.sh:** si el bulk sale de un overlay, un push por vez → build → esperar.

**Magnitud, categorías a mapear y flags a confirmar con Franco/integrador (ticket #430) antes de tocar
prod. NADA de esto se ejecuta sin OK explícito.**

