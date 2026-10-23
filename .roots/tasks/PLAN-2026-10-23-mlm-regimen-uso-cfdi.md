# PLAN 2026-10-23 — MLM: régimen fiscal y uso de CFDI desde billing-info de ML (meli_oerp 16-19)
**Qué:** escribir `l10n_mx_edi_fiscal_regime` (partner) y `l10n_mx_edi_usage` (partner 17+ y sale.order con
l10n_mx_edi_sale) a partir de billing-info (v2 `taxes.taxpayer_type.id` / `taxes.cfdi.id`; legacy
`TAXPAYER_TYPE_ID` código SAT / `CFDI`).
**Por qué:** hallazgo 23-oct (partners/Mexico/the-3-letters/.roots/tasks/PLAN-2026-10-23-535-verificar-billing-v2-mlm.md):
ML los manda y el módulo nunca los escribe; clientes MX con l10n_mx_edi (535, 525, 539…) los cargan a mano.
FCA aprobó desarrollarlo (23-oct). Pedido del coordinador a meli-keeper.
**Sobre:** meli_oerp 16.0/17.0/18.0/19.0, ramas `claude/mlm-cfdi-<v>` desde origin/<v> (26.290). Bump de los 5 módulos del suite.
**Diseño:**
- Pura `_meli_mx_cfdi_codes(billing_info)` → (régimen, uso); `_meli_mx_cfdi_partner_vals(current, codes, valid_reg, valid_use, is_new)`.
- Destino = contacto fiscal final (partner_invoice_id, o partner_id si VAT genérico/dedup). Se salta si `meli_update_forbidden`.
- Regla: partner creado en ESTA importación ⇒ se escribe el valor de ML; existente ⇒ sólo si está vacío; distinto ⇒ NO se pisa + log.
  (Odoo pone 601 por default en partners MX ⇒ partners preexistentes no se corrigen: limitación documentada.)
- sale.order (17+ con l10n_mx_edi_sale): uso por operación; se escribe si venta nueva, o vacío/'G03' (default) y sin facturas.
- Sin l10n_mx_edi: no-op. Código fuera de la selección: no-op + log.
- 16.0: régimen sí (l10n_mx_edi_40); uso no vive en partner ni en sale.order ⇒ sólo régimen.
**Tests:** tests/test_mlm_cfdi_pure.py (AST, sin Odoo): 601/G01, 612/G03, 616/S01 anonimizados (v2 y legacy),
manual no se pisa, módulo no instalado, código inválido. Falla sin el cambio, pasa con él, en las 4 versiones.
**Build:** max+1 de las 4 series × 5 módulos tras fetch. 26.291 tomado por 452 (lock 01:55Z) ⇒ 26.292 salvo que cambie.
**Criterio de terminado:** test rojo→verde en ≥2 versiones; landeado FF en origin/16-19 con bump de los 5 módulos,
ls-remote == local; o ramas claude/* pusheadas y reporte si no se cumple. Sin deploys a clientes.
## Avance
- [x] lectura origin/<v> (orders.py: buyer block, BILLING_SPLIT, create/update fiscal, sale order vals) + l10n_mx_edi 16-19
- [x] worktrees claude/mlm-cfdi-<v> (lock meli_oerp tomado por 452/26.291 ⇒ desarrollo en ramas propias)
- [x] test puro (rojo) — tests/test_mlm_cfdi_pure.py: sin el cambio FAILED (2 fail, 12 err) en 16/17/18/19
- [x] implementación por patcher idéntico en 16/17/18/19 (anclas únicas, py_compile ok)
- [x] test verde 14/14 en 16/17/18/19; test_billing_info_endpoint_pure sigue OK
- [x] reserva 26.292 en el bus (comms.md, grep -c = 1); 26.291 = 452 (L49008)
- [x] lock 5 módulos 02:08Z; 26.291 (452) landeó; fetch rc=0, max=291 ⇒ 26.292; rebase limpio, tests verdes; bump 5×4
- [x] push FF + ls-remote (26.292 landeada 02:2xZ, bus L49054)
- [x] roots-refresh: journal/changelog.md 26.292 en los 5×4

## Paso 2 — override opt-in del default 601/G03 (pedido coordinador 23-oct, build 26.294)
**Qué:** opción de compañía `mercadolibre_mx_cfdi_override_default` (Boolean, default False), visible en la pestaña
de configuración ML (res.config.settings related). Prendida: contacto EXISTENTE con régimen '601' y ML manda otro código
válido ⇒ se escribe el de ML (log `MX_CFDI override 601→X`). Uso CFDI (17+): igual sólo si el contacto tiene 'G03'.
NUNCA pisa un valor distinto de 601/G03 (carga manual) ni contactos `meli_update_forbidden`. 16.0: sólo régimen.
**Por qué:** Odoo pone 601 por default ⇒ personas físicas (612) y público en general (616) ya cargados quedan mal (limitación de 26.292).
**Sobre:** meli_oerp 16/17/18/19, ramas `claude/mlm-cfdi-override-<v>` desde origin/<v> (26.292). Si multiple tiene flags
equivalentes por cuenta (meli config), respetarlo también. Bump 5 módulos × 4 versiones.
**Build:** 26.293 RESERVADO para #239 (sin landear) ⇒ 26.294 (max 4×5 + bus, +1). Reservar en bus, grep -c.
**Tests:** tests/test_mlm_cfdi_pure.py: apagada = 26.292; prendida 601→612, 601→616; no pisa 603; bloqueado; sin l10n_mx_edi no-op.
Rojo sin el cambio, verde con él en 16-19; resto de *_pure.py verde. -u en banco local ≥1 versión rc=0 (campo+vista).
**Terminado:** landeado FF en origin/16-19 de los 5 con 26.294, ls-remote == local, changelog. Nada a clientes/prod.
### Avance paso 2
- [x] fetch 5 módulos rc=0; origin 16-19 ×5 = 26.292; max refs = 26.293 (accounting claude/462-239-*); reserva 26.294 en bus (grep -c = 1)
- [x] patrón: `'<flag>' in config._fields and config.<flag>`; config = res.company o mercadolibre.configuration (multiple: gemelo en connection_configuration.py + connection_account_view.xml; sale.py llama super con config de cuenta)
- [x] tests rojos: test_mlm_cfdi_pure.py 23 tests, contra origin 26.292 FAILED (2 fail, 8 err) en 16/17/18/19
- [x] implementación por patcher idéntico 16-19: orders.py (_MELI_MX_ODOO_DEFAULTS, override_default, config=config, log override), company.py + company_view.xml; multiple: gemelo en ramas claude/mlm-cfdi-override-<v> (worktrees meli_oerp_multiple/claude-mlm-cfdi-override-<v>)
- [x] tests verdes 23/23 en 16-19; resto *_pure.py OK (igual que base)
- [x] -u banco local 18 (leaves/2026-10-23-mlm-cfdi-override-banco)
- [x] sync-lock 5 módulos (03:24-03:28Z), bump 26.294 + changelog 5×4; banco 18: base origin 26.292 (-i multiple) → -u meli_oerp,multiple rc=0, 0 ERROR, columna en res_company y mercadolibre_configuration, campo en ambas vistas, default False
- [x] push FF sin force rc=0, ls-remote == local en las 20 (meli_oerp 16 377d9a39 17 fd2667d0 18 dd7439dd 19 720a4cdf); manifest-version-check: origin 5×4 = 26.294; locks liberados; bus RELEASE 26.294
