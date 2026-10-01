# DISEÑO — Compatibilidades de vehículos (MercadoLibre) en el suite meli

> Frente ordenado por FCA el 1-oct-2026 (*"sí, integrémoslo… es el caso perfecto"*, Steel Tiger 542).
> Plan canónico: `github.claude/.roots/tasks/PLAN-2026-10-01-meli-compatibilidades-vehiculos-ml.md`.
> **Estado: PASO 1 (diseño) — read-only.** Nada de esto está implementado. Ninguna llamada de escritura a ML.
> Versión anterior de este doc (backlog del 22-jul / 14-ago): commit `df2f5c66` en `claude/atributo-no-preload-freetext-19.0`.
> Autor del diseño: meli-keeper, 1-oct-2026.

## 0. Problema (resumen; detalle histórico al final)

En autopartes ML exige la ficha de compatibilidades (marca/modelo/año/versión del vehículo). Sin ella la publicación
queda `under_review / waiting_for_patch` con tag `incomplete_compatibilities` (Koreautos 521, ticket #558: 5 testigos
así desde agosto). El suite **no** las maneja: en ML no son un atributo del item (no viajan en `attributes`), son un
recurso aparte `/items/{id}/compatibilities` — por eso el mapeo de atributos del conector nunca las tocó.
`git grep compatibilities` en `meli_oerp` origin/19.0 (61fa7b1d) = 0 hits funcionales.

---

## (a) API de ML — verificada en la documentación pública (1-oct-2026)

Fuentes leídas (bajadas el 1-oct; el sitio es SPA, el contenido viene en el HTML):
- `developers.mercadolibre.com.ar/es_ar/compatibilidades-entre-items-y-productos` — *"Última actualización 14/07/2026"*.
- `developers.mercadolibre.com.ar/es_ar/referencias-de-dominios-productos-y-atributos-para-autopartes` — *"15/06/2026"*.

⚠️ Lo que sigue es **lo que dice la doc**, no lo que medimos contra la API. Lo único medido: el dump de dominios
**exige token** (`GET /catalog/dumps/domains/MLA/compatibilities` sin token → `403 PA_UNAUTHORIZED_RESULT_FROM_POLICIES`,
igual MCO y MLM). Todo lo demás se confirma en el piloto (d).

### a.1 Sites y dominio de vehículos (el "catálogo" contra el que se compatibiliza)

| Site | Dominio de vehículos | Marca | Modelo | Año | Versión | Motor |
|---|---|---|---|---|---|---|
| **MLA** (AR), MLB, MLU | `<SITE>-CARS_AND_VANS` | `BRAND` | `MODEL` | `VEHICLE_YEAR` | `SHORT_VERSION` | `ENGINE` |
| **MCO** (CO), **MLM** (MX), MLC | `<SITE>-CARS_AND_VANS_FOR_COMPATIBILITIES` | `BRAND` | `CAR_AND_VAN_MODEL` | `YEAR` | `CAR_AND_VAN_SUBMODEL` | `CAR_AND_VAN_ENGINE` |

Secundarios/opcionales MLA: `FUEL_TYPE`, `POWER`, `VEHICLE_BODY_TYPE`, `TRANSMISSION_CONTROL_TYPE`, `TRACTION_CONTROL`,
`DOORS`… · MCO/MLM/MLC: `DRIVE_TYPE`, `CAR_AND_VAN_BODY_TYPE`, `TRANSMISSION_SPEEDS_NUMBER`, `BRAKE_ABS`…
Recurso disponible sólo en MLA, MLM, MLB, MLU, MLC y MCO.

⚠️ **Inconsistencia de la propia doc:** la tabla de referencia dice `VEHICLE_YEAR` para MLA, pero el ejemplo de
`products_families` "excepto MLM" usa `"id": "YEAR"` con `MLA-CARS_AND_VANS`. ⇒ **los ids de atributo NO se
hardcodean**: se leen de `GET /catalog_domains/{DOMAIN_ID}` por site y se cachean. El piloto lo zanja.

