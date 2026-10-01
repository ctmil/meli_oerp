# -*- coding: utf-8 -*-
"""#601 P3: el link de la etiqueta (mercadolibre.shipment.pdf_link) se guardaba con
el access_token de MercadoLibre adentro, legible por cualquiera que vea el envío.
Desde 26.172 se guarda sin token y la descarga lo manda en el header. Esto limpia
los links YA guardados. Idempotente: sólo toca filas que todavía tienen el token."""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(r"""
        UPDATE mercadolibre_shipment
           SET pdf_link = regexp_replace(pdf_link, '&?access_token=[^&]*', '', 'g')
         WHERE pdf_link LIKE '%%access_token=%%'
    """)
    _logger.info("MELI 26.172: access_token quitado de %s pdf_link de envíos", cr.rowcount)
