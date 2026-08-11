# meli_oerp - Errors Log

> Registro de errores encontrados.

---

## Errores Activos

### ERROR-010: `get_meli_state` — guard de DB neutralizada no asigna `mercadolibre_state` → rompe la vista Empresas `[16.0/18.0/19.0 pendientes — RESUELTO en 17.0]`

**Reportado:** 2026-08-10, Camila (Aramid, cuenta 447, UY, 17.0), traceback en staging neutralizada.
**Severidad:** Alta en staging (bloquea Ajustes > Empresas). Producción no afectada (no está neutralizada).
**Estado:** **Resuelto en 17.0** (v17.0.26.91, ver `fixes-log.md` 11-ago-2026). El mismo guard, byte-idéntico,
sigue roto en **16.0, 18.0 y 19.0** — no se tocaron todavía por decisión explícita de FCA
(`sin-precision-en-uno-no-se-masifica`: validar primero en un caso real antes de portar a las otras 3).
**Pendiente:** portar el mismo fix (una línea: `for company in self: company.mercadolibre_state = True`
dentro del guard, antes del `return`) a `models/company.py` de 16.0/18.0/19.0 una vez confirmado en 17.0.

---

### ERROR-009: `get_billing_info()` — el gate `status_code==200` NUNCA es True → el endpoint v2 de billing nunca gana, siempre cae a legacy en silencio `[TODAS las versiones 16/17/18/19]`

**Reportado:** 2026-07-14 (bug-hunter, hallazgo lateral durante el hardening ERROR-008).
**Severidad:** Media latente / no-fatal HOY. El endpoint legacy `/orders/{id}/billing_info` todavía
responde, así que la facturación funciona; pero ML anunció su baja (abr-2026, ver docstring de
`get_billing_info`). Cuando ML apague el legacy, `billing_info` quedará vacío y romperá datos fiscales.
**Estado:** NO corregido (a propósito — ver análisis). Documentado para decisión.

**Ubicación:** `meli_oerp/models/orders.py`, `get_billing_info()` (~L1745-1766).
```python
response = meli.get(url, {'access_token': meli.access_token}, extra_headers={'x-version': '2'})
if response is not None and getattr(response, 'status_code', 0) == 200:   # <-- SIEMPRE False
    ...usa v2...
else:
    ...warning + cae a legacy...
```

**Causa raíz:** `meli.get()` (ambas clases `MeliApiNoSDK` y `MeliApiSDK` en `meli_util.py`) devuelve
`self` y expone `self.response` (JSON parseado) y `self.rjson`, pero **NUNCA setea `self.status_code`**.
`resp.status_code` sólo se usa localmente para logging dentro de `get()`, no se persiste en el objeto.
Por lo tanto `getattr(response, 'status_code', 0)` siempre devuelve el default `0`. Consecuencia:
la rama v2 se llama por red (se hace el GET), pero su resultado se descarta y SIEMPRE se cae a legacy.

**Por qué NO se aplicó como hotfix (cambio de conducta):** arreglar el gate ACTIVARÍA el endpoint v2 +
el normalizador `_normalize_billing_info_v2()` para el 100% de las órdenes con `billing_info.id`. Ese
normalizador deriva campos FISCALES sensibles (INVOICE_TYPE Factura A/B, DOC_TYPE, TAXPAYER_TYPE, cust_type
BU/CO). Blast radius alto y entra en conflicto directo con la estrategia abierta `meli-contact-fiscal-strategy`
(regresión Modo 3). Flipearlo en silencio es riesgoso.

**Qué haría falta para habilitar v2 correctamente (plan para staging, NO ahora):**
1. Exponer el status HTTP real en el cliente: `MeliApiNoSDK.get()` debe setear `self.status_code = resp.status_code`
   (y `0`/`None` en la rama de excepción). Idem semántica en `MeliApiSDK.get()`.
