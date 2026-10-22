# -*- coding: utf-8 -*-
"""[26.268, ex 26.231] Recalcula el estado de facturacion de las ventas ML por la
linea de envio. Desde 26.268 (ex 26.231) la linea de envio de una venta ML (servicio, entrega manual)
se factura como politica "pedido" si tiene precio y no tiene nada que facturar si es $0
(ver sale_order_line._meli_is_ml_shipping_line). Los valores YA guardados de
qty_to_invoice / invoice_status no se recalculan solos al actualizar el modulo: sin esto
las ventas viejas seguirian diciendo "Nada para facturar" / "A facturar" estando facturadas.

Solo toca campos calculados de estado (qty_to_invoice, invoice_status de linea y pedido):
no crea ni modifica facturas, asientos, entregas ni importes. Idempotente.
Loguea cantidades por estado antes/despues, sin datos de clientes."""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def _status_count(env, orders):
    res = {}
    for o in orders:
        res[o.invoice_status] = res.get(o.invoice_status, 0) + 1
    return res


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
    ])
    lines = lines.filtered(lambda l: l._meli_is_ml_shipping_line())
    if not lines:
        _logger.info("MELI 26.268: sin lineas de envio ML confirmadas, nada que recalcular.")
        return
    orders = lines.mapped('order_id')
    before = _status_count(env, orders)
    env.add_to_compute(SOL._fields['qty_to_invoice'], lines)
    env.add_to_compute(SOL._fields['invoice_status'], lines)
    env.add_to_compute(orders._fields['invoice_status'], orders)
    env.flush_all()
    orders.invalidate_recordset(['invoice_status'])
    after = _status_count(env, orders)
    _logger.info("MELI 26.268: estado de facturacion recalculado en %d ventas ML (%d lineas de envio). "
                 "Antes %s -> despues %s", len(orders), len(lines), before, after)
