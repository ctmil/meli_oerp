# -*- coding: utf-8 -*-
"""[#494 Shoppy] Inicializa sale_order.meli_cancel_pending sobre el historico.

El campo es computed+store: al instalarse, Odoo lo calcula solo para los registros
que toque el recompute. Sembrarlo por SQL garantiza que el filtro
"Cancelado en ML, vivo en Odoo" muestre el backlog COMPLETO desde el minuto uno —
que es justamente lo que el cliente pidio poder auditar por su cuenta.

Es idempotente y no toca ninguna otra columna: solo escribe el booleano derivado
de (meli_status = 'cancelled' AND state <> 'cancel'), que es la definicion exacta
del compute.
"""
import logging
_logger = logging.getLogger(__name__)


def _has_column(cr, table, column):
    cr.execute(
        """SELECT 1 FROM information_schema.columns
           WHERE table_name=%s AND column_name=%s""",
        (table, column),
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    if not _has_column(cr, "sale_order", "meli_cancel_pending"):
        # La columna la crea el ORM en el update del modulo; si todavia no esta,
        # el recompute normal de Odoo se encarga. No es un error.
        _logger.info("#494: sale_order.meli_cancel_pending aun no existe, nada que sembrar.")
        return
    if not _has_column(cr, "sale_order", "meli_status"):
        _logger.warning("#494: sale_order.meli_status no existe — no se puede sembrar meli_cancel_pending.")
        return

    # PASO 1 — refrescar meli_status desde el pedido de ML, SOLO para cancelados.
    # sale_order.meli_status es un campo almacenado que en la practica solo se
    # reescribe como efecto lateral del compute NO almacenado _meli_status_brief,
    # o sea cuando alguien ABRE la venta. La verdad vive en mercadolibre_orders.status.
    # Sin este paso el filtro nuevo arrancaria mostrando de menos, que es peor que no
    # tenerlo. Acotado a 'cancelled': no se toca ningun otro estado.
    if _has_column(cr, "mercadolibre_orders", "status") and _has_column(cr, "mercadolibre_orders", "sale_order"):
        cr.execute("""
            UPDATE sale_order so
               SET meli_status = 'cancelled'
              FROM mercadolibre_orders mo
             WHERE mo.sale_order = so.id
               AND mo.status = 'cancelled'
               AND (so.meli_status IS DISTINCT FROM 'cancelled')
        """)
        _logger.info("#494: meli_status='cancelled' propagado a %s venta(s) desde el pedido ML.", cr.rowcount)
    else:
        _logger.warning("#494: no se pudo leer mercadolibre_orders.status/sale_order — "
                        "meli_cancel_pending se siembra solo con lo que ya tenga la venta.")

    # PASO 2 — sembrar el booleano derivado (misma definicion exacta que el compute).
    cr.execute("""
        UPDATE sale_order
           SET meli_cancel_pending = (meli_status = 'cancelled' AND state <> 'cancel')
         WHERE meli_cancel_pending IS DISTINCT FROM (meli_status = 'cancelled' AND state <> 'cancel')
    """)
    _logger.info("#494: meli_cancel_pending sembrado en %s venta(s).", cr.rowcount)

    cr.execute("SELECT COUNT(*) FROM sale_order WHERE meli_cancel_pending")
    pending = cr.fetchone()[0]
    if pending:
        # WARNING y no info: son ventas canceladas por MercadoLibre que en Odoo siguen
        # vivas, con su factura emitida y sin cobrar. Si esto se loguea como informacion
        # nadie lo mira.
        _logger.warning(
            "#494: %s venta(s) canceladas en MercadoLibre siguen VIVAS en Odoo. "
            "Verlas en Ventas con el filtro 'Cancelado en ML, vivo en Odoo'.",
            pending,
        )