2. Propagar `status_code` a través de `get_mini()` (ambas clases): hoy copia sólo `response`/`rjson` desde
   el `_nosdk` interno; debe copiar también `status_code`. CRÍTICO porque v2 SIEMPRE usa `extra_headers`
   → siempre pasa por el path `get_mini`→`MeliApiNoSDK`, nunca por `resource_get` del SDK.
3. Alternativa más robusta (recomendada): NO depender de `status_code`; validar por forma del payload
   (`biljson.get('buyer',{}).get('billing_info')` o `billing_info`) + ausencia de `error`. El `if api_billing_info`
   posterior ya actúa de gate natural.
4. Validar `_normalize_billing_info_v2()` contra payloads v2 REALES por site (MLA/MLM/MLU/MLC/MLB) en staging,
   comparando la factura resultante (tipo A/B, doc, razón social) contra la que hoy produce el legacy, ANTES
   de habilitarlo en producción. Coordinar con la decisión de `meli-contact-fiscal-strategy`.
5. Rollout gradual y con feature-flag por compañía/cuenta, no big-bang en las 4 versiones.

**Recomendación:** dejar como está hasta abrir tanda dedicada (junto con Modo 3). Riesgo de aplicar ya =
alto (fiscal). Riesgo de no aplicar = bajo mientras el legacy siga vivo; monitorear el anuncio de baja de ML.

---

## Errores Resueltos

## Errores Resueltos

### ERROR-008: Spam ERROR en log — `MeliApiSDK.get() got an unexpected keyword argument 'extra_headers'` `[17.0.aramid]`

**Reportado:** 2026-07-14 (post-deploy 26.70 en Aramid; runbook `partners/Uruguay/Aramid/.roots/DEPLOY-26.70-runbook.md`)
**Severidad:** Baja/no-fatal — `get_billing_info()` cae al endpoint legacy (funciona), pero satura el log
(~miles/hora por cada lookup de billing_info).
**Estado:** No reproducible en el source actual del grove (auditado); hardening defensivo aplicado igual.

**Síntoma:** por cada orden, `get_billing_info` (orders.py ~1748) intenta el endpoint v2 de billing con
`meli.get(url, {...}, extra_headers={'x-version':'2'})`; el runbook de Aramid reportaba una excepción
`TypeError: MeliApiSDK.get() got an unexpected keyword argument 'extra_headers'` capturada por el
`except Exception` y logueada como ERROR (no CRITICAL) antes de caer al legacy.

**Investigación (caza-bugs):**
- `MeliApiNoSDK.get()` (línea 224) y `MeliApiSDK.get()` (línea 815, rama `if MELI_SDK_AVAILABLE`) YA aceptan
  `extra_headers=None` desde el commit `717bac7` (versión **26.22**, 28-abr-2026) — mucho antes de 26.70.
  `717bac7` es ancestro directo de todo el historial hasta 26.77 (verificado con `git merge-base --is-ancestor`).
- La rama `else` (SDK no disponible) NO define una clase `MeliApiSDK` fallback — solo hace `MeliApiSDK = None`
  y usa `MeliApiNoSDK` (que también tiene `extra_headers` desde el mismo commit). El "fallback MeliApiSDK
  cuyo get() no acepta extra_headers" que describe el runbook no existe estructuralmente en el código actual.
- Se comparó línea por línea contra la copia YA DEPLOYADA de Aramid
  (`partners/Uruguay/Aramid/ctmil/main/meli_oerp/models/meli_util.py`, versión 26.70 real): tiene el mismo
  fix (`extra_headers=None` en ambas variantes de `get()`).
- Smoke test standalone (pyenv17, con el paquete real `meli` 3.0.0 instalado) instanciando ambas clases y
  llamando `.get(path, params, extra_headers={'x-version':'2'})`: **sin TypeError** en ninguna variante.
- Hallazgo lateral: `meli_oerp/requirements.txt` fija `git+…/ctmil/python-sdk-2025.git` mientras que
  `meli_oerp_stock/requirements.txt` fija `git+…/mercadolibre/python-sdk.git` (oficial) — MISMO nombre de
  paquete pip (`meli`, versión `3.0.0` en ambos) desde DOS fuentes git distintas. Riesgo de build
  no-determinístico (el orden de instalación decide qué fork queda instalado) — no explica el TypeError puntual
  (ninguna de las dos variantes define `RestClientApi.get()` nativo; nuestra subclase siempre lo sobreescribe)
  pero amerita reconciliar en un ticket aparte.
