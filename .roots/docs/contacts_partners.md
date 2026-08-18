# Flujo de Contactos y Partners (Compradores ML -> Odoo)

## Resumen

Cuando se procesa una orden de MercadoLibre, se crean/actualizan hasta 3 contactos en Odoo:

1. **Contacto principal (buyer)**: El comprador de ML, identificado por `meli_buyer_id`
2. **Contacto de facturacion (entidad fiscal)**: Contacto type="invoice" con datos de CUIT/CUIL
3. **Contacto de envio (shipping address)**: Direccion de entrega del shipment

```
res.partner (buyer, type="contact")
  |-- meli_buyer_id = "123456789"
  |-- name = "Juan Perez"
  |-- phone, street, city, state, country
  |
  |-- [Relacionado] res.partner (entidad fiscal, type="invoice")
  |     |-- vat = "20-12345678-9"
  |     |-- name = "EMPRESA SRL" (billing_info.business_name)
  |     |-- l10n_ar_afip_responsibility_type_id (Resp. Inscripto, Monotributo, etc.)
  |     \-- meli_buyer_partner_id -> buyer
  |
  \-- [Hijo] res.partner (shipping, type="delivery")
        |-- name = receiver_name
        |-- street = receiver_address_line
        |-- city, state, country
        \-- parent_id -> buyer
```


## Paso 1: Buscar/crear contacto principal (buyer)

Archivo: `meli_oerp/models/orders.py` ~2063-2113

### Busqueda (deduplicacion):

1. Buscar por `meli_buyer_id` + compania actual
2. Buscar por `meli_buyer_id` sin filtro de compania
3. **Fallback por VAT**: Buscar por `vat` = `billing_info.doc_number` (si no es VAT generico)

### VATs genericos (excluidos de busqueda):

Se definen en `_GENERIC_VATS_DEFAULTS` por pais:
- **AR**: Tipicamente `0`, `00000000000`, consumidor final generico
- **MX**: `XAXX010101000`, etc.
- Configurables por compania

### Creacion:

Si no existe y `mercadolibre_cron_get_orders_shipment_client` esta habilitado:
```python
partner_id = respartner_obj.create(meli_buyer_fields)
```

### Campos del buyer (`meli_buyer_fields`):

| Campo Odoo | Fuente ML | Descripcion |
|------------|-----------|-------------|
| `name` | `buyer_full_name(Buyer)` | Nombre completo |
| `meli_buyer_id` | `Buyer["id"]` | ID del comprador en ML |
| `phone` | `full_phone(Buyer)` | Telefono |
| `email` | `Buyer["email"]` | Email (puede ser @mercadolibre.com) |
| `street` | `Receiver["address_line"]` | Direccion principal |
| `city` | `Receiver["city"]["name"]` | Ciudad |
| `state_id` | Mapeo por `Receiver["state"]` | Provincia/Estado |
| `country_id` | Mapeo por `Receiver["country"]` | Pais |
| `meli_buyer_fields adicionales` | billing_info | Datos adicionales de billing |


## Paso 2: Buscar/crear contacto de facturacion (Modo 3)

Archivo: `meli_oerp/models/orders.py` ~2117-2277

### Modo 3: Entidad fiscal independiente

El sistema usa "Modo 3" donde la entidad fiscal es un contacto independiente
(sin parent_id), vinculado al buyer via `meli_buyer_partner_id`.

Un mismo CUIT puede ser compartido por multiples buyers (ej: empresa que compra
con diferentes usuarios de ML).

### Busqueda:

1. Por VAT + type="invoice" (global)
2. Por parent_id + type="invoice" + VAT (legacy)
3. Por `meli_order_id` + parent_id + type="invoice" (legacy)

### Campos:

| Campo Odoo | Fuente ML | Descripcion |
|------------|-----------|-------------|
| `vat` | `billing_info.doc_number` | CUIT/CUIL/DNI |
| `name` | `billing_info.business_name` | Razon social |
| `type` | "invoice" | Tipo de contacto |
| `l10n_ar_afip_responsibility_type_id` | Mapeo por `billing_info` | Responsabilidad AFIP |
| `partner_document_type_id` | `billing_info.doc_type` | Tipo de documento |
| `meli_buyer_partner_id` | `partner_id.id` | Vinculo al buyer |

### Safety net SQL:

Despues de crear/actualizar la entidad fiscal, se ejecuta SQL directo para
asegurar que los datos fiscales persistan (workaround para `_commercial_sync_from_company`
de Odoo que puede sobreescribir datos del child con los del parent).

```python
self.env.cr.execute(
    "UPDATE res_partner SET partner_document_type_id = %s, vat = %s, ... WHERE id = %s",
    (doc_type_id, vat, partner_invoice_id.id)
)
```

### Deteccion de duplicados:

Si el buyer tiene el mismo VAT que la entidad fiscal, se detectan otros contactos
con el mismo VAT y se genera un warning en el chatter de la orden ML sugiriendo
fusionar contactos.