### a.2 Elegibilidad (¿este item admite/exige compatibilidades?)
- `GET /catalog/dumps/domains/{SITE}/compatibilities` (con token) → por dominio de autoparte: `compatible_domain_id`,
  `type` (sólo `EXTENSION` admite carga), y por categoría: `required`, `note_status`, `restrictions_status`,
  `universal_status`, `restrictions_required` (posición obligatoria).
- En el item (`GET /items/{id}`, que **el multiget REFATODO ya trae**): tags `incomplete_compatibilities`,
  `incomplete_position_compatibilities`, `pending_compatibilities` (sugerencias de ML); atributo `HAS_COMPATIBILITIES`.
- Listas de trabajo: `GET /users/{seller}/items/search?tags=incomplete_compatibilities` (y `pending_…`,
  `has_compatibilities=true`). `POST /items/compatibilities_summary` (máx. 10 items) → conteos por item.

### a.3 Resolución de vehículos — **cambió el 15-jul-2026**
- ⛔ **`POST /catalog_compatibilities/products_search/chunks` ya NO existe desde el 15/07/2026.** Ya no se pueden
  enumerar los productos-vehículo (ids `MLAnnnn`) por búsqueda. Es el cambio que define el diseño.
- ✅ Lo que queda:
  - **Top values** — `POST /catalog_domains/{DOMAIN}/attributes/{ATTR}/top_values` con
    `{"known_attributes":[{"id":"BRAND","value_id":"60249"}, …]}` → `[{id, name, metric}]`. Se encadena
    BRAND → MODEL → año → versión. Es el **traductor nombre → `value_id`**.
  - **Contar** — `POST /catalog_compatibilities/products_search/count_family_products`
    `{"domain_id":…, "attributes":[{"id":…,"value_id"|"value_name":…}]}` → `{"count": N}`. Para validar **antes**
    de escribir que una familia no excede 200 ni es 0.
  ⇒ **El vehículo se describe como FAMILIA (dominio + atributos), no como lista de productos.** Es exactamente la
  forma en que los clientes guardan su dato (marca + modelo + rango de años + versión).

### a.4 Escritura
- **`POST /items/{ITEM_ID}/compatibilities`** — agrega (no reemplaza; *"no es necesario enviar las existentes"*):
  - `products: [{id, creation_source, note?, restrictions?}]` — por producto-vehículo.
  - `products_group: [{ids:[…], creation_source, note, restrictions}]` — misma nota/posición a varios.
  - **`products_families: [{domain_id, creation_source, attributes:[{id, value_id|value_name}], note?, restrictions?}]`** ← la que usamos.
  - **`creation_source` OBLIGATORIO**: `DEFAULT` | `ITEM_SUGGESTIONS` | `NEW_VEHICLES`. Nosotros: `DEFAULT`.
  - Respuesta `{"created_compatibilities_count": N}`.
- **`PUT /items/{ITEM_ID}/compatibilities`** — NO sobrescribe: `{"create":{…}, "update":{…}, "delete":{…}}` con la
  misma estructura (products y/o products_families). Es la herramienta del **diff** (sacar lo que ya no está en Odoo).
- `DELETE /items/{id}/compatibilities` (todas) · `DELETE /items/{id}/compatibilities/{compat_id}` — **sólo** las de
  `source: SELLER`.
- `POST /items/{id}/compatibilities/exception` `{"comment": ≤255}` — categoría exige compat y el vehículo no existe en
  el catálogo ML. `GET …/exception` → `{has_exception}`.
- Copiar: `POST|PUT /items/{id}/compatibilities` con `item_to_copy:{item_id, extended_information}`.
- `universal: true` — **"no disponible en producción"** según la doc. No se diseña sobre eso.

