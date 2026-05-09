<!-- CANONICAL: https://github.com/ctmil/roots_seed/blob/main/roots_seed.md -->
<!-- COPIA distribuida — módulo self-contained. -->
<!-- Cambios permanentes: editar canonical y re-distribuir. -->
<!-- Cambios experimentales: nota al pie de este archivo. -->

# Roots Seed - Agentic Memory Structure

> Plantilla maestra para crear estructura de documentación y memoria de desarrollo. Este archivo define los estándares de formato, estilo y protocolos de poblado.

**Versión:** 1.5

**Changelog:**
- **1.5** (30 Abril 2026) — Nueva sección "Modos de trabajo" con dos modos: **client branch** (`.roots/{version}.{client}/`) y **source** (`.roots/{module}/`). El modo se pregunta al usuario al procesar el seed por primera vez y se persiste en `_meta.json.working_mode`. Actualizada "Estructura Base" con ambos layouts. `on-seed-process` ampliado con paso 0 de detección de modo. Nuevo protocolo de merge entre namespaces de distintos clientes/branches. `_meta.json` extendido con campos `working_mode`, `odoo_version`, `repo`.
- **1.4** (24 Abril 2026) — Nueva carpeta `workbench/` para materiales de referencia del usuario. Nueva sección "Sync con canonical upstream (ctmil/roots_seed)" con protocolo de comparación de versiones y reglas de contribución. Nueva sección "Integración con CLAUDE.md y Claude Code (.claude/)" con jerarquía de contexto, reglas de no-duplicación, template de CLAUDE.md, y tabla de compatibilidad futura. Nuevo hook `on-seed-process.md` que consolida bootstrap completo: sync upstream, distribución, verificación CLAUDE.md, y creación de workbench. `session-start` ampliado para listar `workbench/` al inicio.
- **1.3** (18 Abril 2026) — Regla de distribución del seed dentro de cada `.roots/`. Cada módulo/proyecto lleva una **copia local** del seed que lo generó, así es self-contained y reprocesable aunque se extraiga a otro repo. Nuevo hook `on-seed-update` para re-distribuir al canonical bumpear versión. `session-start` ahora compara copia local vs canonical y avisa si están desincronizadas.
- **1.2** (18 Abril 2026) — Incorporados tres protocolos al seed, tool-agnostic (aplicables a cualquier asistente de IA o desarrollador humano):
  - Hook `on-topic-shift`: al cambiar de foco mid-sesión a un archivo/sistema no cubierto por el bootstrap, re-escanear `.roots/docs/` antes de pedir aclaraciones o decidir.
  - Hook `on-task-done`: al completar cada tarea individual y antes de reportarla, actualizar mínimo `tasks/todo.md` + `tasks/tasks.md` + `docs/commits.md`. Condicionalmente `errors-log.md`, `fixes-log.md`, `decisions.md`, `notes.md`, `glossary.md`, `migrations.md`.
  - `session-start` ampliado: chequeo de versión del seed contra memoria del agente, chequeo de git state (`git branch --show-current`, `git log`, `git status`) vs `_meta.json.active_branch`, aviso al humano si está desincronizado, lectura de `notes.md` y design docs del feature en curso.
- **1.1** — Versión base.

---

## Concepto

La carpeta `.roots/` funciona como **memoria persistente** del proyecto, organizada para:
- Documentar decisiones y progreso
- Mantener logs de errores y fixes
- Registrar ideas y reflexiones
- Trackear tareas pendientes
- Definir skills y workflows reutilizables por módulo

Esta estructura está diseñada para ser usada por **agentes de IA** y **desarrolladores humanos** por igual.

---

## Modos de trabajo (obligatorio preguntar)

**Regla:** al procesar el seed por primera vez en un repo, el agente **DEBE** preguntar al usuario en qué modo trabaja. El modo determina cómo se estructura el namespace dentro de `.roots/` y cómo se comportan los merges.

### Los dos modos

| Modo | Namespace | Cuándo usar | Ejemplo |
|------|-----------|-------------|---------|
| **Client branch** | `.roots/{version}.{client}/` | Trabajando en un branch de cliente específico que luego se mergea al source | `.roots/19.0.tecnolosys/` |
| **Source (full history)** | `.roots/{module}/` | Trabajando en el branch principal del módulo (source of truth) | `.roots/meli_oerp/` |

### Modo Client Branch

El desarrollador trabaja en un branch derivado del source, adaptando y configurando para un cliente específico. El namespace aísla la historia de ese cliente.

**Estructura:**
```
.roots/
└── {version}.{client}/
    ├── _meta.json
    ├── roots_seed.md
    ├── {module_a}/
    │   ├── context.md
    │   ├── journal/
    │   ├── debug/
    │   └── ...
    └── {module_b}/
        └── ...
```

**Características:**
- El namespace `{version}.{client}` identifica la versión del framework (ej: `19.0`) y el cliente/repo (ej: `tecnolosys`)
- Múltiples clientes pueden coexistir: `.roots/19.0.cliente_a/`, `.roots/19.0.cliente_b/`
- Al mergear al source, cada cliente trae su `.roots/` sin pisar el de otros
- `_meta.json` incluye `"working_mode": "client"`, `"odoo_version": "19.0"`, `"repo": "tecnolosys"`

**Cuándo se usa:**
- Branches de implementación para clientes específicos
- Forks con customizaciones
- Branches de testing/staging que capturan contexto del entorno

### Modo Source (Full History)

El desarrollador trabaja directamente en el source del módulo. Es la fuente de verdad.

**Estructura:**
```
.roots/
├── _meta.json
├── roots_seed.md
├── {module_a}/
│   ├── context.md
│   ├── journal/
│   ├── debug/
│   └── ...
└── {module_b}/
    └── ...
```

**Características:**
- Sin namespace extra — los módulos van directamente bajo `.roots/`
- Es el `.roots/` canónico del proyecto
- `_meta.json` incluye `"working_mode": "source"`

**Cuándo se usa:**
- Branch principal de desarrollo (ej: `19.0`, `main`)
- Repositorio canónico del módulo
- Mantenimiento del source sin contexto de cliente

### Pregunta obligatoria al procesar el seed

Al ejecutar `on-seed-process` por primera vez (bootstrap), el agente debe preguntar:

```
¿En qué modo estás trabajando?

1. Client branch — Estoy en un branch de un cliente específico
   (ej: branch 19.0-tecnolosys, fork de cliente)
   → Se creará .roots/{version}.{client}/ con namespace aislado

2. Source / full history — Estoy en el branch principal del módulo
   (ej: branch 19.0, main)
   → Se creará .roots/{module}/ directamente

Si elegís (1), también se preguntará:
  - Versión del framework (ej: 19.0)
  - Nombre del cliente/repo (ej: tecnolosys)
```

La respuesta se persiste en `_meta.json` como `working_mode` y **no se vuelve a preguntar** en sesiones posteriores.

### Merge entre modos

| Escenario | Comportamiento |
|-----------|----------------|
| Client A → Source | `.roots/{version}.{client_a}/` coexiste con `.roots/{module}/` — no se pisan |
| Client A + Client B | `.roots/{version}.{client_a}/` y `.roots/{version}.{client_b}/` coexisten sin conflicto |
| Client → Client (mismo namespace) | Git merge estándar — los archivos append-only (diary, errors-log) se resuelven naturalmente |
| Source → Client | El client hereda el `.roots/{module}/` del source como referencia read-only |

**Regla de merge:** al detectar múltiples namespaces en `.roots/`, **no consolidar automáticamente**. Cada namespace es una historia independiente. Si el usuario quiere consolidar (ej: cerrar un client branch y llevar lo aprendido al source), debe ser explícito:

```
"Consolidar .roots/19.0.tecnolosys/ → .roots/meli_oerp/"
```

El agente entonces:
1. Lee ambos `.roots/`
2. Propone qué migrar (decisions, patterns, glossary son buenos candidatos; diary y errors-log son contextuales)
3. El usuario aprueba item por item
4. Se mergea el contenido seleccionado
5. El namespace del client puede archivarse o eliminarse

### _meta.json extendido

