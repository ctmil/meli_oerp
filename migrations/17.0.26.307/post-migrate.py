# -*- coding: utf-8 -*-
"""[158, 26.307] Recalcula las lineas de envio ML en $0 que quedaron "A facturar".

Hasta 26.306 shipment.py escribia `qty_to_invoice = pedida - facturada` DIRECTO sobre la linea
de envio cuando ML informaba un envio con precio, aunque el guard de venta facturada hubiera
frenado el cambio de precio: la linea quedaba en $0 con qty_to_invoice=1 / "A facturar" y el
pedido figuraba "A facturar" estando facturado (158, 25-oct). La regla del compute (26.268) da
0 / "Facturado" para esas lineas.

Alcance ACOTADO: solo lineas de envio ML (`_meli_is_ml_shipping_line`) confirmadas, con precio
<= 0 y qty_to_invoice != 0. Las lineas de envio CON precio no se tocan. Solo recalcula campos de
estado (qty_to_invoice, invoice_status de linea y pedido): no crea ni modifica facturas,
asientos, entregas ni importes. Idempotente. Loguea cantidades, sin datos de clientes.
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    SOL = env['sale.order.line']
    if 'is_delivery' not in SOL._fields:
        return
    lines = SOL.with_context(active_test=False).search([
        ('is_delivery', '=', True),
        ('order_id.meli_order_id', '!=', False),
        ('state', 'in', ('sale', 'done')),
        ('price_unit', '<=', 0.0),
        ('qty_to_invoice', '!=', 0.0),
    ])
    lines = lines.filtered(lambda l: l._meli_is_ml_shipping_line())
    if not lines:
        _logger.info("MELI 26.307: sin lineas de envio ML $0 con cantidad a facturar, nada que recalcular.")
        return
    orders = lines.mapped('order_id')
    env.add_to_compute(SOL._fields['qty_to_invoice'], lines)
    env.add_to_compute(SOL._fields['invoice_status'], lines)
    env.add_to_compute(orders._fields['invoice_status'], orders)
    env.flush_all()
    left = SOL.search_count([('id', 'in', lines.ids), ('qty_to_invoice', '!=', 0.0)])
    _logger.info("MELI 26.307: %d lineas de envio ML $0 recalculadas en %d ventas; quedan con cantidad "
                 "a facturar: %d", len(lines), len(orders), left)
