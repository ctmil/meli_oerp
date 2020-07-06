# -*- coding: utf-8 -*-

from odoo import models, api, fields, tools
import odoo.addons.decimal_precision as dp
from odoo.tools.translate import _

class ProductImage(models.Model):

    _inherit = 'product.image'
    
    meli_id = fields.Char(u'ID MELI')
    product_attribute_id = fields.Many2one('product.attribute.value', u'Atributo asociado')