```json
{
  "seed_version": "1.5",
  "created_at": "2026-04-30T00:00:00",
  "working_mode": "client",
  "odoo_version": "19.0",
  "repo": "tecnolosys",
  "project": "19.0.tecnolosys",
  "modules": ["meli_oerp", "meli_oerp_multiple", "meli_oerp_stock"]
}
```

| Campo | Modo client | Modo source |
|-------|-------------|-------------|
| `working_mode` | `"client"` | `"source"` |
| `odoo_version` | Versión del framework | Versión del framework |
| `repo` | Nombre del cliente/repo | Nombre del proyecto |
| `project` | `"{version}.{client}"` | Nombre del proyecto |
| `modules` | Lista de módulos | Lista de módulos |

---

## Distribución del seed (obligatorio)

**Regla:** cada `.roots/` lleva una copia del seed que lo generó, como `.roots/roots_seed.md`. No es opcional — es el mecanismo que hace al módulo self-contained y reprocesable.

### Por qué

1. **Self-contained:** si el módulo se extrae a otro repo, el seed viaja con él. Cualquier AI/humano que abra el módulo aislado tiene la spec para interpretar y mantener el `.roots/`.
2. **Reprocesable:** ante duda sobre convenciones, el agente puede releer el seed local y reaplicar sin depender del canonical (que puede haberse movido o no estar accesible).
3. **Versionable:** la copia local refleja con qué versión del seed se generó este `.roots/`. Permite detectar desync y migrar convenciones cuando el canonical evoluciona.
4. **Auditable:** diff entre copia local y canonical = delta pendiente de aplicar al módulo.

### Dónde vive el canonical

El canonical del seed vive en el módulo que lo mantiene. En este repo:

```
odoo_moldeo_roots/roots_seed.md   ← canonical (editable)
```

Toda copia distribuida lleva el header:

```html
<!-- CANONICAL: odoo_moldeo_roots/roots_seed.md -->
<!-- Esto es una COPIA distribuida del seed para que el módulo sea self-contained. -->
<!-- Para cambios permanentes: editar el canonical y re-distribuir a todos los .roots/. -->
<!-- Para cambios locales experimentales: agregar nota al pie de este archivo. -->
```

### Cuándo re-distribuir

- **Al crear un `.roots/` nuevo** → copiar el canonical con header (parte del bootstrap del módulo).
- **Al bumpear la versión del canonical** → ejecutar `hooks/on-seed-update.md` → re-distribuir a todas las copias del repo.
- **Al traer un módulo externo que ya tiene `.roots/`** → comparar seed embebido vs canonical, resolver delta.

### Comando de distribución (one-shot, tool-agnostic)

```bash
SEED="odoo_moldeo_roots/roots_seed.md"  # ajustar según repo
HEADER='<!-- CANONICAL: '"$SEED"' -->
<!-- Esto es una COPIA distribuida del seed para que el módulo sea self-contained. -->
<!-- Para cambios permanentes: editar el canonical y re-distribuir a todos los .roots/. -->
<!-- Para cambios locales experimentales: agregar nota al pie de este archivo. -->

'
find . -type d -name ".roots" -not -path "*/node_modules/*" | while read -r dir; do
    { printf '%s' "$HEADER"; cat "$SEED"; } > "$dir/roots_seed.md"
done
```

---

## Workbench — Materiales de referencia

**Regla:** cada `.roots/{module}/` incluye una carpeta `workbench/` como espacio libre para materiales de referencia que el usuario comparte durante el trabajo.

### Qué va en workbench/

- Imágenes, screenshots, mockups
- PDFs, documentos de análisis
- Videos o links a videos
- Datasets de ejemplo, CSVs
- Archivos de terceros para estudio
- Cualquier material que el usuario pase como referencia

### Reglas

1. **El usuario es quien llena el workbench** — el agente no inventa contenido aquí; sólo lo consulta.
2. **El agente DEBE revisar `workbench/`** al inicio de sesión (ver `session-start`) y al cambiar de tema (ver `on-topic-shift`). Si hay archivos nuevos, leerlos o mencionar su existencia.
3. **No hay formato obligatorio** — es un espacio libre, no requiere estructura interna.
4. **Los archivos pueden ser temporales** — el usuario puede borrar materiales obsoletos sin consecuencias.
5. **No se redistribuye** — a diferencia del seed, el contenido del workbench es local al módulo y no se copia entre `.roots/`.
6. **Si un material inspira una decisión** → referenciar en `design/decisions.md` (ej: "ver `workbench/mockup-v3.png`").
7. **Gitignore selectivo** — archivos pesados (videos, datasets grandes) pueden agregarse a `.gitignore` del módulo; los livianos (screenshots, notas) se commitean.

---

## Sync con canonical upstream (ctmil/roots_seed)

**Regla:** el canonical del seed se publica como copia open-source en:

```
https://github.com/ctmil/roots_seed/blob/main/roots_seed.md
```

Este upstream público es la **referencia de paridad**. El canonical del repo privado (`odoo_moldeo_roots/roots_seed.md`) puede tener extensiones propias, pero las convenciones core deben mantenerse alineadas con el upstream.

### Jerarquía de canonicals

| Nivel | Ubicación | Rol |
|-------|-----------|-----|
| **Upstream público** | `github.com/ctmil/roots_seed/main/roots_seed.md` | Referencia open-source, convenciones core |
| **Canonical del repo** | `odoo_moldeo_roots/roots_seed.md` | Fuente de verdad local, puede extender el upstream |
| **Copias distribuidas** | `.roots/roots_seed.md` (cada módulo) | Self-contained, refleja el canonical del repo |

### Protocolo de sync al procesar el seed

Cada vez que un agente o humano **procesa el seed** (bootstrap, session-start, bump de versión), debe:

1. **Obtener la versión upstream** — fetch de `https://raw.githubusercontent.com/ctmil/roots_seed/main/roots_seed.md`, leer campo `**Versión:**`.
2. **Comparar con la versión del canonical local** — leer `odoo_moldeo_roots/roots_seed.md`, mismo campo.
3. **Resolver según el caso:**

| Caso | Acción |
|------|--------|
| Local < Upstream | Revisar changelog del upstream, aplicar cambios nuevos al canonical local, bumpear versión, re-distribuir |
| Local = Upstream | No action — en paridad |
| Local > Upstream | El canonical local tiene extensiones propias. Evaluar si las extensiones deben subir al upstream (PR a `ctmil/roots_seed`) |
| Diff sin cambio de versión | Cambio cosmético o local. Documentar en `journal/notes.md` |

4. **Si hay delta sustancial** → avisar al humano antes de aplicar. No mergear a ciegas.
5. **Si el upstream no es accesible** (offline, rate limit) → continuar con el canonical local, anotar en `journal/notes.md` que no se pudo verificar.

### Cuándo sincronizar con el upstream

- **Al hacer bootstrap de un `.roots/` nuevo** → verificar que el canonical local está al día con el upstream.
- **Al bumpear la versión del canonical local** → evaluar si el bump incluye cosas que deben subir al upstream público.
- **Al inicio de sesión** (opcional, no bloqueante) → si el agente tiene acceso a internet, hacer un check rápido. No bloquear la sesión si falla.

### Contribuir al upstream

Si el canonical local evoluciona con convenciones útiles para la comunidad:

1. Preparar el diff entre canonical local y upstream.
2. Separar extensiones privadas (específicas del repo) de mejoras genéricas.
3. Las mejoras genéricas → PR a `github.com/ctmil/roots_seed`.
4. Las extensiones privadas → quedan sólo en el canonical local.

---

## Integración con CLAUDE.md y Claude Code (.claude/)

**Principio:** `.roots/` es tool-agnostic — lo debe poder leer cualquier agente o humano. `CLAUDE.md` y `.claude/` son específicos de Claude Code. Cuando ambos conviven, `.roots/` es la **fuente de verdad** y `CLAUDE.md`/`.claude/` son **bridges**.

### Jerarquía de contexto

| Archivo | Alcance | Quién lo lee | Rol |
|---------|---------|--------------|-----|
| `CLAUDE.md` (raíz) | Proyecto global | Claude Code (auto-carga) | Índice y directivas top-level |
| `.roots/{module}/context.md` | Módulo específico | Cualquier agente/humano | Detalle del módulo |
| `.claude/` (raíz) | Config Claude Code | Solo Claude Code | Bridge opcional — settings, hooks json |

