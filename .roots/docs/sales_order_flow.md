# Flujo de Ordenes de Venta MercadoLibre -> Odoo

## Resumen del flujo principal

```
Notificacion ML (orders/created)
  |
  v
orders_update_order()                    (orders.py)
  |
  |-- 1. Crear/actualizar mercadolibre.order
  |-- 2. Crear/actualizar sale.order + lineas de producto
  |-- 3. Procesar payments (API MercadoPago)
  |-- 4. Fetch shipment (API Shipments)
  |-- 5. Confirmar orden (confirm_ml)
  |
  v
Sale Order en Odoo (con lineas de producto, comision y envio)
```


## Paso 1: Crear/actualizar la orden ML

Archivo: `meli_oerp/models/orders.py` ~2200-2420

Desde el JSON de la orden de ML se extraen:
- `order_json["total_amount"]` -> `order.total_amount`, `sorder.meli_total_amount`
- `order_json["paid_amount"]` -> `order.paid_amount`, `sorder.meli_paid_amount`
- `order_json["shipping"]["cost"]` -> `order.shipping_cost`, `sorder.meli_shipping_cost`
- `order_json["coupon"]["amount"]` -> `order.coupon_amount`, `sorder.meli_coupon_amount`


## Paso 2: Crear lineas del pedido de venta

Archivo: `meli_oerp/models/orders.py` ~2500-2790

Para cada `order_item` en la orden ML:
- Se busca/crea el producto en Odoo
- Se crea/actualiza `sale.order.line` con:
  - `price_unit`: precio unitario (puede ser con o sin IVA segun config)
  - `purchase_price`: costo del producto (se busca del producto Odoo)
  - `product_uom_qty`: cantidad

### purchase_price en lineas de producto

El `purchase_price` de las lineas de producto se toma del campo `standard_price`
del producto en Odoo. No viene de MercadoLibre directamente.


## Paso 3: Procesar payments

Archivo: `meli_oerp/models/orders.py` ~2787-2939

Para cada payment en `order_json["payments"]`:

1. Se consulta la API de MercadoPago: `GET /v1/payments/{id}`
2. Se extraen montos: `shipping_amount`, `total_paid_amount`, `taxes_amount`
3. Se extraen datos de tarjeta/metodo de pago
4. Se procesan `fee_details` (formato antiguo) o `charges_details` (formato nuevo):

### charges_details (formato actual)

| type | name | Destino | Descripcion |
|------|------|---------|-------------|
| `fee` | `meli_percentage_fee` | `order.fee_amount` | Comision porcentual de ML |
| `fee` | `flat_fee` | `order.fee_amount` | Comision fija de ML |
| `fee` | `financing_add_on_fee` | `order.fee_amount` | Cargo adicional de financiacion |
| `shipping` | `shp_fulfillment` | `order.shipping_seller_cost` | Costo de fulfillment (envio vendedor) |
| `coupon` | * | `order.fee_amount` (sumado) | Cupon absorbido por el vendedor |

### Propagacion de costos desde payments

```
payment.fee_amount  ----------> order.fee_amount  -------> sorder.meli_fee_amount
payment.shipping_seller_cost -> order.shipping_seller_cost -> sorder.meli_shipping_seller_cost
payment.financing_fee_amount -> order.financing_fee_amount -> sorder.meli_financing_fee_amount
```


## Paso 4: Fetch shipment

Archivo: `meli_oerp/models/shipment.py` ~780-1450

1. Se consulta `GET /shipments/{id}` y `GET /shipments/{id}/costs`
2. Se crea/actualiza `mercadolibre.shipment` con datos de envio
3. Se llama `_update_sale_order_shipping_info()` que:
   - Crea/actualiza la linea de delivery (carrier) en el sale order
   - Setea `price_unit` = monto de envio visible
   - Setea `purchase_price` = costo real del vendedor (shipping_seller_cost)

Ver: [shipping_costs_flow.md](shipping_costs_flow.md) para detalle completo.


## Paso 5: Confirmar orden

Archivo: `meli_oerp_accounting/models/order.py` ~350-530

`confirm_ml()` puede:
1. Confirmar la orden de venta (sale -> done)
2. Agregar linea de comision (FEA) si `mercadolibre_order_add_fea` esta configurado
3. Crear pagos de proveedor para comision y envio si esta configurado
4. Validar recibos de pago


## Lineas especiales en el pedido de venta

### Linea de Comision (FEA)

Config: `mercadolibre_order_add_fea` en `mercadolibre.configuration`

