# FEATURE (importante) — Gestión de compatibilidades de vehículos (MercadoLibre) en el connector meli

> Item estratégico del grove **meli**. Anotado 2026-07-22 a raíz de Koreautos.
> Vertical clave: **autopartes** (CO/MX). Estado: **BACKLOG / feature propuesta**. Prioridad media-alta.

## Problema
En autopartes, MercadoLibre **exige la ficha de COMPATIBILIDADES** (fitment: con qué **marca / modelo / año / versión**
de vehículo encaja la pieza). Si la publicación no las tiene, ML la deja en **`status=under_review`,
`sub_status=waiting_for_patch`**, con el **tag `incomplete_compatibilities`** — no sale plenamente activa/visible.

**El connector meli HOY NO maneja compatibilidades** (grep `compatibilit` en el source = 0 resultados). No hay
modelo, ni UI, ni push por API → **no se pueden cargar/empujar desde Odoo**; hoy sólo se cargan a mano en el editor
de MercadoLibre o por API cruda.

## Caso testigo — Koreautos (cuenta 521, CO)
- Item **C6536 / MCO4142545898** ("Pernos de Ruedas", domain `MCO-VEHICLE_WHEEL_STUDS`): `under_review /
  waiting_for_patch`, tag `incomplete_compatibilities`. Atributos COMPLETOS (marca, PART_NUMBER, dims, tipo de
  vehículo); lo único faltante = **compatibilidades** (`GET /items/{id}/compatibilities` → `products: 0`).
- Detalle en `partners/Colombia/koreautos/.roots/` + memoria de sesión `koreautos-client`.

## API de MercadoLibre (referencia)
- `GET /items/{item_id}/compatibilities` → lista `products` (vehículos compatibles cargados).
- `POST /items/{item_id}/compatibilities` → cargar vehículos (por `domain_id` de vehículo + attrs marca/modelo/año).
- Los vehículos se resuelven por el **catálogo de vehículos de ML** (marca/modelo/año/versión).

## Alcance del feature (a diseñar)
1. **Modelar** compatibilidades en Odoo: modelo/campo por `product.template` (o por binding `mercadolibre.product`)
   que liste los vehículos compatibles (marca/modelo/año/versión).
2. **UI** para cargarlas/mantenerlas (import masivo desde catálogo del proveedor sería ideal — el dato de fitment
   suele venir del fabricante).
3. **Push por API** al publicar / como "patch" a publicaciones existentes (`POST /items/{id}/compatibilities`).
4. **Enganche con REFATODO**: el batch import/refresh vive en `meli_oerp_multiple/models/connection_account.py`
   (`cron_batch_import`, ~L4465-4545, logs "REFATODO ..."). Un push masivo de compatibilidades debería integrarse ahí
   (procesar/empujar en lote), no ítem por ítem.

## Clientes a tener en cuenta
- **Koreautos** (521, autopartes CO) — caso testigo (arriba).
- **Tus Refacciones MX** (431, autopartes MX) — ✅ **CONFIRMADO 2026-08-14: SÍ tiene, y el "no se encontró" del
  22-jul era un falso negativo por mirar el repo equivocado.** No está en `ctmil/main`; está en
  **`partners/Mexico/tus-refacciones-mx/prod/main-deploy`** (el repo de producción `TusRefaccionesMX/Odoo_DB`,
  que vive en **otro org**). Dos módulos, ambos de **su propio dev Mario Alfonso Vidales Vázquez** (AGPL-3 / LGPL-3):
  - **`compatibilidad_automotriz`** v2.4.25 *"[CADP] Compatibilidad Automotriz de Productos"* (`depends: ['product']`),
    16 modelos / ~1.112 LOC: `fabricante → modelo → submodelo` + motor, litros, cilindros, tipomotor,
    tipocombustible, tipoaspiración, transmisión, tracción, carrocería, versión, nacionalidades.
    El central `compatibilidad.producto` (591 LOC) cuelga de `product.template` con **rango
    `anio_inicial`/`anio_final`** (+ `_search_anio_buscar` para buscar por año dentro del rango), `unique_compat`
    por producto+configuración, el patrón "Todos los Fabricantes/Modelos/Submodelos", y la vista
    **"Aplicaciones por producto"**. Suma **`auto.part.interchange`** (123 LOC) = cruces/equivalencias
    OEM/OES/aftermarket por número de parte, con fuente y `confidence`.
    Catálogos semilla **chicos** (12 fabricantes, 24 modelos, 19 submodelos): es el **esqueleto**, no un padrón.
  - **`compatibilidad_automotriz_finder`** v18.0.4.2.0 *"[CABP] Buscador de Productos"* — buscador por
    compatibilidad en backend **y portal web**.
  ⛔ **Límite de la referencia:** `grep -rin "meli|mercadolibre|/compatibilities"` sobre los dos módulos = **0 hits**.
  **No hay ningún puente a ML.** Es catálogo interno + buscador; nunca empuja a MercadoLibre. ⇒ sirve como
  **referencia del modelo de datos**, no como integración reusable — y es **código de su dev, no nuestro**:
  se toma como referencia de diseño, **no se copia**.
  → Ticket abierto en la 521: **#558** "Agregar funcionalidad de compatibilidades de vehículos (MercadoLibre)".

## Próximos pasos sugeridos
- Confirmar con el usuario qué tiene realmente tusrefacciones (o dónde) sobre compatibilidades.
- Para destrabar Koreautos C6536 ya: conseguir la lista de vehículos compatibles (dato del proveedor/cliente) y
  cargarla a mano en ML o por `POST /compatibilities` (piloto), mientras el feature se diseña.
- Diseñar el modelo + push (con odoo-architect / meli-keeper) e integrarlo al batch REFATODO.
