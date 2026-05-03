# meli_oerp - Context

> Conector principal entre Odoo y MercadoLibre. Publica productos, sincroniza órdenes, envíos, preguntas y notificaciones.

---

## Stack

- **Framework:** Odoo 16.0 / 19.0
- **Lenguaje:** Python 3.10+
- **Base de datos:** PostgreSQL
- **APIs externas:** MercadoLibre API v2 (items, orders, questions, categories, shipments)
- **SDK interno:** `melisdk/meli.py` (wrapper GET/POST/PUT/DELETE con `extra_headers`)

## Versiones Activas

| Versión | Estado | Clientes |
|---------|--------|---------|
| 16.0.26.25 | Producción | shoppy |
| 19.0.26.22 | Producción | tecnolosys, múltiples LATAM |

## Estado Actual

Módulo core funcional. Sincronización de productos, órdenes, envíos, preguntas, categorías y notificaciones. Incluye billing-info v2, carrier mapping, descuentos por cupón, fechas de envío detalladas.

## Convenciones Clave

- Modelos con prefijo `mercadolibre.` (ej: `mercadolibre.orders`, `mercadolibre.posting`)
- Campos ML en modelos extendidos prefijados con `meli_` (ej: `meli_id`, `meli_title`)
- SDK en `melisdk/meli.py` — acceso via `meli` instance de `odoo_connector_api`
- Permalink API incluye `access_token` para autenticación directa desde backend
- Carrier mapping (`meli_oerp.carrier.mapping`) para evitar duplicación de transportistas
- Descuentos ML aplicados vía `line.discount` (porcentaje proporcional, NO restando del precio)
- `mail.thread` en `orders` y `shipment` para chatter de Odoo

## Dependencias Críticas

- `odoo_connector_api`: conexión base, OAuth, tokens
- `product`, `sale_management`, `website_sale`, `stock`, `delivery`: módulos base Odoo
- `meli_oerp_stock`: extensión de stock y ubicaciones ML
- `meli_oerp_multiple`: soporte multi-cuenta
- `meli_oerp_accounting`: facturación ML

---
