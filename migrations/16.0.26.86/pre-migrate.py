# -*- coding: utf-8 -*-
"""[#420 Shoppy] estimated_buffering_date: fields.Datetime -> fields.Date.

ML entrega el 'buffering.date' del shipping_option como DÍA calendario a
medianoche-UTC ('YYYY-MM-DD 00:00:00Z'). Al guardarse como timestamp se
renderizaba 21:00 del día anterior en AR (-03). Semánticamente es un DÍA
(deadline de despacho self_service), no un instante.

Casteamos la columna histórica timestamp->date SIN re-pull. El '::date' de
'YYYY-MM-DD 00:00:00' (guardado como medianoche-UTC = el propio día) devuelve
el día correcto. Corre en PRE (antes de que el ORM vea el nuevo fields.Date),
así el update no intenta su propia conversión insegura.
"""
import logging
_logger = logging.getLogger(__name__)


def _column_type(cr, table, column):
    cr.execute(
        """SELECT data_type FROM information_schema.columns
           WHERE table_name=%s AND column_name=%s""",
        (table, column),
    )
    row = cr.fetchone()
    return row[0] if row else None


def migrate(cr, version):
    table, column = "mercadolibre_shipment", "estimated_buffering_date"
    dtype = _column_type(cr, table, column)
    if dtype is None:
        _logger.info("[#420] %s.%s no existe aún; nada que castear", table, column)
        return
    if dtype == "date":
        _logger.info("[#420] %s.%s ya es date; skip", table, column)
        return
    cr.execute(
        'ALTER TABLE mercadolibre_shipment '
        'ALTER COLUMN estimated_buffering_date TYPE date '
        'USING estimated_buffering_date::date'
    )
    _logger.info("[#420] %s.%s casteado %s -> date", table, column, dtype)
