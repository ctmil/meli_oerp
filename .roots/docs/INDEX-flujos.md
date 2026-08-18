# Índice — documentación técnica de flujos (meli_oerp)

Documentacion del flujo de integracion MercadoLibre -> Odoo.

## Documentos disponibles

| Documento | Descripcion |
|-----------|-------------|
| [sales_order_flow.md](sales_order_flow.md) | Flujo completo de ordenes de venta: desde la notificacion ML hasta la confirmacion en Odoo. Modelos, relaciones y configuraciones. |
| [shipping_costs_flow.md](shipping_costs_flow.md) | Flujo detallado de costos de envio: campos, fuentes de datos, propagacion y calculo del purchase_price en la linea de delivery. |
| [commission_fea_flow.md](commission_fea_flow.md) | Flujo de comisiones ML (FEA): como se extraen de la API, modos per_item/grouped, calculo de purchase_price y pagos a proveedor. |
| [purchase_price_margin.md](purchase_price_margin.md) | Como funciona el purchase_price en cada tipo de linea y como se calcula el margen. Problemas conocidos. |
| [contacts_partners.md](contacts_partners.md) | Flujo de creacion de contactos/partners desde compradores ML. Deduplicacion, direcciones de envio. |


## Archivos clave del codigo

| Archivo | Responsabilidad |
|---------|----------------|
| `meli_oerp/models/orders.py` | Procesamiento de ordenes ML, payments, creacion de sale.order |
| `meli_oerp/models/shipment.py` | Procesamiento de shipments, delivery lines, shipping costs |
| `meli_oerp/models/sale_order.py` | Extensiones al sale.order para ML |
| `meli_oerp_accounting/models/order.py` | Confirmacion contable, lineas FEA, pagos proveedor |
| `meli_oerp_accounting/models/payments.py` | Pagos de proveedor (comision y envio) |
| `meli_oerp_multiple/models/connection_configuration.py` | Configuracion de la conexion ML |
| `odoo_connector_api_producteca/models/connection_account.py` | Integracion Producteca (alternativa) |