### Reglas de no-duplicación

1. **`CLAUDE.md` indexa, no repite.** Si existe `.roots/`, `CLAUDE.md` lista los módulos activos y apunta a cada `.roots/{module}/context.md`. No copia el contenido de context.md ni de otros archivos de `.roots/`.
2. **`.claude/hooks/*.json` puede hacer bridge.** Los hooks de Claude Code pueden disparar lectura/ejecución de los protocolos tool-agnostic en `.roots/*/hooks/*.md`. La lógica vive en `.roots/`, el trigger en `.claude/`.
3. **Sin `.roots/`, `CLAUDE.md` es autónomo.** Si un proyecto no tiene `.roots/` (es legacy o simple), `CLAUDE.md` documenta stack y directivas directamente. No se fuerza la creación de `.roots/` en proyectos que no lo necesitan.
4. **Con `.roots/`, `CLAUDE.md` es ligero.** Sólo contiene: (a) directivas globales que aplican a todo el proyecto (ej: reglas de routing Odoo), (b) índice de módulos con `.roots/`, (c) referencia al seed.

### Regla al procesar el seed (obligatoria)

Al hacer bootstrap o bump del seed, verificar `CLAUDE.md`:

| Situación | Acción |
|-----------|--------|
| No existe `CLAUDE.md` | Crear con template mínimo (ver abajo) |
| Existe pero no lista módulos con `.roots/` | Agregar sección de índice de módulos |
| Existe y lista módulos | Verificar que los módulos listados coinciden con los `.roots/` actuales — agregar nuevos, marcar removidos |
| Existe `.claude/` | Verificar que sus hooks referencian `.roots/` sin duplicar lógica |

### Template mínimo de CLAUDE.md

Cuando se crea `CLAUDE.md` desde el seed, usar este template como base:

```markdown
# {Proyecto} - Development Directives

## Módulos con memoria persistente (.roots/)

| Módulo | Context | Estado |
|--------|---------|--------|
| `{module_a}` | [context.md](.roots/{module_a}/context.md) | Activo |
| `{module_b}` | [context.md](.roots/{module_b}/context.md) | Activo |

## Seed

**Versión:** {X.Y}
**Canonical:** `odoo_moldeo_roots/roots_seed.md`
**Upstream:** `github.com/ctmil/roots_seed`

## Directivas globales del proyecto

(Reglas que aplican a todo el proyecto, no a un módulo específico.
Ejemplo: convenciones de routing Odoo multi-website, estándares de JS, etc.)
```

### Compatibilidad futura

Problemas anticipados y cómo resolverlos:

| Problema | Resolución |
|----------|------------|
| Otro agente (Cursor, Copilot) ignora `CLAUDE.md` | No importa — `.roots/` es self-contained y tool-agnostic, el otro agente lo lee directamente |
| Claude Code ignora `.roots/` | `CLAUDE.md` apunta a `.roots/` — Claude Code sigue los links. Alternativamente, un hook `session-start` en `.claude/hooks/` puede forzar la lectura |
| Módulo extraído a otro repo pierde `CLAUDE.md` | El módulo lleva su `.roots/` con seed embebido — es reprocesable sin `CLAUDE.md`. El nuevo repo puede generar su propio `CLAUDE.md` desde el seed |
| `CLAUDE.md` crece demasiado | Señal de que contenido debería migrar a `.roots/`. `CLAUDE.md` debe mantenerse como índice ligero |

---

## Estructura Base

La estructura varía según el modo de trabajo (ver § "Modos de trabajo"):

**Modo Source:**
```
.roots/
├── _meta.json
├── roots_seed.md
└── {module_name}/
```

**Modo Client Branch:**
```
.roots/
└── {version}.{client}/
    ├── _meta.json
    ├── roots_seed.md
    └── {module_name}/
```

Dentro de cada módulo, la estructura interna es idéntica en ambos modos:

```
{module_name}/
    ├── context.md             # Briefing rápido del módulo (30 seg)
    │
    ├── workbench/             # Materiales de referencia del usuario
    │   └── (archivos libres)  # Imágenes, PDFs, videos, análisis, etc.
    │
    ├── journal/               # Bitácora - registros temporales
    │   ├── changelog.md       # Historial de versiones (para clientes)
    │   ├── diary.md           # Reflexiones diarias, qué pasó, pensamientos
    │   └── notes.md           # Ideas precisas, pre-features, observaciones
    │
    ├── debug/                 # Debugging y troubleshooting
    │   ├── errors-log.md      # Errores encontrados, análisis, estado
    │   ├── fixes-log.md       # Qué se arregló, cómo, cuándo
    │   └── migrations.md      # Migraciones de datos, campos, esquemas
    │
    ├── design/                # Diseño y arquitectura
    │   ├── decisions.md       # ADRs (Architecture Decision Records)
    │   └── sketchbook.md      # Bocetos, diagramas, ideas visuales
    │
    ├── docs/                  # Documentación
    │   ├── README.md          # Índice de documentación
    │   ├── manual.md          # Manual de usuario (cómo USAR)
    │   ├── documentation.md   # Documentación técnica (cómo FUNCIONA)
    │   ├── architecture.md    # Arquitectura del sistema
    │   ├── glossary.md        # Términos del dominio y convenciones
    │   └── commits.md         # Historial detallado de commits
    │
    ├── tasks/                 # Gestión de tareas
    │   ├── tasks.md           # Tareas en progreso
    │   └── todo.md            # Backlog y pendientes
    │
    ├── hooks/                 # Hooks de sesión y automatización
    │   ├── session-start.md   # Qué ejecutar al iniciar sesión
    │   ├── session-end.md     # Qué ejecutar al cerrar sesión
    │   ├── on-error.md        # Protocolo al detectar error
    │   ├── on-fix.md          # Protocolo al commitear fix
    │   └── on-seed-process.md # Bootstrap/reprocesamiento del seed
    │
    └── skills/                # Skills y workflows del módulo
        ├── prompts.md         # Prompts reutilizables específicos del módulo
        ├── workflows.md       # Flujos de trabajo comunes del módulo
        └── patterns.md        # Patrones y convenciones del módulo
```

---

## Estándares de Estilo

### Reglas Generales

| Aspecto | Estándar |
|---------|----------|
| **Idioma** | Español para contenido, inglés para código/nombres técnicos |
| **Encabezados** | Usar `#` jerárquico: `#` título, `##` sección, `###` subsección |
| **Fechas** | Formato: `DD Mes YYYY` (ej: `23 Marzo 2026`) |
| **IDs** | Prefijo + número secuencial: `ADR-001`, `ERROR-001`, `WF-001` |
| **Separadores** | Usar `---` entre secciones principales |
| **Listas** | Usar `-` para bullets, `1.` para numeradas, `- [ ]` para checkboxes |
| **Énfasis** | `**negrita**` para términos clave, `código` para técnico |
| **Links** | Relativos dentro de .roots: `[texto](./archivo.md)` |

### Estructura de Documento

Todo archivo `.md` en `.roots/` DEBE seguir esta estructura:

```markdown
# {Module} - {Título del Documento}

> Descripción breve de una línea sobre el propósito del documento.

---

## Sección Principal

Contenido...

---
```

### Voz y Tono

| Documento | Voz | Tono |
|-----------|-----|------|
| `context.md` | Impersonal | Conciso, esencial |
| `changelog.md` | Tercera persona | Profesional, orientado al cliente |
| `diary.md` | Primera persona | Reflexivo, informal |
| `notes.md` | Impersonal | Conciso, técnico |
| `errors-log.md` | Impersonal | Preciso, analítico |
| `fixes-log.md` | Impersonal | Descriptivo, técnico |
| `migrations.md` | Impersonal | Preciso, con versiones |
| `decisions.md` | Primera persona plural (nosotros) | Formal, justificativo |
| `manual.md` | Segunda persona (usted/vos) | Instructivo, amigable |
| `documentation.md` | Impersonal | Técnico, detallado |
| `glossary.md` | Impersonal | Definitorio, con ejemplos |
| `prompts.md` | Imperativo | Directo, claro |
| `workflows.md` | Imperativo | Paso a paso, preciso |
| `patterns.md` | Impersonal | Técnico, con ejemplos |
| `hooks/*.md` | Imperativo | Procedimental, ejecutable |

