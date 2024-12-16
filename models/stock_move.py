# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.addons import decimal_precision as dp
from odoo.exceptions import UserError
from odoo.tools import float_utils
import logging
_logger = logging.getLogger(__name__)
from odoo.tools import str2bool


class StockMove(models.Model):
    _inherit = "stock.move"

    def meli_update_boms( self, config=None ):
        #config = config or self.env.user.company_id
        company_ids = self.env.user.company_ids
        mov = self

        _logger.info("meli_update_boms > "+str(config and config.name))

        if mov.product_id:

            product_id = mov.product_id
            product_id.process_meli_stock_moves_update()

            #_logger.info("meli_update_boms > mov:"+str(mov)+" product: "+str(product_id) )

            is_meli = (mov.product_id.meli_id and mov.product_id.meli_pub)

            if (config and config.mercadolibre_cron_post_update_stock and is_meli):
                #_logger.info("meli_update_boms > process_meli_stock_moves_update() "+str(config and config.name))
                product_id.process_meli_stock_moves_update()
                #product_id.product_post_stock()

            #sin config, recorremos las companias a las que forma parte este producto
            if not config and company_ids:
                for comp in company_ids:
                    is_company = (product_id.company_id==False or product_id.company_id==comp)
                    #_logger.info("is_company: "+str(is_company)+" product_id.company_id:"+str(product_id.company_id)+" comp:"+str(comp))
                    #_logger.info("is_meli: "+str(is_meli)+" comp.mercadolibre_cron_post_update_stock:"+str(comp.mercadolibre_cron_post_updat()e_stock))
                    if (comp and comp.mercadolibre_cron_post_update_stock and is_company and is_meli):
                        _logger.info("update bom product_id process_meli_stock_moves_update()")
                        product_id.process_meli_stock_moves_update()
                        #product_id.product_post_stock()



            #BOM SECTION POST STOCK if needed

            if not ("mrp.bom" in self.env):
                return False

            bomlines = "bom_line_ids" in product_id._fields and product_id.bom_line_ids
            bomlines = bomlines or self.env['mrp.bom.line'].search([('product_id','=',product_id.id)])
            bomlines = bomlines or []

            for bomline in bomlines:

                bm_product_id = bomline.bom_id and bomline.bom_id.product_id
                bm_is_meli = (bm_product_id.meli_id and bm_product_id.meli_pub)

                if (1==2 and bm_product_id.virtual_available !=product_id.virtual_available):
                    #_logger.info("Clone stock: " + str(bomline.bom_id.product_id.virtual_available))
                    #_logger.info("Trigger stock equivalence function:")
                    movs = self.env['stock.move']
                    qty = mov.ordered_qty
                    #_logger.info("ordered_qty:"+str(qty))
                    #_logger.info("bomline.product_qty:"+str(bomline.product_qty))
                    if (bomline.product_qty>0):
                        qty_base = mov.product_id.virtual_available * (1.0 / bomline.product_qty)
                    else:
                        qty_base = mov.product_id.virtual_available
                    #_logger.info("qty_base:"+str(qty_base))
                    qtydiff =  qty_base - bomline.bom_id.product_id.virtual_available
                    #_logger.info("qtydiff:"+str(qtydiff))
                    if (qtydiff>qty):
                        qty = qtydiff
                    #_logger.info("qty:"+str(qty))
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
                        sm._action_done()

                if (config and config.mercadolibre_cron_post_update_stock and bm_product_id and bm_is_meli):
                    _logger.info("meli_update_boms > process_meli_stock_moves_update() "+str(config and config.name))
                    bm_product_id.process_meli_stock_moves_update()
                    #bm_product_id.product_post_stock()

                #sin config, recorremos las companias a las que forma parte este producto
                if not config and company_ids and bm_product_id:

                    for comp in company_ids:
                        bm_is_company = (bm_product_id.company_id==False or bm_product_id.company_id==comp)
                        if (comp and comp.mercadolibre_cron_post_update_stock and bm_is_company and bm_is_meli):
                            bm_product_id.process_meli_stock_moves_update()
                            #bm_product_id.product_post_stock()

        return True

    def _action_assign(self, force_qty=False):
        skip_stock = str2bool(self.env['ir.config_parameter'].sudo().get_param('meli_skip_stock', 'False'))
        company = self.env.user.company_id

        res = super(StockMove, self)._action_assign(force_qty=force_qty)
        if not skip_stock:
            for mov in self:
                mov.meli_update_boms( config = company )

        return res


    def _action_done(self, cancel_backorder=False):
        #import pdb; pdb.set_trace()
        #_logger.info("Stock move: meli_oerp > _action_done")
        company = self.env.user.company_id

        moves_todo = super(StockMove, self)._action_done(cancel_backorder=cancel_backorder)
        skip_stock = str2bool(self.env['ir.config_parameter'].sudo().get_param('meli_skip_stock', 'False'))
        if not skip_stock:
            for mov in self:
                mov.meli_update_boms( config = company )

        return moves_todo
