# -*- coding: utf-8 -*-

from odoo import models, api, fields, tools
import odoo.addons.decimal_precision as dp
from odoo.tools.translate import _

class ProductAttribute(models.Model):

    _inherit = 'product.attribute'
    
    meli_id = fields.Char(u'ID MELI')
    
class ProductAttributevalue(models.Model):
    
    _inherit = "product.attribute.value"
    
    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        if 'product_tmpl_to_filter' in self.env.context:
            if self.env.context.get('product_tmpl_to_filter'):
                template = self.env['product.template'].browse(self.env.context.get('product_tmpl_to_filter'))
                value_ids = template.attribute_line_ids.mapped('value_ids').ids
                if value_ids:
                    args.append(('id', 'in', value_ids))
                else:
                    args.append(('id', '=', 0))
            else:
                args.append(('id', '=', 0))
        res = super(ProductAttributevalue, self)._search(args=args, offset=offset, limit=limit, order=order, count=count, access_rights_uid=access_rights_uid)
        return res