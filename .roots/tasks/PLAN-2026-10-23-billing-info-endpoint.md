# PLAN 2026-10-23 — get_billing_info nunca usa el endpoint nuevo de ML

**Qué:** `get_billing_info` (models/orders.py) intenta `/orders/billing-info/{SITE}/{ID}` (x-version 2) y
decide por `getattr(response,'status_code',0)==200`. `meli.get()` devuelve el propio cliente (self), que
NO tiene `status_code` ⇒ siempre 0 ⇒ siempre cae al endpoint viejo `/orders/{id}/billing_info`.
**Por qué:** pedido del coordinador (hallazgo 23-oct). Riesgo: cuando ML baje el endpoint viejo, las
ventas entran sin datos fiscales (facturación AR/MX).
**Sobre:** meli_oerp 16.0/17.0/18.0/19.0, ramas `claude/billing-info-endpoint-<v>` desde origin/<v> (26.289).
**Forma correcta de leer:** `response.json()` (= rjson, ya parseado; en error es dict con `error`/`status`),
como el resto de los llamados de orders.py.
**Fix:** helper que decide éxito por el contenido (dict, sin `error`, status<400) en vez de `status_code`.
**Criterio de terminado:** test unitario (mock) que FALLA con el código actual y pasa con el fix:
nuevo 200 ⇒ se usa (y no se llama al viejo); 404/410 ⇒ cae al viejo. Build 26.290 en los 5 módulos.
**Sin deploys a clientes.**
