# Flujo de Costos de Envio (Shipping Costs)

## Campos de costo de envio

### En `mercadolibre.shipment` (shipment.py)

| Campo | Fuente | Significado |
|-------|--------|-------------|
| `shipping_cost` | API Shipment: `shipping_option.cost` | Lo que paga el comprador por el envio |
| `shipping_list_cost` | API Shipment: `shipping_option.list_cost` | Costo de lista del envio (precio original/interno) |
| `shipping_seller_cost` | Payment `charges_details` type="shipping" | Lo que ML le cobra al vendedor por el fulfillment |
| `order_cost` | API Shipment: `order_cost` | Costo total de la orden segun shipment |
| `base_cost` | API Shipment: `base_cost` | Costo base del envio |
| `promoted_amount` | API Shipment: `/costs` endpoint, `receiver.discounts` | Descuento promovido aplicado |

### En `mercadolibre.orders` (orders.py)

| Campo | Fuente | Significado |
|-------|--------|-------------|
| `shipping_cost` | Copiado de shipment.shipping_cost | Mirror del costo de envio |
| `shipping_list_cost` | Copiado de shipment.shipping_list_cost | Mirror del costo de lista |
| `shipping_seller_cost` | Payment `charges_details` | Costo de envio del vendedor (origen primario) |
| `payments_shipment_amount` | Computed: suma de `shipping_amount` de payments aprobados | Monto de envio reportado en pagos |

### En `sale.order` (sale_order.py / orders.py)

| Campo | Fuente | Significado |
|-------|--------|-------------|
| `meli_shipping_amount` | `payments_shipment_amount` del ml.order | Monto de envio (del pago) |
| `meli_shipping_cost` | `shipment.shipping_cost` | Costo de envio al comprador |
| `meli_shipping_seller_cost` | `order.shipping_seller_cost` (del payment) | Costo de envio cobrado al vendedor por ML |
| `meli_shipping_list_cost` | `shipment.shipping_list_cost` | Costo de lista del envio |

### En `mercadolibre.payments` (orders.py)

| Campo | Fuente | Significado |
|-------|--------|-------------|
| `shipping_amount` | API MercadoPago: `full_payment.shipping_amount` | Parte del pago correspondiente a envio |
| `shipping_seller_cost` | Calculado de `charges_details` type="shipping" | Costo fulfillment cobrado al seller |

### En linea de pedido (sale.order.line - delivery line)

| Campo | Fuente | Significado |
|-------|--------|-------------|
| `price_unit` | `payments_shipment_amount` o `shipping_cost` (segun config) | Precio visible del envio en la orden |
| `purchase_price` | Calculado via `_ml_get_purchase_price_from_amount(shipping_seller_cost)` | **Coste para calculo de margen** |


## Flujo de datos: De la API al purchase_price

```
API MercadoPago (payment charges_details)
  |
  |-- type="shipping" o name="shp_fulfillment"
  |     amounts.original = COSTO FULFILLMENT
  |
  v
payment_fields["shipping_seller_cost"]   (orders.py ~2896)
  |
  v
order.shipping_seller_cost               (orders.py ~2898)
  |
  v
sorder.meli_shipping_seller_cost         (orders.py ~2928)
  |
  |-- (tambien en orders.py ~2950, despues de fetch_shipment)
  v
shipment.shipping_seller_cost            (shipment.py, en fetch_shipment antes de _update)
  |
  v
_update_sale_order_shipping_info()       (shipment.py ~655)
  |
  |-- ship_cost = shipment.shipping_seller_cost
  |       OR sorder.meli_shipping_seller_cost  (fallback)
  |       OR shipment.shipping_list_cost       (fallback)
  |
  v
delivery_line.purchase_price = _ml_get_purchase_price_from_amount(
    product=product_shipping,
    amount=ship_cost,           # IVA incluido
    amount_type="tax_included",
    quantity=1.0
)
  |
  v
RESULTADO: purchase_price = ship_cost / factor_iva
  (ej: 7000.99 / 1.21 = 5786.77 sin IVA)
```


## Flujo de datos: shipping_cost y shipping_list_cost

