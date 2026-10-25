# meli_oerp - Changelog

> Historial de versiones y cambios orientado al cliente.

---

## 19.0.26.309 — 25-oct-2026 · Ventas marcadas «No actualizar desde ML»: sin errores repetidos en el registro
- Una venta con «No actualizar desde ML» sigue sin tocarse, pero ya no deja un error en el registro cada vez que llega una novedad de MercadoLibre: se avisa una vez y la notificación se da por procesada.

## 19.0.26.308 — 25-oct-2026 · Etiquetas de la venta en español y limpieza de código compartida con Odoo 20
- Pestaña MercadoLibre de la venta y lista de órdenes ML con etiquetas en español: monto del cupón (se corrigió el error de tipeo «Coupont amount»), descuento a cargo del vendedor, provincia/localidad/barrio/código postal del comprador, orden, id de envío, producto, SKU, IVA e ids de ML del producto; también monto de envío, detalle del estado y archivo PDF de la etiqueta.
- Consultas a la base con datos de MercadoLibre como parámetros (no armadas como texto) y 17 índices nuevos en relaciones muy usadas. ⚠️ Al actualizar se crean esos índices: en bases grandes conviene hacerlo fuera del horario de ventas.
- Crear una categoría ML nueva desde «Categorías» ya no da error.
- Se eliminó código que nunca se ejecutaba y los tests no salen a internet. En esta versión se quitaron además dos métodos que Odoo ya no llamaba (sin cambio visible).
- Release de armonización: mismo número 26.308 en 16, 17, 18, 19 y 20 para meli_oerp, meli_oerp_stock, meli_oerp_accounting, meli_oerp_multiple, meli_oerp_autofacturacion, meli_oerp_campaign y odoo_connector_api.

## 19.0.26.307 — 25-oct-2026 · La línea de envío en $0 de una venta ya facturada ya no queda «A facturar» [158]
- Cuando MercadoLibre informa un costo de envío sobre una venta que ya tiene factura emitida, el envío no se modifica (protección de venta facturada) y ahora tampoco se marca para facturar: la venta sigue «Facturada». Antes la línea de envío en $0 quedaba «A facturar» y un «Crear factura» manual armaba una factura con sólo el envío en $0.
- Al actualizar, se recalcula el estado de las líneas de envío de ventas ML en $0 que hubieran quedado así. Las líneas de envío con precio no se tocan.

## 19.0.26.306 — 25-oct-2026 · Devolución automática de envíos FULL con el parámetro `meli_oerp.cancel_return_full` [#607]
- Con el parámetro del sistema `meli_oerp.cancel_return_full = 1`, cuando MercadoLibre cancela una venta FULL con la salida ya hecha, la devolución se crea (y se valida si «Devoluciones» está en «Crear y validar») hacia la ubicación de origen de la salida. Antes sólo funcionaba junto con la política por motivo (`meli_oerp.cancel_reason_policy = by_reason`); ahora vale solo.
- Sin el parámetro en 1 no cambia nada: las ventas FULL siguen sin devolución automática.
- Siguen aplicando los motivos de `meli_oerp.cancel_return_reasons`, el pack dividido (`pack_splitted`, nunca devuelve solo en el modo de siempre) y el control de «ya devuelta» (no se duplica).

## 19.0.26.305 — 25-oct-2026 · Release de flota 26.305 (acompaña el cobro automático de meli_oerp_accounting)
- Test de regresión: re-sincronizar una venta ya facturada no cambia la línea de envío.

## 19.0.26.302 — 24-oct-2026 · Reserva de stock con Fabricación y dependencias
- Reserva de stock compatible con Fabricación (mrp): `stock.move._action_assign` acepta y pasa `force_qty` como el core (antes, con mrp instalado, la reserva podía fallar con TypeError).
- `requirements.txt` sin `Pillow>=12.0.0`: Odoo ya fija su versión de Pillow; forzar otra hacía que Odoo.sh reinstalara una librería del core.
- Build único 26.302 en 16/17/18/19/20 para meli_oerp, meli_oerp_stock, meli_oerp_multiple, meli_oerp_accounting y meli_oerp_autofacturacion.

## 19.0.26.300 — 24-oct-2026 · Contacto de facturación del 2do pack con el DNI + teléfono también en «Móvil» [#682]
- Venta de un pack (carrito) de un comprador que ya tenía otro pack: la venta ahora toma el contacto de facturación con su DNI/CUIT (buscado por el documento de facturación del comprador) en vez del contacto principal, que no lleva DNI. Antes sólo se buscaba por el número del pack y el contacto de facturación conservaba el del primer pack.
- El teléfono que manda MercadoLibre se escribe en «Teléfono» y también en «Móvil» (contacto del comprador y contacto de entrega), para que WhatsApp/SMS lo encuentren. Un móvil cargado a mano (distinto del teléfono) no se pisa. En 19.0 el contacto no tiene campo «Móvil»: sólo se escribe «Teléfono».
- No corrige las ventas ya creadas. Test `meli_682_dni_movil` (sin red).
- Build único 26.300 en 16/17/18/19 para meli_oerp, meli_oerp_stock, meli_oerp_multiple, meli_oerp_accounting y meli_oerp_autofacturacion.

## 19.0.26.299 — 23-oct-2026 · acompaña release de flota (fix #650 en meli_oerp_accounting)
- Sin cambios funcionales en este módulo (acompaña).
- Build único 26.299 en 16/17/18/19 para meli_oerp, meli_oerp_stock, meli_oerp_multiple, meli_oerp_accounting y meli_oerp_autofacturacion.

## 19.0.26.298 — 23-oct-2026 · Importar publicaciones con oferta activa trae el precio de lista [#452]
- Al importar o actualizar desde MercadoLibre una publicación con una oferta/campaña activa, la lista de precios de ML de Odoo ahora recibe el **precio de lista** (`original_price`) y no el precio con descuento (`price`). Si la publicación no tiene oferta, nada cambia.
- El "Precio de venta" de ML del producto/vinculación (`meli_price`) sigue siendo el precio publicado hoy (`price`): publicar el de lista sobre una publicación con campaña podría levantar la promoción.
- Aplica a todos los caminos de importación (asistente masivo, cron, vinculación, actualización desde la plantilla): todos pasan por `product_meli_get_product`. El neteo de IVA (configuración "impuestos excluidos") se aplica igual que antes, sobre el precio de lista.
- Build único 19.0.26.298 en 16/17/18/19 para meli_oerp, meli_oerp_stock, meli_oerp_multiple, meli_oerp_accounting y meli_oerp_autofacturacion (26.297 se saltea: lo usan ramas provisorias).

## 19.0.26.296 — 23-oct-2026 · Vincular variante: el aviso refleja si la vinculación quedó (meli_oerp_multiple)
- Sin cambios funcionales en este módulo (acompaña).
- Build único 19.0.26.296 en 16/17/18/19 para meli_oerp, meli_oerp_stock, meli_oerp_multiple, meli_oerp_accounting y meli_oerp_autofacturacion.

## 19.0.26.295 — 23-oct-2026 · un usuario interno sin grupos de conectores ya puede abrir y editar Contactos [#583]
- Sin cambios funcionales en este módulo (acompaña).
- Build único 19.0.26.295 en 16/17/18/19 para meli_oerp, meli_oerp_stock, meli_oerp_multiple, meli_oerp_accounting, meli_oerp_autofacturacion y odoo_connector_api.

## 19.0.26.294 — 23-oct-2026 · México: opción para corregir el régimen fiscal por defecto (601) con el dato de MercadoLibre
- **Nueva opción, apagada por defecto**: *México: corregir régimen/uso CFDI por defecto (601/G03) con el dato de ML* (`mercadolibre_mx_cfdi_override_default`), en la pestaña de configuración de MercadoLibre de la compañía (y en la configuración de cada cuenta con meli_oerp_multiple).
- Odoo crea los contactos mexicanos con régimen 601 por defecto: personas físicas (612) o público en general (616) ya cargados quedaban con un régimen que no es el suyo y 26.292 no los corregía. Con la opción prendida, si el contacto tiene 601 y ML informa otro código válido, se escribe el de ML (log `MX_CFDI override 601→612`). Uso de CFDI (G03 → p. ej. S01) con la misma regla.
- Nunca se pisa un valor distinto del default (carga manual) ni un contacto bloqueado para MercadoLibre. Apagada: igual que 26.292 (sólo completa vacíos). Sin `l10n_mx_edi`: sin cambios.
- Build único 19.0.26.294 en 16/17/18/19 para meli_oerp, meli_oerp_stock, meli_oerp_multiple, meli_oerp_accounting y meli_oerp_autofacturacion.

## 19.0.26.292 — 23-oct-2026 · México: régimen fiscal y uso de CFDI del comprador se toman de MercadoLibre
- **MLM con `l10n_mx_edi`**: el régimen fiscal (`l10n_mx_edi_fiscal_regime`, p. ej. 601/612/616) y el uso de CFDI (`l10n_mx_edi_usage`, p. ej. G01/G03/S01) que ML informa en los datos de facturación del comprador ahora se cargan en el contacto de facturación. Antes había que cargarlos a mano.
- Contacto creado por la importación: toma el dato de ML. Contacto existente: sólo se completan los campos **vacíos**; un valor cargado a mano **no se pisa** (queda en el log `MX_CFDI`). Contactos fijos de la configuración (bloqueados) no se tocan.
- Uso de CFDI en la venta (17.0+ con `l10n_mx_edi_sale`, que lo pasa a la factura): venta nueva, o venta sin facturas con el uso vacío o en el default G03. En 16.0 el uso no vive en el contacto ni en la venta: sólo se carga el régimen.
- Sin `l10n_mx_edi` instalado (otros países): sin cambios.
- Build único 19.0.26.292 en 16/17/18/19 para meli_oerp, meli_oerp_stock, meli_oerp_multiple, meli_oerp_accounting y meli_oerp_autofacturacion.

