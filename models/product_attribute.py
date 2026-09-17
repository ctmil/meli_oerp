# -*- coding: utf-8 -*-

from odoo import models, api, fields, tools
from odoo.tools.translate import _
from . import versions
from .versions import *

import logging
_logger = logging.getLogger(__name__)

class ProductAttribute(models.Model):

    _inherit = 'product.attribute'

    meli_att_id = fields.Char(string=u'Id Attribute ML',related='meli_default_id_attribute.att_id')
    meli_default_id_attribute = fields.Many2one('mercadolibre.category.attribute',string="ML Attribute default")
    meli_id_attributes = fields.Many2many('mercadolibre.category.attribute',string="ML Attributes")

    meli_default_id_attribute_hidden = fields.Boolean( related="meli_default_id_attribute.hidden", string="Hidden")
    meli_default_id_attribute_variation_attribute = fields.Boolean( related="meli_default_id_attribute.variation_attribute", string="Variation")

    meli_chart_id = fields.Many2one("mercadolibre.grid.chart",string="ML Guia de talle",readonly=True)


    def meli_default_create_variant( self, meli_attribute=None ):

        create_variant = default_no_create_variant
        #_logger.info("meli_default_create_variant meli_attribute: "+str(meli_attribute))
        if meli_attribute and "variation_attribute" in meli_attribute and "hidden" in meli_attribute:
            if meli_attribute["variation_attribute"] and not meli_attribute["hidden"]:
                create_variant = default_create_variant

        # Lista negra: GTIN/SELLER_SKU nunca generan variantes (ver
        # meli_attributes_never_variant en versions.py). En Odoo son el barcode y
        # el default_code de la VARIANTE, no una caracteristica del producto.
        if create_variant == default_create_variant and meli_attribute:
            att_id = meli_attribute.get("att_id") or meli_attribute.get("id")
            if meli_attribute_is_never_variant( att_id ):
                create_variant = default_no_create_variant


        return create_variant