```
API Shipment GET /shipments/{id}
  |
  |-- shipping_option.cost = COSTO ENVIO (comprador)
  |-- shipping_option.list_cost = COSTO DE LISTA
  |
  v
fetch_shipment() -> ship_fields                 (shipment.py ~939-940)
  |
  v
shipment.shipping_cost / shipment.shipping_list_cost
  |
  v
_update_sale_order_shipping_info()              (shipment.py ~454-462)
  |
  |-- sorder.meli_shipping_cost = shipment.shipping_cost
  |-- sorder.meli_shipping_list_cost = shipment.shipping_list_cost
  |-- order.shipping_cost = shipment.shipping_cost
  |-- order.shipping_list_cost = shipment.shipping_list_cost
```


## Configuracion relevante

### `mercadolibre_use_payment_shipping_amount` (boolean)

Determina la fuente del `price_unit` (precio visible) de la linea de envio:
- **True** (default): Usa `order.payments_shipment_amount` (suma de shipping_amount de pagos)
- **False**: Usa `shipment.shipping_cost` (de la API del shipment)

### `mercadolibre_including_shipping_cost` (selection)

Controla si se incluye la linea de envio en la orden:
- **"always"** (default): Siempre agregar linea de envio
- **"never"**: No agregar linea de envio (se remueve)

### `mercadolibre_process_payments_supplier_shipment` (boolean)

Cuando esta habilitado, crea automaticamente un pago saliente (outbound) al proveedor
de envio por el monto de `shipping_seller_cost` o `payments_shipment_amount`.

Archivo: `meli_oerp_accounting/models/payments.py` ~300-470


## Calculo del purchase_price: `_ml_get_purchase_price_from_amount`

Archivo: `meli_oerp/models/orders.py` ~590-688

Convierte un monto bruto (IVA incluido) a precio base (sin IVA) para el campo `purchase_price`.

### Logica:
1. Obtiene los impuestos del producto filtrados por compania
2. Aplica mapeo de posicion fiscal si existe
3. Si no hay impuestos: retorna el monto tal cual
4. Si `amount_type = "tax_excluded"`: usa `compute_all()` directamente
5. Si `amount_type = "tax_included"` (caso envio):
   - Calcula factor con dummy base=1.0: `factor = total_included / total_excluded`
   - `base = amount / factor`
   - Ejemplo con IVA 21%: `7000.99 / 1.21 = 5786.77`


## Problemas conocidos y correcciones aplicadas

### BUG: purchase_price = 0 en linea de envio (CORREGIDO)

**Causa raiz**: El `shipping_seller_cost` se copiaba de `order` a `shipment` DESPUES
de que `_update_sale_order_shipping_info` ya habia ejecutado con el valor 0.

**Secuencia problematica**:
```
1. Payment processing: order.shipping_seller_cost = 7000.99
2. fetch_shipment() -> _update_sale_order_shipping_info()
   -> shipment.shipping_seller_cost = 0 (no se habia copiado aun!)
   -> purchase_price = f(0) = 0  <-- BUG
3. orders.py: shipment.shipping_seller_cost = order.shipping_seller_cost  <-- TARDE!
```

**Correccion**:
1. Se mueve el copy `order.shipping_seller_cost -> shipment.shipping_seller_cost`
   a DENTRO de `fetch_shipment`, ANTES de `_update_sale_order_shipping_info`
2. Se agrega fallback chain: `shipping_seller_cost -> meli_shipping_seller_cost -> shipping_list_cost`
3. Se mantiene el copy en `orders.py` como safety net

### Lineas de propagacion comentadas

En `_update_sale_order_shipping_info` (shipment.py ~455, ~460), las lineas:
```python
#sorder.meli_shipping_seller_cost = shipment.shipping_seller_cost
#order.shipping_seller_cost = shipment.shipping_seller_cost
```
Estan comentadas porque `shipping_seller_cost` NO viene de la API del shipment,
sino de los `charges_details` del payment. La propagacion correcta es
`payment -> order -> shipment`, no `shipment -> order`.


## Notas sobre MEL Distribution

Cuando `shipment.tracking_method == "MEL Distribution"`, hay un bloque (shipment.py ~571-573):
```python
if (shipment.tracking_method == "MEL Distribution"):
    pass;  # no hace continue, sigue el flujo normalmente
```
Este `pass` indica que originalmente se queria saltar el procesamiento de MEL Distribution
pero finalmente se dejo que siga el flujo normal. El `delivery_price` y `purchase_price`
se calculan igual para todos los metodos de envio.
