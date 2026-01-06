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
        """
        Update meli_stock_moves_update for products affected by stock moves.
        Optimized to:
        - Only process products with MeLi publications
        - Collect unique product IDs to avoid duplicate updates
        - Skip updates during concurrent processing to avoid serialization errors
        """
        company_ids = self.env.user.company_ids

        # Collect unique product IDs to update (avoid duplicates)
        products_to_update = set()

        for mov in self:
            company = mov.company_id or self.env.user.company_id
            if not mov.product_id:
                continue

            product_id = mov.product_id

            # Only add if product has MeLi publication or bindings
            if product_id.meli_id or product_id.meli_pub:
                products_to_update.add(product_id.id)

            # BOM SECTION - find parent KITs that use this product as component
            if not ("mrp.bom" in self.env):
                continue

            bomlines = "bom_line_ids" in product_id._fields and product_id.bom_line_ids
            bomlines = bomlines or self.env['mrp.bom.line'].sudo().search([('product_id','=',product_id.id)])
            bomlines = bomlines or []

            for bomline in bomlines:
                bm_product_tmpl_id = bomline.bom_id and bomline.bom_id.product_tmpl_id
                bm_product_id = bomline.bom_id and bomline.bom_id.product_id
                bm_product_id = bm_product_id or (bm_product_tmpl_id and bm_product_tmpl_id.product_variant_ids) or self.env["product.product"]

                for bmpid in bm_product_id:
                    # Only add if parent product has MeLi publication
                    if bmpid.meli_id or bmpid.meli_pub:
                        products_to_update.add(bmpid.id)

        # Log the count for monitoring
        if len(products_to_update) > 0:
            _logger.info("meli_update_boms: %d unique MeLi products to update from %d stock moves",
                        len(products_to_update), len(self))

        # Update all products
        if products_to_update:
            products = self.env['product.product'].browse(list(products_to_update))
            for product in products:
                try:
                    product._meli_stock_moves_update()
                except Exception as e:
                    _logger.debug("Skipping meli_stock_moves_update for %s: %s", product.display_name, e)

        return True

    def _should_skip_meli_stock_update(self):
        """Check if MeLi stock updates should be skipped"""
        # Skip if context flag is set (during order imports)
        if self.env.context.get('meli_skip_stock_update'):
            return True
        # Skip if global config parameter is set
        skip_stock = str2bool(self.env['ir.config_parameter'].sudo().get_param('meli_skip_stock', 'False'))
        return skip_stock

    def _action_assign(self):
        res = super(StockMove, self)._action_assign()
        if not self._should_skip_meli_stock_update():
            self.meli_update_boms()
        return res

    def _action_done(self, cancel_backorder=False):
        moves_todo = super(StockMove, self)._action_done(cancel_backorder=cancel_backorder)
        if not self._should_skip_meli_stock_update():
            self.meli_update_boms()
        return moves_todo

    def _action_cancel(self):
        res = super(StockMove, self)._action_cancel()
        if not self._should_skip_meli_stock_update():
            self.meli_update_boms()
        return res

    def _do_unreserve(self):
        res = super(StockMove, self)._do_unreserve()
        if not self._should_skip_meli_stock_update():
            self.meli_update_boms()
        return res
