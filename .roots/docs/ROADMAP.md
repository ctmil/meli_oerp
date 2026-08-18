# ROADMAP - meli_oerp / meli_oerp_accounting

## Pendiente

### Modelo mercadolibre.billing_info — historial de datos fiscales por orden

**Problema**: actualmente el `billing_info` de MeLi se procesa on-the-fly y se
escribe directamente al `res.partner` (contacto fiscal). No queda registro de
qué datos fiscales trajo cada orden. Si un buyer cambia de entidad fiscal entre
compras, no hay forma de auditar qué billing_info correspondió a cada venta.

**Solución**: crear modelo `mercadolibre.billing_info` siguiendo el patrón de
`mercadolibre.payments` — un registro por orden, vinculado al `order_id`.

#### Estructura del modelo

```python
class MercadolibreBillingInfo(models.Model):
    _name = "mercadolibre.billing_info"
    _description = "Información de facturación MercadoLibre"

    order_id = fields.Many2one("mercadolibre.orders", string="Order",
                               index=True, required=True, ondelete='cascade')

    # Datos crudos de la API
    doc_type = fields.Char('Document Type')          # CUIT, DNI, RUT, NIT, etc.
    doc_number = fields.Char('Document Number')
    first_name = fields.Char('First Name')
    last_name = fields.Char('Last Name')
    business_name = fields.Char('Business Name')

    # Dirección fiscal
    street_name = fields.Char('Street Name')
    street_number = fields.Char('Street Number')
    city_name = fields.Char('City')
    state_name = fields.Char('State')
    zip_code = fields.Char('Zip Code')
    neighborhood = fields.Char('Neighborhood')

    # Datos tributarios
    taxpayer_type = fields.Char('Taxpayer Type')      # IVA_RESPONSABLE_INSCRIPTO, etc.
    economic_activity = fields.Char('Economic Activity')
    vat_discriminated_billing = fields.Char('VAT Discriminated Billing')
    invoice_type = fields.Char('Invoice Type')

    # JSON completo para campos no mapeados / futuros
    raw_json = fields.Text('Raw billing_info JSON')

    # Vínculo al contacto fiscal que se usó/creó
    partner_invoice_id = fields.Many2one('res.partner',
                                         string='Fiscal Entity Used')

    # Verificación (ver sección "Validación fiscal")
    fiscal_verified = fields.Boolean('Verified against tax authority',
                                     default=False)
    verification_date = fields.Datetime('Verification Date')
    verification_source = fields.Char('Verification Source')  # "AFIP", "SII", etc.
    verification_discrepancies = fields.Text('Discrepancies Found')
```

#### Relación con mercadolibre.orders

```python
# En mercadolibre.orders:
billing_info_id = fields.Many2one('mercadolibre.billing_info',
                                   string='Billing Info')
# O alternativamente One2many si se quiere historial de cambios:
billing_info_ids = fields.One2many('mercadolibre.billing_info', 'order_id',
                                    string='Billing Info History')
```

#### Flujo de procesamiento

```
Orden MeLi llega
  │
  ├── API: GET /orders/{id}/billing_info
  │
  ├── Crear/actualizar mercadolibre.billing_info
  │     order_id = orden actual
  │     doc_type = billing_info['DOC_TYPE']
  │     doc_number = billing_info['DOC_NUMBER']
  │     ... (todos los campos)
  │     raw_json = json.dumps(billing_info)
  │
  ├── Buscar/crear contacto fiscal (res.partner) como hoy
  │     → billing_info_record.partner_invoice_id = contacto usado
  │
  └── Si verificación fiscal habilitada:
        → Consultar autoridad fiscal del país
        → billing_info_record.fiscal_verified = True/False
        → billing_info_record.verification_discrepancies = "..."
```

#### Beneficios

- **Auditoría**: qué datos fiscales declaró cada buyer en cada compra.
- **Trazabilidad**: si un contacto fiscal tiene datos incorrectos, se puede
  rastrear qué orden trajo esos datos.
- **No-destructivo**: el billing_info original se preserva aunque el contacto
  fiscal se modifique después.
- **Base para verificación**: el modelo tiene campos para registrar el resultado
  de la validación contra la autoridad fiscal.

---

### Validación de datos fiscales contra autoridad fiscal

**Problema**: MercadoLibre no valida el `billing_info` que el buyer declara.
El buyer escribe un número de documento y razón social sin ningún control.
Esto genera riesgos:

1. **Documento ajeno**: un buyer declara el CUIT/RUT/NIT de una entidad que no
   le pertenece. Se emite factura a alguien que no compró.
2. **Datos inconsistentes**: el buyer declara un tipo de contribuyente incorrecto.
3. **Sobrescritura en Modo 3**: al buscar globalmente por VAT, un buyer con datos
   falsos puede sobrescribir un contacto fiscal existente.

