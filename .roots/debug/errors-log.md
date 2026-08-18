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

## ERROR-012 — ✅ RESUELTO 18-ago-2026 · `invoice_policy` se revertía sola en Odoo 18/19 (FLOTA)
**Versiones:** `meli_oerp` **18.0.26.92** / **19.0.26.91** · `meli_oerp_multiple` **18.0.26.96**.
Detectado en **DT TEC (533)**, pero afectaba a **cualquier** cliente en Odoo 18/19.

**Cadena, verificada eslabón por eslabón:**
1. **Core de Odoo** (`addons/sale/models/product_template.py`, idéntico en 18 y 19):
   `invoice_policy` es un compute `store=True, readonly=False` con `@api.depends('type')`, y el
   compute hace `...filtered(lambda t: t.type == 'consu' or not t.invoice_policy).invoice_policy = 'order'`.
   ⇒ **cualquier write que toque `type` en un template `consu` fuerza `'order'`**, pisando al usuario.
2. **Nosotros** (`models/versions.py`, `UpdateProductType`): el guard era
   `if prod.type not in ['product']: prod.write({'type': 'consu'})`. Ese guard es de Odoo ≤16;
   **en 18/19 el valor `'product'` ya no existe**, así que daba verdadero **siempre** y ejecutaba un
   write **redundante** sobre un producto que ya era `consu`.
3. **Resultado:** ese write "que no cambia nada" **sí** re-dispara el compute ⇒ la política elegida por
   el cliente volvía a `'order'`, **en silencio y en cada importación de orden ML**. Sin error, sin log.

**Por qué no se encontró antes:** buscar `invoice_policy` por nombre no lo encuentra — el conector
**no lo escribe**, lo **dispara** vía `type`. Con un compute almacenado hay que buscar sus `@api.depends`.

**Fix aplicado:** no escribir si no hay nada que cambiar (`vals` acumulado + early-continue); mandar la
política **explícita** en el mismo write (`MeliInvoicePolicy`: cuenta → compañía → la que ya tenía);
`ProductTypeWrite()` para productos existentes; corregido el **guard invertido** de `is_storable`
(`if prod.is_storable: write(is_storable=True)` era un no-op que impedía que la función cumpliera su
objetivo); eliminado el **`UPDATE` SQL crudo** que salteaba compute, tracking y constraints; y nuevo
parámetro *"Política de facturación de productos nuevos"* (vacío = comportamiento de siempre).

**Probado en producción ANTES de entrar al source.** Corrió en DT TEC desde el 15-ago 07:00 UTC.
Medido el 17 y 18-ago en su base: **0** filas de `mail_tracking_value` sobre `invoice_policy`, con
**control positivo** — **11 órdenes ML** importadas en esa ventana, o sea el camino que disparaba el
bug se ejecutó 11 veces sin pisar nada; el template `20392` fue escrito por el conector y quedó en
`delivery`; y la **guardia `ir.cron` que restituía la política fue retirada**, así que el cero no está
enmascarado por un parche corrigiendo por detrás. El **AST** de `versions.py` en el source es
**idéntico** al que corre allí.

**⚠️ 16.0/17.0 NO se tocaron, a propósito:** ahí `'product'` sí existe y el guard viejo tenía sentido;
`prod.type != 'consu'` convertiría **almacenables en consumibles**.

**⚠️ PENDIENTE:** `meli_oerp_multiple` **19.0** no se mergeó (su rama estaba tomada por un worktree con
cambios sin commitear de otra sesión, en los mismos archivos). El fix espera en
`origin/claude/error-012-invoice-policy-19.0`.

**⚠️ NO REPARA LO YA ROTO:** el compute **sólo asigna `'order'`, nunca `'delivery'`** ⇒ nada vuelve
solo. Lo ya dañado se corrige aparte y **de común acuerdo con cada cliente** (es decisión de negocio).

**⚠️ Deployar a cada cliente es decisión aparte:** no mueve datos, pero **cierra sesiones** y le cambia
el comportamiento. Va con ventana y aviso, cliente por cliente.

**Aprendizaje transversal:** *un write no-op deja de serlo cuando re-dispara un compute.*

Plan: `.roots/tasks/PLAN-2026-08-18-error012-port-al-source-y-produccion.md`

---