### a.5 User Products (MLA usa UP — relevante para 542)
`POST|PUT|GET|DELETE /user-products/{UP_ID}/compatibilities` con **`domain_id` (y `category_id`) FUERA de las
listas**; `…/copy-paste`; `…/exception`. La doc no dice si lo cargado en un item se refleja en los items hermanos
del mismo UP ⇒ **pregunta del piloto**. Diseño: el push va al **item** (documentado para todos los sites); el
camino UP queda como variante a habilitar si el piloto muestra que el item no alcanza.

### a.6 Lectura
`GET /items/{id}/compatibilities?extended=true` → `products:[{id, domain_id, catalog_product_id,
catalog_product_name, source, note, restrictions, reputation}]`.
Desde el 15/07/2026 distingue **`source: SELLER`** (completo, editable) vs **`source: CATALOGO`** (las que pone ML:
`id`/`catalog_product_id` = null, sólo marca + `total`, **no se borran ni editan por API**). ⇒ Odoo **sólo gobierna
las SELLER**; las de catálogo se informan como conteo, nunca se intentan pisar.

### a.7 Límites (los que condicionan el batch)
| Límite | Valor (doc) |
|---|---|
| Productos por llamada (incluida la expansión de familias) | **200** |
| Familias por llamada | **10** |
| Rate limit compat (count / POST) | **100 rpm por APP_ID** |
| Nota | 500 caracteres, moderada |
| Posiciones por restricción / ids por posición | 4 / 4 |
| Síncrono por POST/PUT | 200; el resto **asíncrono** (el GET inmediato puede no mostrarlas todas) |
| Copia desde item con > 6.000 compat | excepción de límite |
| `compatibilities_summary` | 10 items por llamada |

---

## (b) Modelo de datos y ADAPTADOR de fuentes

### b.1 Decisión: modelo PROPIO y fino en el suite; CADP y Studio entran como FUENTES
**No se instala CADP como modelo del suite.** Razones (EVAL-2026-09-25): no instala de cero (D1–D4 + `post_init_hook`
con firma vieja), AGPL de un tercero, 100 % español sin `.po`, sin multi-compañía, y **su catálogo embebido es una semilla
de 55 vehículos** — el catálogo que importa acá es **el de ML** (value_ids), que ningún cliente tiene. Lo que sí se toma
de CADP es la **forma** del dato (fabricante → modelo → submodelo + rango `anio_inicial/anio_final` + motor), que
coincide con la del Studio de 542 y con la familia de ML. ⇒ Una **línea canónica** de fitment por nombre, y la
resolución a ids de ML como paso separado y cacheado.

Propuesta de empaquetado (**decisión de FCA**): módulo nuevo **`meli_oerp_compat`** (`depends: meli_oerp`; engancha
con `meli_oerp_multiple` si está), para que el suite base no cargue modelos de autopartes en clientes que no los usan.
Numeración: entra al build de flota (`XX` único del suite) en 16/17/18/19 cuando se implemente; **19.0 primero**.

### b.2 Modelos

**`meli.compat.line`** — línea canónica (lo que el cliente sabe), por `product.template`
| Campo | Tipo | Nota |
|---|---|---|
| `product_tmpl_id` | m2o product.template | |
| `brand_name`, `model_name` | char | obligatorios |
| `year_from`, `year_to` | int | `year_to` vacío = "en adelante" (hasta el último año que devuelva top_values) |
| `version_names` | char (lista `;`) | opcional → `SHORT_VERSION` / `CAR_AND_VAN_SUBMODEL` |
| `engine_name` | char | opcional → `ENGINE` / `CAR_AND_VAN_ENGINE` |
| `all_vehicles` | bool | "compatible con todos" (Studio 542, "Todos los fabricantes" de CADP) — **no se empuja** (universal no está en prod); se reporta |
| `note` | char(500) | → `note` de la familia |
| `position_value_ids` | char | opcional; requerido si la categoría tiene `restrictions_required` |
| `source_model`, `source_res_id` | char/int | trazabilidad al registro de origen (Studio / CADP) |
| `state` | selection | `draft` → `resolved` / `ambiguous` / `not_found` / `too_wide` |
| `family_ids` | o2m `meli.compat.family` | resultado de la resolución |

