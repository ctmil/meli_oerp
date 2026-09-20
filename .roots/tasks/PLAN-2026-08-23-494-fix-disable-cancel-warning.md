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
- [ ] Fix del flag + fix del llamador (dict vs bool) en 16.0.
- [ ] Fix de los 3 fixtures de test + test de regresión del propio defecto.
- [ ] Correr los tests en el TEST de Shoppy y anotar el número REAL.
- [ ] Port a 17.0 y 18.0 (bug activo) y alineación de 19.0.
- [ ] `.roots` (changelog, fixes-log) + liberar lock + avisar por `comms.md`.