---

## Protocolos de Poblado

### Protocolo General

```
┌─────────────────────────────────────────────────────────────┐
│  ANTES de cualquier sesión de trabajo:                      │
│  → Ejecutar hooks/session-start.md                   │
│  1. Leer context.md (briefing del módulo)                   │
│  2. Leer diary.md (últimas 5 entradas)                      │
│  3. Leer notes.md (ideas pendientes)                        │
│  4. Revisar tasks/todo.md (backlog)                         │
│  5. Revisar errors-log.md (errores activos)                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  DURANTE el trabajo:                                        │
│  - Encontré error → hooks/on-error.md → errors-log.md      │
│  - Arreglé algo → hooks/on-fix.md → fixes-log.md           │
│  - Tomé decisión importante → decisions.md                  │
│  - Tuve idea → notes.md                                     │
│  - Completé tarea → tasks/tasks.md (marcar done)            │
│  - Término nuevo → glossary.md                              │
│  - Cambié esquema/datos → migrations.md                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  AL FINAL de la sesión:                                     │
│  → Ejecutar hooks/session-end.md                     │
│  1. Actualizar diary.md con resumen del día                 │
│  2. Si hubo release → changelog.md                          │
│  3. Si hubo commits significativos → commits.md             │
│  4. Si creé patrón reutilizable → patterns.md               │
│  5. Si cambió el stack/estado → actualizar context.md       │
└─────────────────────────────────────────────────────────────┘
```

---

### Protocolo por Documento

#### context.md

| Aspecto | Protocolo |
|---------|-----------|
| **Quién escribe** | Humano o IA (al inicializar o cambiar dirección) |
| **Cuándo** | Al crear el módulo, al cambiar stack o arquitectura significativa |
| **Propósito** | Briefing de 30 segundos para cualquier agente o dev nuevo |
| **Qué incluir** | Qué es, stack, estado actual, convenciones clave, dependencias |
| **Qué NO incluir** | Historial, detalles de implementación (eso va en docs/) |
| **Tamaño** | Máximo 50 líneas — si es más largo, no cumple su propósito |

**Formato de entrada:**
```markdown
# {Module} - Context

> Una línea que describe qué hace el módulo.

---

## Stack

- **Framework:** Odoo 17 / Django / etc.
- **Lenguaje:** Python 3.10+
- **Base de datos:** PostgreSQL
- **APIs externas:** MercadoLibre API v2

## Estado Actual

Breve descripción del estado: en desarrollo, producción, mantenimiento.
Features principales funcionando, qué falta.

## Convenciones Clave

- Convención 1: explicación breve
- Convención 2: explicación breve

## Dependencias Críticas

- `modulo_a`: para qué se usa
- `modulo_b`: para qué se usa

---
```

---

#### changelog.md

| Aspecto | Protocolo |
|---------|-----------|
| **Quién escribe** | Humano (final review) o IA (draft) |
| **Cuándo** | Al hacer release de versión |
| **Trigger humano** | "Preparar changelog para versión X.Y" |
| **Trigger IA** | Detectar commits con tag de versión |
| **Qué incluir** | Cambios agrupados por área funcional |
| **Qué NO incluir** | Detalles técnicos, commits individuales |
| **Idioma** | Español, sin jerga técnica |

**Formato de entrada:**
```markdown
## Versión X.Y
DD Mes YYYY

**Cambios:**

1. **Área funcional:** Descripción del cambio en 1-3 oraciones orientadas al usuario.
   Explicar el beneficio, no el cómo técnico.

2. **Otra área:** Descripción...
```

---

#### diary.md

| Aspecto | Protocolo |
|---------|-----------|
| **Quién escribe** | Humano o IA (basado en sesión) |
| **Cuándo** | Al final de cada sesión de trabajo |
| **Trigger humano** | "Actualizar diary" o implícito al cerrar |
| **Trigger IA** | Final de sesión con cambios significativos |
| **Qué incluir** | Qué se hizo, problemas, decisiones, reflexiones |
| **Qué NO incluir** | Código, detalles excesivos |
| **Idioma** | Español, tono personal |

**Formato de entrada:**
```markdown
**DD Mes** - Resumen en una línea.

Desarrollo del día: qué se trabajó, qué problemas surgieron,
qué decisiones se tomaron y por qué. Reflexiones personales
sobre el código o arquitectura. Máximo 5-7 líneas.
```

---

#### notes.md

| Aspecto | Protocolo |
|---------|-----------|
| **Quién escribe** | Humano o IA (captura de ideas) |
| **Cuándo** | En cualquier momento que surja una idea |
| **Trigger humano** | "Anotar idea: ..." |
| **Trigger IA** | Detectar sugerencia de mejora durante trabajo |
| **Qué incluir** | Ideas, observaciones, cosas a investigar |
| **Qué NO incluir** | Tareas concretas (van a tasks/) |
| **Procesamiento** | Revisar semanalmente, mover a tasks/ o descartar |

**Formato de entrada:**
```markdown
### Título de la idea (DD Mes)

Descripción breve. Por qué podría ser útil.
Referencias o contexto si aplica.

**Estado:** Nueva | En evaluación | Descartada | → tasks/todo.md
```

---

#### errors-log.md

| Aspecto | Protocolo |
|---------|-----------|
| **Quién escribe** | Humano o IA (al encontrar error) |
| **Cuándo** | Inmediatamente al detectar error |
| **Trigger humano** | "Registrar error: ..." |
| **Trigger IA** | Exception, test fallido, comportamiento inesperado |
| **Qué incluir** | Síntomas, contexto, análisis, severidad |
| **Lifecycle** | Activo → En progreso → Resuelto (mover a fixes-log) |

**Formato de entrada:**
```markdown
### ERROR-XXX: Título descriptivo

**Reportado:** DD Mes YYYY
**Severidad:** Alta | Media | Baja
**Estado:** Activo | Investigando | En progreso | Resuelto

**Síntomas:**
Qué se observa, cómo se manifiesta el error.

**Contexto:**
Cuándo ocurre, qué lo dispara, frecuencia.

**Análisis:**
Posibles causas, hipótesis, hallazgos de investigación.

**Resolución:** (cuando se resuelve)
Ver fixes-log.md → FIX-XXX
```

---

#### fixes-log.md

| Aspecto | Protocolo |
|---------|-----------|
| **Quién escribe** | Humano o IA (al resolver error) |
| **Cuándo** | Después de commitear el fix |
| **Trigger humano** | "Documentar fix de ERROR-XXX" |
| **Trigger IA** | Commit que referencia error |
| **Qué incluir** | Qué se arregló, cómo, commit, archivos |
| **Qué NO incluir** | Código completo (solo snippets relevantes) |

**Formato de entrada:**
```markdown
### DD Mes - Título del fix

**Commit:** `abc1234`
**Resuelve:** ERROR-XXX (si aplica)
**Archivos:** archivo1.py, archivo2.py

Descripción de qué se arregló y cómo. Explicar la causa raíz
y la solución implementada. Si hay impacto en performance o
comportamiento, mencionarlo.
```

---

#### migrations.md

| Aspecto | Protocolo |
|---------|-----------|
| **Quién escribe** | Humano o IA (al modificar esquema/datos) |
| **Cuándo** | Al renombrar campos, cambiar tipos, migrar datos |
| **Trigger humano** | "Documentar migración de campo X" |
| **Trigger IA** | Detectar cambio de schema en modelos |
| **Qué incluir** | Campo viejo → nuevo, script de migración, versión afectada |
| **Qué NO incluir** | Cambios que no afectan datos existentes |
| **Lifecycle** | Pendiente → Aplicada → Verificada |

**Formato de entrada:**
```markdown
### MIG-XXX: Título de la migración

**Fecha:** DD Mes YYYY
**Versión:** X.Y → X.Z
**Estado:** Pendiente | Aplicada | Verificada

**Cambio:**
Descripción de qué cambió en el esquema o datos.

**Migración:**
```python
# Script o pasos para migrar datos existentes
```

**Rollback:**
Cómo revertir si algo falla (si aplica).

**Verificación:**
Cómo confirmar que la migración fue exitosa.
```

