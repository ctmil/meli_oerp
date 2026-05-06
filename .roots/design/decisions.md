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