**`meli.compat.family`** — familia ML resuelta (lo que se manda)
`line_id`, `site_id`, `domain_id`, `attributes_json` (`[{id, value_id}]`), `year` (una familia por año),
`ml_count` (de `count_family_products`), `signature` (hash estable de domain+attributes → clave del diff).

**`meli.compat.value`** — cache de top_values (evita repetir llamadas; 100 rpm)
`site_id`, `domain_id`, `attribute_id`, `known_key` (hash de los known_attributes), `value_id`, `name`,
`name_norm` (casefold + sin acentos + espacios colapsados), `metric`, `fetched_at`.

**En el binding** (`mercadolibre.product` / `product.product` sin multiple):
`meli_compat_state` (`none|pending|synced|partial|error|exception`), `meli_compat_signature` (hash del set enviado),
`meli_compat_seller_count`, `meli_compat_catalog_count` (de `source: CATALOGO`), `meli_compat_ml_tag`
(`incomplete` / `incomplete_position` / `pending` / `has`), `meli_compat_last_sync`, `meli_compat_last_error`.

### b.3 Adaptador de fuentes
`meli.compat.source` (AbstractModel) con un solo contrato:
`_meli_compat_read(product_tmpl) -> [ {brand_name, model_name, year_from, year_to, version_names, engine_name,
all_vehicles, note, source_model, source_res_id} ]`. Se elige por configuración de la cuenta
(`mercadolibre_compat_source`: `native | custom_model | cadp`). La sincronización fuente → `meli.compat.line` es
**idempotente** por (`source_model`, `source_res_id`) y nunca escribe en la fuente.

- **`native`** — las líneas se cargan a mano en Odoo (Koreautos 521, que no tiene dato propio).
- **`custom_model`** (Studio de **542**) — **no hardcodeado a 542**: la config guarda el modelo y el mapeo de campos
  (`ir.model.fields`). Mapeo de 542 (`x_studio_compat_modelo_vehiculo_producto`, 1582 reg. / 1355 productos):
  `x_studio_producto_padre`→template · `x_studio_marca_vehiculo_id.name`→brand · `x_studio_modelo_vehiculo_id.name`→model ·
  `x_studio_anio_desde/hasta`→years · `x_studio_version_ids.mapped('name')`→versions · `x_studio_motor_ids`→engine
  (si hay varios: una línea por motor) · `x_studio_compatible_con_todos`→all_vehicles. `x_studio_traccion_ids` /
  `x_studio_cabina_ids` → **no se mandan en v1** (sólo `TRACTION_CONTROL` existe en MLA como opcional; cabina no tiene
  atributo directo); quedan en `note` si el cliente lo pide.
- **`cadp`** (TusRefacciones **431**) — sólo si `'compatibilidad.producto' in env` (no depende del módulo):
  `fabricante_id/modelo_id/submodelo_id.name`, `anio_inicial/anio_final` (selection en string → int),
  `litros_id`/`tipo_motor_id` → engine. "Todos los Fabricantes/Modelos/Submodelos" → se omite ese atributo de la familia
  (más ancha) y la guarda de `count ≤ 200` decide.

### b.4 Resolución línea → familias (paso aparte, cacheado, sin escritura en ML)
1. Por línea y por año del rango: BRAND por `top_values` → MODEL (known BRAND) → año (known BRAND+MODEL) → versión.
2. **Match exacto sobre `name_norm`.** Sin fuzzy automático: 0 coincidencias → `not_found`; >1 → `ambiguous`.
   Ambas se reportan **como lista** (línea, producto, qué nombre no matcheó, candidatos), nunca se empujan a medias.
3. `count_family_products` por familia: `0` → `not_found`; `>200` → se agrega versión/motor o se marca `too_wide`.
4. Agrupado para el envío: lotes de **≤10 familias** con **Σcount ≤200** por POST.
Costo: la cache hace que BRAND/MODEL se pidan una vez por cuenta; el resto escala con modelos distintos, no con productos.

