# PLAN 2026-08-23 — `disable_cancel_warning_enabled = False`: la cancelación que finge cancelar

**Frente:** #494 (SHOPPY 502, Odoo 16.0) · **Módulo:** `meli_oerp` · **Autoriza:** FCA, 23-ago-2026
**Branch:** `claude/494-fix-disable-cancel-warning` · **Base 16.0:** `d40985cf`
(= `claude/494-cancelar-venta-al-cancelar-ml`, que a su vez sale de `origin/16.0` = `6e63ae77`)
**Lock:** `sync-lock.sh acquire meli_oerp` tomado como `meli-keeper-494-cancelwarning`.

## QUÉ

`meli_oerp/models/versions.py` → `disable_cancel_warning_enabled = False`, y los 4 call sites
hacen `with_context(disable_cancel_warning=disable_cancel_warning_enabled).action_cancel()`.

En el core de Odoo **16/17/18**:

```python
def _show_cancel_wizard(self):
    if self.env.context.get('disable_cancel_warning'):
        return False
    return any(so.state != 'draft' for so in self)
```

Con la clave en `False` el guard **no corta** ⇒ `action_cancel()` **devuelve el dict del wizard
`sale.order.cancel`** y **no cancela nada**. No lanza excepción, no loguea. Y el llamador
(`meli_cancel_with_detail`, paso 5) postea el motivo en el chatter igual ⇒ **queda escrito que se
canceló algo que sigue vivo.**

## POR QUÉ (quién lo pidió / qué lo disparó)

Lo encontró la sesión que validó el server de TEST de Shoppy corriendo por primera vez
`tests/test_meli_cancel.py` del #494 (comms 2026-08-23T14:55:55Z). Reproducido en `odoo shell`
con rollback y control positivo. FCA autorizó el arreglo el 23-ago.
**Bloquea al propio #494:** el re-drain que aquel branch agrega reintentaría en cada ciclo del
cron y no cancelaría nunca ninguna venta confirmada.

## SOBRE QUÉ

| Versión | ¿Aplica? | Por qué |
|---|---|---|
| 16.0 | **SÍ (bug activo)** | `_show_cancel_wizard()` lee la clave; `action_cancel()` devuelve el wizard |
| 17.0 | **SÍ (bug activo)** | idem 16 (`sale_order.py:1102`) |
| 18.0 | **SÍ (bug activo)** | idem 16 (`sale_order.py:1315`) |
| 19.0 | **NO hay bug, sí alineación** | el core 19 **eliminó** el wizard y `disable_cancel_warning`: `action_cancel()` siempre llama `_action_cancel()`. La clave es inerte. |

## CRITERIO DE TERMINADO

1. `versions.py` con el valor correcto **y** explicado (por qué `False` = "nunca cancela").
2. `meli_cancel_with_detail()` **distingue dict de bool**: sólo da por cancelada la venta si
   `state == 'cancel'`; si no, **no** postea el `cancel_msg` como si hubiera cancelado.
3. Los 3 errores de fixture de `tests/test_meli_cancel.py` (mueren en `invoice.action_post()` por
   `l10n_latam_document_type_id` de la localización AR) arreglados: los tests **llegan al código**.
4. Tests corridos **dentro de Odoo, contra el addon instalado** en el server de TEST de Shoppy.
   Antes: **5 de 10**. Después: el número real, con `--test-tags` que efectivamente matchee
   (`meli_cancel` está `@tagged`, no cae en el "0 de 0").
5. Branches pusheados en las versiones donde aplica, con manifest bumpeado a un número libre.
6. `.roots` al día (changelog / fixes-log) y lock liberado.

## NÚMEROS DE MANIFEST ELEGIDOS (releer tras cualquier rebase)

