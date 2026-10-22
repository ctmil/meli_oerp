# -*- coding: utf-8 -*-
# 26.188 (un caso): sale.order.meli_handling_limit pasa a almacenado (para ordenar la
# lista). Se crea y llena la columna por SQL antes de cargar el modelo, así Odoo no
# recomputa el related registro por registro en bases grandes.
import logging
_logger = logging.getLogger(__name__)


def _has_column(cr, table, column):
    cr.execute("""SELECT 1 FROM information_schema.columns
                   WHERE table_schema = current_schema()
                     AND table_name = %s AND column_name = %s""", (table, column))
    return bool(cr.fetchone())


def migrate(cr, version):
    if not version:
        return
    cr.execute("ALTER TABLE sale_order ADD COLUMN IF NOT EXISTS meli_handling_limit timestamp")
    # Guarda (26.226, detectado en un cliente): mercadolibre_shipment.estimated_handling_limit
    # nace en 26.16. Al actualizar desde un build anterior la columna todavía no existe
    # (no hay nada que copiar) y el UPDATE abortaba el -u entero (rc=255, "bad query").
    if not _has_column(cr, 'mercadolibre_shipment', 'estimated_handling_limit'):
        _logger.info("meli_oerp 26.222: mercadolibre_shipment.estimated_handling_limit no existe aún "
                     "(upgrade desde < 26.16); nada que copiar")
        return
    cr.execute("""
        UPDATE sale_order so
           SET meli_handling_limit = s.estimated_handling_limit
          FROM mercadolibre_shipment s
         WHERE so.meli_shipment = s.id
           AND s.estimated_handling_limit IS NOT NULL
    """)
    _logger.info("meli_oerp 26.222 (SLA, era 26.188): sale_order.meli_handling_limit llenado en %s pedidos", cr.rowcount)
