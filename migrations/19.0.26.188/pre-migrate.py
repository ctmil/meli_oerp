# -*- coding: utf-8 -*-
# 26.188 (#431): sale.order.meli_handling_limit pasa a almacenado (para ordenar la
# lista). Se crea y llena la columna por SQL antes de cargar el modelo, así Odoo no
# recomputa el related registro por registro en bases grandes.
import logging
_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("ALTER TABLE sale_order ADD COLUMN IF NOT EXISTS meli_handling_limit timestamp")
    cr.execute("""
        UPDATE sale_order so
           SET meli_handling_limit = s.estimated_handling_limit
          FROM mercadolibre_shipment s
         WHERE so.meli_shipment = s.id
           AND s.estimated_handling_limit IS NOT NULL
    """)
    _logger.info("meli_oerp 26.188: sale_order.meli_handling_limit llenado en %s pedidos", cr.rowcount)
