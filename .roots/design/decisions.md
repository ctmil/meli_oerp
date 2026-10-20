# meli_oerp - Architecture Decisions

> Decisiones de diseño y arquitectura (ADRs).

---

## ADR-001: access_token directo en permalink API `[19.0.tecnolosys]`

**Fecha:** 2026-04-30
**Estado:** Aceptado
**Origen:** 19.0.tecnolosys

**Contexto:**
Los permalinks de items ML no eran clickeables desde el backend de Odoo porque la API requiere autenticación.

**Opciones consideradas:**
1. Crear instancia `meli` completa para obtener token — más overhead, crea objeto innecesario
2. Leer `access_token` directo del account/meli — simple, directo, sin overhead

**Decisión:**
Opción 2: leer `access_token` directamente de la cuenta sin crear instancia meli completa.

**Consecuencias:**
El token puede expirar en el link guardado, pero para uso inmediato desde el backend es suficiente.

---

## ADR-002: Descuento de cupón ML vía `line.discount` proporcional `[16.0.shoppy]`

**Fecha:** 2026-05-02
**Estado:** Aceptado
**Origen:** 16.0.shoppy

**Contexto:**
Los cupones de ML llegan como monto total, no por línea. La lógica inicial restaba el cupón del `unit_price`, generando doble descuento cuando también se aplicaba `line.discount`.

**Decisión:**
Aplicar el descuento únicamente vía `line.discount` como porcentaje proporcional al precio de cada línea. Eliminar resta de cupón de `_set_product_unit_price`.

**Consecuencias:**
La factura refleja el monto real pagado. Requiere capturar `coupon_amount` desde `charges_details` del pago (type=coupon) porque el order JSON de ML no incluye el campo `coupon` directamente.

---

## ADR-513: direcciones del pedido — el conector sólo pisa lo que puso él `[#513 TYL]`

**Fecha:** 2026-10-20
**Estado:** Propuesto (19.0.26.282, sin pase)

**Contexto:** la re-sincronización de órdenes reescribía factura / entrega del pedido y la dirección del contacto de entrega,
deshaciendo cambios manuales. `meli_update_forbidden` corta todo lo que viene de ML (estado, envío, pagos), no sirve de escape.

**Opciones consideradas:**
1. Escribir sólo al crear o si está vacío — rompe pedidos creados antes de tener el envío (Odoo pone el cliente por defecto) y
   el cambio de dirección del comprador en ML no entraría nunca.
2. Marcar "manual" en `write` cuando no viene del conector — exige poner contexto en TODAS las escrituras del conector; una que
   falte marcaría manual en falso.
3. Registrar el último valor que puso el conector y comparar (pedido) + huella de la dirección escrita (contacto).
4. Opción de configuración para elegir comportamiento.

**Decisión:** 3, sin opción de configuración. Una escritura del conector que no registre deja el pedido en "manual" ⇒ falla
hacia el lado conservador (no pisa). La opción 4 no aporta: nadie quiere que se deshaga un cambio manual, y un cambio en ML
sigue entrando cuando nadie tocó el pedido.

**Consecuencias:** pedidos viejos con un contacto distinto del cliente quedan "fijados" (no siguen cambios de ML). Huella sólo
para contactos type=delivery (el del comprador lo actualiza orders.py por otro camino).
