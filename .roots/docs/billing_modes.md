# Modos de facturación MeLi - Arquitectura de contactos

## Problema de fondo

En Odoo, los `commercial_fields` (`vat`, `partner_document_type_id`, `country_id`, etc.)
se sincronizan automáticamente del `commercial_partner` (parent) hacia todos sus children.
Esto significa que si un contacto de facturación (type=invoice) es hijo de un buyer,
cualquier cambio en un commercial_field del parent **sobrescribe** los datos fiscales
del child.

En MercadoLibre, un mismo buyer puede facturar con diferentes entidades fiscales por
compra (DNI personal, CUIT empresa A, CUIT empresa B). Esto genera un conflicto
directo con el mecanismo de `commercial_fields`.

---

## Modo 1: Buyer = parent, fiscal = child

```
Partner (buyer, type=contact)        <-- commercial_partner
  └── Contacto facturación (type=invoice, parent_id=buyer)
        vat, partner_document_type_id, etc.
```

**Comportamiento:**
- El buyer es el contacto principal (parent).
- Cada compra genera un child `type=invoice` con los datos fiscales de esa compra.
- El child tiene `parent_id` apuntando al buyer.

**Problemas:**
- `commercial_fields` sincroniza del parent al child. Si se toca `country_id` u otro
  commercial_field en el buyer, Odoo ejecuta `_commercial_sync_from_company()` y
  **borra** `vat` y `partner_document_type_id` del child (los pisa con los del parent,
  que puede tenerlos vacíos o diferentes).
- Un `cr.commit()` seguido de `invalidate_all()` materializa la pérdida: los campos
  quedan NULL en la DB.
- Si el mismo CUIT factura desde dos buyers diferentes, se duplica el contacto fiscal
  (un child por cada buyer con el mismo CUIT).
- **AFIP rechaza** la factura electrónica porque `vat` y/o `partner_document_type_id`
  están NULL en el partner de la factura.

**Mitigación parcial (implementada como fallback):**
- Override de `_commercial_sync_from_company()` en `res_partner.py` que hace backup
  de los campos fiscales antes del sync y los restaura si fueron borrados.
- SQL safety net que fuerza los datos fiscales vía `UPDATE` directo.
- Estas mitigaciones funcionan pero son frágiles ante cambios en el ORM de Odoo.

---

## Modo 2: Fiscal = parent, buyer = child (Odoo estándar)

```
Partner (entidad fiscal, type=contact)   <-- commercial_partner
  └── Contacto buyer MeLi (type=contact, parent_id=fiscal)
        meli_buyer_id, etc.
```

**Comportamiento:**
- La entidad fiscal (CUIT) es el contacto principal.
- El buyer de MeLi es un child del contacto fiscal.
- `commercial_fields` fluyen naturalmente del fiscal (parent) al buyer (child).

**Problemas:**
- Si un buyer factura con diferentes entidades fiscales (CUIT personal en una compra,
  CUIT empresa en otra), hay que duplicar el buyer como child de cada entidad fiscal.
- Un buyer con 3 CUITs diferentes = 3 contactos buyer duplicados.
- Complica el seguimiento del historial del buyer.
- No refleja la realidad de MeLi donde el buyer es la identidad principal.

---

## Modo 3: Entidades independientes (implementado)

```
Partner buyer (type=contact)
  meli_buyer_id = "123456"

Partner fiscal A (type=invoice, sin parent_id)
  vat = "20-28136731-9"
  meli_buyer_partner_id = buyer.id    <-- vínculo sin jerarquía

Partner fiscal B (type=invoice, sin parent_id)
  vat = "30-71234567-0"
  meli_buyer_partner_id = buyer.id    <-- mismo buyer, otro CUIT
```

**Comportamiento:**
- El buyer y la entidad fiscal son contactos **independientes** (sin relación parent/child).
- La entidad fiscal se busca **globalmente por VAT**: un CUIT = un solo contacto fiscal
  en el sistema, compartido por todos los buyers que facturen con ese CUIT.