---

## (c) Dónde se engancha el push

Regla que manda (incidente Shoppy 502, 23-sep): **ninguna llamada de red extra dentro de la transacción de publicar**.
Por eso el push de compat **no** se hace en línea con el `POST /items`; se marca y lo ejecuta un proceso propio.

1. **Al publicar** — `meli_oerp_multiple/models/product.py` `_product_post` (origin/19.0 244baf8), dentro de
   `if "id" in rjson:` justo después del `PUT /items/{id}/description` (~L3502-3512, donde ya existe el patrón
   `otros_errores`): **sólo** `binding.meli_compat_state = 'pending'` si el template tiene líneas `resolved`.
   Equivalente en `meli_oerp/models/product.py` `_product_post` (61fa7b1d, bloque `if "id" in rjson:` ~L4975) para
   instalaciones sin multiple. Un fallo de compat **nunca** revierte una publicación ya creada.
2. **Patch puntual** (botones en el binding / producto): *Leer compatibilidades* (GET extended → contadores y tag) y
   *Enviar compatibilidades* (diff + POST/PUT de ese item). Es el instrumento del piloto.
3. **Masivo** — `meli_oerp_multiple/models/connection_account.py`:
   - **Lectura gratis en REFATODO:** `cron_batch_import_products` (L4617) ya baja cada item por multiget
     (`fetch_meli_products_multiget`, L6375; pre-carga ~L4900-4940). De ese JSON se copian al binding los tags
     `*_compatibilities` y `HAS_COMPATIBILITIES` → **0 llamadas extra**, y queda la lista de trabajo real.
   - **Escritura en un cron hermano `cron_batch_compat_push`**, NO dentro de `cron_batch_import_products`: mismo
     patrón REFATODO (offset persistente, `batch_size` de config, commit cada N), pero **secuencial y con throttle a
     ≤100 rpm por APP_ID** (el import usa 5 threads; acá no). Toma bindings `pending` ordenados con los
     `incomplete_compatibilities` primero. Cada item: GET → diff por `signature` → `PUT {create, delete}` (o POST si
     no tenía) → GET de verificación → estado.
   - Lote con **techo declarado** (`max_items_per_run`) y **corte automático**: si en una corrida la tasa de error
     supera el umbral (p.ej. 2 de 10), el cron se desactiva solo y lo dice en el log y en la cuenta.

Idempotencia: el set enviado se guarda como `signature`; si no cambió, no se llama. Las compat `source: CATALOGO`
no entran al diff. ⚠️ Qué hace ML ante un re-POST de una familia ya cargada (duplica / ignora / 400) **no está en la
doc** → se mide en el piloto antes de decidir POST vs PUT como camino por defecto.

---

## (d) Piloto de UNA publicación y criterio de corte

**Cuenta propuesta: 542 Steel Tiger (MLA)** — es la única con el dato ya cargado (Studio). Koreautos 521 es el que más
lo necesita, pero no tiene la lista de vehículos: entra después con la fuente `native`.
**Medido el 1-oct (snapshot de 184 items MLA de 542 tomado por la sesión de 542):** 8 items ya tienen
`HAS_COMPATIBILITIES` (cargadas en ML por ellos; cubre cárter, protector intercooler, perno). ⇒ **el item piloto tiene
que arrancar con 0 compat**, para que el rollback (`DELETE` de las SELLER) no borre trabajo del cliente.

**Prerequisitos (hoy NO están):** acceso a la instancia/token de 542 (la cuenta figura *disconnected*; QA-UAT con
token de producción apagado hasta el corte), OK de FCA para una escritura en una publicación real, y aviso al cliente
por el canal de la sesión de 542 (no por este frente).

