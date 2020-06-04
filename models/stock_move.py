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

    
    def action_assign(self, no_prepare=False):
        company = self.env.user.company_id
        for mov in self:
            #_logger.info("StockMove action_assign")
            #_logger.info(self)
            #_logger.info("Before: virtual av:" + str(mov.product_id.virtual_available))
            res = super(StockMove, mov).action_assign()
            #_logger.info("After: virtual av:" + str(mov.product_id.virtual_available))

            if mov.product_id:
                bomlines = self.env['mrp.bom.line'].search([('product_id','=',mov.product_id.id)])
                if (bomlines and 1==2):
                    for bomline in bomlines:
                        _logger.info("Clone stock: " + str(bomline.bom_id.product_id.virtual_available))
                        if (bomline.bom_id.product_id.virtual_available !=mov.product_id.virtual_available):
                            _logger.info("Trigger stock equivalence function:")
                            movs = self.env['stock.move']
                            qty = mov.ordered_qty
                            _logger.info("ordered_qty:"+str(qty))
                            _logger.info("bomline.product_qty:"+str(bomline.product_qty))
                            if (bomline.product_qty>0):
                                qty_base = mov.product_id.virtual_available * (1.0 / bomline.product_qty)
                            else:
                                qty_base = mov.product_id.virtual_available
                            _logger.info("qty_base:"+str(qty_base))
                            qtydiff =  qty_base - bomline.bom_id.product_id.virtual_available
                            _logger.info("qtydiff:"+str(qtydiff))
                            if (qtydiff>qty):
                                qty = qtydiff
                            _logger.info("qty:"+str(qty))
                            movfields = {
                                "name": mov.name+str(' (clone)'),
                                "product_id": bomline.bom_id.product_id.id,
                                "location_id": mov.location_id.id,
                                "location_dest_id": mov.location_dest_id.id,
                                "procure_method": mov.procure_method,
                                "product_uom_qty": qty,
                                #"ordered_qty": qty,
                                "product_uom": mov.product_uom.id
                            }
                            _logger.info(movfields)
                            sm = movs.create(movfields)
                            if (sm):
                                sm.action_done()
                if (company.mercadolibre_cron_post_update_stock):
                    if (mov.product_id.meli_id and mov.product_id.meli_pub):
                        mov.product_id.product_post_stock()

        return True

    
    def action_done(self):
        #import pdb; pdb.set_trace()
        company = self.env.user.company_id
        for mov in self:
            #_logger.info("StockMove action_done")
            #_logger.info(self)
            #_logger.info("Before: virtual av:" + str(mov.product_id.virtual_available))
            res = super(StockMove, mov).action_done()
            #_logger.info("After: virtual av:" + str(mov.product_id.virtual_available))


            if mov.product_id:
                bomlines = self.env['mrp.bom.line'].search([('product_id','=',mov.product_id.id)])
                if (bomlines and 1==2):
                    for bomline in bomlines:
                        _logger.info("Clone stock: " + str(bomline.bom_id.product_id.virtual_available))
                        if (bomline.bom_id.product_id.virtual_available !=mov.product_id.virtual_available):
                            _logger.info("Trigger stock equivalence function:")
                            movs = self.env['stock.move']
                            qty = mov.ordered_qty
                            _logger.info("ordered_qty:"+str(qty))
                            _logger.info("bomline.product_qty:"+str(bomline.product_qty))
                            if (bomline.product_qty>0):
                                qty_base = mov.product_id.virtual_available * (1.0 / bomline.product_qty)
                            else:
                                qty_base = mov.product_id.virtual_available
                            _logger.info("qty_base:"+str(qty_base))
                            qtydiff = qty_base - bomline.bom_id.product_id.virtual_available
                            _logger.info("qtydiff:"+str(qtydiff))
                            if (qtydiff>qty):
                                qty = qtydiff
                            _logger.info("qty:"+str(qty))
                            movfields = {
                                "name": mov.name+str(' (clone)'),
                                "product_id": bomline.bom_id.product_id.id,
                                "location_id": mov.location_id.id,
                                "location_dest_id": mov.location_dest_id.id,
                                "procure_method": mov.procure_method,
                                "product_uom_qty": qty,
                                #"ordered_qty": qty,
                                "product_uom": mov.product_uom.id
                            }
                            _logger.info(movfields)
                            sm = movs.create(movfields)
                            if (sm):
                                sm.action_done()
                if (company.mercadolibre_cron_post_update_stock):
                    if (mov.product_id.meli_id and mov.product_id.meli_pub):
                        mov.product_id.product_post_stock()

        return True
