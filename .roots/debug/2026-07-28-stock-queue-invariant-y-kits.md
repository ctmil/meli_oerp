# Sincronización de stock: invariante de cola rota + doble definición de "disponible" (kits)

**Fecha:** 2026-07-28 · **Analista:** meli-keeper · **Origen:** handoff de `/soporte organicoyvital` (475)
**Caso de referencia:** Organico y Vital, prod REAL `57.128.245.36`, site MLM, cuenta ML id=1.
Versiones en prod: `meli_oerp` **19.0.26.82** · `meli_oerp_multiple` **19.0.26.79** · `meli_oerp_stock` 19.0.26.38.
Source al momento del análisis: 26.86 (16/17/18) · 26.85 (19.0).
**Alcance:** producto (afecta a toda la flota). No se tocó código ni prod en este análisis.

---

## 0. Resumen ejecutivo

1. **La sobreventa reportada NO existe.** Las 4 publicaciones "activas vendiendo stock que en Odoo no
   existe" (114 uds) son **KITS** (`mrp.bom` type=`phantom`). Un kit **siempre** tiene 0 `stock_quant`:
   su disponibilidad se deriva de los componentes. Los valores publicados en ML son **exactamente** los
   que calcula el módulo. Ver §1.
2. **La hipótesis del handoff (`product_product.meli_id` vacío) es incorrecta.** El camino de publicación
   usa `bindv.conn_id`, nunca `product.meli_id`. Ver §2.
3. **Causa raíz real de los "bindings congelados": el invariante de cola usa `max(stock_move.create_date)`,
   que se congela.** Es un defecto de diseño, reproducible y de flota. Ver §3. ← **el hallazgo importante**
4. **Segundo defecto estructural: el módulo tiene DOS definiciones distintas de "stock disponible"** — la
   del publicador (honra kits/ubicaciones/BoM) y la del diagnóstico (`stock_quant` crudo). De ahí salen
   todos los falsos positivos del diagnóstico (107 activas "con stock 0", 10 pausadas "con stock"). Ver §4.
5. **Sobreventa REAL, distinta de la reportada:** el módulo publica el stock **completo** en cada
   publicación que comparte producto o componente. En OrgVit: **~1.810 unidades sobre-prometidas** en 14
   componentes. Ver §5.
6. **18 publicaciones con 2 bindings a productos distintos** (misma `conn_id`) que se pisan el stock; 6 de
   ellas son mis-bindings a un SKU completamente diferente. No hay constraint que lo impida. Ver §6.
7. El test `[4d]` del diagnóstico da un **falso OK** (publica el mismo valor que ya tiene). Ver §7.

---

## 1. Los SKU "de sobreventa" son kits — evidencia

`meli_oerp_stock/19.0/models/product.py:417-469` — `_meli_available_quantity()` deriva la cantidad de un
kit a partir del **mínimo** de `componente_libre / cantidad_por_kit`:

```python
if (1==1 and 'mrp.bom' in self.env and new_meli_available_quantity<=10000):   # :417
    ...
    if bom_id and bom_id.type == 'phantom':                                    # :443
        stock_material = int(virtual_comp_av / bom_line.product_qty)           # :465
```

Contraste contra la base de prod (28/07):

| SKU publicado | BoM | Componente | libre comp. | qty/kit | calculado | ML publica |
|---|---|---|---|---|---|---|
| THLSURINF203X2 | phantom | THLSURINF20 | 159 | 3 | 159/3 = **53** | **53** ✔ |
| THRVRDJZN202X1 | phantom | THRVRDJZN20 | 71 | 2 | int(71/2) = **35** | **35** ✔ |
| TOMVIMA52P | phantom | TOMVIMA5 | 26 | 2 | **13** | **13** ✔ |
| TOMVIMA42P | phantom | TOMVIMA4 | 4 | 2 | **2** | **2** ✔ |
| YYPMP10012 | phantom | (pid 7364) | 61 | 12 | int(61/12) = **5** | **5** ✔ |
| HSMCTOIL500 | (sin BoM) | — | 0 | — | **0** | 0 / paused ✔ |

