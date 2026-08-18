# Flujo de Comisiones ML (FEA)

## Que es la comision FEA

FEA = Fee (comision que MercadoLibre cobra al vendedor por cada venta).
Incluye:
- **Comision porcentual** (`meli_percentage_fee`): % sobre el precio de venta
- **Comision fija** (`flat_fee`): monto fijo por operacion
- **Cargo de financiacion** (`financing_add_on_fee`): costo adicional si hay cuotas
- **Cupones absorbidos** (`coupon`): cuando ML da descuento y el vendedor absorbe


## Origen del dato

### Formato nuevo: `charges_details` (API MercadoPago v1)

```json
{
  "charges_details": [
    {
      "type": "fee",
      "name": "meli_percentage_fee",
      "amounts": { "original": 1500.00 }
    },
    {
      "type": "fee",
      "name": "flat_fee",
      "amounts": { "original": 100.00 }
    },
    {
      "type": "shipping",
      "name": "shp_fulfillment",
      "amounts": { "original": 7000.99 }
    }
  ]
}
```

Procesado en: `meli_oerp/models/orders.py` ~2873-2920

### Formato antiguo: `fee_details`

```json
{
  "fee_details": [
    {
      "type": "application_fee",
      "fee_payer": "collector",
      "amount": 1600.00
    }
  ]
}
```

Procesado en: `meli_oerp/models/orders.py` ~2851-2870


## Flujo de datos

```
API MercadoPago GET /v1/payments/{id}
  |
  |-- charges_details (fee)
  |     meli_percentage_fee + flat_fee + financing_add_on_fee + coupon
  |
  v
payment_fields["fee_amount"]  (suma acumulada)
  |
  v
order.fee_amount              (mercadolibre.orders)
  |
  v
sorder.meli_fee_amount        (sale.order)
  |
  v
confirm_ml() -> agregar linea FEA   (si mercadolibre_order_add_fea != "manual")
  |
  v
sale.order.line (COMISION_ML)
  price_unit = 0.0
  purchase_price = _ml_get_purchase_price_from_amount(fee_amount, "tax_included")
```


## Configuracion: `mercadolibre_order_add_fea`

Archivo: `meli_oerp_multiple/models/connection_configuration.py` ~384-388

| Valor | Comportamiento |
|-------|---------------|
| `"manual"` | No agregar linea de comision automaticamente |
| `"per_item"` | Una linea de comision por pago/producto |
| `"grouped"` | Una linea de comision unica agrupada |


## Modo per_item

Archivo: `meli_oerp_accounting/models/order.py` ~388-450

Para cada `mercadolibre.order` asociada al sale.order:
1. Obtiene `fea_amount = morder.fee_amount`
2. Busca producto COMISION_ML (por default_code: COMISION_ML, COMISIONML, o "COMISION ML")
3. Crea linea con:
   - `name`: "COMISION FEA {meli_id} {order_item_id} {sku}"
   - `price_unit`: 0.0
   - `purchase_price`: `_ml_get_purchase_price_from_amount(fee_amount, "tax_included")`
   - `product_uom_qty`: 1.0

### Calculo del purchase_price:
```
purchase_price = fee_amount / factor_iva
Ejemplo: 2829.74 / 1.21 = 2338.63 (sin IVA)
```


## Modo grouped

Archivo: `odoo_connector_api_producteca/models/connection_account.py` ~2064-2104

Similar pero agrupa todas las comisiones en una sola linea por orden.
Usa `pso.transaction_fee` (suma de `transactionFee` de payments aprobados).

```python
'purchase_price': float(fea_amount)  # NOTA: no usa _ml_get_purchase_price_from_amount
```

**Diferencia importante**: El modo `grouped` en Producteca NO descuenta IVA
del `purchase_price`, mientras que `per_item` en meli_oerp_accounting SI lo hace.


## Pagos de proveedor para comision

Config: `mercadolibre_process_payments_supplier_fea` (boolean)

Cuando esta habilitado, se crea un `account.payment` de tipo `outbound` (pago a proveedor)
por el monto de la comision.

Archivo: `meli_oerp_accounting/models/payments.py` ~300-350

```python
vals_payment = {
    'partner_id': partner_id.id,         # Proveedor MercadoLibre
    'payment_type': 'outbound',
    'amount': self.fee_amount,
    'journal_id': journal_id.id,
    'partner_type': 'supplier',
}
```


## Problema conocido: Sobreescritura con multiples pagos

Cuando una orden tiene multiples payments (ej: pago parcial + complemento),
el `order.fee_amount` se sobreescribe con el valor del ultimo payment procesado,
en vez de acumular. Esto puede causar que la comision registrada sea menor a la real.

Ubicacion del problema: `orders.py` ~2891-2892
```python
order.fee_amount = payment_fields["fee_amount"]  # sobreescribe, no acumula entre payments
```

Nota: `payment_fields["fee_amount"]` SI acumula DENTRO de un payment (multiples charges),
pero al hacer `order.fee_amount = ...` en cada iteracion de payments, se pierde la
acumulacion de payments anteriores.


## Problema conocido: Cupones sumados al fee

En `orders.py` ~2903-2909, los cupones de tipo `coupon` en `charges_details` se suman
al `fee_amount` del payment. Esto significa que el `fee_amount` no es solo comision ML,
sino que incluye el costo de cupones absorbidos por el vendedor.

Esto puede distorsionar el reporte de "comision de ML" ya que incluye descuentos de cupones.
