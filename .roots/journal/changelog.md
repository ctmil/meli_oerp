# meli_oerp - Changelog

> Historial de versiones y cambios orientado al cliente.

---

## Versión 16.0.26.72 — "Sugerir Categoría" mucho más rápido [#532]
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


## Versión 16.0.26.71 — Errores al publicar: ahora legibles, en español y accionables [#532]
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


## Versión 16.0.26.70 — Cancelaciones de días anteriores: el barrido ahora cubre TODA la ventana [#475]
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


## Versión 16.0.26.69 — "Actualizar Título": empujar solo el título de la publicación a Mercado Libre
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

## Versión 16.0.26.68 — La fecha de la orden refleja la fecha real de MercadoLibre + cancelación explícita al re-chequear estado
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
> (La versión 26.67 fue un arreglo específico de Odoo 18/19 —`action_create_returns_all`— y no
> aplica a esta versión; por eso 16.0 salta de 26.66 a 26.68.)

## Versión 16.0.26.66 — Surtido multi-almacén: se captura el depósito de origen de MercadoLibre
8 jul 2026

**Cambios:**

1. Cada línea de la orden de MercadoLibre ahora guarda el **depósito logístico de origen** que ML
   asigna al surtir (el nodo de red y la tienda que ML manda en `Item.stock` de la orden), en dos
   campos nuevos de la línea de orden: **"ML Stock Node ID"** y **"ML Stock Store ID"**. Es la base
   del **surtido multi-almacén**: permite rutear la venta al almacén/ubicación de Odoo que
   corresponde al depósito desde el que ML surte esa línea (la resolución vive en el módulo Stock,
   ver meli_oerp_stock). Sin mapeo cargado el comportamiento es idéntico al anterior (inerte).

## Versión 16.0.26.65 — Re-sync de cancelaciones ahora soporta multi-cuenta [#475]
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


## Versión 16.0.26.63 — Medidas del paquete: se corrigen valores viejos equivocados al traer de MercadoLibre [#424]
8 jul 2026

**Cambios:**

1. Al importar/actualizar un producto desde MercadoLibre (y con la acción **"Traer medidas"**), las **dimensiones del paquete del vendedor** (Alto/Ancho/Largo/Peso del paquete — Mercado Envíos) ahora se **corrigen con el valor de MercadoLibre**, que es la fuente autoritativa del paquete. Antes, si un proceso viejo había dejado en esos campos la medida del *producto* en lugar de la del *paquete* (por ejemplo "100 cm", el ancho del producto, en vez de "10 cm", el del paquete), ese valor viejo equivocado se conservaba. Ahora MercadoLibre lo pisa.
2. Si MercadoLibre no informa la medida del paquete, no se borra lo cargado (no se pisa con vacío). Marca/Modelo/Género siguen respetando la carga manual (sólo se completan si están vacíos).


## Versión 16.0.26.62 — Cancelaciones de MercadoLibre que no se reflejaban solas en Odoo [#475]
8 jul 2026

**Cambios:**

1. **Las cancelaciones (y cambios de estado) de pedidos hechas en MercadoLibre ahora se reflejan solas en Odoo, aunque el pedido sea más viejo que las últimas ~50 órdenes.** Antes, el cron horario de importación sólo repasaba las órdenes más nuevas por fecha de creación; si un pedido de días atrás se cancelaba en ML, la cancelación no bajaba a Odoo hasta abrir la orden a mano. Ahora un cron dedicado ("Cron Meli Orders Status Resync", cada 30 min) re-consulta los pedidos abiertos recientes y refleja la cancelación automáticamente (con su devolución/NC según la política contable ya configurada).

2. Nuevos parámetros por compañía (Configuración ML → Automatización ML a Odoo): activar/desactivar el re-sync de estado, ventana en días hacia atrás (default 7) y tope de pedidos por ciclo (default 100) para acotar el uso de la API.


## Versión 16.0.26.61 — Stock multiwarehouse: se corrige un caso que impedía publicar stock [#425]
5 jul 2026

**Cambios:**

1. Se corrigió un error por el cual, en publicaciones con variaciones, el identificador de "producto de
   usuario" (user_product_id) se guardaba con un formato inválido y la actualización de stock por
   user-products no llegaba a intentarse. Ahora se guarda correctamente cuando es inequívoco.


## Versión 16.0.26.60 — backfill "Traer medidas": resolución de cuentas overridable (multi-cuenta real) [#424 Deco/KPI]
3 jul 2026

**Cambios:**

1. **El relleno de medidas ("Traer medidas") ahora funciona también en instalaciones con varias cuentas de
   MercadoLibre.** La resolución de "de qué cuenta leer cada publicación" se hizo **extensible**: la versión
   base sigue funcionando con una cuenta por compañía, y el módulo multi-cuenta (meli_oerp_multiple) la
   completa para recorrer las cuentas reales. Sin este cambio, en instalaciones multi-cuenta el relleno no
   encontraba credenciales y no completaba nada.


## Versión 16.0.26.59 — fix del backfill "Traer medidas": corrige el error al ejecutarlo y soporta multi-cuenta [#424 Deco/KPI]
3 jul 2026

**Cambios:**

1. **El botón "Traer medidas" / acción de lista ya no da error y funciona con varias cuentas de MercadoLibre.**
   La acción de relleno (agregada en 26.58) fallaba al ejecutarse y, en cuentas con varios vendedores de ML
   en la misma base (p. ej. 3 cuentas), intentaba leer cada publicación con el token de una sola cuenta →
   error de permisos (403). Ahora cada publicación se lee con el token de **la cuenta que realmente la
   posee** (se agrupan por cuenta para no repetir conexiones), y se completa correctamente. Sin cambios en
   el mapeo de campos (que ya estaba OK).


## Versión 16.0.26.57 — el IMPORT ML→Odoo trae las medidas del paquete y demás campos de la pestaña "MELI Plantilla" [#424 Deco/KPI]
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


## Versión 16.0.26.56 — no rotar el token de MercadoLibre en bases de prueba (neutralizadas)
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

## Versión 26.46
15 jun 2026

**Cambios:**

1. **Host API ML de rescate (reverse proxy):** Nuevo campo de configuración (solo administrador técnico) **"Host API ML (rescate)"** que permite rutear las llamadas a MercadoLibre — y el OAuth — por un reverse proxy externo cuando la IP del servidor está bloqueada por ML. Vacío = directo a `api.mercadolibre.com` (comportamiento por defecto, sin cambios). Pensado para incidentes de IP bloqueada.

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