## Paso 3: Contacto de envio (shipping address)

El contacto de envio se maneja desde el shipment. Cuando se procesa el shipment
en `fetch_shipment()`, se crea un contacto type="delivery" como hijo del buyer.

Archivo: `meli_oerp/models/shipment.py` (dentro de fetch_shipment)

### Datos de envio del shipment:

| Campo Odoo | Fuente ML (shipment JSON) | Descripcion |
|------------|---------------------------|-------------|
| `name` | `receiver_address.receiver_name` | Nombre del receptor |
| `street` | `receiver_address.address_line` | Direccion completa |
| `street_name` | `receiver_address.street_name` | Nombre de calle |
| `street_number` | `receiver_address.street_number` | Numero |
| `city` | `receiver_address.city.name` | Ciudad |
| `state_id` | Mapeo por `receiver_address.state` | Provincia |
| `country_id` | Mapeo por `receiver_address.country` | Pais |
| `phone` | `receiver_address.receiver_phone` | Telefono receptor |
| `comment` | `receiver_address.comment` | Comentarios de entrega |


## Asignacion al sale.order

| Campo sale.order | Contacto | Uso |
|-----------------|----------|-----|
| `partner_id` | Buyer principal | Cliente de la orden |
| `partner_invoice_id` | Entidad fiscal (si existe) o buyer | Para facturacion |
| `partner_shipping_id` | Contacto de envio o buyer | Direccion de entrega |


## Campos ML en res.partner

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `meli_buyer_id` | Char | ID del comprador en MercadoLibre |
| `meli_order_id` | Char | ID de la orden ML (en contactos hijos) |
| `meli_buyer_partner_id` | Many2one | Vinculo al buyer (en entidad fiscal) |
| `meli_update_forbidden` | Boolean | Impedir actualizaciones automaticas |
| `billing_info_doc_type` | Char | Tipo de documento (DNI, CUIT, etc.) |
| `billing_info_doc_number` | Char | Numero de documento |
| `billing_info_business_name` | Char | Razon social |


## Configuracion relevante

| Campo | Modelo | Descripcion |
|-------|--------|-------------|
| `mercadolibre_cron_get_orders_shipment_client` | config | Habilitar creacion automatica de contactos |
| `mercadolibre_buyer_fields` | config | Campos adicionales a sincronizar del buyer |


## Notas y consideraciones

### Email de ML
Los emails de compradores de ML suelen ser `xxx@mercadolibre.com` (proxied).
Si se detecta un email de ML existente, se limpia al actualizar para evitar
mensajes a correos proxy.

### Actualizacion conservadora
Al actualizar un contacto existente, solo se actualizan campos vacios
(country, state, street, phone). No se sobreescribe el nombre ni datos
fiscales para respetar correcciones manuales del usuario.

### meli_update_forbidden
Si un contacto tiene `meli_update_forbidden = True`, no se actualiza
automaticamente desde ML. Esto permite proteger contactos editados manualmente.


## Safety guard: sale.order sin partner_id

`sale_order.partner_id` es `NOT NULL` en la base de datos de Odoo. Si
`orders_update_order_json` llegara a ejecutar `create()` sin `partner_id`, el
error `psycopg2.errors.NotNullViolation` propaga y deja la transaccion
**abortada**, lo que hace que todos los pedidos siguientes del mismo batch
fallen con `current transaction is aborted`.

Para evitar esto, `meli_oerp/models/orders.py` tiene un guard justo antes de
`saleorder_obj.create()` que omite la creacion y loguea un error claro cuando
`meli_order_fields['partner_id']` no esta presente. Causas tipicas:

1. **`mercadolibre_cron_get_orders_shipment_client = False`** (Importar
   clientes desactivado) y ademas `mercadolibre_contact_partner` no esta
   configurado como fallback. El search por `meli_buyer_id` / VAT no
   encuentra el buyer, la creacion automatica esta deshabilitada y no hay
   contacto default: `partner_id` queda en `False`.
2. **Buyer sin `meli_buyer_id` ni VAT valido** y la busqueda no matcheo.
3. **Error silencioso al crear el `res.partner`** mas arriba (excepcion
   absorbida por el `try/except` alrededor del `create` de contactos).

Cuando se dispara el guard, el log muestra:

```
Skipping sale.order create for ML order <id>: partner_id is missing.
Revisar 'Importar clientes' (mercadolibre_cron_get_orders_shipment_client)
y/o el 'Contacto para MercadoLibre' (mercadolibre_contact_partner) en la
configuracion.
```

Y deja un `message_post` en `mercadolibre.orders` con la misma explicacion
para que el operador vea el problema sobre el pedido afectado.

Para que los pedidos se puedan facturar hay que **activar "Importar clientes"**
en la configuracion de la cuenta MeLi, **o** dejar configurado un
`mercadolibre_contact_partner` que actue como contacto generico cuando la
importacion de clientes esta desactivada.