| Paso | Qué | Escribe en ML |
|---|---|---|
| P0 | `GET /catalog/dumps/domains/MLA/compatibilities` + `GET /items/{id}` del candidato: dominio/categoría elegible (`type EXTENSION`), `required`, `restrictions_required`. `GET /catalog_domains/MLA-CARS_AND_VANS` → ids reales de atributo (YEAR vs VEHICLE_YEAR). `GET …/compatibilities` = 0. | no |
| P1 | Dry-run del adaptador `custom_model` sobre ese producto: líneas → top_values → familias → `count_family_products`. Salida = **la lista** de familias con su count. | no |
| P2 | **Un** `POST /items/{id}/compatibilities` con esas familias (`creation_source: DEFAULT`). `GET ?extended=true` inmediato y a los 15 min (asíncrono >200). | **sí, 1 llamada** |
| P3 | Re-POST idéntico (¿duplica?) y `PUT {"delete": …}` de una familia → GET. Deja el item en el estado correcto. | sí, 2 llamadas |

Criterio para elegir el item: activo y de bajo tráfico, categoría con `required` o al menos
habilitada, **una sola línea** de Studio simple (una marca, un modelo, rango corto, sin versión).
⚠️ Muchos de sus productos (enganches, estribos) **puede que no estén en dominios con compat** — P0 lo dice; si el
candidato no es elegible se elige otro, no se fuerza.

**Terminado (OK del piloto):** P1 resuelve el 100 % de las líneas del item sin `ambiguous/not_found`;
`created_compatibilities_count` = Σ counts de P1; el GET lista esas familias con `source: SELLER`; el item no cambia de
`status` ni recibe moderación en 24 h; P3 deja conocido el comportamiento de re-POST.

**Corte (se frena y no se pasa al lote):** cualquier línea que no resuelva sin ambigüedad (no se empuja parcial);
count creado ≠ esperado; 4xx no documentado; cambio de estado/moderación del item; aparición de `reputation` RED en
alguna compat. **Rollback:** `DELETE /items/{id}/compatibilities` (sólo afecta SELLER; el item arrancó en 0).

**Recién con el piloto OK (paso 3 del PLAN):** lote con techo — 10 items, revisar; luego 50 — siempre con la lista de
no-resueltos entregada como lista, y el cron con su corte automático.

### Decisiones abiertas para FCA
1. Módulo nuevo `meli_oerp_compat` vs. dentro de `meli_oerp` (recomendado: módulo nuevo).
2. CADP: sólo como **fuente** leída por el adaptador (recomendado) vs. portarlo al suite (frente aparte, EVAL §4).
3. Cuenta del piloto: 542 (recomendado, tiene dato) vs. 521 (más urgente, sin dato).

---

## Anexo — historia (del doc del 22-jul / 14-ago)
- **Koreautos 521 (CO)**: C6536 `MCO4142545898` (`MCO-VEHICLE_WHEEL_STUDS`), C9987 `MCO4169134308`, C6310
  `MCO4184939182`, C97128 `MCO4184946778`, C55103 `MCO2045986615` — los 5 `under_review / waiting_for_patch`,
  `incomplete_compatibilities`, `GET …/compatibilities → products: 0` (medido 12-ago). Ticket #558.
- **TusRefacciones 431 (MX)**: `compatibilidad_automotriz` (CADP) + `_finder` de Mario Vidales, en
  `TusRefaccionesMX/Odoo_DB` (otro org), **0 hits** de meli/mercadolibre/compatibilities: catálogo interno + buscador,
  sin puente a ML. Evaluación completa: `github.claude/.roots/tasks/EVAL-2026-09-25-modulo-compatibilidad-automotriz-431.md`.
  Mario dio OK para usarlo. El "no tiene nada" del 22-jul fue un falso negativo (se miró `ctmil/main`).
- **Steel Tiger 542 (AR)**: compat en Studio `x_studio_compat_modelo_vehiculo_producto` (1582 reg. / 1355 productos),
  ticket #648 pregunta si están al día y cómo las cargan hoy en ML.