---

#### decisions.md

| Aspecto | Protocolo |
|---------|-----------|
| **Quién escribe** | Humano (decisiones importantes) |
| **Cuándo** | Al tomar decisión de arquitectura/diseño significativa |
| **Trigger humano** | "Documentar decisión: ..." |
| **Trigger IA** | Sugerir documentar cuando detecta decisión importante |
| **Qué incluir** | Contexto, opciones consideradas, decisión, consecuencias |
| **Inmutabilidad** | NO borrar, marcar como Deprecado/Reemplazado |

**Formato de entrada:**
```markdown
## ADR-XXX: Título de la decisión

**Fecha:** DD Mes YYYY
**Estado:** Propuesto | Aceptado | Deprecado | Reemplazado por ADR-YYY

**Contexto:**
Situación que motivó la decisión. Problema a resolver.

**Opciones consideradas:**
1. Opción A - pros y contras
2. Opción B - pros y contras

**Decisión:**
Qué decidimos hacer y por qué elegimos esta opción.

**Consecuencias:**
Qué implica esta decisión. Trade-offs aceptados.
```

---

#### sketchbook.md

| Aspecto | Protocolo |
|---------|-----------|
| **Quién escribe** | Humano o IA (visualización de ideas) |
| **Cuándo** | Al diseñar UI, flujos, arquitectura visual |
| **Trigger humano** | "Bocetar: ..." |
| **Trigger IA** | Crear diagrama para explicar concepto |
| **Formato visual** | ASCII art, mermaid (si soportado), descripciones |

**Formato de entrada:**
```markdown
## Nombre del diseño (DD Mes)

**Propósito:** Para qué es este boceto.

```
┌─────────────────┐
│  ASCII diagram  │
│  del concepto   │
└─────────────────┘
```

**Notas:** Explicación adicional, alternativas, decisiones visuales.
```

---

#### manual.md

| Aspecto | Protocolo |
|---------|-----------|
| **Quién escribe** | Humano (estructura) + IA (contenido) |
| **Cuándo** | Al agregar features, al hacer release |
| **Audiencia** | Usuarios finales, no técnicos |
| **Estructura** | Instalación → Configuración → Uso diario → Troubleshooting |
| **Estilo** | Paso a paso, con screenshots si posible |

**Secciones obligatorias:**
1. Instalación/Requisitos
2. Configuración inicial
3. Operaciones comunes (con pasos numerados)
4. Solución de problemas

---

#### documentation.md

| Aspecto | Protocolo |
|---------|-----------|
| **Quién escribe** | Humano o IA (documentación técnica) |
| **Cuándo** | Al crear/modificar modelos, APIs, funciones importantes |
| **Audiencia** | Desarrolladores |
| **Estructura** | Modelos → Métodos → Ciclos → Extensión |
| **Estilo** | Técnico, con código de ejemplo |

**Secciones sugeridas:**
1. Arquitectura de módulos
2. Modelos principales (campos, métodos)
3. Ciclos y flujos (diagramas de secuencia)
4. API/Endpoints
5. Hooks y extensión
6. Diagnóstico/Debugging

---

#### glossary.md

| Aspecto | Protocolo |
|---------|-----------|
| **Quién escribe** | Humano o IA (al usar término ambiguo) |
| **Cuándo** | Al introducir concepto nuevo, al detectar confusión de términos |
| **Trigger humano** | "Agregar al glosario: ..." |
| **Trigger IA** | Término técnico o de dominio usado sin definición previa |
| **Qué incluir** | Término, definición, ejemplo de uso, sinónimos si los hay |
| **Ordenamiento** | Alfabético |

**Formato de entrada:**
```markdown
### término

**Definición:** Qué es, en el contexto de este módulo.
**Ejemplo:** `campo.binding_id` — referencia al binding de MercadoLibre.
**Sinónimos:** otros nombres usados para lo mismo (si aplica).
**Ver también:** términos relacionados.
```

---

#### prompts.md

| Aspecto | Protocolo |
|---------|-----------|
| **Quién escribe** | Humano o IA (después de usar prompt exitoso) |
| **Cuándo** | Al identificar tarea repetitiva que se beneficia de prompt |
| **Trigger** | "Guardar este prompt como reutilizable" |
| **Qué incluir** | Uso, contexto necesario, prompt exacto |
| **Prueba** | El prompt debe haber sido probado y funcionar |

**Formato de entrada:**
```markdown
## PROMPT-XXX: Nombre descriptivo

**Uso:** En qué situación usar este prompt.
**Contexto requerido:** Qué información necesita el agente.
**Variables:** {variable1}, {variable2} (si las hay)

```
Texto del prompt aquí.
Usar {variables} para partes que cambian.
```

**Ejemplo de uso:**
Mostrar un ejemplo concreto con variables reemplazadas.
```

---

#### workflows.md

| Aspecto | Protocolo |
|---------|-----------|
| **Quién escribe** | Humano (define) + IA (puede ejecutar) |
| **Cuándo** | Al identificar proceso repetitivo multi-paso |
| **Requisito** | Cada paso debe ser ejecutable y verificable |
| **Qué incluir** | Trigger, pasos, resultado esperado, notas |

**Formato de entrada:**
```markdown
## WF-XXX: Nombre del workflow

**Trigger:** Cuándo/por qué ejecutar este workflow.
**Resultado esperado:** Qué se obtiene al completar.
**Tiempo estimado:** X minutos/horas.

### Pasos

1. **Nombre del paso** — Descripción. Comando o acción específica.
2. **Siguiente paso** — Descripción. Verificación de éxito.
3. ...

### Verificación

Cómo confirmar que el workflow se completó correctamente.

### Rollback

Qué hacer si algo falla (si aplica).
```

---

#### patterns.md

| Aspecto | Protocolo |
|---------|-----------|
| **Quién escribe** | Humano o IA (al identificar patrón) |
| **Cuándo** | Al establecer convención o detectar patrón repetido |
| **Qué incluir** | Ejemplo correcto + anti-patrón |
| **Obligatorio** | Incluir razón del patrón |

**Formato de entrada:**
```markdown
## PAT-XXX: Nombre del patrón

**Aplica a:** Modelos | Vistas | Controllers | JS | CSS | Tests
**Razón:** Por qué usamos este patrón.

### Ejemplo correcto

```python
# Código que SÍ seguir
```

### Anti-patrón

```python
# Código que NO hacer y por qué
```

### Excepciones

Cuándo está permitido no seguir este patrón (si aplica).
```

---

#### hooks/

Los hooks son **protocolos ejecutables** que definen qué hacer automáticamente ante eventos específicos. Cada hook es un archivo `.md` que describe los pasos a seguir — puede ser ejecutado por un agente de IA, por un script, o por un hook real de herramientas como Claude Code (`.claude/hooks/`).

##### session-start.md

| Aspecto | Protocolo |
|---------|-----------|
| **Propósito** | Cargar contexto al inicio de sesión |
| **Ejecutor** | Agente IA o hook de herramienta |
| **Obligatorio** | Sí — sin contexto, el agente trabaja a ciegas |

**Formato de entrada:**
```markdown
# Hook: Session Start

> Protocolo de inicio de sesión de desarrollo.

## Pasos

1. Chequear versión del seed:
   - Leer `.roots/roots_seed.md` (copia local, self-contained) → campo `**Versión:**`
   - Leer canonical (si está accesible en el repo) → mismo campo
   - Si copia local y canonical difieren → disparar `hooks/on-seed-update.md` antes de continuar
   - Si la versión es distinta a la última conocida por la memoria del
     agente → releer seed completo y aplicar convenciones nuevas.
   - Si `.roots/roots_seed.md` NO existe → copiar el canonical con header
     de distribución (regla obligatoria § "Distribución del seed").
2. Leer `context.md` — entender qué es el proyecto.
3. Leer `journal/diary.md` — últimas 5 entradas.
4. Leer `journal/notes.md` — ideas pendientes y observaciones técnicas.
5. Leer `tasks/todo.md` — backlog pendiente.
6. Leer `tasks/tasks.md` — trabajo en progreso (si existe, retomar).
7. Leer `debug/errors-log.md` — errores activos sin resolver.
8. Listar `workbench/` — si hay archivos nuevos o recientes, leer o
   mencionar su existencia al humano. Son materiales de referencia.
9. Leer `_meta.json` — `active_branch` y `current_feature`.
10. Verificar git state:
    - `git branch --show-current`
    - `git log --oneline -10`
    - `git status`
11. Si `_meta.json.active_branch` o `tasks/tasks.md` no reflejan la rama
    actual → el `.roots/` está desincronizado. Avisar al humano antes de
    hacer suposiciones; no decidir a ciegas.
12. Si hay feature activa, buscar design docs en `docs/design-*.md` y
    leer la sección relevante antes de tocar código.

## Output esperado

Resumen interno de: estado del proyecto, tareas pendientes,
errores activos, contexto de última sesión, estado git sincronizado
con `.roots/`, materiales de referencia disponibles en workbench.
```

