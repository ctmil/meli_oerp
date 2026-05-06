# meli_oerp - Errors Log

> Registro de errores encontrados.

---

## Errores Activos

*Ninguno actualmente*

---

## Errores Resueltos

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
