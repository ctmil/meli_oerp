# -*- coding: utf-8 -*-
"""#661 (542): el access_token de MercadoLibre quedaba guardado en claro en campos
que cualquiera con acceso al registro podía ver (y en el link del pago de MP).
Desde 26.213 no se guarda más; esto limpia lo YA guardado. Idempotente: sólo toca
filas que todavía tienen el token. Cada tabla/columna se verifica antes (los
modelos transitorios o de otras versiones pueden no tenerla).

No loguea valores, sólo cantidades."""
import logging

_logger = logging.getLogger(__name__)

# (tabla, columna) con URLs que pueden tener ?access_token= / &access_token=
_URL_COLUMNS = [
    ('mercadolibre_payments', 'mercadopago_url'),
    ('mercadolibre_payment', 'mercadopago_url'),
    ('mercadolibre_shipment', 'pdf_link'),
    ('meli_warning', 'message_html'),
    ('meli_warning', 'message'),
]


def _has_column(cr, table, column):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = current_schema() AND table_name = %s AND column_name = %s
    """, (table, column))
    return bool(cr.fetchone())


def migrate(cr, version):
    for table, column in _URL_COLUMNS:
        if not _has_column(cr, table, column):
            continue
        # quita "access_token=<valor>" con su separador; si quedaba "?&" o "?"/"&" colgando, se acomoda
        cr.execute(r"""
            UPDATE {t}
               SET {c} = regexp_replace(
                           regexp_replace(
                             regexp_replace({c}::text, '([?&])access_token=[^&"''<\s]*&?', '\1', 'g'),
                           '\?&', '?', 'g'),
                         '[?&](?=$|["''<\s])', '', 'g')
             WHERE {c}::text LIKE '%%access_token=%%'
        """.format(t=table, c=column))
        if cr.rowcount:
            _logger.info("MELI 26.213 (#661): access_token quitado de %s fila(s) de %s.%s", cr.rowcount, table, column)

    # Wizard de etiquetas: full_links guardaba un JSON con el token como CLAVE. Es transitorio: se vacía.
    if _has_column(cr, 'mercadolibre_shipment_print', 'full_links'):
        cr.execute("""
            UPDATE mercadolibre_shipment_print SET full_links = '{}'
             WHERE full_links IS NOT NULL AND full_links <> '{}'
        """)
        if cr.rowcount:
            _logger.info("MELI 26.213 (#661): full_links vaciado en %s wizard(s) de etiquetas", cr.rowcount)