**Alcance multi-país**: el módulo opera en múltiples países de América Latina.
Cada país tiene su propia autoridad fiscal y servicios de consulta. La validación
contra padrones NO es un feature universal sino un **servicio opcional** por país.

#### Autoridades fiscales por país

| País | Autoridad | Servicio de consulta | Doc. tipo |
|------|-----------|---------------------|-----------|
| Argentina | AFIP | ws_sr_padron (a4, a5, a10, a13) | CUIT |
| Chile | SII | Consulta RUT web / API | RUT |
| México | SAT | Constancia de situación fiscal | RFC |
| Colombia | DIAN | RUT en línea | NIT |
| Uruguay | DGI | Consulta RUC | RUC |
| Perú | SUNAT | Consulta RUC en línea | RUC |
| Brasil | Receita Federal | Consulta CNPJ/CPF | CNPJ/CPF |

Cada integración requiere:
- Credenciales de acceso al servicio (certificados, tokens, etc.)
- Mapeo de la respuesta a los campos de `res.partner` y `mercadolibre.billing_info`
- Manejo de errores y caídas del servicio

#### Arquitectura propuesta

```
mercadolibre.billing_info
  │
  ├── fiscal_verified = False (recién creado desde MeLi)
  │
  ├── Servicio de verificación (por país, opcional):
  │     │
  │     ├── Argentina (AFIP ws_sr_padron)
  │     │     → Razón social, responsabilidad IVA, domicilio, actividades
  │     │
  │     ├── Chile (SII)
  │     │     → RUT, razón social, giro comercial
  │     │
  │     ├── México (SAT)
  │     │     → RFC, régimen fiscal, nombre/razón social
  │     │
  │     └── ... otros países
  │
  └── fiscal_verified = True
      verification_source = "AFIP" / "SII" / "SAT" / ...
      verification_date = now()
      verification_discrepancies = "razón social difiere: MeLi='ACME' AFIP='ACME SRL'"
```

#### Protección contra sobrescritura

Campo `meli_fiscal_verified` (Boolean) en `res.partner`:
- `True` = datos validados contra autoridad fiscal, no se sobrescriben desde MeLi.
- `False` = datos autodeclarados por buyer, pueden actualizarse.

Lógica al procesar orden:
```
billing_info trae documento X
  │
  ├── Buscar contacto fiscal con VAT = X
  │     │
  │     ├── Encontrado + meli_fiscal_verified = True
  │     │     → NO actualizar datos fiscales desde billing_info
  │     │     → Solo vincular meli_buyer_partner_id
  │     │     → Log warning si datos de MeLi difieren de los verificados
  │     │
  │     ├── Encontrado + meli_fiscal_verified = False
  │     │     → Si hay servicio de verificación para el país:
  │     │     │   → Consultar autoridad fiscal
  │     │     │   → Actualizar con datos oficiales
  │     │     │   → Marcar meli_fiscal_verified = True
  │     │     → Si no hay servicio:
  │     │         → Actualizar con datos de MeLi (sin verificar)
  │     │
  │     └── No encontrado
  │           → Crear contacto fiscal
  │           → Si hay servicio: verificar, marcar verified
  │           → Si no: usar datos de MeLi, dejar unverified
  │
  └── Guardar resultado en mercadolibre.billing_info
```

#### Detalle Argentina: AFIP ws_sr_padron

AFIP expone web services que dado un CUIT devuelven:
- Razón social registrada
- Tipo de responsabilidad (RI, Monotributo, Exento, etc.)
- Domicilio fiscal
- Actividades económicas
- Estado del CUIT (activo/inactivo)

Servicios disponibles:
- `ws_sr_padron_a4`: padrón alcance 4 (datos básicos)
- `ws_sr_padron_a5`: padrón alcance 5 (datos completos)
- `ws_sr_padron_a10`: padrón alcance 10 (constancia de inscripción)
- `ws_sr_padron_a13`: padrón alcance 13 (datos tributarios)

Algunos módulos Odoo ya integran esto (`l10n_ar_afip_ws`, `l10n_ar_partner`).
Verificar si la instalación ya tiene alguno y reutilizarlo.

---

### Migración de contactos legacy (Modo 1 → Modo 3)

Contactos de facturación creados antes de Modo 3 tienen `parent_id` apuntando
al buyer. Migración para desacoplarlos:

1. Buscar contactos con `type=invoice`, `meli_order_id` y `parent_id`.
2. Si ya existe otro contacto fiscal con el mismo VAT sin parent_id, mergear.
3. Si no, quitar `parent_id`, setear `meli_buyer_partner_id` al ex-parent.
4. Verificar que las sale orders y facturas apunten al contacto correcto.

**Riesgo**: facturas ya emitidas tienen `partner_id` apuntando al child con parent.
Cambiar la estructura del child podría afectar `commercial_partner_id` y romper
la conciliación de pagos existentes.