Los seis coinciden al dígito. **El PUT `/items/{id}` sí se aplicó**; lo que "no se movió" es que el
módulo volvió a publicar el mismo valor correcto. `HSMCTOIL500` pasó a `paused/0` porque efectivamente
tiene 0 (no es kit). No hay 200-OK-silencioso: no hay nada que corregir en esas 4 publicaciones.

**Barrido completo de la cuenta** (el universo de las "107 activas con stock 0 en Odoo"):

```
activas con stock_quant=0 : 116
  … de las cuales son KIT : 17
  … con cantidad publicada > 0 : 17   ← las 17 son las mismas 17 kits
  … NO-kit con cantidad publicada > 0 : 0
```

**Cero** casos de publicación activa con cantidad >0 y sin respaldo. La categoría entera del diagnóstico
es un artefacto de medir con `stock_quant`.

> ⚠️ **Detalle relevante:** el kit `meli_oerp_stock` está **sólo** en `meli_oerp_stock`. En el base
> `meli_oerp` la rama BoM está **desactivada** (`meli_oerp/19.0/models/product.py:4714`
> → `if (1==2 and 'mrp.bom' in self.env …)`). O sea la disponibilidad derivada de kits existe únicamente
> donde está instalado `meli_oerp_stock`.

---

## 2. Por qué la hipótesis del `meli_id` vacío no aplica

El dato es cierto — en OrgVit **3.013 de 3.714 bindings tienen `product_product.meli_id` vacío** y el id
vive sólo en `mercadolibre_product.conn_id` (y 301 bindings tienen `pp.meli_id ≠ conn_id`) — pero **no es
la vía de publicación**:

- `meli_oerp_multiple/19.0/models/connection_binding.py:3075` → `meli_id = bindv.conn_id`
- ese `meli_id` viaja a `x_product_post_stock(..., meli_id=meli_id, target=bindv, …)` (`:3300`)
- y ahí `meli_id = meli_id or product.meli_id` (`product.py:3710`) → el fallback a `product.meli_id`
  sólo se usa si el binding no trae `conn_id` (3 bindings en toda la cuenta).

**Sí es un problema aparte** que `product_product.meli_id` esté desincronizado respecto del binding: lo
usa el diagnóstico (`company.py:1717` `AND pp.meli_id LIKE 'M%%'`), lo usa `product_post_price`, y en el
binding 3660 apunta directamente a **otra publicación** (`conn_id=MLM2767494093`, `pp.meli_id=MLM5277681652`).
Es ruido peligroso, pero no la causa de este caso.

---

## 3. ⛔ CAUSA RAÍZ — el invariante de cola se congela (`create_date`)

Es el defecto de producto de verdad, y explica los "bindings congelados" en **cualquier** cliente.

**(a) El campo que gobierna la cola se calcula con `create_date`, no con la fecha del movimiento:**

`meli_oerp/19.0/models/product.py:5241-5269`
```python
def _meli_stock_moves_update( self ):
    for var in self:
        move_dates = []
        if var.stock_move_ids:
            move_dates.extend([m.create_date for m in var.stock_move_ids if m.create_date])   # :5248
        ...  # idem para los componentes de la BoM
                    move_dates.extend([m.create_date for m in bm_pr_id.stock_move_ids ...])   # :5266
        var.meli_stock_moves_update = max(move_dates) if move_dates else False                 # :5269
```

**(b) La cola sólo se alimenta mientras ese valor supere al último push:**

`meli_oerp_multiple/19.0/models/connection_binding.py:2078-2086`
```python
if (bind.meli_stock_moves_update):
    if (bind.stock_update):
        if ( bind.meli_stock_moves_update > bind.stock_update ):
            bind.meli_stock_status = 'update'      # entra a la cola
        else:
            bind.meli_stock_status = 'updated'     # sale de la cola
```

**(c) `stock_update` se sella en CADA push** (`connection_binding.py:3367-3370`), aun sin verificar nada.

