# purchase_price y Calculo de Margen

## Que es purchase_price

El campo `purchase_price` en `sale.order.line` representa el **costo unitario**
del producto/servicio para el vendedor. Odoo lo usa para calcular el **margen de ganancia**.

```
Margen = price_unit - purchase_price
Margen % = (price_unit - purchase_price) / price_unit * 100
```


## Fuentes de purchase_price por tipo de linea

### 1. Lineas de producto

| Fuente | Descripcion |
|--------|-------------|
| `product.standard_price` | Costo estandar del producto en Odoo |

El `purchase_price` se setea automaticamente por Odoo al crear la linea de venta,
tomandolo del `standard_price` del producto.

**No viene de MercadoLibre.** Es responsabilidad del usuario mantener actualizado
el `standard_price` de sus productos.


### 2. Lineas de comision (COMISION_ML / FEA)

| Fuente | Descripcion |
|--------|-------------|
| `order.fee_amount` | Comision total de ML para la orden |

Se calcula con `_ml_get_purchase_price_from_amount()`:
```python
purchase_price = fee_amount / (1 + tasa_iva)
# Ejemplo: 2829.74 / 1.21 = 2338.63
```

El `price_unit` de la linea de comision es 0.0, por lo que el margen es siempre
negativo (representa un costo puro).

Archivo: `meli_oerp_accounting/models/order.py` ~428-433


### 3. Lineas de envio (delivery)

| Fuente | Prioridad | Descripcion |
|--------|-----------|-------------|
| `shipment.shipping_seller_cost` | 1ra | Lo que ML cobra al vendedor por fulfillment |
| `sorder.meli_shipping_seller_cost` | 2da (fallback) | Mismo valor, guardado en sale.order |
| `shipment.shipping_list_cost` | 3ra (fallback) | Costo de lista como ultima opcion |

Se calcula con `_ml_get_purchase_price_from_amount()`:
```python
purchase_price = shipping_seller_cost / (1 + tasa_iva)
# Ejemplo: 7000.99 / 1.21 = 5786.77
```

Archivo: `meli_oerp/models/shipment.py` ~655-670


## `_ml_get_purchase_price_from_amount()` - Detalle

Archivo: `meli_oerp/models/orders.py` ~590-688

### Parametros:
- `product`: Producto Odoo (para obtener impuestos)
- `amount`: Monto bruto (con o sin IVA)
- `amount_type`: `"tax_included"` o `"tax_excluded"`
- `quantity`: Cantidad (default 1.0)

### Logica:
1. Si no hay producto: retorna `amount` sin cambios
2. Obtiene impuestos del producto, filtrados por compania
3. Aplica posicion fiscal si existe
4. Si no hay impuestos: retorna `amount` redondeado
5. Si `amount_type = "tax_excluded"`: usa `taxes.compute_all()` y retorna `total_excluded / qty`
6. Si `amount_type = "tax_included"`:
   - Calcula factor IVA con base dummy: `factor = total_included / total_excluded`
   - `purchase_price = amount / factor / quantity`

### Ejemplo practico:

Producto COMISION_ML con IVA 21% (price_include=False):
```
dummy = taxes.compute_all(1.0)
total_excluded = 1.0
total_included = 1.21
factor = 1.21

amount = 2829.74 (fee_amount con IVA)
purchase_price = 2829.74 / 1.21 = 2338.63
```


## Ejemplo completo de margen en una orden

Orden: ML 2000015229922254

```
Producto (Bolso Patriot 1.2L):
  price_unit     = 10,497.32  (precio ML con IVA, ajustado)
  purchase_price =  4,410.00  (standard_price del producto)
  margen         = +6,087.32

Comision ML FEA:
  price_unit     =      0.00
  purchase_price =  2,338.63  (2829.74 / 1.21)
  margen         = -2,338.63  (costo puro)

Envio (MEL Distribution - Same Day):
  price_unit     =  5,785.94  (monto envio cobrado al comprador)
  purchase_price =  5,785.94  (shipping_seller_cost / 1.21)
  margen         =      0.00  (seller paga lo mismo que cobra)

MARGEN TOTAL ORDEN = 6,087.32 - 2,338.63 + 0.00 = 3,748.69
```


## Problemas potenciales de margen

### 1. purchase_price = 0 en envio (CORREGIDO)
Si el `shipping_seller_cost` no llega al shipment a tiempo, el purchase_price
queda en 0 y el margen del envio es artificialmente alto (o todo el price_unit se
reporta como ganancia). Ver: [shipping_costs_flow.md](shipping_costs_flow.md)

### 2. Cupones sumados al fee
Los cupones absorbidos por el vendedor se suman al `fee_amount`, inflando
el costo de comision reportado. Ver: [commission_fea_flow.md](commission_fea_flow.md)

### 3. standard_price desactualizado
Si el `standard_price` del producto no esta actualizado, el margen de producto
no refleja la realidad. Esto es responsabilidad del usuario.

### 4. Multiples pagos en una orden
Cuando hay multiples payments, el `fee_amount` puede sobreescribirse con el
ultimo payment en lugar de acumular todos. Ver: [commission_fea_flow.md](commission_fea_flow.md)

### 5. Modo grouped no descuenta IVA
En `odoo_connector_api_producteca`, el modo `grouped` de FEA asigna
`purchase_price = float(fea_amount)` sin pasar por `_ml_get_purchase_price_from_amount()`,
lo que significa que el purchase_price incluye IVA y el margen es incorrecto.
