# meli_oerp - Errors Log

> Registro de errores encontrados.

---

## Errores Activos

*Ninguno actualmente*

---

## Errores Resueltos

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
