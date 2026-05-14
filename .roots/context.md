# meli_oerp - Context

> Conector principal entre Odoo y MercadoLibre. Publica productos, sincroniza órdenes, envíos, preguntas y notificaciones.

---

**Versión actual: 26.29** (2026-05-13)

## Stack

- **Framework:** Odoo 16.0 / 19.0
- **Lenguaje:** Python 3.10+
- **Base de datos:** PostgreSQL
- **APIs externas:** MercadoLibre API v2 (items, orders, questions, categories, shipments)
- **SDK interno:** `melisdk/meli.py` (wrapper GET/POST/PUT/DELETE con `extra_headers`)

## Versiones Activas

| Versión | Estado | Clientes |
|---------|--------|---------|
| 26.29 | Actual | (cross-client) |
| 16.0.26.25 | Producción | shoppy |
| 19.0.26.22 | Producción | tecnolosys, múltiples LATAM |

## Estado Actual

Módulo core funcional. Sincronización de productos, órdenes, envíos, preguntas, categorías y notificaciones. Incluye billing-info v2, carrier mapping, descuentos por cupón, fechas de envío detalladas.

### Stock Sync (v26.29+)

- **Priorización por movimiento:** `meli_update_boms()` resetea `meli_stock_update = NULL` vía SQL cuando ocurre un stock move. El cron ordena `ASC NULLS FIRST` — productos con NULL suben al frente del queue y se procesan en el ciclo siguiente (5-10 min). Evita el delay de 30+ min en reactivaciones post-reabastecimiento.
- **`meli_stock_diagnostic()` — red de seguridad:** Corre al final de cada ciclo de `meli_update_remote_stock`. Detecta y corrige drift entre Odoo y ML: reactiva publicaciones pausadas con stock disponible, sincroniza `meli_available_quantity` stale, logea WARNING `MELI_STOCK_DIAG` en casos de drift. Protegida con try/except para no romper el cron.
- **Fulfillment skip guard:** Productos con `meli_shipping_logistic_type` conteniendo `'fulfillment'` se saltean con `continue` en ambos crons de stock (`meli_update_remote_stock`, `meli_update_remote_stock_rt`). ML no permite modificar stock de almacenes fulfillment vía API.

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
