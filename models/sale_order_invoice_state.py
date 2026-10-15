# -*- coding: utf-8 -*-
# [26.230] Estado de FACTURA de una venta de MercadoLibre, para filtrar.
#
# Por que no alcanza `invoice_status` (el "Estado de facturacion" nativo):
#   ese campo dice si QUEDA ALGO POR FACTURAR, no si la venta TIENE factura. Con politica
#   "cantidad entregada" una venta ML ya facturada o con la entrega sin validar muestra
#   "Nada para facturar" -- medido en un cliente (15-oct): de 72 ventas ML confirmadas, 57
#   decian "Nada para facturar" y solo 1 "Facturada", aunque muchas tenian factura publicada.
#
# Este campo responde la otra pregunta: que facturas de cliente tiene la venta.
#   none     -> ninguna factura de cliente (ni borrador)
#   draft    -> solo facturas en borrador
#   posted   -> al menos una factura publicada (y ninguna nota de credito publicada)
#   refunded -> factura publicada y nota de credito publicada (devolucion / anulacion)
#
# NO almacenado: no agrega columna ni recomputos. La busqueda va por SQL y se acota a
# ventas de MercadoLibre (meli_order_id), que es donde se usan los filtros.
from odoo import api, fields, models

MELI_INVOICE_STATES = [
    ('none', 'Sin factura'),
    ('draft', 'Factura en borrador'),
    ('posted', 'Facturada (factura publicada)'),
    ('refunded', 'Con nota de crédito'),
]


class SaleOrder(models.Model):
    _inherit = "sale.order"

    meli_invoice_state = fields.Selection(
        MELI_INVOICE_STATES, string="ML Factura",
        compute='_compute_meli_invoice_state', search='_search_meli_invoice_state',
        help="Qué facturas de cliente tiene la venta (no confundir con 'Estado de facturación', "
             "que indica si queda algo POR facturar): Sin factura / Factura en borrador / "
             "Facturada (publicada) / Con nota de crédito.")

    @api.model
    def _meli_invoice_state_from_moves(self, moves):
        posted = moves.filtered(lambda m: m.state == 'posted')
        if posted.filtered(lambda m: m.move_type == 'out_refund') and \
                posted.filtered(lambda m: m.move_type == 'out_invoice'):
            return 'refunded'
        if posted.filtered(lambda m: m.move_type == 'out_invoice'):
            return 'posted'
        if moves.filtered(lambda m: m.state == 'draft' and m.move_type == 'out_invoice'):
            return 'draft'
        return 'none'

    @api.depends('order_line.invoice_lines.move_id.state', 'order_line.invoice_lines.move_id.move_type')
    def _compute_meli_invoice_state(self):
        for order in self:
            moves = order.order_line.invoice_lines.move_id.filtered(
                lambda m: m.move_type in ('out_invoice', 'out_refund'))
            order.meli_invoice_state = self._meli_invoice_state_from_moves(moves)

    def _meli_invoice_state_ids(self):
        """{estado: set(ids)} de las ventas ML con alguna factura de cliente (none = el resto)."""
        self.env['sale.order'].flush_model()
        self.env['sale.order.line'].flush_model()
        self.env['account.move'].flush_model()
        self.env.cr.execute("""
            SELECT sol.order_id,
                   bool_or(am.move_type = 'out_invoice' AND am.state = 'posted'),
                   bool_or(am.move_type = 'out_refund'  AND am.state = 'posted'),
                   bool_or(am.move_type = 'out_invoice' AND am.state = 'draft')
              FROM sale_order_line sol
              JOIN sale_order so ON so.id = sol.order_id AND so.meli_order_id IS NOT NULL
              JOIN sale_order_line_invoice_rel rel ON rel.order_line_id = sol.id
              JOIN account_move_line aml ON aml.id = rel.invoice_line_id
              JOIN account_move am ON am.id = aml.move_id
             WHERE am.move_type IN ('out_invoice', 'out_refund')
             GROUP BY sol.order_id
        """)
        res = {'draft': set(), 'posted': set(), 'refunded': set(), 'any': set()}
        for order_id, inv_posted, ref_posted, inv_draft in self.env.cr.fetchall():
            res['any'].add(order_id)
            if inv_posted and ref_posted:
                res['refunded'].add(order_id)
            elif inv_posted:
                res['posted'].add(order_id)
            elif inv_draft:
                res['draft'].add(order_id)
        res['none_complement'] = res['draft'] | res['posted'] | res['refunded']
        return res

    def _search_meli_invoice_state(self, operator, value):
        if operator in ('=', '!='):
            values = [value]
        elif operator in ('in', 'not in'):
            values = list(value or [])
        else:
            raise NotImplementedError("Operador no soportado para ML Factura: %s" % operator)
        groups = self._meli_invoice_state_ids()
        wanted = set(v for v in values if v)
        ids = set()
        for st in wanted - {'none'}:
            ids |= groups.get(st, set())
        positive = operator in ('=', 'in')
        if 'none' in wanted:
            # "Sin factura" = todo lo que NO tiene factura de cliente con estado definido
            # (incluye ventas sin ninguna factura); se expresa como complemento.
            excluded = groups['none_complement'] - ids
            return [('id', 'not in', list(excluded))] if positive else [('id', 'in', list(excluded))]
        return [('id', 'in', list(ids))] if positive else [('id', 'not in', list(ids))]


class MercadolibreOrders(models.Model):
    _inherit = "mercadolibre.orders"

    # Inversa de mercadolibre.claim.order_id: sin columna nueva. Permite filtrar ventas
    # por sus reclamos/devoluciones de ML (sale.order -> meli_orders -> claim_ids).
    claim_ids = fields.One2many('mercadolibre.claim', 'order_id', string="Reclamos ML")
