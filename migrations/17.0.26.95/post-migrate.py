# -*- coding: utf-8 -*-
"""Migracion del criterio de impuestos: de constante de modulo a campo de la lista de precios.

⛔ EL PROBLEMA QUE ESTA MIGRACION EXISTE PARA EVITAR
`product.pricelist.meli_include_taxes` nace con `default=True`. En una instancia que hoy tiene
`price_list_apply_tax = False` (customizacion local que varios clientes tienen), dejar que las
listas existentes tomen el default **invierte el comportamiento**: la primera corrida del cron de
precio publicaria todo el catalogo con el impuesto sumado. Con IVA 21% eso es publicar un 21% mas
caro en todas las publicaciones, y el cliente se entera vendiendo cero.

⛔ Y POR QUE NO ALCANZA CON LEER LA CONSTANTE
Las migraciones corren DESPUES de cargar el codigo nuevo, asi que `price_list_apply_tax` que se lee
aca es la del modulo que se esta instalando, no la que el cliente tenia. Si el deploy trae el
`versions.py` del source (que dice True) encima de una instancia que estaba en False, leer la
constante da exactamente la respuesta equivocada.

Por eso manda un PIN explicito: el parametro del sistema `meli_oerp.price_list_apply_tax`.
Quien deploya lo setea ANTES de actualizar el modulo, en la instancia que va a migrar:

    env['ir.config_parameter'].sudo().set_param('meli_oerp.price_list_apply_tax', 'False')

Si el pin no esta, se cae a la constante y se deja dicho en el log, que es lo unico honesto:
no se puede adivinar el criterio comercial de un cliente.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        # Instalacion nueva: no hay comportamiento previo que preservar, el default vale.
        return

    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})

    Pricelist = env["product.pricelist"]
    if "meli_include_taxes" not in Pricelist._fields:
        _logger.error(
            "meli_oerp: el campo meli_include_taxes no existe todavia; la migracion NO corrio. "
            "Esto NO es 'no hacia falta'.")
        return

    pin = env["ir.config_parameter"].sudo().get_param("meli_oerp.price_list_apply_tax")
    if pin is not None and str(pin).strip() != "":
        valor = str(pin).strip().lower() in ("1", "true", "t", "yes", "si", "sí")
        origen = "parametro del sistema meli_oerp.price_list_apply_tax=%r" % pin
    else:
        from odoo.addons.meli_oerp.models.versions import price_list_apply_tax
        valor = bool(price_list_apply_tax)
        origen = ("constante price_list_apply_tax del modulo (NO habia pin). "
                  "Si esta instancia tenia otro criterio antes del upgrade, revisar las listas.")

    listas = Pricelist.with_context(active_test=False).search([])
    _logger.info(
        "meli_oerp: migrando meli_include_taxes = %s en %d lista(s) de precios. Origen: %s",
        valor, len(listas), origen)

    # Se escribe en TODAS las listas existentes a proposito: las que ya existian tienen que
    # conservar el comportamiento vigente, no heredar el default nuevo. Las creadas de aca en
    # adelante si nacen en True.
    if listas:
        listas.write({"meli_include_taxes": valor})

    quedaron = Pricelist.with_context(active_test=False).search_count(
        [("meli_include_taxes", "=", valor)])
    _logger.info(
        "meli_oerp: verificacion post-migracion: %d de %d lista(s) quedaron en %s",
        quedaron, len(listas), valor)
    if listas and quedaron != len(listas):
        _logger.error(
            "meli_oerp: la migracion NO dejo todas las listas en el mismo valor (%d de %d). "
            "Revisar antes de dejar correr el cron de precio.", quedaron, len(listas))