**Consecuencia (demostrada):** `max(create_date)` es **monótono pero se congela**. Una vez que existe el
movimiento más nuevo, el valor no vuelve a avanzar nunca. El primer push posterior deja
`stock_update > meli_stock_moves_update` **para siempre** y el binding queda `updated` — fuera de la cola,
sin error, sin log — hasta que se cree una **fila nueva** de `stock_move` para ese producto o componente.

Todo cambio de stock que **no crea una fila nueva** de movimiento queda invisible:
- validar (`draft/confirmed → done`) un movimiento creado días antes → en prod hay **209 movimientos en
  60 días** validados ≥1 día después de creados;
- reservar / desreservar (mueve `qty - reserved`, que es lo que se publica);
- cancelar; editar cantidad de un movimiento existente; ajustes de inventario sobre un quant ya moviéndose.

**Verificación en prod (28/07)** — el `meli_stock_moves_update` del kit es **idéntico** al
`max(create_date)` de los movimientos de su componente, y anterior por semanas al último push:

| Kit | `meli_stock_moves_update` | `max(create_date)` comp. | `max(date)` comp. | último push |
|---|---|---|---|---|
| THLSURINF203X2 | 2026-07-11 18:08:59.496042 | **2026-07-11 18:08:59.496042** | 2026-07-11 18:09:07 | 28/07 |
| THRVRDJZN202X1 | 2026-07-01 17:54:58.49944 | **2026-07-01 17:54:58.49944** | 2026-07-01 17:55:04 | 28/07 |
| TOMVIMA42P | 2026-07-19 19:14:48.355715 | **2026-07-19 19:14:48.355715** | 2026-07-19 19:14:55 | 19/07 |
| YYPMP10012 | 2026-07-21 18:39:40.878501 | **2026-07-21 18:39:40.878501** | 2026-07-21 18:39:52 | 28/07 |

La propagación kit←componente **sí funciona** (`meli_oerp/19.0/models/stock_move.py:85-105`,
`meli_update_boms` STEP 2). Lo que falla es la **fecha** con la que se compara.

**(d) Agravante — el campo no es monótono.** `stock_move.py` ya parcha algunos casos escribiendo
`meli_stock_moves_update = NOW()` por SQL (cancel/unreserve, `meli_oerp_multiple/19.0/models/stock_move.py:879,887,923,957,966`).
Pero cualquier pasada posterior de `_meli_stock_moves_update()` lo **pisa hacia atrás** con
`max(create_date)` → **anula una entrada de cola pendiente**. El parche y el cálculo se contradicen.

### Fix propuesto (F1) — el central
1. En `_meli_stock_moves_update()`: usar **`GREATEST(m.date, m.write_date, m.create_date)`** en lugar de
   `m.create_date`, y **filtrar por `state='done'`** (o incluir `date` sólo de los `done`).
2. Hacerlo **monótono**: `var.meli_stock_moves_update = max(nuevo, valor_actual)`. Nunca retroceder.
   Esto también hace consistente el parche SQL de cancel/unreserve.
3. **Red de seguridad (imprescindible, independiente del punto 1):** un `max_age` de sincronización por
   configuración — `mercadolibre_stock_resync_days` (default 7). Todo binding `updated` con
   `stock_update < now() - max_age` vuelve a la cola en la próxima corrida. Ningún esquema event-driven
   sobre un campo derivado puede garantizar por sí solo que no se pierdan eventos; el barrido periódico sí.
   Hoy `mercadolibre_stock_diagnostic` es la única red y mide con la definición equivocada (§4).
4. Índice compuesto para que el barrido sea barato:
   `(connection_account, meli_stock_status, stock_update)`.

---

## 4. Doble definición de "stock disponible" → falsos positivos del diagnóstico

El publicador y el diagnóstico miden cosas distintas:

| | Publicador | Diagnóstico |
|---|---|---|
| Fuente | `_meli_available_quantity()` (`meli_oerp_stock:385`) | SQL crudo sobre `stock_quant` |
| Honra kits (BoM phantom) | **sí** | **no** |
| Honra ubicaciones/almacén configurado | **sí** (`_meli_virtual_available`) | **no** (todo `usage='internal'`) |
| Honra `meli_default_stock_product` | **sí** | **no** |
| Clamp de negativos | **sí** | vía `GREATEST(...,0)` |

