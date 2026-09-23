# PLAN 2026-09-23 · #158 Elvimarta — contacto de ENTREGA genérico + teléfono

**Módulo·versión·branch:** `meli_oerp` · 17.0 · `claude/158-contacto-entrega-y-telefono-17.0`
(base = rama `17.0` en `8195aad2`, 17.0.26.124). **Sin bump de manifest** (se recalcula al mergear).
**Disparador:** reporte del cliente 158 Elvimarta (producción 17.0.26.50), con el conteo hecho sobre
2.720 ventas ML desde el 1-sep: 2.611 con shipment → 0 fallas; 109 sin shipment → 4 casos vivos con
la entrega en el contacto genérico "Mercado Libre Marketplace".

## ⚠️ El BUG 2 NO EXISTÍA COMO BUG INDEPENDIENTE — es consecuencia del BUG 1

Se reportaron dos problemas ("la entrega queda en el genérico" y "el teléfono no llega a `phone`").
**Son uno solo.** El conector **sí escribía el teléfono**, en el contacto REAL del comprador
(`meli_buyer_fields['phone']`, activo en 26.50 en `orders.py:2488` y `2513`, con el update guardado
en `3259-3260`). Lo que se veía sin teléfono era el **contacto genérico**, porque la venta apuntaba
al genérico. Corregido el contacto de entrega, el teléfono aparece solo.

**La referencia `orders.py:1145` del diagnóstico original no era el código del teléfono** — en 26.50
esa línea es un comentario de `_ml_get_purchase_price_from_amount`. La línea comentada citada es
`shipment.py:1145`, y ahí mismo, cuatro líneas abajo, el teléfono se escribe con el filtro `XXXX`.
Confirmado por el coordinador contra `origin/main` del cliente.
**Al cliente se le había dado una explicación inexacta en su ticket; quedó corregida de ese lado.**

## Causa real del BUG 1
`partner_shipping_id` arranca en `False` y **sólo** se asigna vía
`mercadolibre.shipment.partner_delivery_id()`, que devuelve `None` sin `Receiver`
(`shipment.py`, guarda "no Partner or no Receiver"). Sin shipment no hay Receiver ⇒ la variable
queda en `False`, el `if partner_shipping_id:` no entra, `meli_order_fields` nunca lleva la entrega,
y **es Odoo quien la deriva de `partner_id`** — que unas líneas antes fue reemplazado por
`config.mercadolibre_contact_partner`. La entrega genérica es el **default de Odoo**, no una
escritura del conector.

## Qué se cambió (todo en `models/orders.py`)
1. **Fallback de entrega** (`~3948-3991`): si la entrega quedaría vacía o en un contacto genérico de
   la config, se completa con el contacto real del comprador (`original_contact_partner_id`, o
   `partner_invoice_id`). No actúa si hay `mercadolibre_shipping_partner`, y **nunca pisa** una
   entrega real ya cargada ni la dirección creada desde el shipment. Log `SHIPPING_FALLBACK [#158]`.
2. **`meli_order_phone()`** (`~2090`): `buyer.phone` → `buyer.alternative_phone`, con filtro `XXXX`.
   El `alternative_phone` se guardaba en `mercadolibre.buyers` y no se usaba nunca para el contacto.
3. **Guard contra borrado de teléfono** (`~2763-2775`): `meli_buyer_fields` se vuelca ENTERO sobre el
   contacto en `update_partner_billing_info()`, así que un `'phone': ''` **borraba un teléfono
   cargado a mano**, sin error ni log. Ahora la clave no se pone si queda vacía.
   **Esto es de toda la flota, no de este cliente** — no depende de shipment ni de configuración.
4. **Update del contacto existente** (`~3515-3520`): completa el teléfono sólo si está vacío.

## Fuera de alcance por decisión explícita
- **NO se usa `full_phone(Receiver)` como tercer candidato del teléfono.** Se implementó y se sacó a
  pedido del coordinador: tocaría 2.611 órdenes que hoy funcionan para resolver un síntoma que ya se
  resuelve con el punto 1, y el cliente viene sensible con la estabilidad. "Sólo rellenar vacíos" no
  alcanza como garantía cuando el universo afectado es tres órdenes de magnitud más grande que el
  problema. Se agrega si aparece un caso real de buyer sin teléfono y receptor con teléfono.
- **ML 2000018302420948 y ML 2000018283742846** (compañía Chile, 4-5 sep): entrega Y factura en el
  genérico, nunca se creó contacto real. Es otro caso y es viejo. Anotado, no tocado.
- Ningún módulo del suite escribe `mobile` (verificado en los 5 módulos, 17.0). El número que el
  cliente ve en `mobile` no lo puso el conector.

## Criterio de terminado
- [x] Fix en 17.0, `py_compile` OK, commit + push de la rama de trabajo
- [x] Changelog del módulo
- [ ] **Verificación en el staging de Odoo.sh del cliente** — la coordina FCA
- [ ] Port a 16.0 / 18.0 / 19.0 **después** de esa verificación (con `sync-lock` tomado)
- [ ] Bump del manifest recalculado contra la rama de deploy **en el momento del merge**
