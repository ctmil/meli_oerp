# -*- coding: utf-8 -*-

from odoo import models, api, fields, tools
import odoo.addons.decimal_precision as dp
from odoo.tools.translate import _

class StockWarehouse(models.Model):

    _inherit = 'stock.warehouse'
    
    meli_published = fields.Boolean(u'Disponible en MELI', copy=False)
    meli_sequence = fields.Integer(u'Secuencia Meli')
    
    
    def meli_publish_button(self):
        self.ensure_one()
        return self.write({'meli_published': not self.meli_published})