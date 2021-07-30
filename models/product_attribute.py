# -*- coding: utf-8 -*-

from odoo import models, api, fields, tools
import odoo.addons.decimal_precision as dp
from odoo.tools.translate import _
from . import versions
from .versions import *

class ProductAttribute(models.Model):

    _inherit = 'product.attribute'

    meli_id = fields.Char(u'Id Attribute ML')
    meli_default_id_attribute = fields.Many2one('mercadolibre.category.attribute',string="ML Attribute default")
    meli_id_attributes = fields.Many2many('mercadolibre.category.attribute',string="ML Attributes")

    def meli_default_create_variant( self, meli_attribute=None ):
        
        create_variant = default_create_variant
        
        if meli_attribute and "variation_attribute" in meli_attribute:
            if not meli_attribute["variation_attribute"]:
                create_variant = default_no_create_variant
                    
        
        return create_variant
        