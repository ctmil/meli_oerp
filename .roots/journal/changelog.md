# meli_oerp - Changelog

> Historial de versiones y cambios orientado al cliente.

---

## Versión 16.0.26.25
2026-05-02 · `[16.0.shoppy]`

**Cambios:**

1. **Nombre de venta con info de envío:** El nombre del pedido de venta ahora muestra el número de seguimiento o ID de envío junto al número de orden ML, facilitando la identificación rápida.

2. **Tabla de mapeo de transportistas:** Nueva pantalla en MercadoLibre > Mapeo de Transportistas donde se pueden asignar los métodos de envío de ML a transportistas existentes en Odoo, evitando la creación de duplicados.

3. **Descuentos de cupón aplicados correctamente:** Los cupones y descuentos de MercadoLibre ahora se reflejan como descuento porcentual en las líneas del pedido de venta, asegurando que la factura refleje el monto real pagado por el cliente.

4. **Fechas de envío detalladas:** Se incorporaron las fechas reales de cada etapa del envío (preparación, despacho, entrega, etc.) además de las fechas estimadas, visibles en la ficha del envío.

5. **Etiqueta de envío visible en albarán:** La etiqueta PDF y su vista previa ahora se muestran directamente en el albarán (stock.picking).

6. **Nombre de impresora en configuración:** Se puede indicar el nombre de la impresora destino para etiquetas ZPL en la configuración de la cuenta ML.

---

## Versión 19.0.26.22
2026-04-30 · `[19.0.tecnolosys]`

**Cambios:**

1. **Publicación de productos:** Permalink API ahora incluye access_token para acceso directo desde el backend de Odoo.

---