| Opcion | Comportamiento |
|--------|---------------|
| `"manual"` | No agregar linea de comision |
| `"per_item"` | Una linea de comision por pago/producto |
| `"grouped"` | Una linea de comision agrupada por orden |

Campos de la linea de comision:
- `product_id`: Producto COMISION_ML (se busca por default_code)
- `price_unit`: 0.0 (la comision es costo, no ingreso)
- `purchase_price`: `_ml_get_purchase_price_from_amount(fee_amount, tax_included)`
- `name`: "COMISION FEA {meli_order_id} {sku}"

Archivo: `meli_oerp_accounting/models/order.py` ~388-450

### Linea de Envio (Delivery)

Se crea automaticamente via `set_delivery_line()` cuando hay carrier configurado.

Campos:
- `product_id`: Producto de envio (carrier product)
- `price_unit`: Monto de envio (del pago o del shipment segun config)
- `purchase_price`: Costo real para el vendedor (shipping_seller_cost sin IVA)
- `is_delivery`: True

Archivo: `meli_oerp/models/shipment.py` ~540-675


## Calculo de margenes

El margen en Odoo se calcula como:
```
margen_linea = (price_unit - purchase_price) * quantity
margen_orden = sum(margen_linea) para todas las lineas
```

### Por tipo de linea:

| Tipo | price_unit | purchase_price | Margen esperado |
|------|-----------|---------------|----------------|
| Producto | Precio venta ML (con/sin IVA) | Costo del producto (standard_price) | Ganancia del producto |
| Comision FEA | 0.0 | Fee amount / (1 + IVA) | Negativo (es costo) |
| Envio | Monto envio cobrado | shipping_seller_cost / (1 + IVA) | Diferencia envio |

### Ejemplo con la orden ML 2000015229922254:

```
Producto: price_unit=10497.32 purchase_price=4410.00 -> margen=+6087.32
Comision: price_unit=0.00     purchase_price=2338.63 -> margen=-2338.63
Envio:    price_unit=5785.94  purchase_price=5785.94 -> margen=0.00
                                        (deberia ser shipping_seller_cost/1.21)
```

**Nota**: Si `shipping_seller_cost == shipping_cost` (el vendedor paga exactamente
lo que cobra), el margen de envio es 0 o cercano a 0. Esto es normal para
envios donde ML intermedia sin descuento.


## Modelos principales y relaciones

```
sale.order (Pedido de Venta)
  |
  |-- order_line (sale.order.line)
  |     |-- Lineas de producto
  |     |-- Linea de comision (COMISION_ML)
  |     \-- Linea de envio (delivery/carrier)
  |
  |-- meli_orders (mercadolibre.orders) [One2many]
  |     |-- payments (mercadolibre.payments) [One2many]
  |     |-- order_items (mercadolibre.order_items) [One2many]
  |     \-- shipment (mercadolibre.shipment) [Many2one]
  |
  \-- meli_shipment (mercadolibre.shipment) [Many2one]

mercadolibre.orders
  |-- fee_amount, financing_fee_amount (comisiones)
  |-- shipping_cost, shipping_list_cost (envio API)
  |-- shipping_seller_cost (envio vendedor, de payments)
  |-- payments_shipment_amount (computed, suma payments)
  \-- total_amount, paid_amount, coupon_amount

mercadolibre.shipment
  |-- shipping_cost (API shipping_option.cost)
  |-- shipping_list_cost (API shipping_option.list_cost)
  |-- shipping_seller_cost (copiado de order, viene de payment)
  \-- tracking_number, tracking_method, logistic_type, status
```


## Configuraciones clave

### Orden y precios

| Campo | Modelo | Descripcion |
|-------|--------|-------------|
| `mercadolibre_order_confirmation` | config | "manual" / "paid_confirm" / auto |
| `mercadolibre_order_add_fea` | config | Agregar linea de comision |
| `mercadolibre_including_shipping_cost` | config | Incluir envio en orden |
| `mercadolibre_use_payment_shipping_amount` | config | Fuente de monto envio |

### Pagos de proveedor

| Campo | Modelo | Descripcion |
|-------|--------|-------------|
| `mercadolibre_process_payments_supplier_fea` | config | Crear pago proveedor para comision |
| `mercadolibre_process_payments_supplier_shipment` | config | Crear pago proveedor para envio |

### Diarios y metodos de pago

| Campo | Modelo | Descripcion |
|-------|--------|-------------|
| `mercadolibre_payment_journal_id` | config | Diario para cobros ML |
| `mercadolibre_payment_method_id` | config | Metodo de pago entrada |

Archivos de configuracion:
- `meli_oerp_multiple/models/connection_configuration.py`
- `meli_oerp_accounting/models/company.py`