`meli_oerp/19.0/models/company.py:1702-1720`:
```sql
LEFT JOIN ( SELECT sq.product_id, SUM(GREATEST(sq.quantity - sq.reserved_quantity, 0)) AS avail_qty
            FROM stock_quant sq JOIN stock_location sl ON sl.id = sq.location_id
            WHERE sl.usage = 'internal' AND sl.active IS TRUE
            GROUP BY sq.product_id ) sq ON sq.product_id = pp.id
WHERE pp.meli_pub IS TRUE
  AND pp.meli_id LIKE 'M%%'                         -- :1717  deja fuera bindings cuyo id vive en conn_id
```

De ahí salen, verificados uno por uno:
- **"107 activas con stock = 0 en Odoo"** → 116 en el barrido, **17 con cantidad publicada, las 17 kits**.
  Falsos positivos al 100 %.
- **"10 pausadas con stock en Odoo — posible pérdida de ventas"** → usa `mp.meli_last_status='paused'`,
  que está stale (§4.bis). El propio log del diagnóstico muestra CHDM345 `active 72/72`.
- **`AND pp.meli_id LIKE 'M%%'`** (`:1717`, y `mp.conn_id LIKE 'M%%'` en `:1769`) → deja fuera los 3.013
  bindings de OrgVit cuyo id vive sólo en `conn_id`; encima con `LIMIT 100` (`:1772`) por corrida.

### Fix propuesto (F2)
- El diagnóstico debe llamar a **`_meli_available_quantity()`** (la misma función del publicador) para
  decidir "hay drift", aunque sea sobre un candidato preseleccionado por SQL. La SQL puede seguir siendo
  el filtro barato; la **decisión** no puede usar otra definición de stock.
- Cambiar el join a `mercadolibre_product` y usar **`conn_id`** como id de publicación; `pp.meli_id` sólo
  como fallback. Quitar el `LIKE 'M%%'` (o hacerlo `~ '^ML[A-Z]'`, que es lo que se quería expresar).
- `LIMIT` configurable, con cursor/rotación para que en N corridas se recorra todo el catálogo.

### 4.bis — `meli_last_status` sí se refresca, pero sólo por la vía que nunca se recorre
El push **sí** persiste el estado (`connection_binding.py:3222-3226`), pero **sólo** para bindings que
entran a la cola. Los 1.027 `paused` locales nunca entran (§3) → no se refrescan nunca.
Y el diagnóstico, que **lee el estado fresco** en `company.py:1820` (`ml_status = rjson.get('status',…)`),
**lo tira**: no lo escribe en ningún lado. Es una línea de fix.
### Fix propuesto (F3)
En `company.py`, tras el GET, persistir `meli_last_status`/`meli_available_quantity` en el binding
(y en `product_product`) siempre — no sólo en las ramas de acción. Costo: 0 llamadas API extra; ahorra
las ~100 llamadas cada 30 min que hoy se queman sobre publicaciones sanas.

---

## 5. Sobreventa REAL — el mismo stock se publica entero en N publicaciones

El módulo publica `_meli_available_quantity()` **completo** en cada binding, sin reparto ni reserva. Con
kits, el mismo stock se promete dos veces: en la publicación directa del componente y en la del pack.

Medido en OrgVit (28/07), publicaciones `active`:

| Componente | libre real | publicado directo (Nº pubs) | comprometido por kits | **sobre-promesa** |
|---|---|---|---|---|
| GELNONI | 318 | 318 (1) | 633 (2 kits) | **+633** |
| THLSURINF20 | 159 | 318 (**2**) | 159 (1 kit) | **+318** |
| (pid 7364, sin `default_code`) | 61 | 61 (1) | 172 (3) | **+172** |
| THRVRDJZN20 | 71 | 142 (**2**) | 70 (1) | **+141** |
| FENROLE275 | 99 | 0 | 192 (2) | **+93** |
| SPRCRSO473 | 88 | 0 | 176 (2) | **+88** |
| FENCUCO275 | 81 | 0 | 160 (2) | **+79** |
| TOMVIMA5 | 26 | 0 | 52 (2) | **+26** |
| NUTR-22-7AP-30-F | 11 | 22 (2) | 9 (1) | **+20** |
| … (14 componentes en total) | | | | **≈ +1.810 uds** |

