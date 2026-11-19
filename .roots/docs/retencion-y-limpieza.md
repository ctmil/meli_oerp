# Retención y limpieza automática (autovacuum) — suite meli

Todo corre en **Base: Auto-vacuum internal data** (`ir.cron` diario del core). Odoo commitea después de
cada método `@api.autovacuum` ⇒ cada GC es su propia transacción; si uno falla, se loguea y sigue el resto.
Motor común (`mercadolibre.notification._gc_meli_run_batches`, desde 26.338/26.425): candidatos por SQL con
tope, lotes `FOR UPDATE SKIP LOCKED` que re-chequean las condiciones, savepoint por lote, `lock_timeout` 2 s,
fila a fila si un lote choca (lock / serialización / deadlock / FK de terceros). **Nunca espera a nadie.**
**Nunca ocupa el worker de cron (26.425):** la selección de candidatos lleva `statement_timeout` propio
(60 s; si vence, log y nada hoy), el loop de lotes tiene presupuesto de 300 s (lo que quede, mañana), y el
NOT EXISTS por resource del GC de notificaciones usa el índice parcial
`mercadolibre_notification_live_resource_idx` (resource WHERE state IN RECEIVED/PROCESSING/FAILED; se crea en el
`-u`). Caso que lo motivó (bus 18-nov): 1,57 M filas ⇒ la selección tardó >11 min y las ventas no entraban.
Banco 19 (1,5 M filas, 500 ítems con 1.500 hermanas viejas y la última viva): **116 s ⇒ 5,0 s** con el mismo
tope de 10.000; 6,4 s con el tope nuevo de 50.000. Chatter: 50.000 borrados en 2,3 s con 2,3 M mensajes en la
tabla (2 M de otros modelos, intactos). `-u meli_oerp` con 1,5 M filas: 6,8 s incluido el índice.

| Parámetro del sistema (`ir.config_parameter`) | Default | Qué limpia | Desde |
|---|---|---|---|
| `meli_oerp.notification_days` | 90 (0 = nunca) | `mercadolibre.notification` SUCCESS/FAILED terminadas | 26.335 |
| `meli_oerp.proxy_audit_days` | 90 (0 = nunca) | `meli.proxy.audit` (auditoría del host alternativo, #661) | — |
| `meli_oerp.chatter_days` | **0 = apagado** (1..6 ⇒ 7) | `mail.message` `notification` de mercadolibre.orders/.shipment/.account | 26.425 |
| `meli_oerp.cron_execution_days` | **0 = apagado** | `mercadolibre.cron.execution` (meli_oerp_multiple) | 26.425 |
| `meli_oerp.gc_max_rows` | 50.000 | tope de filas por corrida de cada GC (antes 500×20 = 10.000 fijo en notificaciones) | 26.425 |

## `_gc_meli_chatter` (26.425, pedido 535 The3letters #696)
**Borra:** `mail.message` con `model IN (mercadolibre.orders, mercadolibre.shipment, mercadolibre.account)`,
`message_type = 'notification'`, `date < hoy - chatter_days`.
**Conserva aunque sea viejo:** `comment` (notas/mensajes de personas) y `email`; otros modelos (sale.order,
account.move, stock.picking: **nunca**); con adjuntos; destacados (`starred_partner_ids` 16–19 /
`bookmarked_partner_ids` 20); con `mail.tracking.value` (16–19; en 20 el tracking es `message_type='tracking'`);
con `mail.mail` (cola/error); con hijos (`parent_id`); con reacciones; con notificación inbox **sin leer**; con
marca `<!-- meli-once:… -->`. Las condiciones se arman desde los metadatos del ORM de cada versión.
**DELETE por SQL, no `unlink()`:** en 17+ `unlink` manda un bus `mail.message/delete` por partner; las tablas
hijas son `ondelete=cascade` en el core (`parent_id` = set null).

### Efecto funcional (medido sobre origin/19.0, 19-nov-2026)
Lectores de chatter del suite: `versions.meli_message_already_posted` / `meli_message_text_posted` (once_key,
guardas de legado), `sale_order._meli_ready_note_posted`, `sorder.message_ids[:50]` («PRODUCTO NO
ENCONTRADO») ⇒ **todos sobre sale.order**. Sobre mercadolibre.account sólo `_meli_injobs_alert`
(multiple), que mira **los mensajes de hoy**. ⇒ con N ≥ 7 d **no hay efecto funcional**. Si en el futuro
se postea con `once_key` sobre estos modelos, la exclusión por marca evita que el aviso se repita.
⚠️ Si agregás un lector de chatter sobre mercadolibre.orders/shipment/account que mire más de 7 días atrás,
actualizá esta sección y `_GC_CHATTER_MIN_DAYS`.

## `_gc_meli_cron_execution` (meli_oerp_multiple 26.425)
Borra `date_start < hoy - N`, salvo `running` y **la última de cada (cuenta, tipo)** (de ahí lee
`mercadolibre.cron.status` la «Última ejecución»). Las estadísticas de cron.status pasan a la ventana
retenida. `cleanup_old_records(days)` (antes sin llamador) delega acá.

## Activar en un cliente
`Ajustes ▸ Técnico ▸ Parámetros del sistema` (o `odoo shell`):
`meli_oerp.chatter_days = 30` · `meli_oerp.cron_execution_days = 30` (opcional `meli_oerp.gc_max_rows`).
La primera corrida borra hasta `gc_max_rows` por GC; un atraso grande se baja en varios días.
Después de un borrado grande, Postgres reutiliza el espacio pero el archivo no se achica sin `VACUUM FULL`
(Odoo.sh: no se pide; el crecimiento se frena igual).
Medir antes/después: `SELECT model, message_type, count(*) FROM mail_message WHERE model LIKE 'mercadolibre.%' GROUP BY 1,2;`

Tests: `--test-tags meli_gc_chatter` (meli_oerp 9 + multiple 4) y `meli_696` (GC de notificaciones).
