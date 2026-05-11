# meli_oerp - Errors Log

> Registro de errores encontrados.

---

## Errores Activos

*Ninguno actualmente*

---

## Errores Resueltos

### ERROR-005: Descuento de cupón ML calculado con denominador sin IVA — factura por menos de lo pagado `[17.0.elvimarta]`

**Reportado:** 2026-05-08
**Severidad:** Alta — la factura quedaba por debajo del monto pagado por el comprador
**Estado:** Resuelto

**Síntomas:**
En órdenes con `coupon_amount > 0` donde `meli_coupon_discount_on_invoice = True`, la factura mostraba un monto menor al esperado. El pago de ML no alcanzaba para cubrir la factura completa, quedando con residual.

**Ejemplo (caso Elvimarta):**
```
coupon_amount = 1480
Cálculo incorrecto: discount_pct = 1480 / sum(price_unit × qty) = 1480 / 48925 = 3.02%
Factura = 48925 × (1 - 3.02%) × 1.21 = $57,412  ← menos de lo que pagó ML

Cálculo correcto: discount_pct = 1480 / sum(price_unit × qty × (1 + IVA)) = 1480 / 59200 = 2.5%
Factura = 48925 × (1 - 2.5%) × 1.21 = $57,720  ← correcto
```

**Causa raíz:**
El denominador para calcular el % de descuento usaba el precio base sin IVA. Como el cupón de ML es un monto bruto (con IVA), aplicar ese porcentaje sobre el precio neto generaba un descuento mayor al real.

**Resolución:** Ver [fixes-log.md](./fixes-log.md) → FIX-010

---

### ERROR-006: Odoo 19 — xpath `//field[@name='locked']` no encontrado en orders_view `[19.0.scoremx]`

**Reportado:** 2026-05-08
**Severidad:** Crítica — ParseError fatal en carga del módulo
**Estado:** Resuelto
**Detalle completo:** `.roots/19.0.scoremx/meli_oerp/debug/errors-log.md → ERROR-002`

**Síntomas:**
```
ParseError: while parsing meli_oerp/views/orders_view.xml:75
El elemento '<xpath expr="//field[@name='locked']">' no puede ser localizado en la vista padre
```
El campo `locked` no existe en la vista base de `sale.order` en Odoo 19.

**Resolución:** Ver [fixes-log.md](./fixes-log.md) → FIX-011

---

### ERROR-004: Seller discount capping incorrecto con cupones `[19.0.keleb]`

**Reportado:** 2026-05-05
**Severidad:** Alta — órdenes con cupón grandes bloqueadas en `confirm_ml`
**Estado:** Resuelto

**Síntomas:**
`confirm_ml` rechaza la orden con "amount doesn't match" cuando hay un cupón de ML. El `seller_discount` reportado por el endpoint `/amounts` es el descuento de lista completo (precio catálogo - precio pagado), no solo el cupón.

**Resolución:** Ver [fixes-log.md](./fixes-log.md) → FIX-007

---

### ERROR-003: billing_info endpoint deprecated por ML `[19.0.keleb]`

**Reportado:** 2026-04-10
**Severidad:** Alta — datos fiscales del comprador no llegaban desde ML
**Estado:** Resuelto

**Síntomas:**
ML deprecó el endpoint `/orders/{id}/billing_info` (03/2026). La respuesta es vacía o devuelve 404. Sin datos fiscales el partner queda como Consumidor Final genérico.

**Nuevo endpoint:** `/orders/billing-info/{SITE_ID}/{BILLING_INFO_ID}` con header `x-version: 2`. La estructura de campos cambió de UPPERCASE flat a nested.

**Resolución:** Ver [fixes-log.md](./fixes-log.md) → FIX-008

---

### ERROR-002: CSRF rechazaba todas las notificaciones ML `[19.0.keleb]`

**Reportado:** 2026-04-10
**Severidad:** Crítica — sin notificaciones ML el sistema queda en polling puro
**Estado:** Resuelto

**Síntomas:**
Las notificaciones de MercadoLibre (órdenes, preguntas, items, envíos) llegaban a Odoo con HTTP 400. Log: `CSRF token validation failed for route /meli_notify`.

**Causa:** Las rutas `/meli_notify` no tenían `csrf=False`. Odoo 17 valida CSRF en POST por defecto.

**Resolución:** Ver [fixes-log.md](./fixes-log.md) → FIX-009

---

### ERROR-001: Permalink API sin access_token `[19.0.tecnolosys]`

**Reportado:** 2026-04-30
**Severidad:** Media
**Estado:** Resuelto
**Origen:** 19.0.tecnolosys

**Síntomas:**
Links de permalink de items ML no eran accesibles directamente desde el backend de Odoo.

**Contexto:**
La URL se construía sin token de autenticación:
`https://api.mercadolibre.com/items/{meli_id}?include_attributes=all`

**Análisis:**
La API de ML requiere `access_token` como query param para acceso directo sin sesión del browser.

**Resolución:** Ver [fixes-log.md](./fixes-log.md) → FIX-001

---