Dos mecanismos suman:
- **(i)** un mismo producto publicado en 2 listings recibe el stock completo en cada uno (THLSURINF20:
  159 reales → 318 publicados). Es el comportamiento clásico de los conectores, discutible pero conocido.
- **(ii)** **kits:** el componente se publica solo *y* dentro de 1..N packs. Nadie descuenta. THLSURINF20:
  159 reales contra 159 + 159 + 53×3 = **477 unidades prometidas**.

Es el riesgo comercial de verdad de esta cuenta, y es **estructural del módulo**, no de OrgVit.

### Fix propuesto (F4)
- **Corto (barato, gran valor):** *diagnóstico* nuevo que liste los componentes sobre-prometidos
  (la consulta de arriba, portada a un `action_diagnose_stock_overcommit()` del `mercadolibre.account`),
  para que el cliente decida qué despublicar. **No cambia comportamiento**, sólo hace visible el riesgo.
- **Medio:** política configurable `mercadolibre_stock_allocation` en la configuración de la cuenta:
  `full` (actual, default — no rompe a nadie) · `split_even` · `priority` (una publicación "dueña" del
  componente se lleva el stock, las demás publican el remanente). Aplicarla dentro de
  `_meli_available_quantity()` para que valga en todos los caminos.
- **Encadenado:** cuando un componente se mueve, **re-encolar también los kits que lo contienen** — hoy
  se propaga el `meli_stock_moves_update` (F1 lo arregla) pero no hay garantía de orden ni de que ambos
  se publiquen en la misma tanda.

---

## 6. 18 publicaciones con dos bindings a productos distintos

El índice único es `(connection_account, conn_id, conn_variation_id, product_id)` — **incluye
`product_id`**, así que permite N bindings del mismo `conn_id` apuntando a productos distintos. Nada
impide que dos productos de Odoo publiquen contra el mismo item de ML. En OrgVit: **24 `conn_id`
duplicados, 18 con productos distintos.** Publican cantidades contradictorias; gana el último cron.

Los peores son **mis-bindings** (SKU completamente distinto, sospecha de import mal resuelto):

| Publicación | binding A | binding B |
|---|---|---|
| MLM4213856188 | YYPMP100 (61) | YYPMP10012, el pack ×12 (5) |
| MLM5277681652 | TOMVIMA42P (2) | TOMVIMA52P (13) |
| MLM1611820115 | WEL-01-ACCC-930-F (7) | WEL-01-SOSS-930 (4) |
| MLM2765193731 | GNVPILPL30 (29) | PJVICA60 (0) |
| MLM5356578534 | BRMCGCM680 (0) | WELLMAGGLY300 (3) |
| MLM5438884508 | HUORSESWBACH45C198 (76) | WAFOCO35 (8) |
| MLM5684277384 | BRMGFSWRF680 (6) | TWHPOT20 (10) |
| MLM2283332372 | TRMEDALERO16 (6) | TRMERODARO16 (13) |

`MLM4213856188` es el que produjo el "61 → 5 parcial" que reportó soporte: **no fue un push a medias, son
dos bindings peleándose la publicación.** Y publicar 61 en un listing que es un pack de 12 sí es
sobreventa real (61 packs = 732 unidades sobre 61 disponibles).

### Fix propuesto (F5)
- **Constraint / validación:** `_check_unique_conn_id_per_account` — un `(connection_account, conn_id,
  conn_variation_id)` no puede tener más de un `product_id`. Como no se puede imponer de golpe sobre bases
  existentes, empezar por: (a) un **diagnóstico** que los liste, (b) un **wizard de resolución** (elegir el
  binding correcto, archivar el otro), (c) recién después el constraint.
