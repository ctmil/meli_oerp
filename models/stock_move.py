# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.addons import decimal_precision as dp
from odoo.exceptions import UserError
from odoo.tools import float_utils
import logging
_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = "stock.move"

    @api.multi
    def action_done(self):
        #import pdb; pdb.set_trace()
        _logger.info("StockMove action_done")
#        _logger.info(self)
        _logger.info("Before: virtual av:" + str(self.product_id.virtual_available))
        res = super(StockMove, self).action_done()
        _logger.info("After: virtual av:" + str(self.product_id.virtual_available))


        if self.product_id:
            bomlines = self.env['mrp.bom.line'].search([('product_id','=',self.product_id.id)])
            if (bomlines):
                for bomline in bomlines:
                    #_logger.info("bomline tpl: "+bomline.bom_id.product_tmpl_id.name)
                    #_logger.info("bomline var: "+bomline.bom_id.product_id.name)
                    #_logger.info("bomline var code: "+bomline.bom_id.product_id.default_code)
                    _logger.info("Clone stock: " + str(bomline.bom_id.product_id.virtual_available))
                    if (bomline.bom_id.product_id.virtual_available !=self.product_id.virtual_available):
                        _logger.info("Trigger stock equivalence function:")
                        movs = self.env['stock.move']
                        qty = self.ordered_qty
                        qtydiff = bomline.bom_id.product_id.virtual_available - self.product_id.virtual_available
                        if (qtydiff>qty):
                            qty = qtydiff
                        movfields = {
                            "name": self.name+str(' (clone)'),
                            "product_id": bomline.bom_id.product_id.id,
                            "location_id": self.location_id.id,
                            "location_dest_id": self.location_dest_id.id,
                            "procure_method": self.procure_method,
                            "product_uom_qty": qty,
                            #"ordered_qty": qty,
                            "product_uom": self.product_uom.id
                        }
                        _logger.info(movfields)
                        sm = movs.create(movfields)
                        if (sm):
                            sm.action_done()

        return True
