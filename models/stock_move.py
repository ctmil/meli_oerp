# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
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
        _logger.info("meli_update_boms > company_ids: "+str(company_ids))

        for mov in self:
            
            company = mov.company_id

            _logger.info("meli_update_boms > mov company: "+str(company and company.name))
            company = company or self.env.user.company_id
            if not mov.product_id:
                continue;


            product_id = mov.product_id

            _logger.info("meli_update_boms > mov product: "+str(product_id and product_id.name) )

            product_id.process_meli_stock_moves_update()

            is_company_post_stock = company  and company.mercadolibre_cron_post_update_stock
            is_meli = (mov.product_id.meli_id and mov.product_id.meli_pub)

            #if (config and config.mercadolibre_cron_post_update_stock and is_meli):
                #_logger.info("meli_update_boms > process_meli_stock_moves_update() "+str(config and config.name))
            #    product_id.process_meli_stock_moves_update()
                #product_id.product_post_stock()

            #sin config, recorremos las companias a las que forma parte este producto
            #if not config and company_ids:
            #    for comp in company_ids:
            #        is_company = (product_id.company_id==False or product_id.company_id==comp)
            #        #_logger.info("is_company: "+str(is_company)+" product_id.company_id:"+str(product_id.company_id)+" comp:"+str(comp))
            #        #_logger.info("is_meli: "+str(is_meli)+" comp.mercadolibre_cron_post_update_stock:"+str(comp.mercadolibre_cron_post_updat()e_stock))
            #        if (comp and comp.mercadolibre_cron_post_update_stock and is_company and is_meli):
            #            _logger.info("update bom product_id process_meli_stock_moves_update()")
            #            product_id.process_meli_stock_moves_update()
                        #product_id.product_post_stock()



            #BOM SECTION POST STOCK if needed
            
            if not ("mrp.bom" in self.env):
                continue;

            bomlines = "bom_line_ids" in product_id._fields and product_id.bom_line_ids
            bomlines = bomlines or self.env['mrp.bom.line'].sudo().search([('product_id','=',product_id.id)])
            bomlines = bomlines or []
            
            _logger.info("meli_update_boms > bomlines related: "+str(bomlines))

            for bomline in bomlines:
                
                bm_product_tmpl_id = bomline.bom_id and bomline.bom_id.product_tmpl_id
                bm_product_id = bomline.bom_id and bomline.bom_id.product_id
                bm_product_id = bm_product_id or (bm_product_tmpl_id and bm_product_tmpl_id.product_variant_ids) or self.env["product.product"]
                bm_is_meli = (bm_product_id.meli_id and bm_product_id.meli_pub)
                _logger.info("meli_update_boms > process bom product KIT: "+str(bm_product_id and bm_product_id.name))
                if bm_product_id:
                    for bmpid in bm_product_id:
                        bmpid.process_meli_stock_moves_update()

                #sin config, recorremos las companias a las que forma parte este producto
                if not config and company_ids and bm_product_id:

                    for comp in company_ids:
                        for bmpid in bm_product_id:
                            bm_is_company = (bmpid.company_id==False or bmpid.company_id==comp)
                            if (comp and comp.mercadolibre_cron_post_update_stock and bm_is_company and bm_is_meli):
                                _logger.info("meli_update_boms multicomp > process_meli_stock_moves_update() "+str(comp and comp.name)+" bm_product_id > "+str(bmpid.display_name))
                                bmpid.process_meli_stock_moves_update()

        return True

    def _action_assign(self):
        #_logger.info("Stock move: meli_oerp > _action_assign")
        skip_stock = str2bool(self.env['ir.config_parameter'].sudo().get_param('meli_skip_stock', 'False'))

        res = super(StockMove, self)._action_assign()
        if not skip_stock:
            self.meli_update_boms()

        return res


    def _action_done(self, cancel_backorder=False):
        #_logger.info("Stock move: meli_oerp > _action_done")
        moves_todo = super(StockMove, self)._action_done(cancel_backorder=cancel_backorder)
        skip_stock = str2bool(self.env['ir.config_parameter'].sudo().get_param('meli_skip_stock', 'False'))
        if not skip_stock:
            self.meli_update_boms()

        return moves_todo

    def _action_cancel(self):
        #_logger.info("Stock move: meli_oerp > _action_cancel")
        skip_stock = str2bool(self.env['ir.config_parameter'].sudo().get_param('meli_skip_stock', 'False'))
        
        res = super(StockMove, self)._action_cancel()
        if not skip_stock:
            self.meli_update_boms()

        return res
    
    def _do_unreserve(self):
        #_logger.info("Stock move: meli_oerp > _do_unreserve")
        skip_stock = str2bool(self.env['ir.config_parameter'].sudo().get_param('meli_skip_stock', 'False'))
        company = self.env.user.company_id

        res = super(StockMove, self)._do_unreserve()
        if not skip_stock:
            self.meli_update_boms()

        return res