##### session-end.md

| Aspecto | Protocolo |
|---------|-----------|
| **Propósito** | Persistir lo aprendido antes de cerrar sesión |
| **Ejecutor** | Agente IA o hook de herramienta |
| **Obligatorio** | Recomendado — previene pérdida de contexto |

**Formato de entrada:**
```markdown
# Hook: Session End

> Protocolo de cierre de sesión.

## Pasos

1. Agregar entrada a `journal/diary.md` con resumen del trabajo
2. Si hubo errores nuevos → agregar a `debug/errors-log.md`
3. Si se arregló algo → agregar a `debug/fixes-log.md`
4. Si se completó tarea → marcar en `tasks/tasks.md`
5. Si se identificó patrón → proponer para `skills/patterns.md`
6. Si hubo commits → actualizar `docs/commits.md`

## Output esperado

Archivos de .roots/ actualizados con el trabajo de la sesión.
```

##### on-error.md

| Aspecto | Protocolo |
|---------|-----------|
| **Propósito** | Documentar error de forma estructurada al detectarlo |
| **Trigger** | Exception, test fallido, comportamiento inesperado |

**Formato de entrada:**
```markdown
# Hook: On Error

> Protocolo al detectar un error.

## Pasos

1. Determinar siguiente ID: revisar último ERROR-XXX en errors-log.md
2. Agregar entrada con formato estándar a `debug/errors-log.md`
3. Si el error es crítico → agregar a `tasks/tasks.md` como tarea
4. Si hay hipótesis de causa → documentar en sección Análisis

## Template

Usar el formato ERROR-XXX definido en el protocolo de errors-log.md.
```

##### on-fix.md

| Aspecto | Protocolo |
|---------|-----------|
| **Propósito** | Documentar fix y cerrar ciclo del error |
| **Trigger** | Commit que resuelve un error conocido |

**Formato de entrada:**
```markdown
# Hook: On Fix

> Protocolo al commitear una corrección.

## Pasos

1. Agregar entrada a `debug/fixes-log.md` con formato estándar
2. Si resuelve un ERROR-XXX → actualizar estado a "Resuelto" en errors-log.md
3. Si el fix introduce patrón reutilizable → proponer para patterns.md
4. Si el fix requiere migración de datos → agregar a migrations.md

## Template

Usar el formato definido en el protocolo de fixes-log.md.
```

##### on-seed-update.md

| Aspecto | Protocolo |
|---------|-----------|
| **Propósito** | Re-distribuir el seed canonical a todas las copias locales (`.roots/roots_seed.md`) del repo cuando cambia la versión canónica |
| **Ejecutor** | Agente IA o desarrollador humano |
| **Trigger** | (a) Se bumpea la versión del seed canonical, (b) un `session-start` detecta desync entre copia local y canonical, (c) se crea un `.roots/` nuevo y hay que poblarlo |
| **Obligatorio** | Sí — sin esto los módulos dejan de ser self-contained y el seed deja de ser reprocesable localmente |

**Formato de entrada:**
```markdown
# Hook: On Seed Update

> Protocolo al bumpear el seed canonical o detectar desync con copias locales.

## Pasos

1. Identificar el canonical (una sola fuente de verdad en el repo).
2. Para cada directorio `.roots/` del repo:
    - Escribir `<dir>/roots_seed.md` con el header de distribución
      seguido del contenido del canonical.
3. Verificar con `diff` (o equivalente) que todas las copias coinciden
   en contenido (ignorando el header de distribución).
4. Registrar la re-distribución en `journal/diary.md` o `docs/commits.md`.
5. Si algún `.roots/` tenía modificaciones locales al seed → preservarlas
   como nota al pie de la copia local antes de sobrescribir. Avisar al
   humano si hay conflicto.

## Comando de referencia (bash, tool-agnostic)

SEED="odoo_moldeo_roots/roots_seed.md"
find . -type d -name ".roots" -not -path "*/node_modules/*" | while read -r dir; do
    cp "$SEED" "$dir/roots_seed.md"
done

## Output esperado

Todas las copias `.roots/roots_seed.md` alineadas con el canonical.
Cada módulo vuelve a ser self-contained y reprocesable aisladamente.
```

##### on-task-done.md

| Aspecto | Protocolo |
|---------|-----------|
| **Propósito** | Cerrar correctamente cada tarea individual (no al final de la sesión) manteniendo `.roots/` sincronizado |
| **Ejecutor** | Agente IA o desarrollador humano |
| **Trigger** | Una tarea listada en `tasks/tasks.md` o `tasks/todo.md` queda completada y está por reportarse al humano |
| **Obligatorio** | Sí — evita dejar el `.roots/` desactualizado entre tareas de la misma sesión |

**Formato de entrada:**
```markdown
# Hook: On Task Done

> Protocolo al completar una tarea, antes de reportarla al humano.

## Pasos mínimos (siempre)

1. `tasks/todo.md` — marcar la tarea como `[x]` o moverla a "Completadas"
2. `tasks/tasks.md` — mover la tarea de "En Progreso" a "Completadas Recientemente"
3. `docs/commits.md` — si hubo commit, agregar entrada con hash, motivación y cambios

## Pasos condicionales

- Si se encontró un error durante la tarea → `debug/errors-log.md` (ERROR-XXX)
- Si se aplicó un fix → `debug/fixes-log.md` (FIX-XXX)
- Si se tomó una decisión arquitectónica → `design/decisions.md` (ADR-XXX)
- Si surgió una idea → `journal/notes.md`
- Si aparece término nuevo del dominio → `docs/glossary.md`
- Si cambió esquema/datos → `debug/migrations.md`

## Output esperado

`.roots/` sincronizado con la tarea completada ANTES de reportar al humano.
Un humano que lea sólo `.roots/` debe poder reconstruir qué se hizo y por qué.
```

##### on-topic-shift.md

| Aspecto | Protocolo |
|---------|-----------|
| **Propósito** | Garantizar que el agente no trabaje a ciegas cuando la conversación pivota a un archivo/sistema no cubierto por el bootstrap |
| **Ejecutor** | Agente IA, desarrollador o cualquier herramienta de asistencia de código |
| **Trigger** | Aparece en la conversación un archivo, módulo o sistema no tocado en los últimos pasos |
| **Obligatorio** | Sí — evita preguntas redundantes y decisiones sin contexto |

**Formato de entrada:**
```markdown
# Hook: On Topic Shift

> Protocolo al cambiar de foco a un archivo/sistema no cubierto por el bootstrap de sesión.

## Pasos

1. Listar `.roots/docs/` (`ls` o equivalente).
2. Buscar un doc con nombre relacionado al nuevo foco.
3. Si existe, leer la sección relevante ANTES de preguntar aclaraciones
   o proponer un diseño.
4. Revisar `.roots/journal/notes.md` y `.roots/design/decisions.md` por
   observaciones o ADRs sobre el mismo sistema.
5. Revisar `.roots/workbench/` por materiales de referencia relacionados.
6. Solo preguntar al humano lo que quede genuinamente no documentado.
7. Si al terminar la tarea se descubre información que debería haber
   estado en `.roots/docs/` pero no estaba → agregarla o proponer un
   nuevo doc.

## Output esperado

Contexto cargado del sistema nuevo antes de escribir código o pedir
aclaraciones. Preguntas al humano reducidas a lo no documentado.

## Compatibilidad

Este protocolo es tool-agnostic. Aplica a cualquier asistente de IA
(Claude Code, Cursor, Copilot Workspace, Aider, etc.) o desarrollador
humano que retome el repo.
```