- Hallazgo lateral 2 (no arreglado, fuera de alcance): en `get_billing_info()`, el chequeo
  `getattr(response, 'status_code', 0) == 200` nunca puede dar True — ni `MeliApiSDK` ni `MeliApiNoSDK` setean
  `self.status_code` (solo usan la variable local `resp.status_code` dentro del método). El endpoint v2 nunca
  "gana" realmente; siempre cae al legacy (consistente con lo observado en el runbook: "billing_info se
  resuelve por el endpoint LEGACY, 0 legacy endpoint failed").

**Conclusión:** no se pudo confirmar la causa raíz exacta descripta (posible artefacto transitorio de
deploy/worker no reciclado en Odoo.sh). Se aplicó de todos modos un hardening defensivo (ver fixes-log) para
que ningún `get/get_mini/post/post_mini/put/put_mini/delete` de ninguna variante pueda romper por firma de
`extra_headers` u otro kwarg inesperado, y se corrigió una inconsistencia real menor (`MeliApiNoSDK.get_mini()`
no propagaba `extra_headers`). Mismo patrón (get_mini/post sin extra_headers) confirmado presente en
16.0/18.0/19.0 del grove — no migrado, solo reportado.

---

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

### ERROR-005: Publicaciones ML no se reactivan al reabastecer stock

**Reportado:** 12 Mayo 2026
**Severidad:** Alta
**Estado:** Resuelto

**Síntomas:**
Cuando ML auto-pausa una publicación (`status=paused, sub_status=out_of_stock`), al
reabastecer el stock en Odoo la publicación no se reactiva automáticamente. Puede
tardar 30+ minutos o no activarse.

**Causa raíz:**
`meli_update_boms()` actualizaba `meli_stock_moves_update` (timestamp del movimiento)
pero no tocaba `meli_stock_update` (timestamp del último sync con ML). El cron ordena
por `meli_stock_update ASC NULLS FIRST` — un producto synced recientemente con qty=0
quedaba al fondo de la cola.

**Solución:**
`meli_update_boms()` ahora también resetea `meli_stock_update = NULL` vía SQL directo.
Con NULL, el cron (NULLS FIRST) procesa el producto en el primer ciclo siguiente.

---

### ERROR-006: Endpoint billing_info v1 deprecado por ML (Q1 2026)

**Reportado:** 10 Abril 2026
**Severidad:** Alta
**Estado:** Resuelto

**Síntomas:**
Emisión de facturas falló porque el endpoint `/orders/{order_id}/billing_info` quedó
deprecado. ML migró a `/orders/billing-info/{SITE_ID}/{BILLING_INFO_ID}` con header
`x-version: 2`.

**Causa raíz:**
El código seguía llamando al endpoint legacy sin el nuevo path y sin el header requerido.
El formato de respuesta también cambió radicalmente (UPPERCASE flat → JSON anidado).

**Solución:**
Migrado al endpoint v2 con normalizador de claves para mantener compatibilidad con el
código consumidor sin tocar 100+ líneas de procesamiento.

---

### ERROR-007: Webhooks ML rechazados con 400 CSRF

**Reportado:** 10 Abril 2026
**Severidad:** Alta
**Estado:** Resuelto

**Síntomas:**
```
werkzeug: POST /odoo/meli_notify/keleb 400
odoo.http: No CSRF validation token provided for path '/odoo/meli_notify/keleb'
```

**Causa raíz:**
Los decorators de route de `/meli_notify` y `/meli_notify/<login_id>` no tenían
`csrf=False`. Odoo rechazaba los POST externos de ML.

**Solución:**
Agregado `csrf=False` a ambos decorators. La validación de origen se hace via
`application_id` y `user_id` en el handler.

---