- Emparejar con el barrido que ya pidió la sesión de Aramid:
  `mercadolibre_product.product_tmpl_id <> product_product.product_tmpl_id` — misma familia de defecto.

---

## 7. El test `[4d]` del diagnóstico da un falso OK

`meli_oerp_multiple/19.0/models/connection_account.py:2559-2585` — publica **el mismo valor que ya tiene**
y concluye que el endpoint funciona:

```python
current_avail = item_json.get('available_quantity', 0)      # :2555
legacy_body = {"available_quantity": int(current_avail)}    # :2561  ← mismo valor
...
lines.append("    → PUT legacy /items FUNCIONA ✓")          # :2584  ← sólo mira el HTTP 200
```

Un 200 sobre un no-cambio no prueba que un cambio se aplique. (En este caso el veredicto era correcto —
§1 —, pero el test no lo demostró.)

### Fix propuesto (F6)
Publicar un **valor distinto y seguro** (`current_avail + 1` si `current_avail > 0`, si no `1`), **releer**
el item, comparar, y **restaurar** el valor original. Reportar `aplicado / no aplicado (200 pero sin
efecto)` en vez de `FUNCIONA ✓`. Mismo patrón para 4b/4c/4e. Bajo riesgo si se restaura.

---

## 8. Otros hallazgos menores (mismo recorrido)

**(a) `return {}` después de tragarse la excepción** — `meli_oerp/19.0/models/product.py:4939-4949`:
el `except` registra el error en `meli_stock_error` pero la función **retorna `{}` (= éxito)**. El
llamador marca el binding como publicado. Mismo patrón en `x_product_post_stock`
(`meli_oerp_multiple/19.0/models/product.py:4569-4583`): si la excepción cae después del PUT,
`posted_try` ya es `True` → devuelve `{'_timing':…}` sin `error`.
→ **Fix:** devolver `error` cuando lo hubo. Es de la misma familia que los 4 branches
`claude/fix-swallowed-db-errors-tx-poisoning-*` pendientes de merge.

**(b) Ninguna verificación de lo publicado.** El módulo nunca compara el `available_quantity` que
devuelve ML contra el que mandó — las líneas que lo hacían están comentadas
(`meli_oerp_multiple/19.0/models/product.py:4548-4553`). Un 200 con el valor viejo pasa por éxito.
→ **Fix (F7):** verificar `rjson['available_quantity'] == enviado`; si no coincide, `stock_error` y
`meli_stock_status='revision_not_applied'` (estado nuevo). Con esto el gap del handoff (200-sin-efecto)
sería **detectable** aunque hoy no se esté dando.

**(c) `for bindv in self: … return {}`** — `connection_binding.py:3394` (y `product_post_price`,
`product_post_title`): el loop **retorna en el primer registro**. Cualquier llamador que pase un
recordset múltiple procesa **sólo el primero**, en silencio. Hoy los callers iteran de a uno, pero es una
trampa latente. → **Fix:** acumular y retornar al final.

**(d) Reactivación sin backoff** — `meli_oerp/19.0/models/company.py:1832-1847`: se reactiva en cada
corrida sin contador de intentos. FENPIGI2754P (MLM4948220924) lleva días en ese loop porque ML la
vuelve a pausar por calidad de ficha. → **Fix (F8):** `meli_reactivate_attempts` + `meli_reactivate_last`
en el binding; backoff exponencial (1h, 4h, 12h, 24h) y a los N intentos `meli_stock_status='revision_reactivate_failed'`
con aviso al chatter. Reset del contador cuando ML confirma `active`.

---

## 9. Prioridad y plan de versiones