Máximos tomados hoy en `origin`: 16.0 → 26.96 (#411) · 17.0 → 26.95 · 18.0 → 26.95 · 19.0 → 26.95.

- **16.0.26.97** · **17.0.26.96** · **18.0.26.96** · **19.0.26.96**

## LÍMITES

- NO deployar. NO tocar producción de ningún cliente. NO contestar tickets.
- Otro agente está deployando el #524 a la prod de Shoppy: toca `meli_oerp_accounting` y
  `meli_oerp_multiple`; yo sólo `meli_oerp`.
- Merge a la rama de deploy: **lo confirma FCA**.

## PASOS

- [x] Diagnóstico read-only: core 16/17/18/19, call sites, historia del flag.
- [x] Averiguar **por qué** estaba en `False` (ver `.roots/debug/fixes-log.md`).
- [x] Plan escrito (esto) y pusheado ANTES de la primera escritura de código.
- [x] Fix del flag + fix del llamador (dict vs bool) en 16.0 — `3ebe1625`.
- [x] Fix de los fixtures de test + tests de regresión del propio defecto — `66c9cb8b`, `3f0ffe43`.
- [x] Tests corridos en el TEST de Shoppy. **ANTES 5/10 · DESPUÉS 14/14.**
- [x] Port a 17.0 (`a1a2ac6f`) y 18.0 (`0c8fc4d7`); alineación de 19.0 (`156f10d2`).
- [x] `.roots` (changelog, fixes-log) al día en las 4 versiones.
- [ ] Liberar lock + avisar por `comms.md`.
- [ ] **Lo confirma FCA:** merge a las ramas de deploy y deploy. NO hecho.

## RESULTADO DE LOS TESTS (medido, no heredado)

Todo en el server de TEST de Shoppy (`149.50.137.28`), db `test_2_9_2026`, **dentro de Odoo**
(`-u meli_oerp --test-enable --test-tags meli_cancel`), contra el addon del `addons_path`
(`/opt/odoo/sources/meli-staging-shoppy`). `meli_cancel` **sí** está en `@tagged`, así que el
selector matchea: no es un "0 de 0".

| corrida | código | tests | resultado |
|---|---|---|---|
| **ANTES** | integración #494+#411 (`ffafcdf`, 26.96) | 10 | **2 failed + 3 errors → 5 pasan** |
| paso 1 | + fix del flag y del llamador | 14 | 1 failed + 3 errors → 10 pasan |
| paso 2 | + fixture (diario no electrónico, cadena de albaranes) | 14 | 1 failed + 0 errors → 13 pasan |
| **DESPUÉS** | + fixture del re-drain (`date_created`) | 14 | **0 failed, 0 errors → 14/14**, RC=0 |
| **mutación** | código PRE-fix + tests NUEVOS | 14 | **4 failed + 2 errors → 8 pasan** |

**14 tests distintos arrancaron y 0 se saltearon** (`skip` = 0 en el log): ninguno pasa por no
ejercitar nada. La fila de **mutación** es la que lo prueba de verdad: con el código viejo y los
tests nuevos la suite se pone en rojo ⇒ **detecta el defecto**, no lo esquiva.

Y el dato más limpio: **`test_cancel_confirmed_not_delivered` no lo toqué** y pasó de FAIL a PASS
sólo por el cambio de código.

## LO QUE APARECIÓ AL ARREGLAR EL FIXTURE (y no estaba diagnosticado)

1. **Segundo muro detrás del tipo de documento:** el diario de ventas por defecto es
   **electrónico**, así que `action_post()` llama a `do_pyafipws_request_cae()` y **pide un CAE
   real a AFIP**. En TEST corta por certificado; en una instancia con el certificado cargado
   **un test emitiría un comprobante fiscal, y el CAE no se deshace con un rollback**. El fixture
   ahora elige un diario **sin `afip_ws`**.
2. **`test_cancel_delivered_creates_return` no era un defecto del producto:** el fixture validaba
   `order.picking_ids[:1]`, que en el almacén multi-paso de Shoppy es el **PICK (interno)**;
   `_meli_return_done_pickings()` filtra por `outgoing` y no tenía nada que devolver. Ahora se
   valida **toda la cadena** hasta que el albarán de SALIDA queda en `done`.
3. **`test_redrain_...` no seteaba `date_created`**, y el dominio del re-drain filtra por fecha ⇒
   el pedido quedaba fuera del barrido y el test medía 0 creyendo que medía el re-drain.

## ERROR PROPIO, ANOTADO

El script con el que porté a 17/18/19 **truncó la segunda rama del wizard manual** ("Desbloquear y
Cancelar"): cortaba en la primera línea de warning. Compilaba, y los chequeos agregados
("helper definido", "cero usos del patrón viejo") daban **verde**. Lo agarró contar los call sites
**uno por uno** contra 16.0 (3 esperados, había 2). Reparado en `a1a2ac6f` / `0c8fc4d7` / `156f10d2`.
**Un chequeo que suma no distingue "está" de "está completo".**
