# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_utils
import logging
import time
_logger = logging.getLogger(__name__)
from odoo.tools import str2bool

# Benchmark threshold in seconds - only log detailed benchmarks if total time exceeds this
MELI_BENCHMARK_THRESHOLD = 0.5

# Module-level cache for log setting
_meli_log_cache = {}


class StockMove(models.Model):
    _inherit = "stock.move"

    def _meli_log_enabled(self):
        """
        Check if MELI debug logging is enabled via meli_cron_log_chatter.
        Uses module-level cache to avoid repeated DB lookups within the same request.
        """
        global _meli_log_cache
        company_id = self.env.company.id
        cache_key = f"log_enabled_{company_id}"

        if cache_key not in _meli_log_cache:
            if 'mercadolibre.account' not in self.env:
                _meli_log_cache[cache_key] = False
            else:
                account = self.env['mercadolibre.account'].sudo().search([
                    ('company_id', '=', company_id),
                    ('meli_cron_log_chatter', '=', True)
                ], limit=1)
                _meli_log_cache[cache_key] = bool(account)

        return _meli_log_cache[cache_key]

    def meli_update_boms( self, config=None ):
        """
        Update meli_stock_moves_update for products affected by stock moves.
        OPTIMIZED to:
        - Only process products with MeLi publications
        - Collect unique product IDs to avoid duplicate updates
        - Skip updates during concurrent processing to avoid serialization errors
        - Batch query for BOM lines instead of N+1 queries per product

        BENCHMARKED: Logs timing for each step when processing takes > MELI_BENCHMARK_THRESHOLD
        """
        t_start = time.time()
        benchmark_data = {
            'moves_count': len(self),
            'move_products': 0,
            'direct_meli_products': 0,
            'bomlines_found': 0,
            'bom_parent_products': 0,
            'total_products_to_update': 0,
        }

        # STEP 1: Collect unique product IDs from moves
        t1 = time.time()
        move_product_ids = set()
        products_to_update = set()

        for mov in self:
            if not mov.product_id:
                continue
            product_id = mov.product_id
            move_product_ids.add(product_id.id)
            # Only add if product has MeLi publication or bindings
            if product_id.meli_id or product_id.meli_pub:
                products_to_update.add(product_id.id)

        benchmark_data['move_products'] = len(move_product_ids)
        benchmark_data['direct_meli_products'] = len(products_to_update)
        t1_end = time.time()

        # STEP 2: BOM SECTION - batch query for all parent KITs
        t2 = time.time()
        bom_parents_added = 0
        if move_product_ids and "mrp.bom" in self.env:
            # Single batch search instead of N+1 queries per product
            bomlines = self.env['mrp.bom.line'].sudo().search([
                ('product_id', 'in', list(move_product_ids))
            ])
            benchmark_data['bomlines_found'] = len(bomlines)

            for bomline in bomlines:
                if not bomline.bom_id:
                    continue
                bm_product_id = bomline.bom_id.product_id
                bm_product_tmpl_id = bomline.bom_id.product_tmpl_id

                if bm_product_id:
                    # Only add if parent product has MeLi publication
                    if bm_product_id.meli_id or bm_product_id.meli_pub:
                        if bm_product_id.id not in products_to_update:
                            bom_parents_added += 1
                        products_to_update.add(bm_product_id.id)
                elif bm_product_tmpl_id:
                    for variant in bm_product_tmpl_id.product_variant_ids:
                        if variant.meli_id or variant.meli_pub:
                            if variant.id not in products_to_update:
                                bom_parents_added += 1
                            products_to_update.add(variant.id)

        benchmark_data['bom_parent_products'] = bom_parents_added
        benchmark_data['total_products_to_update'] = len(products_to_update)
        t2_end = time.time()

        # STEP 3: Batch update all products
        t3 = time.time()
        if products_to_update:
            products = self.env['product.product'].browse(list(products_to_update))
            try:
                products.process_meli_stock_moves_update()
            except Exception as e:
                _logger.debug("Error in batch meli_stock_moves_update: %s", e)
                # Fallback to individual updates if batch fails
                for product in products:
                    try:
                        product._meli_stock_moves_update()
                    except Exception as e2:
                        _logger.debug("Skipping meli_stock_moves_update for %s: %s", product.display_name, e2)
        t3_end = time.time()

        # Calculate total time and log benchmark if enabled
        t_total = time.time() - t_start

        if self._meli_log_enabled() and products_to_update:
            _logger.info(
                "MELI_BENCHMARK meli_update_boms: moves=%d, products=%d (direct=%d, bom_parents=%d), "
                "bomlines=%d, total_time=%.3fs",
                benchmark_data['moves_count'],
                benchmark_data['total_products_to_update'],
                benchmark_data['direct_meli_products'],
                benchmark_data['bom_parent_products'],
                benchmark_data['bomlines_found'],
                t_total
            )

            # Detailed timing breakdown if slow
            if t_total > MELI_BENCHMARK_THRESHOLD:
                _logger.warning(
                    "MELI_BENCHMARK_DETAIL meli_update_boms SLOW (%.3fs > %.1fs threshold): "
                    "step1_collect_moves=%.3fs, step2_bom_search=%.3fs, step3_update_products=%.3fs | "
                    "Data: %s",
                    t_total, MELI_BENCHMARK_THRESHOLD,
                    t1_end - t1,
                    t2_end - t2,
                    t3_end - t3,
                    benchmark_data
                )

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
        t_start = time.time()
        res = super(StockMove, self)._action_assign()
        t_super_end = time.time()

        if not self._should_skip_meli_stock_update():
            self.meli_update_boms()
        t_meli_end = time.time()

        t_total = time.time() - t_start
        if self._meli_log_enabled() and t_total > MELI_BENCHMARK_THRESHOLD:
            _logger.warning(
                "MELI_BENCHMARK _action_assign SLOW: moves=%d, total=%.3fs (super=%.3fs, meli=%.3fs)",
                len(self), t_total, t_super_end - t_start, t_meli_end - t_super_end
            )
        return res

    def _action_done(self, cancel_backorder=False):
        t_start = time.time()
        moves_todo = super(StockMove, self)._action_done(cancel_backorder=cancel_backorder)
        t_super_end = time.time()

        if not self._should_skip_meli_stock_update():
            self.meli_update_boms()
        t_meli_end = time.time()

        t_total = time.time() - t_start
        if self._meli_log_enabled() and t_total > MELI_BENCHMARK_THRESHOLD:
            _logger.warning(
                "MELI_BENCHMARK _action_done SLOW: moves=%d, total=%.3fs (super=%.3fs, meli=%.3fs)",
                len(self), t_total, t_super_end - t_start, t_meli_end - t_super_end
            )
        return moves_todo

    def _action_cancel(self):
        t_start = time.time()
        res = super(StockMove, self)._action_cancel()
        t_super_end = time.time()

        if not self._should_skip_meli_stock_update():
            self.meli_update_boms()
        t_meli_end = time.time()

        t_total = time.time() - t_start
        if self._meli_log_enabled() and t_total > MELI_BENCHMARK_THRESHOLD:
            _logger.warning(
                "MELI_BENCHMARK _action_cancel SLOW: moves=%d, total=%.3fs (super=%.3fs, meli=%.3fs)",
                len(self), t_total, t_super_end - t_start, t_meli_end - t_super_end
            )
        return res

    def _do_unreserve(self):
        t_start = time.time()
        res = super(StockMove, self)._do_unreserve()
        t_super_end = time.time()

        if not self._should_skip_meli_stock_update():
            self.meli_update_boms()
        t_meli_end = time.time()

        t_total = time.time() - t_start
        if self._meli_log_enabled() and t_total > MELI_BENCHMARK_THRESHOLD:
            _logger.warning(
                "MELI_BENCHMARK _do_unreserve SLOW: moves=%d, total=%.3fs (super=%.3fs, meli=%.3fs)",
                len(self), t_total, t_super_end - t_start, t_meli_end - t_super_end
            )
        return res