##### on-seed-process.md

| Aspecto | Protocolo |
|---------|-----------|
| **Propósito** | Consolidar todos los pasos de bootstrap/reprocesamiento del seed en un solo hook ejecutable |
| **Ejecutor** | Agente IA o desarrollador humano |
| **Trigger** | (a) Se inicializa un `.roots/` nuevo, (b) se bumpea la versión del seed, (c) se detecta desync con upstream o canonical, (d) el humano pide "procesar el seed" explícitamente |
| **Obligatorio** | Sí — es el punto de entrada para cualquier operación sobre el seed |

**Formato de entrada:**
```markdown
# Hook: On Seed Process

> Protocolo maestro al procesar/reprocesar el seed. Consolida sync
> upstream, distribución, y verificación de CLAUDE.md.

## Pasos

0. **Detectar modo de trabajo (solo en bootstrap inicial):**
   - Si `_meta.json` ya existe y tiene `working_mode` → usar ese modo, no preguntar
   - Si no existe `_meta.json` o no tiene `working_mode` → preguntar al usuario:
     - Client branch → pedir versión y nombre de cliente → crear `.roots/{version}.{client}/`
     - Source → crear `.roots/{module}/` directamente
   - Persistir la respuesta en `_meta.json.working_mode`
   - Este paso NO se repite en sesiones posteriores

1. **Sync con upstream público:**
   - Fetch `https://raw.githubusercontent.com/ctmil/roots_seed/main/roots_seed.md`
   - Comparar versión upstream vs versión del canonical local
   - Si local < upstream → avisar al humano, proponer aplicar cambios
   - Si local > upstream → evaluar si hay mejoras genéricas para PR
   - Si no hay acceso al upstream → anotar en `journal/notes.md`, continuar

2. **Verificar canonical del repo:**
   - Leer `odoo_moldeo_roots/roots_seed.md` (o la ruta canonical configurada)
   - Confirmar que el campo `**Versión:**` coincide con lo esperado
   - Si hay ediciones locales no bumpeadas → avisar al humano

3. **Distribuir a todas las copias:**
   - Ejecutar `hooks/on-seed-update.md`
   - Cada `.roots/roots_seed.md` queda alineado con el canonical
   - Verificar con diff que no quedaron copias desincronizadas

4. **Verificar/crear CLAUDE.md:**
   - Si no existe `CLAUDE.md` en la raíz → crearlo con el template
     definido en § "Integración con CLAUDE.md"
   - Si existe → verificar que la lista de módulos con `.roots/`
     está actualizada (agregar nuevos, marcar removidos)
   - Si existe `.claude/` → verificar que sus hooks referencian
     `.roots/` sin duplicar lógica

5. **Verificar workbench/:**
   - Para cada `.roots/{module}/` que no tenga `workbench/` → crearla
   - No agregar contenido — es espacio del usuario

6. **Registrar:**
   - Agregar entrada en `journal/diary.md` o `docs/commits.md`
     documentando el procesamiento del seed, versión, y acciones tomadas

## Output esperado

- Canonical local alineado (o con delta documentado) con upstream
- Todas las copias `.roots/roots_seed.md` sincronizadas
- `CLAUDE.md` actualizado con índice de módulos
- Carpetas `workbench/` existentes en todos los módulos
- Registro del procesamiento en journal o commits
```

---

#### tasks.md y todo.md

| Aspecto | tasks.md | todo.md |
|---------|----------|---------|
| **Contenido** | Trabajo activo | Backlog |
| **Estado items** | En progreso, Bloqueado | Pendiente |
| **Límite** | 3-5 tareas máximo | Sin límite |
| **Movimiento** | todo.md → tasks.md → Completado |

**Formato tasks.md:**
```markdown
## En Progreso

### TASK-XXX: Título
**Asignado:** Nombre o "IA"
**Inicio:** DD Mes
**Estado:** En progreso | Bloqueado por XXX

Descripción breve de la tarea.

- [ ] Subtarea 1
- [x] Subtarea 2 (completada)
```

**Formato todo.md:**
```markdown
## Alta Prioridad

- [ ] Tarea importante 1
- [ ] Tarea importante 2

## Media Prioridad

- [ ] Tarea normal

## Ideas / Backlog

- [ ] Cosa que algún día podríamos hacer
```

---

## Uso con Agentes de IA

### Instrucciones para el Agente

Al iniciar sesión en un proyecto con `.roots/`:

```
1. LEER contexto (seguir hooks/session-start.md):
   - .roots/{module}/context.md (briefing rápido)
   - .roots/{module}/journal/diary.md (últimas 5 entradas)
   - .roots/{module}/tasks/todo.md
   - .roots/{module}/debug/errors-log.md (errores activos)

2. DURANTE el trabajo:
   - Al encontrar error: seguir hooks/on-error.md → errors-log.md
   - Al arreglar algo: seguir hooks/on-fix.md → fixes-log.md
   - Al tener idea de mejora: AGREGAR a notes.md
   - Al tomar decisión importante: PREGUNTAR si documentar en decisions.md
   - Al usar término de dominio nuevo: AGREGAR a glossary.md
   - Al cambiar esquema/campos: AGREGAR a migrations.md

3. AL FINALIZAR sesión (seguir hooks/session-end.md):
   - AGREGAR entrada a diary.md resumiendo el trabajo
   - Si hubo patrón reutilizable: PROPONER agregarlo a patterns.md
   - Si creé prompt útil: PROPONER agregarlo a prompts.md
   - Si cambió el estado del proyecto: ACTUALIZAR context.md

4. NUNCA:
   - Borrar contenido existente sin preguntar
   - Modificar decisions.md (solo agregar o marcar deprecado)
   - Inventar IDs que ya existen (revisar último número)
   - Ignorar hooks/ — son el protocolo estándar
```

### Triggers Automáticos para IA

| Situación | Acción |
|-----------|--------|
| Inicio de sesión | → Ejecutar hooks/session-start.md |
| Exception en código | → Ejecutar hooks/on-error.md → errors-log.md |
| Commit con fix | → Ejecutar hooks/on-fix.md → fixes-log.md |
| Usuario dice "versión X.Y lista" | → Proponer actualizar changelog.md |
| Patrón de código repetido 3+ veces | → Proponer documentar en patterns.md |
| Explicación compleja dada | → Proponer guardar en documentation.md |
| Término de dominio sin definir | → Proponer agregar a glossary.md |
| Cambio de esquema/campos | → Proponer agregar a migrations.md |
| Final de sesión larga | → Ejecutar hooks/session-end.md |
| Bootstrap o bump del seed | → Ejecutar hooks/on-seed-process.md |
| Nuevo material en workbench/ | → Leer/mencionar al humano |

---

## Script de Inicialización

```bash
#!/bin/bash
# init_roots.sh - Inicializa estructura .roots para un módulo

MODULE_NAME=${1:-"module"}
BASE_PATH=".roots/$MODULE_NAME"
SEED_VERSION="1.4"

mkdir -p "$BASE_PATH"/{journal,debug,design,docs,tasks,hooks,skills,workbench}

# Meta
cat > ".roots/_meta.json" << EOF
{
  "seed_version": "$SEED_VERSION",
  "created_at": "$(date -Iseconds)",
  "modules": ["$MODULE_NAME"]
}
EOF

# Context
cat > "$BASE_PATH/context.md" << 'EOF'
# {MODULE} - Context

> Breve descripción de qué hace el módulo.

---

## Stack

- **Framework:** ...
- **Lenguaje:** ...
- **Base de datos:** ...

## Estado Actual

En desarrollo / producción / mantenimiento.

## Convenciones Clave

- ...

## Dependencias Críticas

- ...

---
EOF

# Journal
cat > "$BASE_PATH/journal/changelog.md" << 'EOF'
# {MODULE} - Changelog

> Historial de versiones y cambios.

---

*Sin releases aún*

---
EOF

