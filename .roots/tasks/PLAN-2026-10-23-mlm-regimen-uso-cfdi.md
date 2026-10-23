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
- [ ] push FF + ls-remote
- [x] roots-refresh: journal/changelog.md 26.292 en los 5×4