## 19.0.26.291 — 23-oct-2026 · el servicio de envío archivado o con la referencia cambiada ya no se duplica en cada venta [#452]
- **Producto de servicio de envío** [#452]: al importar una venta, el módulo buscaba el producto de envío sólo entre los **activos** y, si no lo encontraba, creaba uno nuevo **antes** de mirar el producto del transportista. Con el servicio archivado (p. ej. para sacarlo de otra tienda) o con la referencia interna cambiada por una secuencia automática (`product_sequence`), se creaba un «ME1 - zip» nuevo en cada pasada del cron — y ni siquiera se usaba en la línea. Ahora se busca: activos (por referencia y por nombre) → producto del transportista → archivados; sólo se crea si no existe ninguno.
- Productos duplicados ya creados no se borran solos: se eliminan a mano si no tienen ventas ni asientos.
- Build único 19.0.26.291 en 16/17/18/19 para meli_oerp, meli_oerp_stock, meli_oerp_multiple, meli_oerp_accounting y meli_oerp_autofacturacion.

## 19.0.26.289 — 22-oct-2026 · una venta de MercadoLibre que falla a mitad del lote del cron de órdenes se reintenta en la corrida siguiente [#543]
- Sin cambios funcionales en este módulo (acompaña).
- Build único 19.0.26.289 en 16/17/18/19 para meli_oerp, meli_oerp_stock, meli_oerp_multiple, meli_oerp_accounting y meli_oerp_autofacturacion.

## 19.0.26.288 — 22-oct-2026 · cancelaciones por motivo: pack dividido devuelve si la venta gemela ya tiene su salida [#624]
- **Pack dividido (`pack_splitted`) con la política `meli_oerp.cancel_reason_policy = by_reason`** [#624]: si la venta gemela (mismo comprador y producto, creada por ML al dividir el paquete) está en Odoo y tiene **su propia salida hecha**, la venta cancelada se cancela y **se devuelve su salida** (como A/B), con una nota que nombra la gemela y las dos salidas: sin esto quedaban dos salidas por un solo envío. Si la gemela no tiene salida propia o no está en Odoo: como antes, nota + actividad, sin devolución.
- FULL: la devolución respeta `meli_oerp.cancel_return_full`. Sin la política activa, `pack_splitted` sigue como siempre.
- Build único 19.0.26.288 en 16/17/18/19 para meli_oerp, meli_oerp_stock, meli_oerp_multiple, meli_oerp_accounting y meli_oerp_autofacturacion.

## 19.0.26.287 — 22-oct-2026 — landeo #529 26.245 + 26.249 (build de flota 26.287)
- Landeo en origin de `claude/529-cupon-facturada-19.0` (26.245) y `claude/529-descuento-vendedor-iva-19.0` (26.249), renumerados a 26.287.
- Merge con 26.229 (cupón del vendedor prorrateado con `items_total` + guarda de precio negativo): se conserva el prorrateo de 26.229; de 26.249 queda el salto de los detalles `type=discount` (oferta ya en `unit_price`), la guarda de venta confirmada, el IVA de una sola compañía y el 401.
- 26.245 combinado con 26.229: la guarda de factura posteada va ANTES del reparto del cupón.
- `rjson.get("error")` en el refresh: con el 401 sin clave `error` el `rjson["error"]` daba KeyError.

## 19.0.26.249 — 19-oct-2026 · descuento del vendedor restado dos veces, IVA de una sola compañía, 401 de ML [#529 #543]
- **#529 Descuento del vendedor:** una **oferta de precio** de ML (`/discounts` tipo `discount`) ya viene dentro del precio unitario; el importador la volvía a restar. Ej. Kindon: precio ML 54.312,50 (lista 55.000 − oferta 687,50) entraba como 53.625 y la venta quedaba 689,56 por debajo de lo cobrado. Ahora sólo se resta lo que no está en el precio (p. ej. el cupón financiado por el vendedor), y el importe a controlar/facturar usa el mismo valor.
- **#529** El descuento del vendedor, que es de la **orden**, se **prorratea** entre sus ítems (antes se restaba entero en cada línea).
- **#529** Una venta ya **confirmada** no recibe un descuento del vendedor nuevo al re-sincronizar: sus líneas no se reescriben, y cambiarlo dejaba el control de importe desalineado.
- **#543 Multicompañía:** al importar precios de ML (y al publicarlos con «impuestos excluidos») se usa sólo el IVA de la compañía de la configuración. Un producto con el IVA de dos compañías dividía por 1,42 en vez de 1,21.
- **«Tax Included = Configuración del sistema» (`auto`):** queda explícito que en Odoo 17+ equivale a «impuestos incluidos» (el grupo que consultaba existe sólo hasta 16). **No cambia ningún precio publicado.** Las ventas importadas ya se netean siempre desde 26.185 (#486).
- **#529** Un **401 de token vencido** de ML (que viene sin `error`) ahora dispara el refresh del token.
- Build único 26.249 en 16/17/18/19 (con meli_oerp_multiple 26.249).
## 19.0.26.245 — 19-oct-2026 · el cupón de ML ya no cambia una venta facturada [#529]
- **#529** Si la venta ya tiene una factura de cliente **publicada**, la actualización de la orden de ML ya no reescribe el descuento del cupón en sus líneas: venta y factura quedan con el mismo importe. Las ventas sin factura o con factura en borrador siguen recibiendo el cupón como antes.
## 19.0.26.284 — 22-oct-2026 · una venta de MercadoLibre ya no se crea dos veces [#431]
- **Venta duplicada:** cuando dos procesos traían la misma venta de MercadoLibre al mismo tiempo (las notificaciones y el repaso periódico de ventas), se creaban dos ventas, dos envíos y el contacto dos veces. Ahora cada venta (o carrito) la importa un solo proceso: el otro la saltea y la venta queda una sola vez.
- Requiere actualizar (`-u meli_oerp,meli_oerp_multiple`); sin campos nuevos. Build único 26.284 en 16/17/18/19.

## 19.0.26.283 — 22-oct-2026 · cancelaciones ML por motivo (opt-in) [#624] + botón Publicar Plazo [#609]
- **Cancelaciones de MercadoLibre según el motivo** [#624] (opt-in, modo de cancelación `legacy`): con el parámetro del sistema `meli_oerp.cancel_reason_policy = by_reason`:
  - cancelada por el comprador (`buyer_cancel_express`) y paquete cancelado por ML (`shipment_not_delivered` con el pago reintegrado): se cancela la venta y se devuelve la salida hecha;
  - mediación/devolución (`mediations` con el pago reintegrado): se cancela la venta y la devolución queda **sin validar**, con una actividad «Revisar cancelación de MercadoLibre» para decidirla con la resolución del reclamo;
  - ML **cubrió la venta** (pago `bpp_covered`: «Te dimos el dinero…», «Paquete no entregado. Te reembolsamos…»): **venta concretada**, no se cancela ni se devuelve; nueva marca «ML Cancelada con venta cubierta por ML», nuevo filtro, y sale del filtro «Canceladas pendientes en Odoo» y del banner;
  - pack dividido (`pack_splitted`): sin devolución automática; la nota nombra la **venta gemela** y su salida, y se agenda una actividad;
  - motivo ambiguo sin dato de pago: no se acciona, actividad de revisión. El dato de pago sale del `order_json` o de la foto fresca de ML (GET con timeout antes de escribir).
- `meli_oerp.cancel_return_full = 1`: con la política activa, las devoluciones de envíos **FULL** se crean (para quien lleva el stock del depósito FULL en Odoo).
- Sin los parámetros, el comportamiento es el de siempre.
- Build único 19.0.26.283 en 16/17/18/19 para meli_oerp, meli_oerp_stock, meli_oerp_multiple, meli_oerp_accounting y meli_oerp_autofacturacion.

## 19.0.26.282 — 22-oct-2026 · las direcciones de entrega y factura cambiadas a mano ya no vuelven a la original al sincronizar [#513]
- Si en un pedido de ML se cambia a mano el contacto de entrega o de factura, o la calle/ciudad/teléfono del contacto de entrega, la re-sincronización desde ML (cron, notificación o «Actualizar») lo respeta. Si nadie lo tocó, un cambio de dirección hecho en ML sigue entrando.
- Pestaña MercadoLibre del pedido: «Factura puesta por ML» / «Entrega puesta por ML» (sólo lectura).
- Pedidos anteriores a esta versión cuya entrega/factura no es el propio cliente se consideran fijados (no se re-sincroniza su dirección).
- Sólo meli_oerp en este build; el resto del suite se alinea en el próximo build de flota.

## 19.0.26.280 — 22-oct-2026 · la actualización de stock de una entrada grande ya no se pierde en silencio [#475]
- Sin cambios funcionales en este módulo (acompaña).
- Build único 19.0.26.280 en 16/17/18/19 para meli_oerp, meli_oerp_stock, meli_oerp_multiple, meli_oerp_accounting y meli_oerp_autofacturacion.

## 19.0.26.279 — 22-oct-2026 · panel CRONs: «Ejecutar ahora» con lock y contador de la corrida de precios [#427]
- Sin cambios funcionales en este módulo (acompaña).
- Build único 19.0.26.279 en 16/17/18/19 para meli_oerp, meli_oerp_stock, meli_oerp_multiple, meli_oerp_accounting y meli_oerp_autofacturacion.

## 19.0.26.273 — 22-oct-2026 · número de la retención del pago = ID de operación de MercadoPago [#484]
- Sin cambios funcionales en este módulo (acompaña).
- Build único 19.0.26.273 en 16/17/18/19 para meli_oerp, meli_oerp_stock, meli_oerp_multiple, meli_oerp_accounting y meli_oerp_autofacturacion.

## 19.0.26.272 — 22-oct-2026 · reintento de etiquetas de envíos buffered: cola y ventana desde la liberación [#158]
- Sin cambios funcionales en este módulo (acompaña).
- Build único 19.0.26.272 en 16/17/18/19 para meli_oerp, meli_oerp_stock, meli_oerp_multiple, meli_oerp_accounting y meli_oerp_autofacturacion.

## 19.0.26.271 — 22-oct-2026 · ventas ML: adopción de línea sin vínculo, carrito de una orden y carrito parcial [#431]
- **Ventas ML sin líneas duplicadas** [#431]: al sincronizar, si la venta tiene una línea del mismo producto sin vínculo ML (p. ej. la que deja cancelar y reconfirmar a mano) se la **adopta** escribiéndole los ids de ML en vez de crear otra; en una venta confirmada sin candidata no crea y deja **una** nota de control por ítem. Igual en las líneas de un pack.
- **Carrito de una orden**: una venta de carrito con una sola orden toma el estado cancelado de ML.
- **Carrito parcial**: si ML cancela una sola orden de un carrito, la venta no se cancela entera mientras quede alguna orden vigente (nota única); la última cancelación sigue el camino de siempre.
- Build único 19.0.26.271 en 16/17/18/19 para meli_oerp, meli_oerp_stock, meli_oerp_multiple, meli_oerp_accounting y meli_oerp_autofacturacion.

## 19.0.26.270 — 22-oct-2026 · pagos salientes ML con línea de método explícita + aviso de dinero sin registrar siempre visible
- Avisos de **dinero sin registrar** (cobro o pago de ML que no se pudo crear) quedan **siempre** en el chatter: con el modo de notificaciones «Desactivadas» van como nota interna (sin inbox), una vez por pago. Nuevo `meli_money_block_post` y parámetro `force_chatter` en `meli_message_post`; el help del modo lo documenta.
- Build único 19.0.26.270 en 16/17/18/19 para meli_oerp, meli_oerp_stock, meli_oerp_multiple, meli_oerp_accounting y meli_oerp_autofacturacion.

## 19.0.26.269 — 22-oct-2026 · cobros ML con línea de método explícita + lectura de mercadolibre.client [#526 #630 #542]
- Nuevo helper `meli_payment_method_line_for(journal, tipo, partner)` en `models/versions.py`: elige la línea de método de pago del diario que tenga «Cuenta de pagos pendientes» (o el default que la versión de Odoo aplique). Lo usan los cobros de meli_oerp_accounting y meli_oerp_multiple.
- Build único 19.0.26.269 en 16/17/18/19 para meli_oerp, meli_oerp_stock, meli_oerp_multiple, meli_oerp_accounting y meli_oerp_autofacturacion.

## 19.0.26.268 — 22-oct-2026 · release de flota: integración 462 (224–231) + aviso Publicar Stock [#462 #452]
- **Filtros de Ventas ML** (ex 26.230): Sin confirmar, A facturar, Nada para facturar, Totalmente facturadas, Sin factura publicada, Factura en borrador, Con factura publicada, Con nota de crédito, Full / Flex / Colecta / Punto de entrega, reclamos y devoluciones.
- **Línea de envío** (ex 26.231): se factura con el pago y no con la entrega; con envío $0 no deja el pedido en «Nada para facturar»; nunca se factura sola. La migración `migrations/19.0.26.268` recalcula el estado de facturación de las ventas ya confirmadas (renumerada desde 26.231 para que corra también en bases que ya están en 26.267).
- Aviso «lo cobrado no coincide»: nombra el ítem sin producto y se publica una sola vez (ex 26.231).
- Cupón a cargo del vendedor, prorrateado por ítem y sin llevar nunca un precio a cero; envío pagado por el comprador tomado de los pagos; cupón + descuento sin restar dos veces; venta de un pack cancelado entero toma el estado; la sincronización no agrega líneas a una venta confirmada (ex 26.229).
- Import de órdenes: el contacto de facturación sólo se escribe si algo cambió (ex 26.228). Textos neutros (ex 26.227).
- Guarda del pre-migrate 26.222 cuando la base viene de un build anterior a 26.16 (ex 26.226). URLs de la API armadas con el host configurado y sin SDK (ex 26.225). Etiquetas: descarga separada de su escritura (ex 26.224).
- Build único 19.0.26.268 en 16/17/18/19 para meli_oerp, meli_oerp_stock, meli_oerp_multiple, meli_oerp_accounting y meli_oerp_autofacturacion = 26.267 + integración 224–231 (nunca landeada hasta hoy) + #452.

## 19.0.26.267 — 22-oct-2026 · release de flota [#525 #539 #526]
- 267 = release flota: 265 #525 + 266 #539 + 267 #526. Sin cambios funcionales nuevos en este módulo en este build (acompaña).
- Build único 26.267 en 16/17/18/19 para meli_oerp, meli_oerp_multiple, meli_oerp_stock, meli_oerp_accounting y meli_oerp_autofacturacion.

## 19.0.26.265 — 22-oct-2026 · integración del pase de ROEN [#525]
- incluye #611 (diagnóstico de stock no reactiva sin stock publicable; REACTIVADA sólo verificada, ex 26.257) y #615 (enlace del reclamo a la mediación, ex 26.259).
- Build único 26.265 en 16/17/18/19 para meli_oerp, meli_oerp_multiple, meli_oerp_stock y meli_oerp_accounting.

## 19.0.26.257 — 21-oct-2026 · el diagnóstico de stock ya no «reactiva» lo que no puede publicar [#611]
- **#611** El control automático **Meli Stock Diagnostic** ya no intenta reactivar una publicación pausada cuando la existencia que ve está en ubicaciones de las que esa publicación **no publica** (p.ej. sólo en Full): calcula la cantidad con la misma regla que el envío de stock.
- Sólo anota **«REACTIVADA»** si Mercado Libre la muestra activa después; si sigue pausada lo dice (**«NO QUEDÓ ACTIVA»**, con el motivo que informa ML).
- Build único 26.257 en 16/17/18/19 (junto con meli_oerp_multiple 26.257).
## 19.0.26.259 — 21-oct-2026 · el enlace del reclamo abre la mediación en el panel del vendedor [#615]
- **#615** En una **mediación**, «Claim Link» abre ahora la mediación en el panel del vendedor: `https://vendedores.<dominio>/ventas/nueva/mensajeria/<pack o, si no hay, orden>/mediacion/<reclamo>`. Antes abría `www.<dominio>/reclamos/<reclamo>`, que Mercado Libre redirige a la venta.
- Devoluciones y cancelaciones conservan el enlace anterior: el formato del panel para esos tipos no está confirmado.

## 19.0.26.246 — 19-oct-2026 · match de SKU por token (opcional) [#543]
- **#543** Nueva opción **«Search SKU by token»** (`mercadolibre_sku_token_match`, por defecto **apagada**) y **«SKU token separators»** (default `- /`). Para catálogos donde el SKU de Mercado Libre trae el código de Odoo **más** una descripción (p.ej. `21342-ALIMENTO PERRO 20K` contra Referencia interna `21342`): se parte el SKU por los separadores y se vincula **sólo** si exactamente un trozo coincide con la Referencia interna de un único producto. Ningún trozo, dos trozos o código repetido en Odoo ⇒ no vincula (queda en el log). Es respaldo: corre después de la búsqueda exacta de siempre; apagada, todo funciona igual que antes.
- Config de la compañía (pestaña de importación, junto a «Search SKU»). Aplica a la importación de publicaciones (`product_meli_get_products`) y a la búsqueda de producto al importar ventas (`orders.py`).

## 19.0.26.238 — 17-oct-2026 · build de flota (sin cambios funcionales en este módulo)
- Acompaña a meli_oerp_multiple 26.238 (#361: stock de publicaciones pausadas en México). Build único 26.238 (sólo serie 19.0 en esta entrega).
## 19.0.26.231 — 15-oct-2026 · estado de facturación correcto con la línea de envío, aviso de ítem sin producto [#462]
- **Línea de envío de una venta ML:** se factura con el pago, no con la entrega. Con precio, entra en la factura junto al producto (antes podía quedar afuera y la factura salía por menos de lo cobrado); a $0 no tiene nada que facturar. Nunca se factura sola, sin el producto.
- **Estado de facturación:** una venta ML facturada ya no muestra «Nada para facturar» ni «A facturar» por culpa de la línea de envío. Al actualizar, el estado de las ventas existentes se recalcula solo (sólo el estado: no se tocan facturas, importes ni entregas).
- **Aviso «lo cobrado no coincide»:** ahora nombra el ítem de ML que no tiene producto en Odoo (ítem, SKU, título, cantidad, precio) y se publica una sola vez por motivo, no en cada sincronización.
- Requiere actualizar el módulo (`-u meli_oerp`); migración 19.0.26.231 (recalcula el estado de facturación de ventas ML confirmadas).
- Build único 26.231 en 16/17/18/19 para los 5 módulos del suite (integra 26.224–26.230).
## 19.0.26.224 — 14-oct-2026 · etiquetas: la descarga se separa del guardado [#158]
- **#158** La descarga de la etiqueta de Mercado Libre se separa de su guardado (nuevo `_meli_label_fetch_vals`), para que el reintento automático de meli_oerp_multiple pueda guardarla en una transacción corta. La impresión manual y el asistente funcionan igual que antes.
- Build único 26.224 en 16/17/18/19.
## 19.0.26.229 — 15-oct-2026 · cupón del vendedor en la venta, envío del comprador, cancelación de packs, sin líneas nuevas en ventas confirmadas
- **Cupón a cargo del vendedor:** si MercadoLibre informa que el cupón lo paga el vendedor (`/orders/{id}/discounts`, `amounts.seller`), la venta **nace con el descuento** (precio de la línea = precio de ML − descuento del vendedor) y la factura sale por lo que pagó el comprador. Antes la venta nueva se creaba a precio lleno. El descuento se reparte entre los ítems si la orden trae más de uno. También se consulta cuando el cupón viene sólo en el pago. En los modos «cupón como descuento» / «cupón en línea aparte» se imputa sólo la parte que financia ML (sin descontarlo dos veces).
- **Envío pagado por el comprador:** si el pago trae el envío y la venta no lo tenía registrado (`meli_shipping_amount` en 0, visto en cross_docking), se toma del pago: la venta cuadra y deja de figurar «Incompleta».
- **Cupón + descuento del vendedor:** cuando la venta ya tiene el descuento en el precio, el importe a facturar ya no lo vuelve a restar del pago. Sólo en ese caso y sólo si el cálculo anterior no cuadraba; el resto queda igual.
- **Cancelación de packs:** si MercadoLibre cancela **todas** las órdenes de un pack, la venta pasa a cancelada por el camino de siempre (fecha de corte, pack dividido y devoluciones sin cambios).
- **Sin líneas nuevas en ventas confirmadas:** la sincronización ya no agrega líneas a una venta confirmada o bloqueada (p. ej. después de cancelarla y reconfirmarla a mano).
- Requiere actualizar el módulo (`-u meli_oerp`): campo nuevo `discount_seller_coupon_amount` en órdenes ML (se crea solo, sin migración de datos).
- Build único 26.229 en 16/17/18/19.
## 19.0.26.230 — 15-oct-2026 · filtros de facturación, logística y reclamos en Ventas [#462]
- **Nuevo «ML Factura»** en las ventas: *Sin factura / Factura en borrador / Facturada / Con nota de crédito*. Dice qué facturas **tiene** la venta; el «Estado de facturación» nativo dice si **queda algo por facturar** (por eso una venta ya facturada, o con la entrega sin validar, muestra «Nada para facturar»).
- **Filtros nuevos** en Pedidos y en Cotizaciones (todos «ML · …»): Sin confirmar, A facturar, Nada para facturar, Totalmente facturadas, Sin factura publicada, Factura en borrador, Con factura publicada, Con nota de crédito, Full, Flex, Colecta, Punto de entrega, Con reclamo abierto y Con devolución (reclamo de ML) — estos dos, para usuarios con permiso de MercadoLibre.
- **Agrupar por** «ML · Estado de facturación» (ambas) y «ML · Tipo de logística» (Pedidos).
- Sin columnas nuevas ni migración: requiere actualizar el módulo (`-u meli_oerp`).
- Build único 26.230 en 16/17/18/19.

## 19.0.26.223 — 13-oct-2026 · stock de seguridad en el diagnóstico, fecha de la venta al confirmar, devoluciones canceladas, aviso de seguridad [#529 #640 #641]
- **#529** El diagnóstico de stock descuenta el stock de seguridad **por SKU según las Reglas de SKU tipo «Stock Rule»** (columna «Quantity Stock»; el SKU exacto gana sobre `*`), igual que el envío de stock: ya no reactiva ni «corrige» publicaciones que el resguardo deja en 0 a propósito. Sin reglas, igual que antes. El campo «Stock de seguridad (ML)» de 26.208 ya no se lee.
- **#640** Al confirmar una venta de MercadoLibre se conserva la **fecha de la venta de ML** (antes se pisaba con la hora de confirmación). Reemplazar un producto después ya no genera una devolución y dos transferencias internas pendientes.
- **#641** Si se cancela a mano la devolución automática de una cancelación de ML, queda como decisión tomada: el conector **ya no la vuelve a crear** en cada ciclo.
- **Seguridad:** nuevo `SECURITY.md` con el aviso de la ruta `/download/saveas` (eliminada desde 26.206/26.207) y el **crédito a kta1kri**, que la reportó de forma responsable.
- Build único 26.223 en 16/17/18/19.

## 19.0.26.222 — 13-oct-2026 · cancelaciones (pack dividido, fecha de corte), límite de despacho, línea de envío ME1 [#431 #158 #529]
- **Pack dividido por MercadoLibre (`pack_splitted`) en el modo de cancelación `legacy`:** si la venta ya tiene la salida hecha o una factura publicada, **ya no se cancela**: queda abierta, sin devolución ni nota de crédito, con un aviso para buscar la venta gemela (la misma regla que el modo `por_estado_ml`). Antes la venta entregada se cancelaba. Sin salida ni factura, se cancela como siempre.
- **«Cancelaciones automáticas desde»** (compañía y cuenta): lo que ML canceló antes de esa fecha queda **retenido** (marcado y en el filtro «Cancelaciones retenidas») en vez de procesarse solo. Vacío = como hasta ahora.
- **«Venta sin existencia al confirmar»** (cuenta): confirmar como siempre / confirmar con la salida en espera / no confirmar hasta que haya existencia. Envíos FULL: nunca se crea devolución automática al almacén propio.
- **Límite despacho ML:** se toma de `/shipments/{id}/sla` cuando ML no lo manda en el envío; columna opcional en pedidos y presupuestos. La migración llena la columna por SQL.
- **#158** En ventas ME1 donde el pago trae el envío aparte, el importe a facturar incluye el flete: la línea de envío y lo cobrable coinciden y la línea deja de ir y venir.
- El parámetro `meli_oerp.cancel_return_reasons` (26.221) sigue decidiendo qué motivos devuelven stock; el pack dividido entregado ya no llega a ese paso.
- **#529** Si el cupón de ML cambia después de crear la factura en borrador, el descuento se re-sincroniza en el borrador (nunca en una factura publicada). El diagnóstico de stock descuenta el stock de seguridad.
- Build único 26.222 en 16/17/18/19.

## 19.0.26.221 — 13-oct-2026 · cancelaciones de ML: qué motivos devuelven el stock solos
- **Nuevo parámetro del sistema `meli_oerp.cancel_return_reasons`** (Ajustes › Técnico › Parámetros del sistema):
  motivos de cancelación de MercadoLibre (`cancel_detail.code`, separados por coma) con los que la mercadería ya
  entregada se **devuelve automáticamente**. Por defecto **`buyer_cancel_express,fraud`**. `*` = todos los motivos
  (el comportamiento anterior).
- Con cualquier otro motivo (p. ej. `pack_splitted`, `shipment_not_delivered`, `mediations`, o sin motivo) la venta
  se cancela igual que antes, pero **no se crea la devolución**: queda marcada «ML Cancelada sin devolución de
  stock», con un aviso en el chatter, y se lista con el filtro **«ML: cancelada sin devolución de stock»** de Ventas.
- Aplica a todas las cancelaciones automáticas de ML (barrido de estados, importación) y a los dos modos de
  cancelación (`legacy` / `por_estado_ml`). Pedido de The 3 Letters (#638).
- Sigue acompañando a meli_oerp_multiple 26.221 (sello de stock). Build único 26.221 en 16/17/18/19.

## 19.0.26.221 — 12-oct-2026 · build de flota (sin cambios funcionales en este módulo)
- Acompaña a meli_oerp_multiple 26.221: el sello de stock ya no deja abortada la operación que lo llama (validar devoluciones, botones y crons de otros módulos). Build único 26.221 en 16/17/18/19.

## 19.0.26.220 — 12-oct-2026 · build de flota (sin cambios funcionales en este módulo)
- Acompaña a meli_oerp_multiple 19.0.26.220: el ajuste de redondeo del total usaba `tax_id` en Odoo 19 (`tax_ids`) y fallaba en silencio. Build único 26.220 en 16/17/18/19.

## 19.0.26.219 — 10-oct-2026 · build de flota (sin cambios funcionales en este módulo)
- Acompaña a meli_oerp_accounting 26.219 (#361 Score): no se concilia una factura global desde la notificación de una venta. Build único 26.219 en 16/17/18/19.

## 19.0.26.218 — 10-oct-2026 · ventas de MercadoLibre: cancelaciones, estado de envío, línea de envío e IVA (#638 #618 #620 #486)
- **#638** El re-chequeo de estado de órdenes recorre de forma rotativa todas las ventas abiertas (no sólo las últimas): una venta cancelada en ML se cancela en Odoo y, si ya tenía la salida de stock hecha, se genera su devolución.
- **#618** El mismo re-chequeo refresca el estado de los envíos no terminales (p. ej. `ready_to_ship` → `delivered`).
- **#620** La línea de envío de la venta refleja lo que **paga el comprador** según ML: si el flete lo cubre el vendedor (envío gratis/subsidiado, `cost_details`), la línea queda en 0 y no se suma al total.
- **#486** La importación de órdenes toma el precio de ML siempre como IVA incluido, sin depender del flag de publicación.
- Sin migración de datos nueva. Build 26.218 en 16/17/18/19 (paralelo a 26.217; al integrarse ambos en la rama de la serie se renumera).
## Versión 19.0.26.217 — La venta ya no se llena de mensajes «Línea adicional» [#462 Olpa]
10 oct 2026

**Cambios:**

1. **El problema:** en algunas ventas Full el historial sumaba un mensaje *«Línea adicional con [MEL Distribution]»*
   (o del envío Flex) en cada actualización desde Mercado Libre: cientos por venta. El conector ponía el envío en 0
   (porque la venta superaba lo cobrado) y en la pasada siguiente lo volvía a poner, y cada vez borraba y recreaba la línea.
2. **La solución:** el precio del envío sólo se repone si producto + envío no supera lo cobrado. La venta queda
   estable igual a lo cobrado y no se recrea la línea.

Además: `.gitignore` deja afuera el bytecode también dentro de `.roots/`. Build único de flota 26.217.

---

## 19.0.26.216 — 10-oct-2026 · build de flota (sin cambios funcionales en este módulo)
- Acompaña a meli_oerp_accounting 26.216 (#462 Olpa): los «Grupos de pago» de las ventas de MercadoLibre se confirman también con módulos cuyo botón Confirmar es `action_post` (p. ej. `account_payment_group_pro`). Integra además 26.214 (#486) y 26.215 (#661/542). Build único de flota 26.216 en 16/17/18/19.

---

## 19.0.26.215 — 10-oct-2026 · seguridad (#661, caso 542): sin dependencias externas desde git
- `requirements.txt` ya no instala el SDK de Mercado Libre desde `git+https://github.com/ctmil/python-sdk-2025.git` (no estaba fijado a una versión). El módulo habla con la API de ML con `requests` directo (`MeliApiNoSDK`), como ya hacía cuando el SDK no estaba instalado.
- Se elimina la carpeta `melisdk/` (SDK viejo 1.0.0 vendorizado, sin uso: todos sus imports estaban comentados).
- Si una instancia ya tiene el paquete `meli` instalado, sigue funcionando igual (se usa si está; ya no se exige). Sin migración de datos. Build único de flota 26.215 en 16/17/18/19.
## 19.0.26.213 — 9-oct-2026 · seguridad (#661, caso 542): el token de Mercado Libre ya no queda en links ni campos
- **Link Api** de la publicación, botón **Abrir API** y links **Descargar PDF/ZPL** de etiquetas: ahora los sirve Odoo (`/meli/item_api`, `/meli/shipment_labels`, sólo usuarios internos); el token viaja en el encabezado del servidor y ya no aparece en pantalla, historial del navegador ni logs.
- El link del pago de Mercado Pago se guarda sin token; la sugerencia de categoría y la subida de imágenes legacy mandan el token por encabezado.
- Al actualizar (migración 26.213) se limpian los tokens que ya estaban guardados (pagos, links de etiquetas, avisos). Requiere `-u meli_oerp`. Build único de flota 26.213 en 16/17/18/19.
## 19.0.26.210 — 9-oct-2026 · seguridad (#661, caso 542): Nivel de seguridad en todas las versiones + URL de la API única
- **Nivel de seguridad** (Predeterminado/Bajo/Alto, en la compañía): disponible también en 16/17/18 (antes sólo 19). Login de ML sin mostrar tokens; fuera las páginas /meli/, /meli_authorize/, /meli_logout/, /meli/image y /download/saveas.
- **URL de la API de Mercado Libre**: un único campo validado en la compañía (por defecto la oficial). Reemplaza al "Host API ML (rescate)" de la compañía y de cada cuenta; al actualizar se copia solo, nada cambia para quien no usa proxy.
- **Registro de uso**: si la URL no es la oficial, cada llamada queda en *Ventas › MercadoLibre › Registro de uso de la URL de la API* (sólo Administrador; sin tokens) y en el log `meli_oerp.proxy_audit`. Con Nivel **Alto** la URL alternativa se ignora y se usa la oficial.
## 19.0.26.198 — 8-oct-2026 · release de flota: #601 (P1/P3/P6/P7), seguridad #661, contacto del albarán #643
- **Envío gratis (#601 P1):** una orden con envío gratis ya no se pierde al importarse.
- **Etiquetas (#601 P3):** el link de la etiqueta ya no lleva el token de ML; descarga con timeout y con modo vacío.
- **Cron de stock/precio (#601 P6):** savepoint por ítem — un ítem que falla ya no aborta el resto del lote.
- **Diagnóstico de stock (#601 P7):** nueva opción *Sólo las pausadas por falta de stock*: deja de reactivar pausas manuales.
- **Seguridad (#661):** `/download/saveas` exige usuario y lista blanca (vacía: sin usos internos); `get_meli_state`
  asigna el compute en bases neutralizadas (antes rompía la edición de la empresa).
- **Contacto del albarán (#643):** si el conector cambia la dirección de entrega de una venta ML ya confirmada, se
  propaga al grupo de abastecimiento y a los albaranes abiertos que llevaban la anterior (uno cargado a mano no se pisa).
- Requiere `-u meli_oerp` (migración 26.172 incluida). Build único de flota 26.198 en 16/17/18/19.

---
## 19.0.26.179 — 3-oct-2026 · El estado del envío se mantiene al día [#618]
- Las ventas de MercadoLibre ya no quedan en "Listo para enviar" para siempre: el barrido periódico de estados
  vuelve a consultar también el **envío** (enviado, entregado, no entregado) de las órdenes abiertas, por turnos.
- Se puede desactivar con el parámetro del sistema `meli_oerp.resync_shipment_status = 0`.
## 19.0.26.194 — 7-oct-2026 · La línea de envío deja de ir y venir [#158]
- En ventas donde MercadoLibre informa el envío en el pago pero no en el total pagado, el importe a facturar ahora
  incluye ese envío. La línea de envío y lo que se factura usan el mismo monto: la línea ya no pasa de $0 al
  envío y vuelta en cada actualización, y la factura sale con el envío.
- Incluye el cambio #620 (26.180).

## 19.0.26.180 — 3-oct-2026 · La línea de envío lleva lo que pagó el comprador [#620]
- La línea de envío de la venta toma el costo que MercadoLibre informa como pagado por el comprador. Ya no queda en
  $0 en unas ventas y con monto en otras, y el importe a facturar incluye ese envío.
- Si el envío es gratis para el comprador (lo cubre el vendedor), la línea queda en 0 y no se factura.
- El ajuste "Usar Monto de envío de Pagos" de la cuenta se sigue respetando.

## 19.0.26.185 — 5-oct-2026 · las ventas de ML entran siempre por lo cobrado, publiques con o sin IVA [#486]
- **El problema:** el campo *Impuestos incluidos* de la configuración decidía dos cosas a la vez: cómo se
  PUBLICA la lista de precios y cómo se IMPORTAN las ventas. Con *impuestos incluidos* (lista con IVA) y un
  IVA de venta no incluido en el producto, cada venta importada sumaba el impuesto encima del precio ya
  final de ML (total x1,16) y quedaba en presupuesto por diferencia de montos.
- **Ahora** la importación toma siempre el precio de ML como final con impuestos y lo netea por los
  impuestos de venta no incluidos del producto: el total de la venta en Odoo es lo cobrado en ML.
- **Sin cambios** en la publicación de precios, ni para quien tiene *impuestos excluidos* o impuestos
  con precio incluido.
## 19.0.26.171 — 1-oct-2026 · casos especiales de confirmación y cancelación [Tus Refacciones 431]
- **"Venta sin existencia al confirmar = Confirmar siempre" ahora también funciona con la ruta "Obtener bajo
  pedido (MTO)" estándar de Odoo** (antes sólo con la variante "Tomar del stock, si no disponible, ordenar"). La
  venta se confirma y la salida queda en espera aunque la compra no se pueda generar.
- **Nueva opción "Cancelaciones automáticas desde"** (cuenta de MercadoLibre y compañía): lo que MercadoLibre
  canceló antes de esa fecha no se procesa solo — queda marcado ("ML Cancelación retenida") y en el filtro
  *MercadoLibre Cancelaciones retenidas (anteriores al corte)* para revisarlo a mano, o procesarlo con la acción
  *MercadoLibre: procesar cancelación ignorando la fecha de corte*. Vacía = como hasta ahora.
- **Envíos FULL:** al cancelarse, ya no se crea una devolución al almacén propio (el stock lo maneja
  MercadoLibre).
- **Pack dividido por MercadoLibre (pack_splitted):** no se crea devolución ni nota de crédito; si la venta ya
  tenía la salida hecha o una factura publicada, queda abierta con un aviso para revisar la venta gemela.
- El aviso *"Monto correcto, listo para confirmar venta."* se publica una sola vez por venta.

---
## 19.0.26.159 — 29-sep-2026 · build de flota
- Sin cambios de código en esta serie: el número se alinea con 18.0.26.159 (#504/#520, descuento de vendedor y
  envío decididos juntos — la opción de tope existe sólo en 18.0).

---
## 19.0.26.158 — 29-sep-2026 · build de flota
- Sin cambios de código en esta serie: el número se alinea con 18.0.26.158 (#504/#520, lectura del tope del
  descuento de vendedor con cuentas de conexión — la opción existe sólo en 18.0).

---
## 19.0.26.138 — 24-sep-2026 · build de flota: alineación local↔origin
- Integra en la rama de deploy lo que estaba sólo en local: video_id vacío (26.127), guard de devoluciones
  `scrapped`/`scrap_id` resuelto contra `_fields` (26.129), ports del #494.
- Sin cambios de datos ni vistas: el salto de build es para que las cuatro series designen el mismo release.

## Versión 19.0.26.134 — Los reclamos de MercadoLibre vuelven a verse en Odoo, y el link de mensajes lleva al país de la cuenta
23 sep 2026

**Cambios:**

1. **Los reclamos de MercadoLibre vuelven a aparecer en Odoo [#615].** La pantalla de reclamos
   quedaba **vacía y sin ningún aviso**: MercadoLibre informa tipos de reclamo que el conector no
   tenía previstos (`returns`, `mediations`, `cancel_purchase`, `cancel_sale`) y la sincronización
   se cortaba en silencio, empresa por empresa. Ahora esos tipos están contemplados y, si en el
   futuro aparece uno nuevo, el reclamo **igual se guarda**: queda sin tipo, con un aviso en el
   registro técnico y el dato original completo. Verificado sobre una base real: los **17** reclamos
   abiertos entraron, los **17** con su venta asociada.

2. **El link para ver los mensajes lleva al sitio del país de la cuenta [#615].** Antes apuntaba
   siempre a `mercadolibre.com.ar` y al lado del **comprador**, así que desde una cuenta de México,
   Colombia, Chile, Perú, Uruguay o Brasil no llevaba a ninguna parte útil. Ahora abre el centro de
   mensajes **del vendedor**, en el dominio que le corresponde a la cuenta.

3. **Las devoluciones automáticas dejan de reintentar para siempre [#409].** En esta versión de
   Odoo, el control que decide si hay algo real para devolver leía un campo del albarán que ya no
   existe. El error quedaba tapado: se registraba como *"Error creating return"* y la tarea
   programada volvía a intentarlo cada pocos minutos, indefinidamente, sobre el mismo remito
   (medido en una instancia real: **428** intentos en un día sobre un único albarán). Ahora el
   control usa el campo que corresponde a cada versión de Odoo y la devolución se procesa o se
   saltea, pero no vuelve en bucle.

4. **Qué versión mirar.** Este build es **26.134** y es el mismo número en las cuatro versiones de
   Odoo (16, 17, 18 y 19): nombrarlo alcanza para saber qué trae, sin aclarar de cuál.

Requiere actualizar el módulo (`-u meli_oerp`).

---
## Versión 19.0.26.127 — Las publicaciones sin video vuelven a subir a MercadoLibre [#492 / #577]
21 sep 2026

**Cambios:**

1. **El problema:** al publicar un producto que **no tiene un video cargado**, MercadoLibre
   rechazaba la publicación con el mensaje *"The field video_id must have at least 3 characters"*
   (*el campo video_id debe tener al menos 3 caracteres*). El producto no llegaba a publicarse.
2. **La causa:** el conector enviaba **siempre** el campo del video, incluso cuando estaba vacío.
   Hasta hace poco MercadoLibre **descartaba** ese campo vacío con un simple aviso
   (`item.video_id.dropped`) y la publicación seguía adelante; **ahora lo rechaza**. El envío del
   campo vacío existe desde 2018: lo que cambió fue la validación de MercadoLibre, no el conector.
3. **La corrección:** el campo del video **ya no se envía cuando está vacío**. Sólo viaja si el
   producto tiene un video cargado. Aplica tanto al **alta** de una publicación como a su
   **actualización**.
4. **Efecto lateral que conviene conocer:** al actualizar una publicación, el conector **ya no pisa
   el video** que se haya cargado directamente desde el panel de MercadoLibre. Antes lo intentaba
   borrar en cada actualización.
5. **Qué hay que hacer:** nada. No requiere cargar ningún video ni tocar los productos.

---
## Versión 19.0.26.124 — La cancelación automática verifica que la venta haya quedado cancelada [#494]
20 sep 2026

**Cambios:**

1. **Esta versión de Odoo NO tenía el problema** que sí afectaba a 16, 17 y 18 (ahí la cancelación
   automática no cancelaba ninguna venta confirmada). Se alinea igual el código para que las cuatro
   versiones del conector se comporten y se lean igual.
2. **La cancelación ahora se verifica.** El conector ya no da por cancelada una venta: comprueba
   que haya quedado en estado Cancelado. Si no lo consigue, lo dice — aviso explícito en el
   historial de la venta y error en el registro — en vez de seguir de largo.
3. **El historial deja de poder mentir.** El mensaje *"Orden cancelada por MercadoLibre"* se
   escribe **sólo si la venta quedó realmente cancelada**.

Requiere actualizar el módulo (`-u meli_oerp`).

---

## Versión 19.0.26.115 — El código universal de producto (GTIN) ya no genera variantes
17 sep 2026

**Cambios:**

1. **El problema:** Mercado Libre declara el **GTIN** (código universal de producto) como atributo
   "de variación", porque del lado de ML cada variación puede llevar su propio código. El conector
   le hacía caso y marcaba ese atributo en Odoo como generador de variantes. Pero en Odoo el GTIN es
   el **código de barras de la variante**, no una característica del producto: el resultado era
   **una variante nueva por cada código**, justo lo contrario de para lo que se usan las variantes.
2. **Ahora** el GTIN y el SKU del vendedor (`SELLER_SKU`) **nunca** quedan marcados como generadores
   de variantes, aunque Mercado Libre los declare así. Vale tanto al traer los atributos de una
   categoría como al usar el botón *Fix attribute*.

3. **Además, en esta versión:** el botón *Fix attribute* ganó el camino inverso. Hasta ahora sólo
   podía **subir** un atributo a "genera variantes"; ahora también puede **bajarlo**, que es lo que
   hace falta para reparar un catálogo donde el GTIN ya quedó cargado como característica.
   Si alguna variante de un producto ya tiene movimientos de stock o ventas, ese producto **se
   saltea** y queda anotado en el log: no se borra nada que ya haya operado.

**A quién le importa esto:** a cualquier cuenta que publique en categorías donde ML declara el GTIN
de variación. Un caso medido: la categoría de **Cables Eléctricos** (`MLA455454`) declara de
variación exactamente dos atributos, y el GTIN es uno de ellos.

---

## Versión 19.0.26.109 — Vincular publicaciones por CÓDIGO DE BARRAS, sin depender del SKU
8 sep 2026

**Cambios:**

1. **El problema:** al importar publicaciones, el conector sólo reconocía un producto por su
   **Referencia interna** (`default_code`). Si el aviso de MercadoLibre no traía SKU, o si el código
   del catálogo estaba cargado en el **código de barras** y no en la referencia interna, la
   publicación **no se vinculaba con ningún producto** y había que cargar SKUs sólo para eso.
2. **Ahora hay un parámetro nuevo:** *Search Barcode*, en la configuración de MercadoLibre de la
   compañía. Con él encendido, cuando la búsqueda por SKU no encuentra exactamente un producto, el
   conector reintenta **por código de barras**, en dos casos:
   - el aviso **sí** trae SKU, pero ese código en Odoo vive en el campo *Código de barras*;
   - el aviso **no** trae SKU y sí trae **GTIN/EAN**: se busca ese GTIN contra el código de barras.
   Funciona tanto para la publicación como para cada **variación**.
3. **Sólo vincula si la coincidencia es única.** Si el código de barras aparece en dos o más
   productos, **no vincula ninguno** y lo deja anotado en el log. Es a propósito: el código de barras
   no es único por construcción, y hay catálogos donde ese campo guarda en realidad un código interno
   — vincular "el primero" asociaría la publicación al producto equivocado, y eso se arrastraría al
   stock y a las ventas.
4. **Viene DESACTIVADO.** Al actualizar, el comportamiento no cambia para nadie: hay que encenderlo a
   propósito en la compañía que lo necesite.

*Este camino ya existía para las **ventas** (una venta de MercadoLibre cuyo SKU no aparecía como
referencia interna se buscaba por código de barras); esta versión lo lleva también a la
**vinculación de publicaciones**, que era donde faltaba.*

Requiere actualizar el módulo (`-u meli_oerp`).
## Versión 19.0.26.96 — La cancelación automática verifica que la venta haya quedado cancelada
23 ago 2026

**Cambios:**

1. **Esta versión de Odoo NO tenía el problema** que sí afectaba a 16, 17 y 18 (ahí la cancelación
   automática no cancelaba ninguna venta confirmada). Se alinea igual el código para que las cuatro
   versiones del conector se comporten y se lean igual.
2. **La cancelación ahora se verifica.** El conector ya no da por cancelada una venta: comprueba que
   haya quedado en estado Cancelado. Si no lo consigue, lo dice — aviso explícito en el historial de
   la venta y error en el log — en vez de seguir de largo.
3. **El historial deja de poder mentir.** El mensaje *"Orden cancelada por MercadoLibre"* se escribe
   **sólo si la venta quedó realmente cancelada**.

Requiere actualizar el módulo (`-u meli_oerp`).

---
## Versión 19.0.26.94 — Los pedidos ya facturados quedan protegidos de punta a punta (y ahora avisan)
21 ago 2026

**Cambios:**

1. **Se completa lo de la versión anterior.** Además de no poner el envío en cero, el conector **no
   reescribe ninguna línea ni monto** de un pedido que ya tiene factura emitida — por **ninguno** de los
   caminos posibles, incluido el borrado de la línea de envío. Cuando MercadoLibre informa un cambio
   sobre un pedido ya facturado, el pedido **se deja como está** y queda **un aviso en su historial**
   (una sola vez, no en cada reintento) explicando qué cambio no se aplicó y con qué factura choca, para
   que se resuelva desde la factura (nota de crédito o ajuste) y no por debajo de ella.
2. **Es configurable:** *No modificar pedidos ya facturados*, en la configuración de MercadoLibre de la
   compañía. Viene **activado**; desactivarlo restaura el comportamiento anterior.

*Esta protección ya existía en la versión 16 desde julio (caso Shoppy); esta versión la trae a Odoo 19.*

Requiere actualizar el módulo (`-u meli_oerp`).

## Versión 19.0.26.93 — El envío ya facturado deja de quedar en cero en la orden
21 ago 2026

**Cambios:**

1. **El problema:** una venta de MercadoLibre entraba con su costo de envío, se facturaba con el envío
   incluido, y una actualización posterior de MercadoLibre **dejaba el envío en 0 en la orden**. La
   factura ya emitida quedaba con el flete y la orden sin él: orden y factura descuadradas, y el flete
   había que rehacerlo a mano. Ahora, si la línea de envío ya fue facturada, el conector **no la toca** y
   deja constancia en el registro del servidor. En órdenes todavía no facturadas nada cambia.
   *Medido en un cliente AR: 61 de 347 facturas de MercadoLibre con flete quedaron descuadradas en siete
   semanas, por $1.673.959,97.*
## Versión 19.0.26.95 — El diagnóstico de stock ya no puede decir "todo bien" cuando no revisó nada [#535 Score]
19 ago 2026

**Cambios:**

1. **Cuando MercadoLibre rechaza una consulta, ahora se ve.** El diagnóstico de stock le pregunta a MercadoLibre por cada publicación sospechosa. Si ML respondía con un rechazo (por ejemplo *403: la publicación pertenece a otro vendedor*), esa respuesta **se leía como si fuera una publicación normal sin nada para corregir** y quedaba anotada como *"sin acción"*. Con varias cuentas de ML en la misma base eso significaba que **todas** las publicaciones de una cuenta podían ser rechazadas y la revisión terminaba informando **cero problemas**. Ahora cada rechazo se cuenta, se registra con su motivo y aparece en el resumen del historial de la cuenta.
2. **Una revisión que no revisó nada deja de figurar como exitosa.** El resultado del diagnóstico ahora informa cuántas publicaciones se consultaron de verdad, cuántas rechazó MercadoLibre y con qué código, para que la página de **CRONs** de la cuenta pueda mostrarla como *advertencia* con el motivo escrito, en lugar de un tilde verde con 0 ítems procesados. *(La corrección que usa este dato para marcar la ejecución viaja en el módulo `meli_oerp_multiple`.)*

*Medido en un cliente MX con dos cuentas de ML en la misma base: 134 publicaciones de la segunda cuenta se consultaban con el token de la primera y devolvían 403; el proceso terminaba en verde con 0 ítems procesados, así que el problema estuvo semanas a la vista sin verse.*

Requiere actualizar el módulo (`-u meli_oerp`).

## Versión 19.0.26.90 — La devolución automática de ventas canceladas por ML vuelve a funcionar (y deja de llenar el historial de avisos repetidos)
30 jul 2026

**Cambios:**

1. **El problema principal:** cuando MercadoLibre cancelaba una venta que ya se había facturado y despachado, el conector intentaba generar la devolución del remito y **fallaba siempre** con *"Especifique al menos una cantidad diferente a cero"*. En Odoo 16 la ventana de devolución se abría **sin líneas** (el conector la creaba por código y las líneas sólo se completan al abrirla a mano), así que no había nada que devolver. Es decir: **en Odoo 16 la devolución automática nunca funcionó**. Ahora las líneas se completan también por código y la devolución se crea sola.
2. **El proceso automático dejaba de reintentar nunca:** como la devolución fallaba, el proceso volvía a intentarlo **cada 5 minutos, para siempre**, por cada venta cancelada en esa situación. Se agregó el mismo control de "no hay nada que devolver" que ya existía en las otras variantes, así que las entregas sin cantidades reales (típico de las ventas FULL, cuyo stock vive en el depósito de ML) se saltean limpio en vez de reintentarse eternamente.
3. **Se terminó el historial inundado de avisos repetidos:** los avisos *"No se pudo devolver el albarán…"* y *"Cancelación de ML pendiente: factura publicada sin resolver"* se volvían a escribir en el historial de la venta en **cada** reintento. Ahora se escriben **una sola vez**; si la situación cambia (otra factura, otro remito), se vuelve a avisar. *Medido en un cliente AR: 2.047 mensajes repetidos en el historial de dos ventas y 514 errores por día en el registro del servidor.*

Requiere actualizar el módulo (`-u meli_oerp`).

## Versión 19.0.26.88 — El stock vuelve a sincronizarse solo (se arregló una cola que se congelaba)
28 jul 2026

**Cambios:**

1. **El problema:** una publicación podía quedar con el stock de MercadoLibre desactualizado **para siempre**, sin ningún aviso. El conector decide qué publicaciones re-enviar mirando la fecha del último movimiento de stock del producto; esa fecha se tomaba de *cuándo se creó* el movimiento y no de *cuándo cambió el stock*. Resultado: si el stock cambiaba sin crear un movimiento nuevo — validar un remito creado días antes, reservar o liberar mercadería, cancelar una entrega —, el conector no se enteraba. Peor: una vez enviado ese stock una primera vez, la publicación salía de la cola y **ningún proceso automático la volvía a mirar nunca**. Ahora la fecha considera la validación y las modificaciones posteriores del movimiento, y nunca puede "retroceder".
2. **Red de seguridad nueva:** toda publicación cuyo último envío de stock a MercadoLibre supere los **7 días** vuelve a la cola por sí sola, haya habido movimientos o no. Es configurable en la cuenta (*Resincronización de stock*); poner 0 la desactiva. Así, si alguna vez se pierde un aviso, el desfase dura días y no meses.
3. **Los kits (listas de materiales) entran en la cuenta:** un producto tipo kit no tiene movimientos propios — su stock sale de los componentes. Ahora los movimientos de los componentes también reactivan la publicación del kit.
4. **Se detecta cuando MercadoLibre acepta el envío pero no aplica el stock.** Hasta ahora, si ML respondía "OK" y dejaba la cantidad vieja, el conector lo daba por publicado y la publicación quedaba desactualizada en silencio. Ahora se compara la cantidad enviada contra la que responde ML y, si no coinciden, la publicación queda marcada como **"ML aceptó el envío pero NO aplicó el stock"** y se reintenta.
5. **Errores que se perdían:** si fallaba algo al publicar el stock, el error quedaba anotado pero la operación se informaba como exitosa. Ahora el fallo se propaga y la publicación no se marca como actualizada.
6. El diagnóstico de stock ahora **guarda el estado real** que le responde MercadoLibre (activa/pausada). Antes lo consultaba y lo descartaba, así que el estado guardado quedaba viejo por meses y generaba avisos falsos de "publicación pausada con stock" sobre publicaciones que en realidad estaban activas.

*Detectado en una cuenta MX con 3.700 publicaciones: 209 movimientos validados con demora en 60 días quedaban fuera de la sincronización, y publicaciones con la fecha congelada desde hacía semanas.*

Requiere actualizar el módulo (`-u meli_oerp`).
## Versión 19.0.26.88 — Queda constancia cuando la importación de pedidos corta por el tope configurado
3 ago 2026

**Cambios:**

1. El proceso de importación de pedidos toma las ventas **de la más nueva a la más vieja** y, cuando
   está configurado el *Límite de órdenes por cron*, procesa sólo esa cantidad y **no sigue** con el
   resto. Eso es intencional —el parámetro está para acotar el trabajo por ciclo y no reventar los
   límites de la API de MercadoLibre—, pero hasta ahora **no dejaba ningún rastro**: si una venta
   quedaba fuera de esa ventana, nadie se enteraba. Ahora, cada vez que la ventana se corta, queda un
   **aviso en el registro del servidor** con cuántas ventas informa MercadoLibre, cuántas se
   procesaron, y el recordatorio de que las que quedan afuera dependen del proceso
   *MELI: reintentar facturas que quedaron sin emitir*.
2. **El comportamiento del proceso no cambia**: se documentó la decisión y se agregó la constancia.
   La red de seguridad para las ventas que quedan afuera (y cuya factura falló) es el nuevo reintento
   de facturación de `meli_oerp_accounting`.

**Detalle técnico:** `mercadolibre.orders.orders_query_iterate` — cuando hay `orders_limit`,
`offset_next` sigue en 0 (tope deliberado: paginar ahí invertiría el sentido del campo y haría que un
seller con miles de órdenes recorriera todo su historial en páginas del tamaño del límite en cada
ciclo). Se agrega un `_logger.warning` de truncamiento.

---

## Versión 19.0.26.87 — El costo de envío ya no se pierde de la orden [Elvimarta #508]
27 jul 2026

**Cambios:** al recalcular el flete, el conector reescribía la línea de envío con el mecanismo de Odoo, que primero **borra** la línea y recién después la vuelve a crear. Si en ese momento la venta no tenía transportista asignado, o la recreación fallaba (compañía incompatible, orden ya facturada, impuestos), el borrado quedaba hecho y la venta se quedaba **sin flete y sin transportista**: el costo de envío no llegaba nunca a la factura, y el error se descartaba en silencio. Ahora, sin transportista válido no se toca la línea (solo se actualiza su precio) y la reescritura va dentro de un punto de guardado, de modo que si algo falla se deshace el borrado y la línea original sobrevive; los fallos quedan registrados en el log con la venta involucrada. *Detectado en un cliente AR: 47 órdenes sin flete en 7 semanas, 20 de ellas facturadas por debajo de lo cobrado al comprador.*
## Versión 19.0.26.86 — Se elimina la foto fantasma que se agregaba en cada publicación
23 jul 2026

**Cambios:**

1. Se corrige un problema por el cual el conector agregaba una **imagen extra inválida** en cada publicación de MercadoLibre (una segunda foto "basura"), lo que en algunos casos impedía activar la publicación. Ahora la imagen de logo sólo se agrega si realmente está configurada.

## Versión 19.0.26.85 — Aviso de mensajes del comprador sin leer en las órdenes de ML [#499 Deco/KPI]
22 jul 2026

**Cambios:**

1. Las órdenes de MercadoLibre ahora muestran un contador de **mensajes del comprador sin responder** (post-venta), para saber de un vistazo qué ventas tienen un mensaje pendiente sin tener que revisar publicación por publicación en MercadoLibre.
2. Nuevo filtro **"Con mensajes del comprador sin leer"** en la lista de órdenes, y un enlace directo a la conversación en MercadoLibre.
3. Se actualiza solo cada 10 minutos (proceso automático) y también hay un botón **"Refrescar mensajes"** en la cuenta para actualizarlo al instante.

## Versión 19.0.26.84 — "Traer medidas" ahora completa TODAS las variantes, no solo la primera [#424 Deco/KPI]
21 jul 2026

**Cambios:**

1. Al traer las medidas e impuestos de una publicación (con "Traer medidas" o al importar), los datos ahora se escriben en **todas las variantes** de esa publicación, no solo en la primera. Antes, en publicaciones con varias variantes (por ejemplo distintos colores), solo la primera quedaba con las medidas cargadas y el resto quedaba vacío.

## Versión 19.0.26.82 — Comprador (nickname/ID) y zona del receiver buscables en el pedido de venta [#404 Deco/KPI]
19 jul 2026

**Cambios:**

1. En el **pedido de venta** (sale.order) ahora se puede **buscar y filtrar** por datos del comprador y del destinatario de MercadoLibre:
   - **Nickname** e **ID** del comprador ML (ej. "VIEIROBRIAN20210623234209" / "780371376").
   - **Provincia**, **Localidad**, **Barrio** y **Código Postal** del receiver del envío.
   Aparecen en el buscador (filtros) y en la pestaña MercadoLibre del formulario del pedido.
2. El objeto **Envío** (mercadolibre.shipment) ahora guarda además el **Barrio** y el **Municipio** del destinatario, parseados de la dirección que envía MercadoLibre.

Feature genérica, promovida desde el cliente Deco/KPI (cuenta 526). Requiere actualizar el módulo (-u meli_oerp).
## Versión 19.0.26.83 — Savepoints anti-`InFailedSqlTransaction` al importar categorías y productos [#410 SOLSUN]
20 jul 2026

**Cambios:**

1. La importación de categorías y de productos ya no puede dejar la transacción de base de datos
   "abortada" cuando falla un paso frágil (carga de atributos de categoría, filtros de búsqueda o
   asignación de categoría a un ítem): cada paso queda **aislado** con un punto de guardado
   (savepoint), así un fallo puntual **no interrumpe el resto de la sincronización** con el error en
   cascada `InFailedSqlTransaction`.
2. Cierra además la **causa raíz** del error de clave foránea de categoría (`meli_category`) que
   aparecía al importar (#410): la categoría recién creada ya no se pierde en un rollback silencioso.
## Versión 19.0.26.82 — El diagnóstico de stock reactiva de forma EXPLÍCITA las publicaciones pausadas con stock
17 jul 2026

**Cambios:**

1. Cuando el diagnóstico de stock (la red de seguridad que corre al terminar el cron de stock) detecta —consultando el estado **en vivo** a MercadoLibre— una publicación **pausada** que **sí tiene stock** en Odoo, ahora la **reactiva de forma explícita** (la pone "activa") además de reenviarle el stock.
2. Antes se dependía de un estado guardado localmente que a veces quedaba **desactualizado** (Odoo la creía "activa" cuando MercadoLibre ya la había pausado por falta de stock): en ese caso el stock se reenviaba pero la publicación **seguía pausada**. Ahora, al confirmar el estado real contra MercadoLibre, se garantiza que vuelva a quedar activa.
3. Sigue respetando el **bloqueo manual** de stock (productos marcados como "no actualizar stock" no se tocan) y es **idempotente**: si la publicación ya estaba activa, no genera ningún cambio.

## Versión 19.0.26.79 — Al publicar, se envían a MercadoLibre las dimensiones y los impuestos del producto [#424/#474 Deco/KPI]
16 jul 2026

**Cambios:**

1. Al **publicar o actualizar** una publicación en MercadoLibre, ahora se envían automáticamente, como atributos de la publicación, el **Ancho / Alto / Largo del producto** (WIDTH/HEIGHT/LENGTH, reconstruidos como "1.2 m" desde el número + unidad) y el **IVA** e **Impuesto interno** (VALUE_ADDED_TAX / IMPORT_DUTY).
2. Como IVA e Impuesto interno suelen ser **obligatorios** para publicar, enviarlos automáticamente **evita el error de publicación** por atributo faltante (el que se veía en el ticket #474).

Con la importación (26.78) y la publicación (26.79), estos campos viajan en los dos sentidos: MercadoLibre → Odoo al importar, y Odoo → MercadoLibre al publicar.

## Versión 19.0.26.78 — Dimensiones del producto + IVA/Impuesto interno se traen de la ficha técnica de ML [#424/#474 Deco/KPI]
16 jul 2026

**Cambios:**

1. Nuevos campos en el producto (plantilla y variante), en la pestaña MercadoLibre Plantilla, que se completan solos al importar desde la **ficha técnica** de la publicación:
   - **Ancho / Alto / Largo del producto** (valor numérico + su unidad, tal como los publica MercadoLibre). Son las medidas **del producto** (por ejemplo la cortina), distintas de las dimensiones del **paquete** de envío que ya existían.
   - **IVA** y **Impuesto interno** (ej. "21 %", "0 %"). Suelen ser **obligatorios** para publicar; al traerlos automáticamente ya no hace falta cargarlos a mano.
2. Estos campos se completan tanto al **Importar** productos como con el botón **"Traer medidas"**, y MercadoLibre es la fuente autoritativa (si la publicación trae el dato, se actualiza; si no lo trae, no se borra lo que haya).

**Nota:** las medidas del producto salen de los atributos de la publicación (Ancho/Alto/Largo). Si la variación de MercadoLibre trae su propia medida se usa esa; si no, se usa la de la publicación.

## Versión 19.0.26.77 — "Traer medidas" ahora avisa qué hizo (antes parecía no hacer nada) [#485 Deco/KPI]
15 jul 2026

**Cambios:**

1. La acción **"Traer medidas"** (botón del producto y acción masiva desde la vista Lista) ahora **muestra un aviso en pantalla al terminar**, con el resultado: cuántos productos se actualizaron, cuántos se omitieron por no tener publicación vinculada, y cuántos no se pudieron leer de MercadoLibre. Antes terminaba en silencio: el proceso corría varios minutos sobre miles de productos y no informaba nada, así que desde la pantalla era **indistinguible de que no hiciera nada**.
2. Se corrigió la **acción masiva de la vista Lista**, que además descartaba el resultado: aunque el proceso corriera bien, nunca llegaba ningún aviso al usuario.
3. Si no hay ninguna cuenta de MercadoLibre conectada, o si ninguno de los productos seleccionados está vinculado a una publicación, ahora lo dice explícitamente en vez de terminar en silencio.

**Nota:** "Traer medidas" trae las medidas **del paquete de envío** (Mercado Envíos: alto/ancho/largo/peso), marca, modelo y género. No trae medidas propias del producto (por ejemplo el ancho y el largo de una cortina).


## Versión 19.0.26.73 — Errores de publicación: se muestra el NOMBRE del atributo faltante [#521 Koreautos]
11 jul 2026

**Cambios:**

1. Cuando MercadoLibre rechaza una publicación por atributos faltantes, el mensaje ahora
   muestra el **nombre real en español** del atributo además de su código técnico. Antes se
   veía "atributo obligatorio 'PART_NUMBER'"; ahora "atributo obligatorio Número de pieza
   [PART_NUMBER]". Si faltan varios (ej. Marca y Tipo de vehículo) se listan todos con su
   nombre. El nombre sale del catálogo de atributos de MercadoLibre ya importado en el sistema.

---

## Versión 19.0.26.72 — "Sugerir Categoría" mucho más rápido [#532]
10 jul 2026

**Cambios:**

1. El botón **"Sugerir Categoría"** (pestaña MercadoLibre del producto) ahora responde en 1-2s
   en vez de ~10s. Antes, al sugerir, se importaba cada categoría candidata con TODOS sus
   atributos y su árbol completo (decenas de llamadas a la API de MercadoLibre). Ahora la
   sugerencia trae sólo lo necesario para elegir (identificador + nombre) de las 3 primeras
   opciones; si la categoría ya existe en el sistema, no vuelve a consultar a ML.
2. Los **atributos completos** de la categoría se cargan al **SELECCIONARLA** (no al sugerir),
   por lo que la publicación sigue validando y enviando todo igual que antes (el pre-flight de
   atributos obligatorios no cambia).


## Versión 19.0.26.71 — Errores al publicar: ahora legibles, en español y accionables [#532]
10 jul 2026

**Cambios:**

1. Cuando MercadoLibre rechaza una publicación, el aviso que ve el usuario ahora traduce a
   **español claro y accionable** varios errores que antes salían crudos en inglés:
   - "attributes are required" / build-title → *"Faltan atributos obligatorios de la categoría.
     Completá la ficha técnica del producto (marca, modelo, código universal, etc.)…"*.
   - `[family_name]` faltante → *"Falta el Nombre de la familia (Family Name)…"*.
   - GTIN/EAN requerido o faltante → *"Debe definir el código de barras (GTIN/EAN)…"*.
   - SKU del vendedor, categoría inválida/requerida, y otras propiedades del catálogo.
2. Se mejoró la **presentación**: cuando el error llega como un único mensaje (no como lista de
   causas) —el caso típico de build-title— ahora se muestra con el mismo recuadro estilado
   (rojo si bloquea la publicación, amarillo si es advertencia), con ícono y un título claro,
   igual que la lista de causas. Antes ese caso se veía pobre y en amarillo fijo.
3. Comportamiento **defensivo**: si un mensaje no coincide con ningún patrón conocido, se
   conserva el texto original de MercadoLibre (nunca se pierde información).


## Versión 19.0.26.70 — Cancelaciones de días anteriores: el barrido ahora cubre TODA la ventana [#475]
10 jul 2026

**Cambios:**

1. El barrido que detecta y cancela solas las ventas que MercadoLibre canceló días atrás
   (sin abrir el pedido) ahora se concentra en las órdenes **en tránsito / no entregadas**,
   que son las únicas que un comprador puede cancelar. Las ya **entregadas** se excluyen
   (no son cancelables por esa vía), lo que reduce muchísimo el volumen a revisar y permite
   que el barrido cubra **toda la ventana de días** configurada, en lugar de solo un puñado
   de las más recientes (que el proceso normal ya cubría).
2. El barrido ahora recorre primero las órdenes **más viejas** de la ventana — que son
   justamente las de mayor riesgo de haber sido canceladas sin que Odoo se enterara — y deja
   para el final las más nuevas (ya cubiertas por el proceso normal).
3. Se ampliaron los valores por defecto de la ventana (15 días) y del tope por ciclo (500);
   en la práctica se ajustan por configuración según el volumen de cada cuenta.


## Versión 19.0.26.69 — "Actualizar Título": empujar solo el título de la publicación a Mercado Libre
10 jul 2026

**Cambios:**

1. **Nueva opción "Actualizar Título" en el wizard de Publicar.** Al publicar/actualizar productos en
   Mercado Libre ahora hay una casilla **Actualizar Título** (junto a Actualizar Stock / Actualizar
   Precio). Marcada, empuja **solo el título** de la/s publicación/es (`PUT /items/{id}` con
   `{ "title": ... }`), sin re-publicar el producto completo. Disponible en el wizard de producto y
   en el de plantilla. El título enviado sale del campo **ML Title** (`meli_title`) del producto; si
   está vacío se usa el nombre del producto.
2. **Reporte de error en pantalla.** Si Mercado Libre rechaza el cambio de título (p. ej. título
   > 60 caracteres, publicación con catálogo/moderación o no modificable), el wizard muestra el
   detalle del error devuelto por ML en un aviso, en lugar de fallar en silencio.

> Motivado por el cliente RPM Motos (#532), que necesitaba actualizar títulos de publicaciones desde
> Odoo. El título es un dato a nivel item (no por variación): el PUT se hace siempre contra el item padre.

## Versión 19.0.26.68 — La fecha de la orden refleja la fecha real de MercadoLibre + cancelación explícita al re-chequear estado
9 jul 2026

**Cambios:**

1. **BUG-009 — Fecha de la orden = fecha real de MercadoLibre.** Al crear/actualizar la orden de
   venta desde una orden de MercadoLibre, la **Fecha de la orden** (`date_order`) ahora toma la
   fecha de cierre de la operación en ML (o la fecha de creación como respaldo), en lugar del
   momento en que Odoo importó la orden. Las ventas dejan de "entrar con delay" con una fecha que
   no coincide con la de MercadoLibre.
2. **BUG-007 — Cancelación explícita al re-chequear estado.** El re-chequeo puntual de estado de un
   pedido (`update_order_status`), cuando MercadoLibre reporta la orden como **cancelada**, ahora
   marca la orden de venta como cancelada y dispara la cancelación con detalle (albaranes/facturas)
   en lugar de reconfirmarla. Antes reconfirmaba de forma incondicional y las sub-órdenes de un pack
   podían quedar sin cancelar.

> Corrige una regresión de sincronización: ambos arreglos vivían solo en un cliente (Dannok) y no
> estaban en el código base; ahora quedan en el source para las 4 versiones (16/17/18/19).

## Versión 19.0.26.66 — Surtido multi-almacén: se captura el depósito de origen de MercadoLibre
8 jul 2026

**Cambios:**

1. Cada línea de la orden de MercadoLibre ahora guarda el **depósito logístico de origen** que ML
   asigna al surtir (el nodo de red y la tienda que ML manda en `Item.stock` de la orden), en dos
   campos nuevos de la línea de orden: **"ML Stock Node ID"** y **"ML Stock Store ID"**. Es la base
   del **surtido multi-almacén**: permite rutear la venta al almacén/ubicación de Odoo que
   corresponde al depósito desde el que ML surte esa línea (la resolución vive en el módulo Stock,
   ver meli_oerp_stock). Sin mapeo cargado el comportamiento es idéntico al anterior (inerte).

## Versión 19.0.26.65 — Re-sync de cancelaciones ahora soporta multi-cuenta [#475]
8 jul 2026

**Cambios:**

1. El barrido que re-consulta a MercadoLibre el estado de los pedidos abiertos de días
   anteriores (para cancelarlos solos sin abrirlos uno por uno — ver 26.62) ahora puede
   trabajar **por cuenta de MercadoLibre**. El método `orders_resync_status` acepta un
   parámetro opcional de cuenta: cuando se le indica, limita el barrido a los pedidos de
   esa cuenta y usa la compañía de su configuración. Sin ese parámetro, el comportamiento
   es idéntico al anterior (mono-cuenta). Esto habilita que en instalaciones con varias
   cuentas/tiendas de MercadoLibre en un mismo Odoo, TODAS las cuentas queden cubiertas
   (el dispatcher vive en el módulo Multi-cuenta).


## Versión 19.0.26.63 — Medidas del paquete: se corrigen valores viejos equivocados al traer de MercadoLibre [#424]
8 jul 2026

**Cambios:**

1. Al importar/actualizar un producto desde MercadoLibre (y con la acción **"Traer medidas"**), las **dimensiones del paquete del vendedor** (Alto/Ancho/Largo/Peso del paquete — Mercado Envíos) ahora se **corrigen con el valor de MercadoLibre**, que es la fuente autoritativa del paquete. Antes, si un proceso viejo había dejado en esos campos la medida del *producto* en lugar de la del *paquete* (por ejemplo "100 cm", el ancho del producto, en vez de "10 cm", el del paquete), ese valor viejo equivocado se conservaba. Ahora MercadoLibre lo pisa.
2. Si MercadoLibre no informa la medida del paquete, no se borra lo cargado (no se pisa con vacío). Marca/Modelo/Género siguen respetando la carga manual (sólo se completan si están vacíos).


## Versión 19.0.26.62 — Cancelaciones de MercadoLibre que no se reflejaban solas en Odoo [#475]
8 jul 2026

**Cambios:**

1. **Las cancelaciones (y cambios de estado) de pedidos hechas en MercadoLibre ahora se reflejan solas en Odoo, aunque el pedido sea más viejo que las últimas ~50 órdenes.** Antes, el cron horario de importación sólo repasaba las órdenes más nuevas por fecha de creación; si un pedido de días atrás se cancelaba en ML, la cancelación no bajaba a Odoo hasta abrir la orden a mano. Ahora un cron dedicado ("Cron Meli Orders Status Resync", cada 30 min) re-consulta los pedidos abiertos recientes y refleja la cancelación automáticamente (con su devolución/NC según la política contable ya configurada).

2. Nuevos parámetros por compañía (Configuración ML → Automatización ML a Odoo): activar/desactivar el re-sync de estado, ventana en días hacia atrás (default 7) y tope de pedidos por ciclo (default 100) para acotar el uso de la API.


## Versión 19.0.26.61 — Stock multiwarehouse: se corrige un caso que impedía publicar stock [#425]
5 jul 2026

**Cambios:**

1. Se corrigió un error por el cual, en publicaciones con variaciones, el identificador de "producto de
   usuario" (user_product_id) se guardaba con un formato inválido y la actualización de stock por
   user-products no llegaba a intentarse. Ahora se guarda correctamente cuando es inequívoco.


## Versión 19.0.26.60 — backfill "Traer medidas": resolución de cuentas overridable (multi-cuenta real) [#424 Deco/KPI]
3 jul 2026

**Cambios:**

1. **El relleno de medidas ("Traer medidas") ahora funciona también en instalaciones con varias cuentas de
   MercadoLibre.** La resolución de "de qué cuenta leer cada publicación" se hizo **extensible**: la versión
   base sigue funcionando con una cuenta por compañía, y el módulo multi-cuenta (meli_oerp_multiple) la
   completa para recorrer las cuentas reales. Sin este cambio, en instalaciones multi-cuenta el relleno no
   encontraba credenciales y no completaba nada.


## Versión 19.0.26.59 — fix del backfill "Traer medidas": corrige el error al ejecutarlo y soporta multi-cuenta [#424 Deco/KPI]
3 jul 2026

**Cambios:**

1. **El botón "Traer medidas" / acción de lista ya no da error y funciona con varias cuentas de MercadoLibre.**
   La acción de relleno (agregada en 26.58) fallaba al ejecutarse y, en cuentas con varios vendedores de ML
   en la misma base (p. ej. 3 cuentas), intentaba leer cada publicación con el token de una sola cuenta →
   error de permisos (403). Ahora cada publicación se lee con el token de **la cuenta que realmente la
   posee** (se agrupan por cuenta para no repetir conexiones), y se completa correctamente. Sin cambios en
   el mapeo de campos (que ya estaba OK).


## Versión 19.0.26.57 — el IMPORT ML→Odoo trae las medidas del paquete y demás campos de la pestaña "MELI Plantilla" [#424 Deco/KPI]
3 jul 2026

**Cambios:**

1. **Al importar un producto desde MercadoLibre ya se completan los campos de la pestaña "MercadoLibre / Plantilla".**
   Antes, al traer un item de ML, la sección **"Dimensiones del paquete (Vendedor – Mercado Envíos)"**
   (Alto/Ancho/Largo/Peso del paquete) y los campos **Marca**, **Modelo** y **Género** quedaban vacíos —
   había que cargarlos a mano para poder **re-publicar** (Mercado Envíos exige las medidas del paquete).
   Ahora el import lee esos datos del propio item de ML y los rellena automáticamente. Si ML no informa un
   dato, **no se pisa** lo que hayas cargado a mano (es idempotente).
2. **Nuevo botón "Traer medidas" y acción masiva** para los productos **ya importados** sin estos datos:
   en la ficha del producto (pestaña MELI Plantilla) y como acción sobre la lista de productos, relee el
   item de ML de cada producto con publicación y completa los campos faltantes. Procesa de a lotes de forma
   segura: si un producto falla, el resto continúa.


## Versión 19.0.26.56 — no rotar el token de MercadoLibre en bases de prueba (neutralizadas)
1 jul 2026

**Cambios:**

1. **Las copias de prueba (staging/duplicados en Odoo.sh) ya no desconectan a producción.** Al duplicar
   la base para un entorno de test, Odoo la marca como *neutralizada*. Hasta ahora el conector seguía
   intentando **renovar el token** de MercadoLibre desde esa copia; como el token de renovación es rotativo
   (un solo uso), cada renovación desde el test **invalidaba la sesión de producción** (y viceversa),
   causando cortes intermitentes de conexión (401). Ahora una base neutralizada **nunca renueva el token**:
   el entorno de prueba sigue leyendo con el token vigente hasta que expira y luego queda desconectado
   (esperado en test), sin afectar a producción. _(Producción sin cambios de comportamiento.)_

## Versión 26.55 — cupón ML: respeta la preferencia de facturación (modo de cupón configurable) [#433]
30 jun 2026

**Cambios:**

1. **El cupón de MercadoLibre vuelve a respetar la configuración del cliente.** Una corrección previa
   (#399) forzaba el descuento del cupón sobre el producto cuando el comprador pagaba el envío completo,
   incluso con la opción de facturar-con-descuento **desactivada** — pisando la preferencia del vendedor
   (regresión #433). Ahora el tratamiento del cupón depende **solo** del modo declarado en la cuenta.

2. **Modo de facturación del cupón (tri-estado).** La antigua casilla pasa a un selector con tres modos:
   - **Precio pleno** (por defecto, equivale a la casilla desactivada): la factura se emite por el precio
     completo. Correcto cuando MercadoLibre reembolsa el cupón al vendedor (el ingreso gravado es el precio
     pleno). *Ni el producto ni el envío llevan el descuento del cupón.*
   - **Descuento en producto** (equivale a la casilla activada): el cupón se refleja como % de descuento
     sobre las líneas de producto.
   - **Línea de descuento separada** (opcional, avanzado): el cupón se imputa como línea(s) de descuento
     aparte, una por grupo de impuesto, sin tocar producto ni envío. *Requiere validación fiscal previa.*

   En todos los modos el total facturado sigue cuadrando con lo que corresponde cobrar. La migración deja a
   cada cuenta en el modo equivalente a su configuración anterior (desactivada → Precio pleno; activada →
   Descuento en producto).

---

## Versión 26.54 — alta automática de productos inexistentes al importar órdenes (sin frenar por permisos)
30 jun 2026

**Cambios:**

1. **Productos nuevos al importar una orden:** cuando llega una orden de MercadoLibre cuyo producto aún no
   existe en Odoo y la cuenta tiene activada *"Crear producto desde la orden"*, el sistema lo da de alta
   automáticamente. Si el cron operaba a nombre del *Vendedor ML* (sin permiso para crear productos), esa
   alta fallaba con un error de acceso y la orden quedaba sin importar. Ahora la creación y el vínculo del
   producto corren con **privilegios de sistema** (es parte de la integración automática), de modo que la
   orden se importa completa. Con la opción **desactivada** el comportamiento no cambia: el producto no se
   crea y la incidencia se registra en el log sin abortar el resto de la importación.

---

## Versión 26.48
17 jun 2026

**Cambios:**

1. **Refactor interno — helper `meli_confirm_ready` (sin cambio de comportamiento):** se extrajo el criterio de "venta lista para confirmar" (la condición de monto de `confirm_ml`: monto a facturar de ML vs total del pedido, con tolerancia por cupón y retenciones, con/sin envío) a un método **read-only** `meli_confirm_ready()` que devuelve `(lista, motivo)`. La confirmación automática lo consume sin cambiar su lógica ni sus mensajes. Esto permite que otros flujos (p. ej. el wizard de importación de `meli_oerp_multiple`) detecten ventas incompletas **con exactamente el mismo criterio**, sin confirmar ni modificar las ventas.

---

## Versión 26.46
15 jun 2026

**Cambios:**

1. **Host API ML de rescate (reverse proxy):** Nuevo campo de configuración (solo administrador técnico) **"Host API ML (rescate)"** que permite rutear las llamadas a MercadoLibre — y el OAuth — por un reverse proxy externo cuando la IP del servidor está bloqueada por ML. Vacío = directo a `api.mercadolibre.com` (comportamiento por defecto, sin cambios). Pensado para incidentes de IP bloqueada.

---

## Versión 26.41
11 jun 2026

**Cambios:**

1. **Devoluciones — Sin duplicar al cancelar:** Corregido el chequeo de devoluciones ya existentes (busca por `origin_returned_move_id` sobre los movimientos del picking, no al revés) y eliminada una doble llamada interna en la cancelación, que generaban pickings de devolución (IN) duplicados por cada ciclo de cron.

2. **AFIP — Códigos de responsabilidad ampliados:** El mapeo de tipo de contribuyente de ML reconoce más variantes (`RESPONSABLE INSCRIPTO`, `IVA EXENTO`, `EXENTO`, `SUJETO EXENTO`).

3. **Envíos — Línea de envío con costo en factura:** Cuando el envío tiene costo real, se restaura `qty_to_invoice` en la línea para que aparezca en la factura (el conector factura al pago, no a la entrega).

---

## Versión 26.40
10 jun 2026

**Cambios:**

1. **Envíos — Flete del comprador en órdenes pack/ME2:** En ventas tipo pack (varios ítems en un carrito), el costo de envío a cargo del comprador no viene en el pago (`payment.shipping_amount=0`) ni en la orden — vive en el envío (`/shipments/{id}/costs → receiver.cost`). Ahora el conector lo captura (`mercadolibre.shipment.shipping_receiver_cost`) y lo usa como precio de la línea de envío cuando el pago no lo trae, de modo que la factura cierra con lo que pagó el comprador (producto + envío).

---

## Versión 26.39
10 jun 2026

**Cambios (tanda fixes meli jun-2026):**

1. **Mapeo de transportistas — respeta el producto del carrier:** La línea de envío del pedido ahora usa el producto del transportista mapeado en su tabla de mapeo (antes lo pisaba con un servicio de envío autogenerado). `shipment.py _update_sale_order_shipping_info`.
2. **Etiqueta de envío — modos PDF / ZPL (zip) / ZPL (txt):** Nuevo modo `zpl_txt` que extrae el contenido ZPL del zip que entrega ML y lo guarda como `.zpl` plano (listo para impresora). Además **fix del nombre de descarga**: los binarios de etiqueta ahora llevan `filename=`, así la descarga muestra `Shipment_<id>.pdf/.zpl` en vez del tamaño (`"1.10 Kb"`).
3. **Equipo / vendedor:** `meli_fix_team` ya no resetea el equipo ni el vendedor cuando fueron seteados a mano; asigna `seller_team` aunque la cuenta no tenga compañía (guard company-less).
4. **Posición fiscal configurable:** El sistema respeta el flag `mercadolibre_set_fiscal_position` (default True). En False deja en blanco la posición fiscal de la venta. `orders.py`.
5. **Fechas placeholder de ML descartadas:** `ml_datetime` descarta las fechas placeholder de ML (año < 1970) que rompían el `write` del envío con `ValueError '1-01-01 00:00:00'`. `versions.py`.
6. **Costo de envío en la primera importación:** `_ensure_payment_shipping_amounts` completa el `shipping_amount` del pago antes de calcular la línea de envío, evitando que el envío quede en 0 en la primera importación de la orden. `orders.py`.
7. **Fechas del envío desde `shipping_option`:** Se incorporan buffering_date, schedule_limit, pay_before, pickup_promise (from/to) y desired_promised_delivery a la ficha del envío.

---

## Versión 26.29
2026-05-13

**Cambios:**

1. **Stock — Priorización por movimiento de stock:** Cuando ocurre un movimiento de stock para un producto publicado en ML, `meli_update_boms()` ahora resetea `meli_stock_update = NULL` vía SQL directo. El cron ordena por `meli_stock_update ASC NULLS FIRST` — con NULL, el producto sube al frente del queue en el primer ciclo siguiente (5-10 min). Antes, un producto synced con qty=0 quedaba al fondo de la cola y podía tardar 30+ minutos en reactivarse.

2. **Stock — `meli_stock_diagnostic()` como red de seguridad:** Nueva función que corre al final de cada ciclo de `meli_update_remote_stock`. Detecta y corrige automáticamente:
   - Items `status=paused` en ML con `virtual_available > 0` → reactiva vía `product_post_stock()`
   - Items `status=active` con `available_quantity=0` pero Odoo tiene stock → push corrección
   - `meli_available_quantity` stale cuando ML tiene qty>0 → sincroniza desde ML (SQL directo)
   - Drift de cantidades (Odoo ≠ ML) → log WARNING `MELI_STOCK_DIAG`

3. **Stock — Skip fulfillment en cron:** Productos con `meli_shipping_logistic_type='fulfillment'` ya no generan llamadas a ML API innecesarias en el cron de stock (ML no permite modificar stock de almacenes fulfillment vía API). El cron ahora hace `continue` directamente con `meli_stock_error="fulfillment"`.

4. **Órdenes — Fix `seller_discount` sobreestimado con cupón:** `amounts.seller` del endpoint `/orders/{id}/discounts` contiene el descuento total de precio de lista (precio original − precio de venta), no la contribución real del vendedor al cupón. Para evitar que `meli_amount_to_invoice` devuelva un valor menor al correcto, el descuento del vendedor se capea al `coupon_amount` cuando `(paid - seller_discount) < amount_total`.

5. **Webhooks ML — CSRF desactivado en `/meli_notify`:** Los endpoints de webhook de ML (`/meli_notify`, `/meli_notify/<login_id>`) ahora tienen `csrf=False` en el decorator. Sin este flag, Odoo rechazaba los POST de ML con 400 "No CSRF validation token provided".

6. **Billing info — Migración a API v2:** El endpoint legacy `/orders/{order_id}/billing_info` fue deprecado por ML en Q1 2026. Migrado al nuevo endpoint `/orders/billing-info/{SITE_ID}/{BILLING_INFO_ID}` con header `x-version: 2`. Incluye normalizador de formato para el nuevo schema anidado (antes UPPERCASE flat, ahora `identification.type`, `name`, `address.street_name`).

7. **Compatibilidad Odoo 19 — `_sql_constraints` obsoletos eliminados:** 23 warnings de startup eliminados. Odoo 19 emite `DeprecationWarning` por cada clase con `_sql_constraints`. Todos los modelos ya tenían `UniqueIndex`/`Constraint` como atributos de clase — el atributo era redundante.

---

## Versión 26.28
2026-05-08

**Cambios:**

1. **Cupón ML — control de descuento en factura:** El campo `coupon_amount` de MercadoLibre es un costo que ML financia al comprador — el vendedor cobra el precio completo. La lógica anterior aplicaba ese monto como descuento en las líneas del SO siempre, y calculaba el porcentaje sobre el precio base sin IVA (incorrecto). Cambios:
   - Nuevo campo de configuración `meli_coupon_discount_on_invoice` (Boolean, default=False):
     - **Desactivado (default):** factura por precio de venta completo. Si hubo descuentos incorrectos previos, se limpian automáticamente al reimportar la orden.
     - **Activado:** aplica el cupón como descuento porcentual usando el precio bruto **con IVA** como denominador (corrección del bug de cálculo).

2. **Reparar entrega — notificación de resultado (UX):** El método `meli_repair_missing_pickings()` ahora retorna una notificación Odoo con el resultado (`success` si reparó, `warning` si no encontró movimientos huérfanos).

3. **Advertencias ML — renderizado de causas anidadas:** Los errores de la API ML que devuelven `causes` como lista ahora se renderizan como alertas HTML individuales en el chatter, mostrando el detalle de cada causa aunque el mensaje principal sea un string simple.

4. **Compatibilidad Odoo 19 — `qty_done` → `quantity`:** En Odoo 19 el campo `qty_done` de `stock.move.line` fue renombrado a `quantity`. La detección ahora es automática via `hasattr`, sin hardcodear el nombre del campo.

5. **Compatibilidad Odoo 19 — view_mode f-string:** Fix en `cron_execution.py`: la variable `view_mode_tree` no se expandía en el string de la acción de ventana de CRONs.

---

## Versión 26.27
2026-05-07

**Cambios:**

1. **Protección de billing child en `_commercial_sync_from_company`:** Los contactos hijos de tipo `invoice` (billing child) cuyo padre tiene órdenes ML (`meli_buyer` o `meli_order_id`) ahora están protegidos de la sincronización fiscal automática de Odoo. Sin esta protección, Odoo sobreescribía los datos fiscales del hijo con los del padre comercial, eliminando el CUIT y tipo de responsabilidad AFIP.

2. **Propagación de `partner_invoice_id` en sub-órdenes pack:** Al confirmar una orden con sub-órdenes (packs ML), si el billing child resuelto es diferente del partner padre del buyer, se propaga `partner_invoice_id` a todas las sub-órdenes para que facturen al mismo billing child.

3. **Context flags en `_assign_picking()`:** Al llamar `_assign_picking()` durante la confirmación de la orden, se activan los flags `tracking_disable=True`, `mail_notrack=True` y `meli_skip_stock_update=True` para evitar triggers innecesarios de notificaciones y actualizaciones de stock en cada asignación individual.

---

## Versión 26.26
2026-05-05

**Cambios:**

1. **Descuento de vendedor con cupones (fix):** Cuando ML reporta un `seller_discount` grande (precio de lista vs. precio pagado) y hay un cupón, el descuento se capea al monto del cupón solo si la diferencia produciría un monto por debajo del total del SO. Resuelve el error "amount doesn't match" en órdenes con descuentos de lista + cupón.

2. **Reparación de pickings huérfanos:** Nuevo método `meli_repair_missing_pickings()`. Detecta stock moves en órdenes confirmadas sin picking asignado y los asigna a un picking existente (o crea uno). Se llama automáticamente si `confirm_ml()` produce una orden sin picking. También disponible como acción en el wizard de operaciones.

3. **API billing_info v2:** Migración al endpoint `/orders/billing-info/{SITE_ID}/{BILLING_INFO_ID}` con `x-version: 2`. La respuesta v2 se normaliza al formato legacy (claves UPPERCASE) para transparencia. Fallback automático al endpoint viejo.

4. **CSRF webhooks (fix crítico):** Los endpoints `/meli_notify` ahora tienen `csrf=False`. Sin este fix todas las notificaciones ML eran rechazadas con HTTP 400.

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
