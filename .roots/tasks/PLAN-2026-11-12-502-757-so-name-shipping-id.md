# PLAN 2026-11-12 — #757 Shoppy (502): nombre de venta con shipping_id (opción) + sufijo en carritos

- **Qué:**
  1. Opción de configuración nueva en res.company / settings (default = comportamiento actual: sufijo con tracking)
     para usar el ID de envío (shipping_id) como sufijo del nombre de la venta. Con la opción activa, el renombre
     posterior por tracking (shipment.py `_update_sale_order_shipping_info`) NO toca el nombre.
  2. Carrito/pack creado en shipment.py (~2097, 'ML <pack_id>'): agregar sufijo al crear cuando ya se conoce el
     shipping_id (igual que orders.py en venta simple), respetando la opción.
  - No romper orders.py ~1105 (búsqueda invoice.origin = so.name).
- **Por qué:** pedido de soporte (sesión soporte-manager, cliente 502 Shoppy, ticket #757). Diagnóstico:
  partners/Argentina/gonzalo-shoppy/.roots/tasks/PLAN-2026-11-12-502-757-758.md. La etiqueta ML lleva el shipping_id;
  el origin del albarán sale del nombre de la venta; en colecta ML cambia el tracking a 26 chars al despachar y en
  Flex el tracking nunca contiene el shipping_id.
- **Sobre:** meli_oerp, ramas `claude/502-757-so-name-shipping-id` desde origin/16.0, 17.0, 18.0, 19.0.
  Manifest = max(todas las ramas de todas las series del suite)+1, mismo número en las 4.
- **Terminado cuando:** 4 ramas commiteadas y pusheadas; probado en Odoo 16 local el camino real (venta simple y
  pack, opción on/off); entrada en .roots/state/comms.md to @soporte-manager; lock liberado. SIN deploy a clientes.

## Replan (diagnóstico read-only, 19:15Z)
- El flag existente `mercadolibre_so_name_tracking` está definido SÓLO en meli_oerp_multiple
  (models/connection_configuration.py, vista connection_account_view.xml). meli_oerp lo lee con `in config._fields`.
  ⇒ la opción nueva (Selection `mercadolibre_so_name_label`: 'tracking' default | 'shipping_id') va en
  meli_oerp_multiple 16/17/18/19 (rama claude/502-757-so-name-shipping-id-<ver>, worktrees c757-<ver>), y la lógica en meli_oerp.
  Se toma también el sync-lock de meli_oerp_multiple. Bump de manifest en ambos módulos (mismo build).
- Las líneas del diagnóstico (2097/6948/1062/1105) son de 26.386; en origin/16.0 están en shipment.py ~2107/1072, orders.py ~7094.

## Avance
- [x] sync-lock meli_oerp tomado
- [x] worktrees (c757-<ver>, ramas claude/502-757-so-name-shipping-id-<ver>) de rama creadas (16/17/18/19)
- [x] código 16.0 (meli_oerp versions.py helper + orders.py + shipment.py rename y carrito; multiple campo+vista)
- [x] prueba Odoo 16 local: banco leaves/2026-11-12-502-757-banco (probe757.py, camino real orders_update_order_json→fetch_shipment). fix 18 OK/0 FAIL; control origin/16.0 9 OK/1 FAIL (= bug A, carrito nace sin sufijo); off/tracking idénticos fix vs control
- [x] meli_oerp_multiple: campo `mercadolibre_so_name_label` + vista 16-19 (16 attrs, 17+ invisible=)
- [x] port 17/18/19 (mismos parches, CRLF de shipment.py preservado); banco 17 y 19: 18 OK/0 FAIL
- [x] versión: max post-fetch rc=0 sobre TODOS los refs del suite = 26.396; 26.397 reservado MINT-F0 ⇒ 26.398 (reservado en comms), en meli_oerp y meli_oerp_multiple 16-19
- [ ] push ramas
- [ ] comms.md + lock liberado
