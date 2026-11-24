# -*- coding: utf-8 -*-
"""[26.445] Limpia el family_name 'None'/'False' que dejaba la importacion vieja.

Hasta 26.444 la importacion de una publicacion guardaba `str(rjson['family_name'])`: si ML lo devolvia
null (items que no son de user product) quedaba el TEXTO 'None' (y 'False' por un str(False)). Al
publicar, ese texto viajaba como family_name y ML armaba el titulo "None <Color> <Talle>" y moderaba
el item. Desde 26.445 el codigo trata esos valores como vacio; esta migracion deja vacio el dato.

Por que es segura:
- Toca SOLO la columna meli_family_name y SOLO las filas cuyo valor (sin espacios) es exactamente
  'None' o 'False': ningun nombre de familia real es eso; es la huella de un str() sobre un vacio.
- Vacio es lo que el modulo ya sabe manejar: al publicar, la plantilla se completa con el titulo o el
  nombre (como cualquier producto nuevo). No cambia titulos, precios, stock ni vinculos.
- No llama a ML: las publicaciones ya creadas no cambian (ML no acepta family_name en un PUT).
- Idempotente; en una instalacion nueva no hace nada. Loguea solo cantidades.
"""
import logging

_logger = logging.getLogger(__name__)

TABLES = ('product_template', 'product_product')


def _column_exists(cr, table, column):
    cr.execute("SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
               (table, column))
    return bool(cr.fetchone())


def migrate(cr, version):
    if not version:
        return
    for table in TABLES:
        if not _column_exists(cr, table, 'meli_family_name'):
            continue
        cr.execute("UPDATE " + table + " SET meli_family_name = NULL "
                   "WHERE btrim(meli_family_name) IN ('None', 'False')")
        _logger.info("MELI 26.445: %s.meli_family_name 'None'/'False' -> vacio: %d filas", table, cr.rowcount)