- El vínculo buyer-fiscal se hace via `meli_buyer_partner_id` (Many2one en el fiscal
  apuntando al buyer que lo creó/usó).
- Los pagos se registran contra la entidad fiscal (`partner_invoice_id`), no contra
  el buyer.

**Ventajas:**
- **Sin problemas de commercial_fields**: al no haber relación parent/child, el
  mecanismo de sync no aplica. Los datos fiscales del contacto invoice nunca se
  sobrescriben.
- **Sin duplicación de CUITs**: si dos buyers facturan con el mismo CUIT, ambos
  usan el mismo contacto fiscal.
- **Pagos correctos**: el pago va contra la misma entidad fiscal que la factura,
  permitiendo conciliación automática via `commercial_partner_id`.
- **Compatible con multi-entidad**: un buyer puede facturar con DNI personal en una
  compra y con CUIT empresa en otra, sin conflictos.

**Campos nuevos en `res.partner`:**
- `meli_buyer_partner_id` (Many2one → res.partner): buyer que originó el contacto fiscal.
- `meli_billing_partner_ids` (One2many inversa): todos los contactos fiscales de un buyer.

**Riesgo: datos fiscales no verificados** (ver ROADMAP.md):
- MeLi no valida `billing_info` contra la autoridad fiscal. El buyer autodeclara
  número de documento y razón social.
- Un buyer podría declarar un documento ajeno. En Modo 3, al buscar globalmente
  por VAT, ese buyer reutilizaría el contacto fiscal existente y podría
  sobrescribir sus datos.
- Mitigaciones planificadas: modelo `mercadolibre.billing_info` (historial por
  orden), validación opcional contra autoridad fiscal del país (AFIP, SII, SAT,
  etc.), y flag `meli_fiscal_verified` para proteger contactos verificados.

---

## Búsqueda de contacto fiscal (orders.py)

El orden de búsqueda al procesar una orden de MeLi:

1. **Global por VAT** — `('vat', '=', billing_vat), ('type', '=', 'invoice')`:
   busca si ya existe un contacto fiscal con ese CUIT en el sistema.
2. **Fallback legacy parent_id + VAT** — para contactos creados antes de Modo 3
   que aún tienen `parent_id`.
3. **Fallback legacy meli_order_id + parent_id** — para contactos muy antiguos
   creados por versiones previas del módulo.

Si no se encuentra, se crea un contacto nuevo **sin parent_id**, con
`meli_buyer_partner_id` apuntando al buyer.

---

## Protección legacy (_commercial_sync_from_company)

Para contactos de facturación creados antes de Modo 3 (que todavía tienen `parent_id`),
el override de `_commercial_sync_from_company()` en `res_partner.py` sigue activo:

- Solo aplica a contactos con `type=invoice` y `meli_order_id` (billing children de MeLi).
- Hace backup de campos fiscales antes del sync.
- Restaura los valores si el sync los borró.
- Campos protegidos: `vat`, `partner_document_type_id`,
  `l10n_latam_identification_type_id`, `property_account_position_id`,
  `l10n_ar_afip_responsibility_type_id`.

---

## Diagrama de flujo: procesamiento de orden

```
Orden MeLi llega
  │
  ├── Buyer → buscar/crear res.partner (type=contact, meli_buyer_id)
  │
  ├── billing_info tiene VAT?
  │     │
  │     ├── SI → buscar contacto fiscal global por VAT
  │     │     ├── Encontrado → actualizar, vincular meli_buyer_partner_id
  │     │     └── No encontrado → crear sin parent_id, con meli_buyer_partner_id
  │     │
  │     └── NO → usar buyer como partner_invoice_id
  │
  ├── Delivery → buscar/crear contacto de envío (child del buyer)
  │
  └── Sale Order
        partner_id = buyer
        partner_invoice_id = entidad fiscal (o buyer si no hay VAT)
        partner_shipping_id = contacto de envío
```