| # | Fix | Impacto | Riesgo | Versión |
|---|---|---|---|---|
| **F1** | `create_date` → `GREATEST(date, write_date, create_date)` + monotonía + **resync por antigüedad** | 🔴 alto — corta el drift silencioso en toda la flota | medio (toca la cola: hay que vigilar el volumen de la primera tanda) | **26.87** |
| **F7** | verificar el `available_quantity` devuelto + `revision_not_applied` | 🔴 alto — hace visible el "200 sin efecto" | bajo | **26.87** |
| **F3** | persistir `meli_last_status` en el diagnóstico | 🟠 medio — limpia falsos positivos, ahorra API | muy bajo | **26.87** |
| **F6** | test `[4d]` con valor distinto + relectura + restore | 🟠 medio — deja de mentir | bajo | **26.87** |
| **F2** | diagnóstico usando `_meli_available_quantity()` + `conn_id` + sin `LIKE 'M%'` | 🔴 alto — hoy el diagnóstico oficial es ruido | medio | **26.88** |
| **F5** | diagnóstico de `conn_id` duplicados + wizard; constraint después | 🟠 medio — datos, no sobreventa directa | bajo (fase 1) | **26.88** |
| **F8** | backoff de reactivación | 🟡 bajo — ruido y API | bajo | **26.88** |
| **F4a** | diagnóstico de sobre-promesa por componente/kit | 🔴 alto (visibilidad) | nulo (read-only) | **26.88** |
| **F4b** | política `mercadolibre_stock_allocation` | 🔴 alto (comercial) | **alto** — cambia lo que se publica | **26.90**, con opt-in y piloto |
| (a)(c) | `return {}` tras except · loop que retorna en el primero | higiene | bajo | **26.87** junto a los branches de tx envenenada |

**Orden de trabajo:** 26.87 en `19.0` (donde está el cliente de referencia) → forward/backport a
16/17/18 por [[sources-align]] (fechas mandan, manifest = versión más alta) → bump de manifests y
migraciones por versión. F1 y F7 conviene que viajen juntos: F7 es la red que hace observable a F1.

---

## 10. Alcance de flota

- **F1, F3, F6, F7, (a), (c), F5, F8:** afectan a **todos** los clientes del suite. F1 y F7 en particular
  no dependen de kits ni del sitio: la cola se congela en cualquier instalación.
- **Kits (§1, §5, F2, F4):** sólo donde está instalado **`meli_oerp_stock`** — es el único módulo con la
  rama BoM activa (`meli_oerp` la tiene con `1==2`). Hoy figura en la ficha de ~20 clientes
  (AR: justdistribution, legion-extranjera, delbre, elvimarta, rpm-motos · CO: accesorios-adhesivos,
  koreautos, vitaliah · MX: acotron, elekmex, itera, organicoyvital, r-d-metabolismo, refatodo, scoremx,
  solsun, turefaccionaria, tus-refacciones · UY: aramid, mundo-mascota). **Verificar cliente por cliente**
  cuáles tienen BoMs `phantom` publicadas antes de dar por afectado a ninguno.
- El defecto de `conn_id` duplicado es de datos: hay que barrerlo por cliente
  (misma familia que el `product_tmpl_id` desalineado reportado por Aramid el 28/07).

---

## 11. Mitigación inmediata en OrgVit

**No hace falta ninguna sobre las 4 publicaciones**: no hay sobreventa ahí (§1). Lo que sí conviene, en
este orden:

1. **Nada urgente que escribir en prod.** Frenar/pausar esas 4 sería **perder ventas legítimas**.
2. **Sí revisar los 18 `conn_id` duplicados** (§6) — ahí hay sobreventa real y producto equivocado. Es
   corrección de **datos del cliente**, no de código: requiere decidir con el cliente cuál binding vale.
   Empezar por `MLM4213856188` (YYPMP100 vs pack ×12) y `MLM5277681652` (TOMVIMA42P vs 52P).
3. **Sobre-promesa por componente compartido** (§5, ~1.810 uds): es una decisión comercial del cliente
   (¿despublica el pack, o el suelto, o acepta el riesgo?). Llevarle la tabla, no tocar nada.
4. **Re-encolado manual sólo si se quiere refrescar ya**: poner `meli_stock_status='update'` en los
   bindings con `stock_update` más viejo que N días es seguro (es exactamente lo que hará F1), pero
   **requiere confirmación de FCA** porque escribe en la prod del cliente y dispara tanda de cron.