cat > "$BASE_PATH/journal/diary.md" << 'EOF'
# {MODULE} - Development Diary

> Reflexiones diarias sobre el desarrollo.

---

## $(date +%Y)

*Comenzar a documentar aquí*

---
EOF

cat > "$BASE_PATH/journal/notes.md" << 'EOF'
# {MODULE} - Notes

> Ideas y notas que podrían convertirse en features.

---

## Ideas pendientes

*Agregar ideas aquí*

---
EOF

# Debug
cat > "$BASE_PATH/debug/errors-log.md" << 'EOF'
# {MODULE} - Errors Log

> Registro de errores encontrados.

---

## Errores Activos

*Ninguno actualmente*

---

## Errores Resueltos

Ver [fixes-log.md](./fixes-log.md)

---
EOF

cat > "$BASE_PATH/debug/fixes-log.md" << 'EOF'
# {MODULE} - Fixes Log

> Historial de correcciones implementadas.

---

*Sin fixes documentados aún*

---
EOF

cat > "$BASE_PATH/debug/migrations.md" << 'EOF'
# {MODULE} - Migrations

> Registro de migraciones de datos, campos y esquemas.

---

*Sin migraciones documentadas aún*

---
EOF

# Design
cat > "$BASE_PATH/design/decisions.md" << 'EOF'
# {MODULE} - Architecture Decisions

> Decisiones de diseño y arquitectura (ADRs).

---

*Sin decisiones documentadas aún*

---
EOF

cat > "$BASE_PATH/design/sketchbook.md" << 'EOF'
# {MODULE} - Sketchbook

> Bocetos, diagramas e ideas visuales.

---

*Sin bocetos aún*

---
EOF

# Docs
cat > "$BASE_PATH/docs/README.md" << 'EOF'
# {MODULE} - Documentation

> Índice de documentación.

---

## Documentos

| Archivo | Descripción |
|---------|-------------|
| [manual.md](./manual.md) | Manual de usuario |
| [documentation.md](./documentation.md) | Documentación técnica |
| [architecture.md](./architecture.md) | Arquitectura del sistema |

---
EOF

touch "$BASE_PATH/docs/manual.md"
touch "$BASE_PATH/docs/documentation.md"
touch "$BASE_PATH/docs/architecture.md"

cat > "$BASE_PATH/docs/glossary.md" << 'EOF'
# {MODULE} - Glossary

> Términos del dominio y convenciones de nomenclatura.

---

*Agregar términos en orden alfabético*

---
EOF

# Tasks
cat > "$BASE_PATH/tasks/tasks.md" << 'EOF'
# {MODULE} - Tasks

> Tareas en progreso.

---

## En Progreso

*Sin tareas activas*

---
EOF

cat > "$BASE_PATH/tasks/todo.md" << 'EOF'
# {MODULE} - TODO

> Backlog y tareas pendientes.

---

## Alta Prioridad

*Sin tareas pendientes*

---

## Media Prioridad

---

## Ideas / Backlog

---
EOF

# Skills
cat > "$BASE_PATH/skills/prompts.md" << 'EOF'
# {MODULE} - Prompts

> Prompts reutilizables para tareas frecuentes.

---

*Sin prompts documentados aún*

---
EOF

cat > "$BASE_PATH/skills/workflows.md" << 'EOF'
# {MODULE} - Workflows

> Flujos de trabajo comunes.

---

*Sin workflows documentados aún*

---
EOF

cat > "$BASE_PATH/skills/patterns.md" << 'EOF'
# {MODULE} - Patterns

> Patrones de código y convenciones.

---

*Sin patrones documentados aún*

---
EOF

# Hooks
cat > "$BASE_PATH/hooks/session-start.md" << 'EOF'
# Hook: Session Start

> Protocolo de inicio de sesión de desarrollo.

---

## Pasos

1. Leer `context.md` — entender qué es el proyecto
2. Leer `journal/diary.md` — últimas 5 entradas
3. Leer `tasks/todo.md` — backlog pendiente
4. Leer `debug/errors-log.md` — errores activos
5. Si hay `tasks/tasks.md` con tareas en progreso → retomar

## Output esperado

Resumen interno de: estado del proyecto, tareas pendientes,
errores activos, contexto de última sesión.

---
EOF

cat > "$BASE_PATH/hooks/session-end.md" << 'EOF'
# Hook: Session End

> Protocolo de cierre de sesión.

---

## Pasos

1. Agregar entrada a `journal/diary.md` con resumen del trabajo
2. Si hubo errores nuevos → agregar a `debug/errors-log.md`
3. Si se arregló algo → agregar a `debug/fixes-log.md`
4. Si se completó tarea → marcar en `tasks/tasks.md`
5. Si se identificó patrón → proponer para `skills/patterns.md`
6. Si hubo commits → actualizar `docs/commits.md`
7. Si cambió estado del proyecto → actualizar `context.md`

## Output esperado

Archivos de .roots/ actualizados con el trabajo de la sesión.

---
EOF

cat > "$BASE_PATH/hooks/on-error.md" << 'EOF'
# Hook: On Error

> Protocolo al detectar un error.

---

## Pasos

1. Determinar siguiente ID: revisar último ERROR-XXX en errors-log.md
2. Agregar entrada con formato estándar a `debug/errors-log.md`
3. Si el error es crítico → agregar a `tasks/tasks.md` como tarea
4. Si hay hipótesis de causa → documentar en sección Análisis

## Template

Usar el formato ERROR-XXX definido en el protocolo de errors-log.md.

---
EOF

cat > "$BASE_PATH/hooks/on-fix.md" << 'EOF'
# Hook: On Fix

> Protocolo al commitear una corrección.

---

## Pasos

1. Agregar entrada a `debug/fixes-log.md` con formato estándar
2. Si resuelve un ERROR-XXX → actualizar estado a "Resuelto" en errors-log.md
3. Si el fix introduce patrón reutilizable → proponer para patterns.md
4. Si el fix requiere migración de datos → agregar a migrations.md

## Template

Usar el formato definido en el protocolo de fixes-log.md.

---
EOF

# Replace placeholder
find "$BASE_PATH" -type f -name "*.md" -exec sed -i "s/{MODULE}/$MODULE_NAME/g" {} \;

echo "✓ Created .roots/$MODULE_NAME structure (seed v$SEED_VERSION)"
echo "  - context.md: briefing del módulo"
echo "  - journal/: changelog, diary, notes"
echo "  - debug/: errors-log, fixes-log, migrations"
echo "  - design/: decisions, sketchbook"
echo "  - docs/: README, manual, documentation, architecture, glossary"
echo "  - tasks/: tasks, todo"
echo "  - skills/: prompts, workflows, patterns"
echo "  - workbench/: materiales de referencia (vacío)"
echo "  - hooks/: session-start, session-end, on-error, on-fix"
echo "  - _meta.json: metadata de inicialización"
```

---

## Mejores Prácticas

1. **context.md es la puerta de entrada** — Lo primero que lee cualquier agente o dev nuevo
2. **diary.md es la memoria a corto plazo** — Actualizar al final de cada sesión
3. **changelog.md es para clientes** — Sin jerga técnica, enfocado en beneficios
4. **decisions.md es inmutable** — No borrar, solo deprecar o reemplazar
5. **errors-log.md es temporal** — Mover a fixes-log.md cuando se resuelve
6. **notes.md es libre** — Ideas rápidas, procesar semanalmente
7. **glossary.md evita ambigüedades** — Definir términos del dominio una sola vez
8. **migrations.md previene pérdida de datos** — Documentar todo cambio de esquema
9. **hooks/ son el protocolo estándar** — Seguirlos garantiza consistencia entre sesiones
10. **skills/ es específico del módulo** — No duplicar patrones genéricos
11. **patterns.md incluye anti-patrones** — Qué NO hacer es igual de importante
12. **workflows.md debe ser ejecutable** — Pasos claros que un agente pueda seguir
13. **Mantener IDs únicos** — Revisar último número antes de crear nuevo
14. **Consistencia de formato** — Seguir las plantillas de este documento
15. **_meta.json es automático** — No editarlo manualmente, es para herramientas
16. **workbench/ es del usuario** — El agente consulta pero no inventa contenido ahí; revisar al inicio de cada sesión

---
