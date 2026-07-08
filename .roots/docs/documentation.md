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
