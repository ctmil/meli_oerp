# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (c) 2025 Moldeo Interactive (https://www.moldeointeractive.com.ar)
#
##############################################################################

from odoo import fields, models


class ProductPricelist(models.Model):
    """Extiende la lista de precios con el criterio de impuestos al publicar en MercadoLibre.

    Por que vive ACA y no en la configuracion de MeLi: la pregunta que responde este campo es
    "¿los precios de esta lista ya llevan el impuesto adentro?", y eso es una propiedad DE LA
    LISTA. Una misma instancia publica desde mas de una (la config tiene `mercadolibre_pricelist`
    y `mercadolibre_pricelist_usd`), y cada una puede tener su respuesta. Puesto en la
    configuracion, todas las listas quedarian obligadas a compartir criterio.

    Antes de esto la decision era una constante de modulo (`price_list_apply_tax` en versions.py)
    que se editaba a mano por cliente: no se veia desde ninguna pantalla, era global a la
    instancia, y cambiarla exigia un commit y un deploy.
    """

    _inherit = "product.pricelist"

    meli_include_taxes = fields.Boolean(
        string="Al publicar en MeLi, incluir impuestos",
        default=True,
        help="Si esta activo, al publicar el precio a MercadoLibre se le suman los impuestos de "
             "venta que no esten incluidos en el precio (los que tienen 'Incluido en el precio' "
             "desmarcado).\n\n"
             "Apagalo cuando los precios de esta lista YA tienen el impuesto adentro: si no, se "
             "cobra dos veces y se publica mas caro de lo que corresponde.\n\n"
             "Viene activado por defecto porque publicar de mas se nota; publicar de menos se "
             "pierde en silencio.")
