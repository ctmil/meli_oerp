# -*- coding: utf-8 -*-
"""OLA 3 del mapeo de cancelaciones: siembra sale_order.meli_cancel_reason_code
sobre el historico, extrayendolo del texto donde hasta hoy quedaba sepultado.

POR QUE HACE FALTA.
Hasta el build 26.138 el `cancel_detail.code` que informa MercadoLibre se
CONCATENABA dentro de `meli_status_detail` (un fields.Text), con este formato
exacto (models/orders.py, cuatro sitios):

    status_detail + " | %s: %s (solicitado por: %s, fecha: %s)"
                      code  descripcion       requested_by      date

El campo nuevo se puebla de ahora en mas en la importacion, pero las
cancelaciones YA IMPORTADAS lo tendrian vacio. Sin esta siembra el agrupado
"ML Motivo de cancelacion" arrancaria mostrando casi todo en "None" y se leeria
como que el dato no existe — el mismo modo de falla que se documento en la
migracion 26.95 del #494 ("arrancaria mostrando de menos, que es peor que no
tenerlo").

QUE HACE, EXACTAMENTE.
Toma el ULTIMO separador " | " de `meli_status_detail` (el texto se APPENDEA al
final, asi que el ultimo es el del cancel_detail) y se queda con el token que
va hasta el primer ": ". Si no hay separador, o el token no parece un codigo,
no escribe nada.

ES IDEMPOTENTE Y ACOTADA: solo escribe filas donde el campo esta NULL o vacio,
y NO toca `meli_status_detail` ni ninguna otra columna. Si se corre dos veces,
la segunda no cambia nada.
"""
import logging
import re

_logger = logging.getLogger(__name__)

# El codigo de ML es un identificador: letras, digitos, guion y guion bajo.
# Ej.: pack_splitted, buyer_regretted, fraud, seller_cancelled_...
_CODE_RE = re.compile(r"^([A-Za-z0-9_.\-]{2,64}):\s")


def _has_column(cr, table, column):
    cr.execute(
        """SELECT 1 FROM information_schema.columns
           WHERE table_name=%s AND column_name=%s""",
        (table, column),
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    if not _has_column(cr, "sale_order", "meli_cancel_reason_code"):
        # La columna la crea el ORM en el update del modulo; si todavia no esta,
        # no hay nada que sembrar. No es un error.
        _logger.info("OLA3: sale_order.meli_cancel_reason_code aun no existe, nada que sembrar.")
        return
    if not _has_column(cr, "sale_order", "meli_status_detail"):
        _logger.warning("OLA3: sale_order.meli_status_detail no existe — no se puede sembrar el motivo.")
        return

    cr.execute(
        """SELECT id, meli_status_detail
             FROM sale_order
            WHERE meli_status_detail IS NOT NULL
              AND meli_status_detail LIKE '%% | %%'
              AND (meli_cancel_reason_code IS NULL OR meli_cancel_reason_code = '')""")
    rows = cr.fetchall()
    _logger.info("OLA3: %s ventas candidatas con motivo embebido en el texto.", len(rows))

    found = 0
    for so_id, detail in rows:
        idx = (detail or "").rfind(" | ")
        if idx == -1:
            continue
        match = _CODE_RE.match(detail[idx + 3:])
        if not match:
            # cancel_detail venia sin `code` (se concatenaba ": descripcion"),
            # o el " | " era parte del status_detail original. Se deja vacio.
            continue
        cr.execute(
            "UPDATE sale_order SET meli_cancel_reason_code = %s WHERE id = %s",
            (match.group(1), so_id),
        )
        found += 1

    _logger.info("OLA3: meli_cancel_reason_code sembrado en %s de %s ventas.", found, len(rows))