**Estrategia**: solo migrar contactos que no tengan facturas validadas pendientes
de conciliación. Los que tengan deuda abierta, dejar como están (el override de
`_commercial_sync_from_company` los protege).

---

### Eliminación de safety nets

Una vez que Modo 3 esté estabilizado y los contactos legacy migrados:

1. **SQL safety net en orders.py**: el `UPDATE res_partner SET ...` directo a la DB
   debería poder removerse, ya que sin `parent_id` no hay commercial_fields sync.
2. **SQL safety net en accounting/order.py**: el pre-action_post backup/restore
   puede simplificarse o removerse.
3. **Override _commercial_sync_from_company**: mantener mientras existan contactos
   legacy con `parent_id`. Remover cuando todos estén migrados.

---

## Completado

### Modo 3: entidades fiscales independientes
- Contactos de facturación sin `parent_id` (evita commercial_fields sync).
- Búsqueda global por VAT (un CUIT = un contacto fiscal).
- Campos `meli_buyer_partner_id` / `meli_billing_partner_ids` para vínculo.
- Pagos contra `partner_invoice_id` (entidad fiscal) en vez de buyer.

### Protección commercial_fields (fallback legacy)
- Override `_commercial_sync_from_company()` para contactos con `parent_id`.
- SQL safety nets como defensa en profundidad.
- Pre-validación fiscal antes de `action_post`.

### CondicionIVAReceptorId — ARCA RG 5616

**Problema**: AFIP/ARCA hizo obligatorio el campo `CondicionIVAReceptorId` en el
request `FECAESolicitar` del web service WSFE. Sin este campo, AFIP rechaza la
factura con error: "El campo Condicion IVA receptor no es valido para la clase
de comprobante informado".

**Cronología ARCA:**
- Feb 4, 2025: campo aparece en entorno de homologación
- Abr 6, 2025: liberado en producción
- Abr 15, 2025: obligatorio por RG 5616 (pero no excluyente hasta Jun 30, 2025)
- Jul 1, 2025: requests sin el campo son rechazados

**Causa raíz**: la librería `l10n_ar_api` (de BLUEORANGE GROUP SRL) no incluía
`CondicionIVAReceptorId` en el SOAP request. Producción tenía v2.7.8.

**Soporte en `l10n_ar_api`:**
- v2.9.0 (Feb 12, 2025): agrega atributo `customer_fiscal_position` en
  `ElectronicInvoice` que se mapea a `CondicionIVAReceptorId` en `WsfeInvoiceDetails`.
- Atributo: `electronic_invoice.customer_fiscal_position = <int>`
- Valores: coinciden con códigos AFIP de `ar.fiscal.position`
  (1=RI, 4=Exento, 5=CF, 6=Mono, etc.)

**Fix implementado** — módulo `meli_oerp_bo` (bridge module):

Override de `_set_electronic_invoice_details()` en `meli_oerp_bo/models/account_move.py`.
Usa `super()` para obtener el `electronic_invoice` del módulo WSFE base y le inyecta
`customer_fiscal_position` antes de retornarlo. No modifica `odoo_addons_l10n_ar`.

```python
electronic_invoice = super()._set_electronic_invoice_details(document_afip_code)
customer_fiscal_position = 5  # Default: Consumidor Final
ar_fp = self.partner_id.property_account_position_id.ar_fiscal_position_id
if ar_fp:
    customer_fiscal_position = int(
        self.env['codes.models.relation'].get_code(
            'ar.fiscal.position', ar_fp.id, 'Afip'
        )
    )
electronic_invoice.customer_fiscal_position = customer_fiscal_position
return electronic_invoice
```

**Path de resolución del código AFIP:**
```
partner.property_account_position_id   (account.fiscal.position)
  → .ar_fiscal_position_id             (ar.fiscal.position)
    → codes.models.relation.get_code('ar.fiscal.position', id, 'Afip')
      → '1' (RI), '4' (Exento), '5' (CF), '6' (Mono), etc.
```

**Requisito**: `l10n_ar_api >= 2.9.0` (declarado en `meli_oerp_bo/__manifest__.py`
como external dependency; debe instalarse en producción con
`pip install 'l10n_ar_api>=2.9.0'`).

**Nota sobre enterprise**: el módulo enterprise EDI (`l10n_ar_edi`) no se ve
afectado porque construye el dict SOAP directamente con
`self.partner_id.l10n_ar_afip_responsibility_type_id.code`. Esa vía no usa
`l10n_ar_api`. El fix aplica solo a la vía CER/Blue Orange (WSFE addon).

**Nota sobre WSBFE**: el bono fiscal electrónico (`wsbfe`) en `l10n_ar_api` 2.9.0
aún no incluye `CondicionIVAReceptorId`. Si ARCA lo requiere para WSBFE en el
futuro, se necesitará un fix similar en `_set_electronic_bond_details()` y una
versión de `l10n_ar_api` que lo soporte para WSBFE.
