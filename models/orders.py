# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2009 Tiny SPRL (<http://tiny.be>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from odoo import fields, models, api
from odoo.tools import html_escape
from markupsafe import Markup
import logging
import re
from .meli_oerp_config import *

# Traducción de códigos de cancelación ML → español
_MELI_CANCEL_CODES_ES = {
    'expired_order':            'Orden vencida — plazo de pago superado (más de 20 días)',
    'buyer_cancel_pre_payment': 'El comprador canceló antes de realizar el pago',
    'buyer_cancel_accepted':    'Devolución solicitada por el comprador y aceptada',
    'seller_cancel':            'El vendedor canceló la orden',
    'meli_cancel':              'Cancelado por MercadoLibre',
    'non_payment':              'Pago no realizado',
    'out_of_stock':             'Sin stock disponible al momento de la venta',
    'refund_obligatory':        'Devolución obligatoria (reembolso)',
    'chargeback':               'Contracargo bancario',
    'payment_issue':            'Problema con el método de pago',
    'system_cancel':            'Cancelado automáticamente por el sistema',
    'receiver_absent':          'Receptor ausente al momento de la entrega',
    'fraud':                    'Fraude detectado',
    'duplicate':                'Orden duplicada',
    'forced_close':             'Cierre forzado por MercadoLibre',
    'quality_issue':            'Problema de calidad reportado',
    'user_request':             'Solicitado por el usuario',
    'internal_ml':              'Proceso interno de MercadoLibre',
    'not_delivery':             'No se realizó la entrega',
    'return_expired':           'Plazo de devolución vencido',
    'not_yet_shipped':          'No despachado en el tiempo requerido',
    'buyer_not_pick_up':        'El comprador no retiró el paquete',
    'bad_debt':                 'Deuda incobrable',
}
_MELI_REQUESTED_BY_ES = {
    'meli':     'MercadoLibre',
    'buyer':    'Comprador',
    'seller':   'Vendedor',
    'system':   'Sistema automático',
    'admin':    'Administrador ML',
    'mediator': 'Mediador',
}

#from ..melisdk.meli import Meli

import json

import logging
_logger = logging.getLogger(__name__)

import builtins  # so we can use builtins.Exception safely
from odoo.exceptions import ValidationError

from . import posting
from . import product
from . import shipment
from dateutil.parser import *
from datetime import *
from urllib.request import urlopen
import requests
try:
    from urllib import urlencode
except ImportError:
    from urllib.parse import urlencode

from . import versions
import time
try:
    from psycopg2 import errors as psycopg2_errors
except ImportError:
    psycopg2_errors = None
from .versions import *

class sale_order_line(models.Model):
    _inherit = "sale.order.line"

    meli_order_item_id = fields.Char('Meli Order Item Id')
    meli_order_item_variation_id = fields.Char('Meli Order Item Variation Id')
    meli_order_item_iva = fields.Char("Meli Order Item IVA")

class sale_order(models.Model):
    _inherit = "sale.order"

    meli_order_id =  fields.Char(string='Meli Order Id',index=True)
    meli_orders = fields.Many2many('mercadolibre.orders',string="ML Orders")

    MELI_STATUS_LABELS = {
        "paid ship-ready_to_shipprinted":        "Etiqueta impresa",
        "paid ship-ready_to_shipready_to_print": "Lista para imprimir",
        "paid ship-ready_to_ship":               "Listo para enviar",
        "paid ship-shippedout_for_delivery":     "En camino - en reparto",
        "paid ship-shipped":                     "En camino",
        "paid ship-delivered":                   "Entregado",
        "paid ship-not_delivered":               "No entregado",
        "paid ship-":                            "Pagado",
        "payment_in_process ship-":              "Pago en proceso",
        "cancelled ship-":                       "Cancelado",
    }

    def _meli_status_brief(self):
        # WARNING: This is a computed field - it must NEVER modify data or call APIs
        # Calling update_order_status() here was causing multiple pickings to be created
        # every time someone viewed the order in the UI
        for order in self:
            morder = order.meli_orders and order.meli_orders[0]
            if morder:
                # Only read existing values, do NOT call update_order_status()
                order.meli_status = morder.status
                order.meli_status_detail = morder.status_detail
                raw = str(morder.status)+" ship-"+( (morder.shipment_status and str(morder.shipment_status)) or "" ) + ( (morder.shipment_substatus and str(morder.shipment_substatus)) or "")
                order.meli_status_brief = self.MELI_STATUS_LABELS.get(raw, raw)
            else:
                order.meli_status_brief = "-"
                order.meli_status =  order.meli_status
                order.meli_status_detail = order.meli_status_detail

    def search_meli_status_brief(self, operator, value):
        #_logger.info(search_meli_status_brief")
        #_logger.info(operator)
        #_logger.info(value)
        if operator == 'ilike':
            #name = self.env.context.get('name', False)
            #if name is not False:
            id_list = []
            #_logger.info(self.env.context)
            #name = self.env.context.get('name', False)
            sale_orders = self.env['sale.order'].search([], limit=10000,order='id desc')
            if (value):
                for so in sale_orders:
                    if (value in so.meli_status_brief):
                        id_list.append(so.id)

            return [('id', 'in', id_list)]
        else:
            _logger.error(
                'The field name is not searchable'
                ' with the operator: {}',format(operator)
            )

    def _search_meli_buyer_name( self, operator, value ):
        #_logger.info("_search_meli_buyer_name")
        #_logger.info(operator)
        #_logger.info(value)
        if operator == 'ilike':
            #name = self.env.context.get('name', False)
            #if name is not False:
            id_list = []
            #_logger.info(self.env.context)
            #name = self.env.context.get('name', False)
            meli_orders = []
            buyer_ids = []
            if value:
                buyers = self.env['mercadolibre.buyers'].search([('name','=ilike','%'+str(value)+'%')], limit=10000,order='name asc')
                if buyers:
                    for buyer in buyers:
                        buyer_ids.append(buyer.id)
                    if buyer_ids:
                        meli_orders = self.env['mercadolibre.orders'].search([('buyer','in',buyer_ids)], limit=10000 )
            #sale_orders = self.env['sale.order'].search([], limit=10000,order='id desc')
            #if (value):
                #for so in sale_orders:
                #    if (value in so.meli_buyer_name):
                #        id_list.append(so.id)
            if (meli_orders):
                for mo in meli_orders:
                    if mo.sale_order and mo.sale_order.id:
                        id_list.append(mo.sale_order.id)
            return [('id', 'in', id_list)]
        else:
            _logger.error(
                'The field name is not searchable'
                ' with the operator: {}',format(operator)
            )

    @api.depends('meli_orders')
    def _get_meli_order( self ):
        for so in self:
            so.meli_order = False
            so.meli_buyer = False
            so.meli_buyer_name = False

            meli_order = so.meli_orders and so.meli_orders[0]
            if meli_order:
                so.meli_order = meli_order
                meli_buyer = meli_order and meli_order.buyer
                if meli_buyer:
                    so.meli_buyer = meli_buyer
                    so.meli_buyer_name = meli_buyer and meli_buyer.name

    meli_order = fields.Many2one( 'mercadolibre.orders',string="Meli Orden", compute="_get_meli_order", store=True, index=True )
    meli_buyer =  fields.Many2one( "mercadolibre.buyers",string="Meli Comprador", compute="_get_meli_order", store=True, index=True)
    meli_buyer_name =  fields.Char( string="Meli Comprador Nombre", compute="_get_meli_order", search=_search_meli_buyer_name, store=True, index=True )

    meli_status = fields.Selection( [
        #Initial state of an order, and it has no payment yet.
        ("confirmed","Confirmado"),
        #The order needs a payment to become confirmed and show users information.
        ("payment_required","Pago requerido"),
        #There is a payment related with the order, but it has not accredited yet
        ("payment_in_process","Pago en proceso"),
        #The order has a related payment and it has been accredited.
        ("paid","Pagado"),
        #The order has a related partial payment and it has been accredited.
        ("partially_paid","Parcialmente Pagado"),
        #The order has not completed by some reason.
        ("cancelled","Cancelado"),
        #The order has been invalidated as it came from a malicious buyer.
        ("invalid","Invalido: malicious"),
        #The order status is cancelled, but an action is pending to complete the process.
        ("pending_cancel", "Pendiente de cancelar"),

        ("partially_refunded", "Parcialmente reembolsado")
        ], string='Order Status')

    meli_status_brief = fields.Char(string="Meli Status Brief", compute="_meli_status_brief", search=search_meli_status_brief, store=False, index=True)

    meli_status_detail = fields.Text(string='Status detail, in case the order was cancelled.')
    meli_date_created = fields.Datetime('Meli Creation date')
    meli_date_closed = fields.Datetime('Meli Closing date')

#        'meli_order_items': fields.one2many('mercadolibre.order_items','order_id','Order Items' ),
#        'meli_payments': fields.one2many('mercadolibre.payments','order_id','Payments' ),
    meli_shipping = fields.Text(string="Shipping")

    meli_total_amount = fields.Float(string='Total amount')
    meli_shipping_amount = fields.Float(string='Shipping Amount',help='Pago envío')
    meli_shipping_cost = fields.Float(string='Shipping Cost',help='Gastos de envío')
    meli_shipping_seller_cost = fields.Float(string='Shipping Seller Cost',help='Gastos de envío (Vendedor)')
    meli_shipping_list_cost = fields.Float(string='Shipping List Cost',help='Gastos de envío, costo de lista/interno')
    meli_paid_amount = fields.Float(string='Paid amount',help='Paid amount (include shipping cost)')
    meli_fee_amount = fields.Float(string='Fee amount',help="Comisión")
    meli_coupon_amount = fields.Float(string='Coupont amount',help="Descuento",default=0.0)
    meli_discount_seller_amount = fields.Float(string='Discount Seller Amount',help="Monto del descuento que absorbe el vendedor (desde /orders/{id}/discounts)",default=0.0)
    meli_financing_fee_amount = fields.Float(string='Financing fee amount',help="Financiamiento",default=0.0)

    meli_currency_id = fields.Char(string='Currency ML')
#        'buyer': fields.many2one( "mercadolibre.buyers","Buyer"),
#       'meli_seller': fields.text( string='Seller' ),
    meli_shipping_id =  fields.Char('Meli Shipping Id')
    meli_shipment = fields.Many2one('mercadolibre.shipment',string='Meli Shipment Obj')
    meli_shipment_pdf_file = fields.Binary(string='Pdf File',attachment=True, related="meli_shipment.pdf_file",readonly=True)
    meli_shipment_pdf_filename = fields.Char(string='Pdf Filename',related="meli_shipment.pdf_filename",readonly=True)
    meli_shipment_logistic_type = fields.Char(string="Logistic Type",index=True)
    meli_update_forbidden = fields.Boolean(string="Bloqueado para actualizar desde ML",default=False, index=True)

    meli_handling_limit = fields.Datetime(
        related='meli_shipment.estimated_handling_limit',
        readonly=True, string="Límite despacho ML")

    meli_handling_limit_status = fields.Selection([
        ('none',    'Sin fecha límite'),
        ('ok',      'En plazo'),
        ('urgent',  'Urgente (< 4 h)'),
        ('overdue', 'Vencido'),
    ], compute='_compute_so_handling_limit_status', store=False,
       string="Estado límite despacho")

    @api.depends('meli_shipment.estimated_handling_limit', 'meli_shipment.estimated_buffering_date')
    def _compute_so_handling_limit_status(self):
        from datetime import timedelta
        now = fields.Datetime.now()
        for rec in self:
            ship = rec.meli_shipment
            ehl = (ship.estimated_handling_limit or ship.estimated_buffering_date) if ship else False
            if not ehl:
                rec.meli_handling_limit_status = 'none'
            elif ehl < now:
                rec.meli_handling_limit_status = 'overdue'
            elif ehl < now + timedelta(hours=4):
                rec.meli_handling_limit_status = 'urgent'
            else:
                rec.meli_handling_limit_status = 'ok'

    def _ml_shipping_status(self):

        for ord in self:

            ord.ml_shipping_status = 'draft'

            stats = {
            "draft": 0,
            "waiting": 0,
            "confirmed": 0,
            "assigned": 0,
            "done": 0,
            "cancel": 0,
            }
            for spick in ord.picking_ids:
                if (spick.state in ['draft']):
                    ord.ml_shipping_status = 'draft'
                    stats["draft"]+=1
                    break;
                if (spick.state in ['waiting']):
                    ord.ml_shipping_status = 'waiting'
                    stats["waiting"]+=1
                    break;
                if (spick.state in ['confirmed']):
                    ord.ml_shipping_status = 'confirmed'
                    stats["confirmed"]+=1
                    break;
                if (spick.state in ['assigned']):
                    ord.ml_shipping_status = 'assigned'
                    stats["assigned"]+=1
                    break;
                if (spick.state in ['done']):
                    ord.ml_shipping_status = 'done'
                    stats["done"]+=1
                    continue;
                if (spick.state in ['cancel']):
                    ord.ml_shipping_status = 'cancel'
                    stats["cancel"]+=1
                    break;

            if stats["done"] and (stats["cancel"] or stats["draft"] or stats["waiting"] or stats["assigned"] or stats["confirmed"]):
                ord.ml_shipping_status = 'done_to_verify'




    ml_shipping_status = fields.Selection(selection=[
    ('draft','Entrega Borrador'),
    ('waiting','Entrega Esperando'),
    ('confirmed','Entrega Preparado'),
    ('assigned','Entrega Listo'),
    ('done','Entrega Hecho'),
    ('done_to_verify','Entrega hecha a verificar'),
    ('cancel','Entrega Cancelado'),
    ],compute=_ml_shipping_status)

    def action_confirm(self):
        #_logger.info("meli order action_confirm: " + str(self.mapped("name")) )
        res = super(sale_order,self).action_confirm()
        try:
            for order in self:
                if(order.meli_order_id):
                    for line in order.order_line:
                        if ((line.is_delivery and line.price_unit<=0.0) and line.qty_to_invoice>0):
                            #_logger.info(line)
                            line.write({ "qty_to_invoice": 0.0 })
                            #_logger.info(line.qty_to_invoice)
                            pass;
        except:
            pass;

        try:
            company = self.env.user.company_id
            #_logger.info(Company: "+str(company))
            #_logger.info(Order done: company.mercadolibre_cron_post_update_stock: "+str(company.mercadolibre_cron_post_update_stock))
            #for order in self:
            #    for line in order.order_line:
            #        if (company.mercadolibre_cron_post_update_stock):
            #            if line.product_id and line.product_id.meli_id and line.product_id.meli_pub:
            #                _logger.info("Order done: product_post_stock: "+str(line.product_id.meli_id))
            #                #line.product_id.product_post_stock()
        except:
            pass;
        return res

    def action_done(self):
        #_logger.info(meli order action done: " + str(self.mapped("name")) )
        res = super(sale_order,self).action_done()
        try:
            for order in self:
                if(order.meli_order_id):
                    for line in order.order_line:
                        if ((line.is_delivery and line.price_unit<=0.0) and line.qty_to_invoice>0):
                            #_logger.info(line)
                            line.write({ "qty_to_invoice": 0.0 })
                            #_logger.info(line.qty_to_invoice)
                            pass;
        except:
            pass;

        try:
            company = self.env.user.company_id
            #_logger.info(Company: "+str(company))
            #_logger.info(Order done: company.mercadolibre_cron_post_update_stock: "+str(company.mercadolibre_cron_post_update_stock))
            #for order in self:
            #    for line in order.order_line:
            #        if (company.mercadolibre_cron_post_update_stock):
            #            if line.product_id and line.product_id.meli_id and line.product_id.meli_pub:
            #                #_logger.info(Order done: product_post_stock: "+str(line.product_id.meli_id))
            #                line.product_id.product_post_stock()
        except:
            pass;
        return res

    def _get_meli_invoices(self):
        invoices = self.env[acc_inv_model].search([('origin','=',self.name)])
        #_logger.info("_get_meli_invoices")
        #_logger.info(self)
        #_logger.info(invoices)
        if invoices:
            return invoices[0]
        return None

    def meli_amount_to_invoice( self, meli=None, config=None ):

        total_config = (config and "mercadolibre_order_total_config" in config._fields) and config.mercadolibre_order_total_config

        meli_ord = None
        meli_shipment = None

        if self.meli_orders:
            meli_ord = self.meli_orders[0]
            meli_shipment = self.meli_shipment

        if not config or not total_config:
            return self.meli_total_amount;

        including_shipping_cost = "mercadolibre_including_shipping_cost" in config._fields and config.mercadolibre_including_shipping_cost
        including_shipping_cost = including_shipping_cost or "always"


        if total_config in ['manual']:
            #resolve always as conflict
            return 0

        seller_discount = self.meli_discount_seller_amount or 0.0
        _coupon_cap = self.meli_coupon_amount or 0.0
        # /orders/{id}/discounts amounts.seller has two meanings depending on the order:
        # (A) List-price reduction already reflected in SO unit_price → over-deduction:
        #     (meli_paid_amount - seller_discount) falls BELOW so.amount_total.
        #     Cap at coupon_amount to avoid under-invoicing.
        # (B) Legitimate seller-absorbed discount not in SO unit_price →
        #     (meli_paid_amount - seller_discount) is ABOVE or near so.amount_total.
        #     No cap needed; the tolerance in confirm_ml/meli_create_invoice covers the rest.
        # Distinguish by result: cap only when uncapped amount_to_invoice < so.amount_total.
        if _coupon_cap > 0 and self.amount_total > 0:
            _uncapped = (self.meli_paid_amount or 0.0) - seller_discount
            if _uncapped < self.amount_total:
                seller_discount = min(seller_discount, _coupon_cap)

        if total_config in ['manual_conflict']:

            if abs(self.meli_total_amount - self.meli_paid_amount + self.meli_coupon_amount)<1.0:
                if ( meli_shipment and meli_shipment.shipping_cost>0 and meli_shipment.shipping_list_cost>0 ):
                    return 0
                return (self.meli_paid_amount - seller_discount)
            else:
                #conflict if do not match
                if ( meli_shipment and meli_shipment.shipping_cost>0 and meli_shipment.shipping_list_cost>0 ):
                    if ( self.meli_total_amount + self.meli_shipping_cost - self.meli_paid_amount )<1.0:
                        return (self.meli_paid_amount - seller_discount)
                return 0

        if total_config in ['paid_amount','transaction_amount']:

            if (including_shipping_cost=="never"):
                return (self.meli_paid_amount - seller_discount - self.meli_shipping_amount)

            return (self.meli_paid_amount - seller_discount)

        if total_config in ['total_amount']:
            return self.meli_total_amount

        return 0

    def meli_confirm_order( self, meli=None, config=None ):
        res = {}

        if ( self.meli_status=="paid" and self.state in ('draft','sent')):

            #_logger.info(paid_confirm ok! confirming sale")

            if (self.is_pricelist_meli( meli=meli, config=config)):
                #_logger.info("Action confirm!!")
                self.action_confirm()

        return res

    def meli_create_invoice( self, meli=None, config=None):
        _logger.info("Meli Base meli_create_invoice")
        res = {}
        if self.state in ['sale','done']:
            #_logger.info(paid_confirm with invoice ok! create invoice")
            self.action_invoice_create()
        return res

    def meli_deliver(self, meli=None, config=None, data=None):
        res = {}
        cancel_backorder = False
        # Sólo operamos si la orden de venta ya está confirmada o hecha
        if self.state in ('sale', 'done') and self.picking_ids:
            for spick in self.picking_ids:
                try:
                    #Confirmar el picking si aún no está confirmado
                    if spick.state == 'draft':
                        spick.action_confirm()

                    #Asignar existencias (reserva y crea move_line_ids)
                    if (spick.state in ['confirmed','partially_available','waiting','draft']):
                        spick.action_assign()

                    #Marcar qty_done = product_uom_qty en todas las líneas
                    if spick.move_line_ids:
                        stock_picking_set_quantities(picking=spick)

                    #Validar el picking para mover físicamente y generar valoración
                    if spick.state == 'assigned':
                        action = spick.button_validate()

                        # Wizard de transferencia inmediata (stock.immediate.transfer)
                        if isinstance(action, dict) and action.get('res_model') == 'stock.immediate.transfer':
                            Immediate = self.env['stock.immediate.transfer'].sudo()
                            wiz = action.get('res_id') and Immediate.browse(action['res_id']).exists()
                            if not wiz:
                                # Fallback: crear wizard si por alguna razón no vino res_id
                                wiz = Immediate.create({'pick_ids': [(6, 0, [spick.id])]})
                            # En v15+ process() mira button_validate_picking_ids en el contexto
                            wiz.with_context(button_validate_picking_ids=spick.ids).process()

                        # Wizard de backorder (stock.backorder.confirmation)
                        if isinstance(action, dict) and action.get('res_model') == 'stock.backorder.confirmation':
                            Backorder = self.env['stock.backorder.confirmation'].sudo()
                            wiz = action.get('res_id') and Backorder.browse(action['res_id']).exists()
                            if not wiz:
                                wiz = Backorder.create({'pick_ids': [(6, 0, [spick.id])]})
                            if cancel_backorder:
                                # Algunas versiones traen process_cancel_backorder, otras usan process() + contexto
                                if hasattr(wiz, 'process_cancel_backorder'):
                                    wiz.process_cancel_backorder()
                                else:
                                    wiz.with_context(cancel_backorder=True).process()
                            else:
                                wiz.process()

                except Exception as e:
                    _logger.error(f"Error validando picking {spick.id}: {e}")
                    res = {'error': str(e)}
        return res

    def meli_cancel_with_detail(self, cancel_msg):
        """
        Cancela la orden forzando la cancelacion cuando Meli informa un cancel_detail.
        - Si hay albaranes entregados (done), crea devoluciones automaticamente.
        - Si hay facturas publicadas (posted), intenta resetearlas a borrador o
          notifica que se requiere una nota de credito manual.
        - Facturas: delega a _meli_cancel_invoices() si existe (respeta
          mercadolibre_invoice_cancel_mode). Si no existe el método, NO toca
          las facturas y postea en el chatter para gestión manual.
        - Cancela la orden de venta (desbloqueandola si hace falta) y postea
          el motivo en el chatter de la orden y de cada factura involucrada.
        """
        # 1. Devolver albaranes ya entregados
        # _meli_return_done_pickings usa hasattr para compatibilidad Odoo 16/17/18
        # (action_create_returns / create_returns) y evita crear devoluciones duplicadas.
        self._meli_return_done_pickings()

        # 2. Gestionar facturas existentes — delegar a la política de configuración
        _has_unresolved_posted_invoice = False
        if hasattr(self, '_meli_cancel_invoices'):
            try:
                self._meli_cancel_invoices()
            except Exception as e:
                _logger.warning("meli_cancel_with_detail: _meli_cancel_invoices falló para %s: %s", self.name, e)
        else:
            # Sin módulo accounting: solo notificar, no tocar facturas
            for invoice in self.invoice_ids:
                if invoice.state == 'posted':
                    # Intentar resetear a borrador para poder cancelar
                    reverted = False
                    try:
                        invoice.button_draft()
                        reverted = True
                        invoice.message_post(
                        body=cancel_msg + " — Factura revertida a borrador por cancelación de orden en MercadoLibre.",
                        message_type=order_message_type
                        )
                    except Exception as e:
                        _logger.warning("meli_cancel_with_detail: no se pudo revertir factura %s a borrador: %s", invoice.name, e)
                    if not reverted:
                        # No se pudo revertir: la orden NO debe cancelarse automáticamente.
                        # El usuario debe crear una Nota de Crédito manualmente desde la factura.
                        _has_unresolved_posted_invoice = True
                        invoice.message_post(
                        body=cancel_msg + " — ⚠️ ACCIÓN REQUERIDA: esta factura no pudo revertirse a borrador. "
                            "Debe crear una NOTA DE CRÉDITO manualmente para reversarla. "
                            "La orden de venta NO fue cancelada automáticamente para permitir la gestión.",
                        message_type=order_message_type
                        )
                        self.message_post(
                        body="⚠️ Cancelación de ML pendiente: factura %s publicada no pudo revertirse. "
                            "Crear nota de crédito desde la factura y luego cancelar la orden manualmente. "
                            "Motivo ML: %s" % (invoice.name, cancel_msg),
                        message_type=order_message_type
                        )
                elif invoice.state == 'draft':
                    try:
                        if hasattr(invoice, 'button_cancel'):
                            invoice.button_cancel()
                    except Exception as e:
                        _logger.warning("meli_cancel_with_detail: no se pudo cancelar borrador de factura %s: %s", invoice.name, e)

        # Verificar si quedaron facturas publicadas sin resolver
        posted_invoices = self.invoice_ids.filtered(lambda inv: inv.state == 'posted' and inv.move_type == 'out_invoice')
        if posted_invoices:
            _has_unresolved_posted_invoice = True
            self.message_post(
                body="⚠️ Cancelación de ML pendiente: %d factura(s) publicada(s) sin resolver (%s). "
                     "Gestionar manualmente. Motivo ML: %s" % (
                    len(posted_invoices),
                    ", ".join(posted_invoices.mapped('name')),
                    cancel_msg
                ),
                message_type=order_message_type
            )

        if _has_unresolved_posted_invoice:
            _logger.warning("meli_cancel_with_detail: orden %s NO cancelada — factura publicada sin resolver. Acción manual requerida.", self.name)
            return

        # 3. Desbloquear si la orden esta bloqueada o en estado done
        is_locked = self.state == 'done' or ('locked' in self._fields and self.locked)
        if is_locked:
            try:
                self.action_unlock()
            except Exception as e:
                _logger.warning("meli_cancel_with_detail: no se pudo desbloquear la orden %s: %s", self.name, e)

        # 4. Cancelar la orden de venta
        if self.state in ['draft', 'sale', 'sent', 'done']:
            try:
                self.with_context(disable_cancel_warning=disable_cancel_warning_enabled).action_cancel()
            except Exception as e:
                _logger.error("meli_cancel_with_detail: no se pudo cancelar la orden %s: %s", self.name, e, exc_info=True)
                self.message_post(
                    body="No se pudo cancelar la orden automáticamente: %s. Gestionar manualmente." % str(e),
                    message_type=order_message_type
                )

        # 5. Postear el motivo de cancelacion en el chatter de la orden
        self.message_post(body=cancel_msg, message_type=order_message_type)

    def is_meli_order_fulfillment( self ):
        res = False
        res = self.meli_shipment_logistic_type and "fulfillment" in self.meli_shipment_logistic_type

        return res

    def is_pricelist_meli( self, meli=None, config=None ):
        res = False
        #config ok y pricelist existe
        res = config and config.mercadolibre_pricelist and config.mercadolibre_pricelist.id
        res = res and ( config.mercadolibre_pricelist.id == self.pricelist_id.id )
        return res

    def meli_repair_missing_pickings(self):
        """Repair sale orders that are confirmed (state='sale') but have stock.move
        records with picking_id=NULL.  This can happen when an exception inside
        action_confirm() is silently caught, leaving the SO confirmed but without
        a delivery order.

        Strategy: call _assign_picking() directly on the orphan moves so that
        Odoo creates (or reassigns) the picking without re-running full procurement.
        Safe to call multiple times (idempotent).
        """
        repaired = 0
        skipped = 0
        for so in self:
            if so.state not in ('sale', 'done'):
                skipped += 1
                continue
            orphan_moves = self.env['stock.move'].search([
                ('picking_id', '=', False),
                ('state', 'in', ['confirmed', 'waiting', 'partially_available', 'assigned']),
                ('sale_line_id.order_id', '=', so.id),
            ])
            if not orphan_moves:
                skipped += 1
                continue
            _logger.warning(
                "meli_repair_missing_pickings: SO %s (id=%d) has %d orphan moves — attempting _assign_picking()",
                so.name, so.id, len(orphan_moves)
            )
            for move in orphan_moves:
                try:
                    move.with_context(
                        tracking_disable=True,
                        mail_notrack=True,
                        meli_skip_stock_update=True,
                    )._assign_picking()
                    repaired += 1
                except Exception as e:
                    _logger.error(
                        "meli_repair_missing_pickings: failed to assign picking for move %d on SO %s: %s",
                        move.id, so.name, e, exc_info=True
                    )
        _logger.info("meli_repair_missing_pickings: repaired=%d skipped=%d", repaired, skipped)
        if repaired:
            msg = "Entrega reparada correctamente. Recargá la página para ver el botón de entrega."
            msg_type = 'success'
        else:
            msg = "No se encontraron movimientos de stock huérfanos para reparar."
            msg_type = 'warning'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Reparar entrega',
                'message': msg,
                'type': msg_type,
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def _meli_return_done_pickings(self):
        """Create return pickings for done outgoing pickings when MeLi cancels the order."""
        ReturnWiz = self.env["stock.return.picking"]
        for picking in self.picking_ids.filtered(
            lambda p: p.state == "done" and p.picking_type_code == "outgoing"
        ):
            # Skip if a return already exists for this picking.
            # Correct check: look for moves that reference this picking's moves as their origin.
            # (origin_returned_move_id is set on the RETURN move, not the original OUT move,
            # so checking it on picking.move_ids was always False — causing duplicate returns.)
            already_returned = self.env['stock.move'].search_count([
                ('origin_returned_move_id', 'in', picking.move_ids.ids),
                ('state', '!=', 'cancel'),
            ])
            if already_returned:
                continue
            try:
                wiz = ReturnWiz.with_context(active_id=picking.id, active_ids=[picking.id], active_model="stock.picking").create({})
                # Guard cantidad-cero: si el wizard no calculó nada a devolver, no intentar
                # (action_create_returns tiraría 'Especifique al menos una cantidad diferente a
                # cero' y el cron lo reintentaría en bucle). Típico de pickings FULL cuyo stock
                # vive en el fulfillment de ML.
                if "product_return_moves" in wiz._fields and not sum(wiz.product_return_moves.mapped("quantity")):
                    _logger.info("Return omitida para %s: sin cantidades a devolver (FULL).", picking.name)
                    continue
                if hasattr(wiz, "action_create_returns"):
                    wiz.action_create_returns()
                elif hasattr(wiz, "create_returns"):
                    wiz.create_returns()
                else:
                    _logger.warning("stock.return.picking: no create_returns method found")
                    meli_message_post(self, "No se pudo devolver el albarán %s automáticamente: método no encontrado. Gestionar manualmente." % picking.name)
                    continue
                meli_message_post(self, "Devolución creada automáticamente para albarán %s (orden cancelada por MeLi)." % picking.name)
            except Exception as e:
                _logger.error("Error creating return for picking %s: %s", picking.name, e, exc_info=True)
                meli_message_post(self, "No se pudo devolver el albarán %s automáticamente. Error: %s. Gestionar manualmente." % (picking.name, str(e)))

    def meli_confirm_ready( self, meli=None, config=None ):
        """Evalúa, SIN efectos secundarios, si la venta ML está lista para confirmar.

        Devuelve una tupla (ready: bool, reason: str). `reason` queda vacío cuando
        `ready` es True; si no, contiene un motivo legible para mostrar al usuario.

        Es el corazón de `confirm_ml` extraído como helper read-only para que tanto
        la confirmación como el wizard de importación (pestaña "Ventas incompletas")
        compartan exactamente la misma matemática (mismo amount_to_invoice, misma
        tolerancia con cupón/retenciones, misma comparación con/sin envío).

        Notas:
        - Las órdenes canceladas NO son "incompletas": se reportan ready=True con
          reason vacío para que el llamador las excluya del listado de incompletas.
        - Devuelve también el detalle numérico embebido en `reason` cuando hay
          mismatch, igual que el mensaje MELI de confirm_ml.
        """
        # Órdenes canceladas: NO son incompletas (las maneja confirm_ml aparte).
        if self.meli_status == "cancelled":
            return (True, "")

        # Sin pedido de venta no se puede evaluar el monto.
        if not self.order_line:
            return (False, "Sin líneas de venta / producto no encontrado (SKU sin vincular)")

        amount_to_invoice = self.meli_amount_to_invoice( meli=meli, config=config )
        # coupon_amount es costo de ML, no del vendedor — el SO ya tiene el precio completo.
        # La tolerancia extendida se mantiene como safety-net para órdenes anteriores al fix
        # que todavía tengan el descuento aplicado en líneas.
        _tolerance = 1.1
        _coupon = abs(self.meli_coupon_amount or 0.0)
        if _coupon > 0:
            _tolerance = max(_tolerance, _coupon * 1.3)
        # If retention taxes are on SO lines (legacy, without withholding module),
        # add back their amounts so the check compares like-for-like.
        # Skip withholding-on-payment taxes — they belong on the payment, not SO lines.
        tax_field = SaleOrderLineTaxField(self)
        _has_wth = 'is_withholding_tax_on_payment' in self.env['account.tax']._fields
        _retention_total = 0.0
        for line in self.order_line:
            if line.price_unit <= 0:
                continue
            for tax in line[tax_field]:
                if tax.amount < 0:
                    if _has_wth and tax.is_withholding_tax_on_payment:
                        continue
                    _retention_total += abs(line.price_subtotal * tax.amount / 100.0)
        _amount_total_before_retentions = self.amount_total + _retention_total
        _diff_direct = abs( float(amount_to_invoice) - _amount_total_before_retentions )
        # For self_service logistics the SO has no shipping line, but
        # meli_paid_amount (and thus amount_to_invoice) includes the shipping
        # amount. Accept if the diff is fully explained by shipping.
        _shipping = self.meli_shipping_amount or 0.0
        _diff_no_ship = abs( float(amount_to_invoice) - _shipping - _amount_total_before_retentions ) if _shipping > 0 else _diff_direct
        confirm_cond = (amount_to_invoice > 0) and (
            _diff_direct < _tolerance
            or (_shipping > 0 and _diff_no_ship < _tolerance)
        )
        if not confirm_cond:
            serror = (
                "MELI: Condition not met: meli_paid_amount and amount_total doesn't match, "
                "check products missings, taxes and discounts. "
                "(amount_to_invoice=%.2f, amount_total=%.2f, diff=%.2f, diff_no_ship=%.2f, tolerance=%.2f, "
                "coupon=%.2f, seller_discount=%.2f)"
            ) % (
                amount_to_invoice or 0, self.amount_total or 0,
                _diff_direct, _diff_no_ship,
                _tolerance, _coupon, self.meli_discount_seller_amount or 0,
            )
            return (False, serror)

        return (True, "")

    def confirm_ml( self, meli=None, config=None ):
        try:
            #_logger.info("meli_oerp confirm_ml")
            company = (config and 'company_id' in config._fields and config.company_id) or self.env.user.company_id
            config = config or company
            res = {}

            stock_picking = self.env["stock.picking"]

            #cancelling with no conditions, here because paid_amount is 0, dont use confirm_cond
            if (self.meli_status=="cancelled"):
                cancel_msg = "Orden cancelada por MercadoLibre."
                if self.meli_status_detail:
                    cancel_msg += " Motivo: %s" % self.meli_status_detail
                # meli_cancel_with_detail already calls _meli_return_done_pickings() internally.
                # Do NOT call it here too — that caused duplicate IN return pickings per cron cycle.
                self.meli_cancel_with_detail(cancel_msg)
                return res

            # Misma matemática que antes, ahora vía helper read-only compartido con
            # el wizard de importación. confirm_cond conserva idéntico comportamiento.
            confirm_ready, serror = self.meli_confirm_ready( meli=meli, config=config )
            confirm_cond = confirm_ready
            if not confirm_cond:
                # FIX #415 (NipSkin/Inity 520, tickets #414/#415): evitar spam en chatter.
                # El cron reintenta la orden cada ciclo (afecta ordenes con amount_total=0 sin
                # lineas) y re-posteaba siempre. Postear solo si no hay ya un "Condition not met"
                # en los ultimos ~5 mensajes.
                _recent_cond = self.message_ids[:5].filtered(
                    lambda m: m.body and "Condition not met" in (m.body or "")
                )
                if not _recent_cond:
                    meli_message_post(self, serror, config=config)
                return {'error': serror}

            if (self.state in ['draft']):
                meli_message_post(self, "Monto correcto, listo para confirmar venta.", config=config)

            #check currency
            pricelist_is_meli = self.is_pricelist_meli(meli=meli, config=config)
            confirm_cond = confirm_cond and pricelist_is_meli
            if not confirm_cond:
                serror = "MELI: Condition not met: pricelist is not correct, check partners property_product_pricelist."
                meli_message_post(self, serror, config=config)
                return {'error': serror}

            if (self.is_meli_order_fulfillment()):

                if ( config.mercadolibre_order_confirmation_full and "paid_confirm" in config.mercadolibre_order_confirmation_full):
                    self.meli_confirm_order( meli=meli, config=config )

                if (config.mercadolibre_order_confirmation_full and "paid_delivered" in config.mercadolibre_order_confirmation_full):

                    self.meli_confirm_order( meli=meli, config=config )

                    res = self.meli_deliver( meli=meli, config=config )


                if (config.mercadolibre_order_confirmation_full=="paid_confirm_with_invoice" or config.mercadolibre_order_confirmation_full=="paid_delivered_with_invoice"):
                    self.meli_create_invoice( meli=meli, config=config )

            else:

                if (config.mercadolibre_order_confirmation and "paid_confirm" in config.mercadolibre_order_confirmation):
                    self.meli_confirm_order( meli=meli, config=config )

                if (config.mercadolibre_order_confirmation and "paid_delivered" in config.mercadolibre_order_confirmation):

                    self.meli_confirm_order( meli=meli, config=config )

                    res = self.meli_deliver( meli=meli, config=config )

                if (config.mercadolibre_order_confirmation=="paid_confirm_with_invoice" or config.mercadolibre_order_confirmation=="paid_delivered_with_invoice"):
                    self.meli_create_invoice( meli=meli, config=config )


        except Exception as e:
            # Log diagnostic context. Use self.id (in-memory) and str(e) only —
            # do NOT access ORM fields (self.name, self.state) because the DB
            # transaction may be aborted (InFailedSqlTransaction).
            try:
                _logger.error(
                    "MELI confirm_ml EXCEPTION on SO id=%s: %s",
                    self.id, str(e), exc_info=True,
                )
            except Exception:
                _logger.error("MELI confirm_ml EXCEPTION (cannot log details): %s", str(e))
            return { 'error': str(e) }
        #_logger.info("meli_oerp confirm_ml ended.")

        # Post-confirmation integrity check: warn if SO is confirmed but has no picking.
        if self.state in ('sale', 'done') and not self.picking_ids:
            orphan = self.env['stock.move'].search([
                ('picking_id', '=', False),
                ('state', 'not in', ['cancel', 'draft']),
                ('sale_line_id.order_id', '=', self.id),
            ])
            if orphan:
                _logger.warning(
                    "MELI confirm_ml POST-CHECK: SO '%s' (id=%d) confirmed but has %d "
                    "orphan moves with no picking — attempting auto-repair",
                    self.name, self.id, len(orphan)
                )
                try:
                    self.meli_repair_missing_pickings()
                except Exception as repair_err:
                    _logger.error("meli_repair_missing_pickings failed for SO %s: %s",
                                  self.name, repair_err, exc_info=True)

        return res

    def meli_fix_team( self, meli=None, config=None ):
        so = self
        if not so:
            return None

        company = (config and "company_id" in config._fields and config.company_id) or so.company_id or self.env.user.company_id

        seller_team = (config and config.mercadolibre_seller_team) or None
        seller_user = (config and config.mercadolibre_seller_user) or None

        #_logger.info("meli_fix_team: company: "+str(company.name)
        #            +" seller_team:"+str(seller_team and seller_team.name))


        team_id = so.sudo().team_id
        user_id = so.sudo().user_id
        warehouse_id = so.sudo().warehouse_id

        #_logger.info("meli_fix_team: so.team_id: "+str(team_id and team_id.name)+ " warehouse_id: "+str(warehouse_id and warehouse_id.company_id.name) )
        #_logger.info("check warehouse_id company")
        if (warehouse_id and warehouse_id.company_id and (warehouse_id.company_id.id != company.id)):
            #unassign, wrong warehouse_id company
            so.sudo().write( { 'warehouse_id': None } )
        #_logger.info("check team")
        # Un equipo SIN compañía (company_id vacío) es válido en cualquier compañía:
        # solo se reasigna/limpia si tiene una compañía distinta o si está vacío. Así
        # no se pisa un equipo seteado a mano (mismo patrón que warehouse_id arriba).
        if (team_id and team_id.company_id and team_id.company_id.id != company.id) or not team_id:
            # Un seller_team SIN compañía (company_id vacío) también es válido y debe
            # ASIGNARSE: solo se descarta si tiene una compañía distinta a la de la orden.
            # (Antes se exigía company_id == company → un seller_team sin compañía no
            #  pasaba y caía al else, dejando el equipo en None: por eso "no se asignaba".)
            seller_team_ok = seller_team and (not seller_team.company_id or seller_team.company_id.id == company.id)
            if seller_team_ok:
                if not team_id or team_id.id != seller_team.id:
                    so.sudo().write( { 'team_id': seller_team.id } )
            else:
                #unassign: equipo de otra compañía y sin seller_team válido para reemplazarlo
                so.sudo().write( { 'team_id': None } )
        #_logger.info("check user id")
        # Mismo criterio que el team: respetar un vendedor seteado a mano que sea
        # válido para la compañía (está en sus company_ids); solo corregir cuando el
        # vendedor está vacío o no puede operar en la compañía.
        user_company_ok = bool(user_id and company.id in user_id.company_ids.ids)
        if (user_id and not user_company_ok) or not user_id:
            if seller_user:
                so.sudo().write( { 'user_id': seller_user.id } )
            else:
                so.sudo().write( { 'user_id': None } )

    def meli_oerp_update( self ):
        res = {}
        for order in self:
            if order.meli_orders:
                res = order.meli_orders[0].orders_update_order()
            # Auto-repair: if SO is confirmed but has no picking, fix orphan moves
            if order.state in ('sale', 'done') and not order.picking_ids:
                orphan = self.env['stock.move'].search([
                    ('picking_id', '=', False),
                    ('state', 'in', ['confirmed', 'waiting', 'partially_available', 'assigned']),
                    ('sale_line_id.order_id', '=', order.id),
                ], limit=1)
                if orphan:
                    order.meli_repair_missing_pickings()
        return res

    def meli_oerp_print( self ):
        res = {}
        for order in self:
            if order.meli_shipment:
                res = order.meli_shipment.shipment_print( include_ready_to_print=True )
        return res



    def _ml_get_purchase_price_from_amount(
        self,
        product,
        amount,
        amount_type="tax_included",  # 'tax_included' or 'tax_excluded'
        quantity=1.0,
    ):
        """Return a *tax-excluded* unit price (base) for purchase_price.

        - amount_type = 'tax_included': `amount` is gross (with all taxes)
        - amount_type = 'tax_excluded': `amount` is already net/base
        """

        self.ensure_one()
        amount = float(amount or 0.0)

        if not product:
            return amount

        # 1) Taxes for this product & company
        taxes = product.taxes_id.filtered(lambda t: t.company_id == self.company_id)

        # 2) Fiscal position mapping
        if self.fiscal_position_id:
            #taxes = self.fiscal_position_id.map_tax(taxes, product, self.partner_id)
            taxes = map_tax_compat(
                self.fiscal_position_id, taxes, product, self.partner_id
            )

        if not taxes:
            #_logger.info(
            #    "_ml_get_purchase_price_from_amount > no taxes, returning amount as base: %s",
            #    amount,
            #)
            return self.currency_id.round(amount)

        #_logger.info(
        #    "_ml_get_purchase_price_from_amount > product:%s amount:%s amount_type:%s taxes:%s",
        #    product, amount, amount_type, taxes.ids,
        #)

        # CASE A: amount is already tax-excluded
        if amount_type == "tax_excluded":
            # Just let Odoo normalize price_include taxes if any,
            # but base is basically the amount.
            res = taxes.compute_all(
                amount,
                currency=self.currency_id,
                quantity=quantity,
                product=product,
                partner=self.partner_id,
                handle_price_include=True,
            )
            base = res["total_excluded"] / (quantity or 1.0)
            #_logger.info(
            #    "_ml_get_purchase_price_from_amount > tax_excluded res:%s base:%s",
            #    res, base,
            #)
            return self.currency_id.round(base)

        # CASE B: amount is tax-included and taxes are price_excluded (your case)
        # We compute a ratio using a dummy base=1.0
        # so we can reverse GROSS -> NET.
        # This assumes all relevant taxes are price_include=False (as in your log).
        dummy = taxes.compute_all(
            1.0,
            currency=self.currency_id,
            quantity=1.0,
            product=product,
            partner=self.partner_id,
            handle_price_include=True,
        )
        total_excluded = dummy["total_excluded"]
        total_included = dummy["total_included"]

        #_logger.info(
        #    "_ml_get_purchase_price_from_amount > dummy res:%s total_excluded:%s total_included:%s",
        #    dummy, total_excluded, total_included,
        #)

        if not total_excluded or not total_included or total_included == total_excluded:
            # Fallback: no effect of taxes or odd config; assume amount ~ base
            base = amount
        else:
            # e.g. with 21% IVA:
            # total_excluded = 1.0
            # total_included = 1.21
            # factor = 1.21; base = gross / 1.21
            factor = total_included / total_excluded
            base = amount / factor

        #_logger.info(
        #    "_ml_get_purchase_price_from_amount > final base (unit):%s from gross:%s",
        #    base, amount,
        #)

        # Divide by quantity if needed (in your case quantity=1.0 for fee)
        base_unit = base / (quantity or 1.0)
        return self.currency_id.round(base_unit)

    _unique_meli_order_id = versions.UniqueIndex('meli_order_id', message='Meli Order id already exists!')

    meli_cancel_banner = fields.Html(
        compute='_compute_meli_cancel_banner',
        string='Banner cancelación ML',
        sanitize=False,
    )

    @api.depends('meli_status_detail', 'state')
    def _compute_meli_cancel_banner(self):
        for order in self:
            detail = (order.meli_status_detail or '').strip().lstrip('|').strip()
            if not detail or order.state != 'cancel':
                order.meli_cancel_banner = False
                continue

            # Parse: "code: description (solicitado por: X, fecha: Y)"
            code = desc = by_raw = date_raw = ''
            m = re.match(
                r'^(\w+):\s*(.+?)(?:\s*\(solicitado\s+por:\s*([^,]+),\s*fecha:\s*([^)]+)\))?$',
                detail.strip(),
            )
            if m:
                code     = m.group(1) or ''
                desc     = (m.group(2) or '').strip()
                by_raw   = (m.group(3) or '').strip()
                date_raw = (m.group(4) or '').strip()
            else:
                desc = detail

            code_es = _MELI_CANCEL_CODES_ES.get(
                code, code.replace('_', ' ').title() if code else 'Motivo desconocido'
            )
            by_es = _MELI_REQUESTED_BY_ES.get(by_raw.lower(), by_raw) if by_raw else ''

            # Format ISO date → dd/mm/YYYY HH:MM
            date_display = date_raw
            if date_raw:
                try:
                    from datetime import datetime as _dt
                    date_display = _dt.fromisoformat(date_raw[:19]).strftime('%d/%m/%Y %H:%M')
                except Exception:
                    pass

            code_line = Markup(
                '<div style="margin-bottom:4px;">'
                '<span style="font-size:13px;color:#495057;">'
                '<b>Código:</b> {ce} '
                '<span style="color:#888;font-size:11px;">({c})</span>'
                '</span></div>'
            ).format(ce=html_escape(code_es), c=html_escape(code)) if code else Markup('')

            desc_line = Markup(
                '<div style="margin-bottom:4px;">'
                '<span style="font-size:13px;color:#495057;">'
                '<b>Descripción original:</b> {d}'
                '</span></div>'
            ).format(d=html_escape(desc)) if desc else Markup('')

            meta_parts = []
            if by_es:
                meta_parts.append(Markup('<b>Solicitado por:</b> {v}').format(v=html_escape(by_es)))
            if date_display:
                meta_parts.append(Markup('<b>Fecha:</b> {v}').format(v=html_escape(date_display)))
            meta_line = Markup(
                '<div style="font-size:12px;color:#6c757d;margin-top:2px;">{c}</div>'
            ).format(c=Markup(' &nbsp;·&nbsp; ').join(meta_parts)) if meta_parts else Markup('')

            order.meli_cancel_banner = Markup("""
<div style="position:relative;overflow:hidden;background:#fff8e1;
            border-left:5px solid #e53935;border-radius:4px;
            padding:14px 20px 14px 16px;margin-bottom:12px;">
  <div style="position:absolute;top:18px;right:-24px;background:#e53935;
              color:#fff;font-size:10px;font-weight:700;padding:5px 44px;
              transform:rotate(45deg);letter-spacing:1.5px;
              box-shadow:0 1px 4px rgba(0,0,0,.25);white-space:nowrap;">
    CANCELADO ML
  </div>
  <div style="display:flex;align-items:flex-start;gap:12px;padding-right:70px;">
    <span style="font-size:28px;line-height:1;flex-shrink:0;">🚫</span>
    <div>
      <div style="font-size:15px;font-weight:700;color:#b71c1c;margin-bottom:8px;">
        Orden cancelada por MercadoLibre
      </div>
      {cl}{dl}{ml}
    </div>
  </div>
</div>
""").format(cl=code_line, dl=desc_line, ml=meta_line)

    # -----------------------------------------------------------------------
    # Banner: cancelado en ML pero NO cancelado en Odoo (acción requerida)
    # -----------------------------------------------------------------------
    meli_cancel_pending_banner = fields.Html(
        compute='_compute_meli_cancel_pending_banner',
        string='Alerta: cancelación ML pendiente en Odoo',
        sanitize=False,
    )

    @api.depends('meli_status', 'state', 'meli_status_detail',
                 'invoice_ids.state', 'picking_ids.state')
    def _compute_meli_cancel_pending_banner(self):
        for order in self:
            # Solo mostrar cuando ML canceló pero Odoo NO está cancelado
            if order.meli_status != 'cancelled' or order.state == 'cancel':
                order.meli_cancel_pending_banner = False
                continue

            # Parsear motivo de cancelación
            detail = (order.meli_status_detail or '').strip().lstrip('|').strip()
            code = desc = by_raw = date_raw = ''
            if detail:
                m = re.match(
                    r'^(\w+):\s*(.+?)(?:\s*\(solicitado\s+por:\s*([^,]+),\s*fecha:\s*([^)]+)\))?$',
                    detail.strip(),
                )
                if m:
                    code     = m.group(1) or ''
                    desc     = (m.group(2) or '').strip()
                    by_raw   = (m.group(3) or '').strip()
                    date_raw = (m.group(4) or '').strip()
                else:
                    desc = detail

            code_es = _MELI_CANCEL_CODES_ES.get(
                code, code.replace('_', ' ').title() if code else 'Motivo desconocido'
            )
            by_es = _MELI_REQUESTED_BY_ES.get(by_raw.lower(), by_raw) if by_raw else ''
            date_display = date_raw
            if date_raw:
                try:
                    from datetime import datetime as _dt
                    date_display = _dt.fromisoformat(date_raw[:19]).strftime('%d/%m/%Y %H:%M')
                except Exception:
                    pass

            reason_html = Markup('')
            if code_es or desc:
                reason_html = Markup(
                    '<div style="margin:6px 0 10px 0;padding:8px 12px;'
                    'background:rgba(0,0,0,.05);border-radius:4px;font-size:13px;">'
                    '<b>Motivo:</b> {ce}'
                    '{sep}{d}'
                    '{meta}'
                    '</div>'
                ).format(
                    ce=html_escape(code_es),
                    sep=Markup(' &mdash; ') if desc and desc != code_es else Markup(''),
                    d=html_escape(desc) if desc and desc != code_es else Markup(''),
                    meta=Markup(
                        '<span style="color:#888;font-size:12px;display:block;margin-top:3px;">'
                        '{by}{sep2}{fecha}'
                        '</span>'
                    ).format(
                        by=Markup('<b>Por:</b> {v}').format(v=html_escape(by_es)) if by_es else Markup(''),
                        sep2=Markup(' &nbsp;·&nbsp; ') if by_es and date_display else Markup(''),
                        fecha=Markup('<b>Fecha:</b> {v}').format(v=html_escape(date_display)) if date_display else Markup(''),
                    ) if (by_es or date_display) else Markup(''),
                )

            # Detectar documentos pendientes
            done_pickings = order.picking_ids.filtered(
                lambda p: p.state == 'done' and p.picking_type_code == 'outgoing'
            )
            has_return = done_pickings.filtered(
                lambda p: any(p.move_ids.mapped('origin_returned_move_id'))
            )
            needs_return = done_pickings - has_return
            posted_invoices = order.invoice_ids.filtered(
                lambda i: i.move_type == 'out_invoice' and i.state == 'posted'
            )

            steps_html = Markup('')
            step_n = 1
            if needs_return:
                names = ', '.join(needs_return.mapped('name'))
                steps_html += Markup(
                    '<li style="margin-bottom:6px;">'
                    '<b>Paso {n}:</b> Crear devolución (albarán de entrada) para: <b>{names}</b>'
                    '<br/><span style="font-size:12px;color:#555;">Ir al albarán → Devolver</span>'
                    '</li>'
                ).format(n=step_n, names=html_escape(names))
                step_n += 1
            if has_return:
                names = ', '.join(has_return.mapped('name'))
                steps_html += Markup(
                    '<li style="margin-bottom:6px;color:#388e3c;">'
                    '✓ Devolución ya creada para: <b>{names}</b>'
                    '</li>'
                ).format(names=html_escape(names))
            if posted_invoices:
                names = ', '.join(posted_invoices.mapped('name'))
                steps_html += Markup(
                    '<li style="margin-bottom:6px;">'
                    '<b>Paso {n}:</b> Emitir Nota de Crédito para: <b>{names}</b>'
                    '<br/><span style="font-size:12px;color:#555;">'
                    'Ir a la factura → Agregar Nota de Crédito</span>'
                    '</li>'
                ).format(n=step_n, names=html_escape(names))
                step_n += 1
            steps_html += Markup(
                '<li style="margin-bottom:4px;">'
                '<b>Paso {n}:</b> Cancelar esta orden de venta manualmente'
                '</li>'
            ).format(n=step_n)

            order.meli_cancel_pending_banner = Markup("""
<div style="background:#fff3e0;border-left:6px solid #f57c00;border-radius:4px;
            padding:16px 20px;margin-bottom:14px;position:relative;">
  <div style="position:absolute;top:14px;right:-20px;background:#f57c00;
              color:#fff;font-size:10px;font-weight:700;padding:5px 40px;
              transform:rotate(45deg);letter-spacing:1.5px;
              box-shadow:0 1px 4px rgba(0,0,0,.3);white-space:nowrap;">
    ACCIÓN REQUERIDA
  </div>
  <div style="padding-right:72px;">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
      <span style="font-size:26px;line-height:1;">⚠️</span>
      <div>
        <div style="font-size:16px;font-weight:800;color:#e65100;line-height:1.2;">
          Cancelada en MercadoLibre — pendiente en Odoo
        </div>
        <div style="font-size:12px;color:#6d4c41;margin-top:2px;">
          ML canceló esta orden pero no se pudo cancelar automáticamente en Odoo
          por existir entregas realizadas y/o facturas emitidas.
        </div>
      </div>
    </div>
    {reason}
    <div style="background:rgba(0,0,0,.04);border-radius:4px;padding:10px 14px;margin-top:8px;">
      <div style="font-size:13px;font-weight:700;color:#4e342e;margin-bottom:6px;">
        Pasos a seguir:
      </div>
      <ol style="margin:0;padding-left:20px;font-size:13px;color:#4e342e;">
        {steps}
      </ol>
    </div>
  </div>
</div>
""").format(reason=reason_html, steps=steps_html)

class mercadolibre_orders(models.Model):
    _name = "mercadolibre.orders"
    _description = "Pedidos en MercadoLibre"

    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']

    def fix_locals(self,  Receiver={}, Buyer={} ):
        updated = {}

        country_id = self.country( Receiver=Receiver, Buyer=Buyer )
        state_id = self.state( country_id, Receiver=Receiver, Buyer=Buyer )
        city_name = self.city( Receiver=Receiver, Buyer=Buyer )

        # Brasil: mapear ciudad a res.city (usado por l10n_br y Odoo base)
        company = self.env.user.company_id
        if company.country_id.code == "BR" and city_name and "res.city" in self.env:
            res_city = self.env["res.city"].search([
                ('name', 'ilike', city_name),
                ('country_id', '=', country_id),
            ], limit=1)
            if not res_city and state_id:
                res_city = self.env["res.city"].search([
                    ('name', 'ilike', city_name),
                    ('state_id', '=', state_id),
                ], limit=1)
            if res_city:
                updated['city_id'] = res_city.id
                updated['city'] = res_city.name
                _logger.info("BR_CITY: city_id=%s (%s)", res_city.id, res_city.name)
            else:
                updated['city'] = city_name
                _logger.warning("BR_CITY: res.city nao encontrada para '%s' (country=%s state=%s)", city_name, country_id, state_id)

        if "l10n_co_cities.city" in self.env:
            city = self.env["l10n_co_cities.city"].search([('city_name','ilike',city_name)])

            if not city and state_id:
                _logger.warning("City not found for: "+str(city_name) + " state_id: "+str(state_id))
                #_logger.info(Search FIRST city for state: " + str(state_id))
                city = self.env["l10n_co_cities.city"].search([('state_id','=',state_id)])

            if city:
                #_logger.info(city)
                city = city[0]

                #_logger.info(Founded cities for state: " + str(state_id)+ " city_name: "+str(city.city_name))

                updated["cities"] = city.id

                postal = self.env["l10n_co_postal.postal_code"].search([('city_id','=',city.id)])
                if postal:
                    postal = postal[0]
                    updated["postal_id"] = postal.id
                else:
                    _logger.error("Postal code not found for: " + str(city.city_name)+ "["+str(city.id)+"]")
            else:
                _logger.error("City not found for: " + str(updated["city"]))

        return updated

    def street(self, Receiver={}, Buyer={} ):
        full_street = 'no street'
        if (Receiver and 'address_line' in Receiver):
            full_street = Receiver['address_line']
        if ( Buyer and 'billing_info' in Buyer and 'STREET_NAME' in Buyer['billing_info'] ):
            binfo = Buyer['billing_info']
            full_street = str( ('STREET_NAME' in binfo and binfo['STREET_NAME']) or '' )
            full_street+= str(' ') + str(('STREET_NUMBER' in binfo and binfo['STREET_NUMBER']) or '')
        return full_street

    def city(self,  Receiver={}, Buyer={} ):
        full_city = ''
        if (Receiver and 'city' in Receiver):
            full_city = Receiver['city']['name']
        if ( Buyer and 'billing_info' in Buyer and 'CITY_NAME' in Buyer['billing_info'] ):
            binfo = Buyer['billing_info']
            full_city = str(('CITY_NAME' in binfo and binfo['CITY_NAME']) or '')
        return full_city

    def state(self, country_id,  Receiver={}, Buyer={} ):
        full_state = ''
        state_id = False
        #_logger.info("Receiver:"+str(Receiver)+" country_id:"+str(country_id))
        if (Receiver and 'state' in Receiver):
            if ('id' in Receiver['state']):
                state = self.env['res.country.state'].search([('code','ilike',Receiver['state']['id']),('country_id','=',country_id)])
                if (len(state)):
                    state_id = state[0].id
                    return state_id
            id_ml = 'id' in Receiver['state'] and str(Receiver['state']['id']).split("-")
            #_logger.info(Receiver)
            #_logger.info(id_ml)
            if (id_ml and len(id_ml)==2):
                id = id_ml[1]
                state = self.env['res.country.state'].search([('code','ilike',id),('country_id','=',country_id)])
                if (len(state)):
                    state_id = state[0].id
                    return state_id
            if ('name' in Receiver['state']):
                full_state = Receiver['state']['name']
                state = self.env['res.country.state'].search(['&',('name','ilike',full_state),('country_id','=',country_id)])
                if (len(state)):
                    state_id = state[0].id

        if ( Buyer and 'billing_info' in Buyer and 'STATE_NAME' in Buyer['billing_info'] ):
            binfo = Buyer['billing_info']
            full_state = str(('STATE_NAME' in binfo and binfo['STATE_NAME']) or '')
            if (full_state=="Capital Federal"):
                full_state = "Ciudad Autónoma de Buenos Aires"
            state = self.env['res.country.state'].search(['&',('name','ilike',full_state),('country_id','=',country_id)])
            if (len(state)):
                state_id = state[0].id

        return state_id

    def country(self,  Receiver={}, Buyer={} ):
        full_country = ''
        country_id = False
        if (Receiver and 'country' in Receiver):
            if ('id' in Receiver['country']):
                country = self.env['res.country'].search([('code','like',Receiver['country']['id'])])
                if (len(country)):
                    country_id = country[0].id
                    return country_id
            if ('name' in Receiver['country']):
                full_country = Receiver['country']['name']
                country = self.env['res.country'].search([('name','like',full_country)])
                if (len(country)):
                    country_id = country.id
        if not country_id:
            company = self.env.user.company_id
            country_id = company.country_id and company.country_id.id

        return country_id

    def buyer_additional_info(self, billing_info={} ):
        ret = {}

        ret['billing_info_doc_type'] = ('DOC_TYPE' in billing_info and billing_info['DOC_TYPE']) or ''
        ret['billing_info_doc_number'] = ('DOC_NUMBER' in billing_info and billing_info['DOC_NUMBER']) or ''

        ret["first_name"] = ("FIRST_NAME" in billing_info and billing_info["FIRST_NAME"]) or ""
        ret["last_name"] = ("LAST_NAME" in billing_info and billing_info["LAST_NAME"]) or ""
        ret["billing_info_business_name"] = ("BUSINESS_NAME" in billing_info and billing_info["BUSINESS_NAME"]) or ""
        ret["billing_info_street_name"] = ("STREET_NAME" in billing_info and billing_info["STREET_NAME"]) or ""
        ret["billing_info_street_number"] = ("STREET_NUMBER" in billing_info and billing_info["STREET_NUMBER"]) or ""
        ret["billing_info_city_name"] = ("CITY_NAME" in billing_info and billing_info["CITY_NAME"]) or ""
        ret["billing_info_state_name"] = ("STATE_NAME" in billing_info and billing_info["STATE_NAME"]) or ""
        ret["billing_info_zip_code"] = ("ZIP_CODE" in billing_info and billing_info["ZIP_CODE"]) or ""

        ret["billing_info_tax_type"] = ("TAXPAYER_TYPE_ID" in billing_info and billing_info["TAXPAYER_TYPE_ID"]) or ""

        ret['billing_info_doc_type'] = ret['billing_info_doc_type'] or ('doc_type' in billing_info and billing_info['doc_type']) or ''
        ret['billing_info_doc_number'] = ret['billing_info_doc_number'] or ('doc_number' in billing_info and billing_info['doc_number']) or ''

        ret["billing_info_economic_activity"] = ("ECONOMIC_ACTIVITY" in billing_info and billing_info["ECONOMIC_ACTIVITY"]) or ""
        ret["billing_info_neighborhood"] = ("NEIGHBORHOOD" in billing_info and billing_info["NEIGHBORHOOD"]) or ""
        ret["billing_info_vat_discriminating_billing"] = ("VAT_DISCRIMINATED_BILLING" in billing_info and billing_info["VAT_DISCRIMINATED_BILLING"]) or ""
        ret["billing_info_invoice_type"] = ("INVOICE_TYPE" in billing_info and billing_info["INVOICE_TYPE"]) or ""

        return ret

    def buyer_full_name( self, Buyer={}):

        full_name = ("name" in Buyer and Buyer['name']) or ""

        first_name = str( ('first_name' in Buyer and Buyer['first_name'] ) or '' )
        last_name = str( ('last_name' in Buyer and Buyer['last_name']) or '' )

        if first_name and last_name:
            first_name = first_name.capitalize()
            last_name = ' '+last_name.capitalize()

        full_name = first_name + last_name

        business_name = ('business_name' in Buyer and Buyer['business_name'])
        full_name = full_name or business_name or ''

        # Fallback to buyer ID if no name available
        if not full_name:
            buyer_id = Buyer.get('id')
            if buyer_id:
                full_name = "Cliente MeLi " + str(buyer_id)

        # Ultimate fallback - never return empty name (violates res_partner constraint)
        return full_name or "Cliente MercadoLibre"

    def zip_code( self, Receiver={}, Buyer={}):
        if ( Receiver and 'billing_info' in Receiver and 'ZIP_CODE' in Receiver['billing_info'] ):
            return Receiver['billing_info']["ZIP_CODE"]

        if ( Buyer and 'billing_info' in Buyer and 'ZIP_CODE' in Buyer['billing_info'] ):
            return Buyer['billing_info']["ZIP_CODE"]
        return ""

    def _normalize_billing_info_v2(self, bi, site_id=None):
        """Flatten the new ML billing-info v2 response into the legacy
        UPPERCASE-key dict that the rest of this module consumes.

        Input (v2 shape, from /orders/billing-info/{SITE_ID}/{BILLING_INFO_ID}):
          {
            "name": "...", "last_name": "...",
            "identification": {"type": "...", "number": "..."},
            "taxes": {"taxpayer_type": {"description": "..."}, "economic_activity": "..."},
            "address": {"street_name": "...", "state": {"name": "..."}, "zip_code": "..."},
            "attributes": {"vat_discriminated_billing": "true", "cust_type": "CO"|"BU", ...}
          }

        Output: a new dict preserving all v2 fields PLUS the legacy uppercase
        keys (FIRST_NAME, LAST_NAME, DOC_TYPE, DOC_NUMBER, ...) the downstream
        code in this module expects. Also fills INVOICE_TYPE per site_id
        rules now that the upstream field is being phased out:
        MLA: CUIT -> Factura A, DNI/CUIL -> Factura B.
        """
        if not isinstance(bi, dict):
            return bi

        out = dict(bi)  # preserve v2 fields as fallbacks

        attributes = bi.get('attributes') or {}
        cust_type = (attributes.get('cust_type') or attributes.get('customer_type') or '').upper()
        name = bi.get('name') or ''
        last_name = bi.get('last_name') or ''
        if cust_type == 'BU':
            out['BUSINESS_NAME'] = name
            out['FIRST_NAME'] = ''
            out['LAST_NAME'] = ''
        else:
            out['FIRST_NAME'] = name
            out['LAST_NAME'] = last_name
            out['BUSINESS_NAME'] = ''
        out['first_name'] = out['FIRST_NAME']
        out['last_name'] = out['LAST_NAME']

        identification = bi.get('identification') or {}
        doc_type = identification.get('type') or ''
        doc_number = identification.get('number') or ''
        out['DOC_TYPE'] = doc_type
        out['DOC_NUMBER'] = doc_number
        out['doc_type'] = doc_type
        out['doc_number'] = doc_number

        taxes = bi.get('taxes') or {}
        taxpayer_type = taxes.get('taxpayer_type') or {}
        out['TAXPAYER_TYPE_ID'] = taxpayer_type.get('description') or ''
        out['ECONOMIC_ACTIVITY'] = taxes.get('economic_activity') or ''

        address = bi.get('address') or {}
        state = address.get('state') or {}
        out['STREET_NAME'] = address.get('street_name') or ''
        out['STREET_NUMBER'] = address.get('street_number') or ''
        out['CITY_NAME'] = address.get('city_name') or ''
        out['STATE_NAME'] = state.get('name') or ''
        out['ZIP_CODE'] = address.get('zip_code') or ''
        out['NEIGHBORHOOD'] = address.get('neighborhood') or ''

        out['VAT_DISCRIMINATED_BILLING'] = str(attributes.get('vat_discriminated_billing') or '')

        # INVOICE_TYPE: the upstream attribute is being removed; keep it when
        # present (MLA still returns it as of 03/2026) and otherwise derive
        # from doc_type for MLA.  IMPORTANT: CUIT alone does NOT imply Factura A —
        # Monotributo taxpayers also hold CUIT but must receive Factura B.
        # So we also check TAXPAYER_TYPE_ID before mapping CUIT → Factura A.
        invoice_type = attributes.get('invoice_type') or bi.get('invoice_type') or ''
        if not invoice_type and site_id and str(site_id).upper() == 'MLA':
            _doc = (doc_type or '').upper()
            _taxpayer_desc = (out.get('TAXPAYER_TYPE_ID') or '').strip().upper()
            # Only map CUIT to Factura A when the taxpayer is RI; Monotributo/Exento/CF with CUIT → Factura B
            _ri_keywords = ('RESPONSABLE INSCRIPTO',)
            _non_ri_keywords = ('MONOTRIBUTO', 'EXENTO', 'CONSUMIDOR FINAL', 'NO RESPONSABLE', 'NO CATEGORIZADO')
            _is_ri = any(kw in _taxpayer_desc for kw in _ri_keywords)
            _is_non_ri = any(kw in _taxpayer_desc for kw in _non_ri_keywords)
            if _doc == 'CUIT' and _is_ri and not _is_non_ri:
                invoice_type = 'Factura A'
            elif _doc == 'CUIT' and not _taxpayer_desc:
                # Unknown taxpayer type with CUIT — default to Factura A (RI is most common with CUIT)
                invoice_type = 'Factura A'
            elif _doc in ('DNI', 'CUIL') or (_doc == 'CUIT' and _is_non_ri):
                invoice_type = 'Factura B'
        out['INVOICE_TYPE'] = invoice_type

        return out

    def get_billing_info( self, order_id=None, meli=None, data=None, site_id=None ):
        """Fetch the billing info for a ML order.

        Since April 2026 the legacy endpoint /orders/{id}/billing_info was
        replaced by /orders/billing-info/{SITE_ID}/{BILLING_INFO_ID} with an
        'x-version: 2' header, and the billing_info_id now lives inside the
        order itself at order.buyer.billing_info.id. We call the new endpoint
        first and normalize the response to the legacy UPPERCASE-key shape so
        the 100+ downstream consumers keep working unchanged.

        site_id resolution order:
          1. explicit `site_id` kwarg (caller knows best, e.g. multi-account
             context where the mercadolibre.account has its own site_id)
          2. data['site_id']  (root of the ML order payload — always present
             on modern orders)
          3. company._get_ML_sites(meli=meli)  (derived from the company's
             currency — used only as last-resort safety net)

        The legacy endpoint is still attempted as a last-resort fallback in
        case an order does not have billing_info.id yet (transitional), but
        it will disappear as MercadoLibre completes the migration.
        """
        order_id = order_id or (data and 'id' in data and data['id']) or (self and self.order_id)
        Buyer = (data and 'buyer' in data and data['buyer']) or {}
        _billing_info = ('billing_info' in Buyer and Buyer['billing_info']) or {}

        if not (meli and order_id):
            return _billing_info

        # Resolve site_id with explicit fallbacks so we NEVER call the new
        # endpoint with a wrong site (e.g. MLA account hitting /billing-info/MLM/...).
        site_id_source = None
        if site_id:
            site_id_source = "kwarg"
        elif data and data.get('site_id'):
            site_id = data.get('site_id')
            site_id_source = "order_payload"
        else:
            # Safety net: derive from the current company's currency.
            try:
                company = self.env.user.company_id
                site_id = company and company._get_ML_sites(meli=meli)
                site_id_source = "company_currency_fallback"
            except Exception as e:
                _logger.warning("get_billing_info: could not derive site_id from company: %s", str(e))
                site_id = None

        billing_info_id = None
        if isinstance(_billing_info, dict):
            billing_info_id = _billing_info.get('id')

        _logger.info(
            "get_billing_info: order_id=%s site_id=%s (source=%s) billing_info_id=%s",
            order_id, site_id, site_id_source, billing_info_id,
        )

        api_billing_info = None

        # 1) NEW endpoint: /orders/billing-info/{SITE_ID}/{BILLING_INFO_ID}
        if site_id and billing_info_id:
            try:
                url = "/orders/billing-info/%s/%s" % (str(site_id), str(billing_info_id))
                response = meli.get(
                    url,
                    {'access_token': meli.access_token},
                    extra_headers={'x-version': '2'},
                )
                if response is not None and getattr(response, 'status_code', 0) == 200:
                    biljson = response.json() or {}
                    # v2 wraps billing_info under buyer
                    api_billing_info = (
                        (biljson.get('buyer') or {}).get('billing_info')
                        or biljson.get('billing_info')
                    )
                    # Prefer site_id echoed back by the API for the normalizer
                    response_site_id = biljson.get('site_id') or site_id
                    if api_billing_info:
                        api_billing_info = self._normalize_billing_info_v2(api_billing_info, site_id=response_site_id)
                else:
                    _logger.warning(
                        "get_billing_info: new endpoint %s returned status=%s for order_id=%s, "
                        "falling back to legacy endpoint",
                        url, response and getattr(response, 'status_code', None), order_id,
                    )
            except Exception as e:
                _logger.error(
                    "get_billing_info: new endpoint failed for order_id=%s site=%s bid=%s: %s",
                    order_id, site_id, billing_info_id, str(e),
                )

        # 2) LEGACY endpoint fallback: /orders/{order_id}/billing_info
        #    Kept as a safety net for transitional orders without
        #    billing_info.id in their payload. Will 404 once ML removes it.
        if not api_billing_info:
            try:
                response = meli.get("/orders/"+str(order_id)+"/billing_info", {'access_token':meli.access_token})
                if response:
                    biljson = response.json()
                    #_logger.info("get_billing_info: "+str(biljson))
                    api_billing_info = (biljson and 'billing_info' in biljson and biljson['billing_info']) or None
                    if api_billing_info:
                        if "additional_info" in api_billing_info:
                            adds = api_billing_info["additional_info"]
                            for add in adds:
                                api_billing_info[add["type"]] = add["value"]
                                # Also add lowercase version for compatibility
                                api_billing_info[add["type"].lower()] = add["value"]
                    else:
                        _logger.debug(
                            "get_billing_info: legacy response sin billing_info, "
                            "usando fallback de la orden. order_id: %s biljson keys: %s",
                            order_id, str(biljson and biljson.keys()),
                        )
            except Exception as e:
                _logger.error("get_billing_info: legacy endpoint failed for order_id=%s: %s", order_id, str(e))

        if api_billing_info:
            _billing_info = api_billing_info

        return _billing_info

    def billing_info( self, billing_json, context=None ):
        billinginfo = ''

        if billing_json and 'doc_type' in billing_json:
            if billing_json['doc_type']:
                billinginfo+= billing_json['doc_type']

        if billing_json and 'doc_number' in billing_json:
            if billing_json['doc_number']:
                billinginfo+= billing_json['doc_number']

        return billinginfo

    def full_phone( self, buyer_json, context=None ):
        full_phone = ''
        if "phone" in buyer_json:
            phone_json = buyer_json["phone"]
            if phone_json:
                if 'area_code' in phone_json:
                    if phone_json['area_code']:
                        full_phone+= phone_json['area_code']

                if 'number' in phone_json:
                    if phone_json['number']:
                        full_phone+= phone_json['number']

                if 'extension' in phone_json:
                    if phone_json['extension']:
                        full_phone+= phone_json['extension']

        if "receiver_phone" in buyer_json and buyer_json["receiver_phone"]:
            full_phone+= buyer_json["receiver_phone"]

        return full_phone

    def full_alt_phone( self, buyer_json, context=None ):
        full_phone = ''
        if buyer_json:
            if "alternative_phone" in buyer_json:
                phone_json = buyer_json["alternative_phone"]
                if phone_json:
                    if 'area_code' in phone_json:
                        if phone_json['area_code']:
                            full_phone+= phone_json['area_code']

                    if 'number' in phone_json:
                        if phone_json['number']:
                            full_phone+= phone_json['number']

                    if 'extension' in phone_json:
                        if phone_json['extension']:
                            full_phone+= phone_json['extension']

        return full_phone

    def _fetch_order_discounts(self, meli=None):
        """Fetch /orders/{order_id}/discounts to determine seller-funded discount amount.
        Sets discount_seller_amount = sum of amounts.seller from all discount items.
        If seller=0 for all items, the discount is fully ML-funded and doesn't affect the SO price."""
        if not meli or not self.order_id:
            return
        try:
            response = meli.get("/orders/"+str(self.order_id)+"/discounts", {'access_token': meli.access_token})
            rjson = response.json()
            if not rjson or 'details' not in rjson:
                return
            seller_total = 0.0
            for detail in rjson.get('details', []):
                for item in detail.get('items', []):
                    amounts = item.get('amounts', {})
                    seller_total += float(amounts.get('seller', 0) or 0)
            self.discount_seller_amount = seller_total
            _logger.info("MELI discounts for order %s: seller_amount=%.2f (coupon_amount=%.2f)",
                         self.order_id, seller_total, self.coupon_amount)
        except Exception as e:
            _logger.info("MELI: Could not fetch /orders/%s/discounts: %s", self.order_id, e)
            self._estimate_seller_discount_from_charges()

    def _estimate_seller_discount_from_charges(self):
        """Fallback: estimate seller discount from payment charges (mercadolibre.payment.charge).
        If coupon account_from='collector' -> seller pays; from='ml' -> ML pays."""
        if not self.sale_order:
            return
        seller_total = 0.0
        charge_model = self.env.get('mercadolibre.payment.charge')
        if not charge_model:
            return
        for meli_order in self.sale_order.meli_orders:
            for payment in meli_order.payments:
                if not hasattr(payment, 'charge_ids'):
                    continue
                for charge in payment.charge_ids:
                    if charge.charge_type == 'coupon' and charge.account_from == 'collector':
                        seller_total += float(charge.amount_original or 0)
        self.discount_seller_amount = seller_total

    def _set_product_unit_price( self, product_related_obj, Item, config=None ):
        order = self
        seller_discount = float(order.discount_seller_amount or 0)
        unit_price = float(Item['unit_price']) - float(seller_discount / float(Item['quantity']))
        upd_line = {
            "price_unit": ml_product_price_conversion( self, product_related_obj=product_related_obj, price=unit_price, config=config )
        }
        #else:
        #    if ( float(Item['unit_price']) == product_template.lst_price and not self.env.user.has_group('sale.group_show_price_subtotal')):
        #        upd_line[tax_field] = None
        return upd_line

    def pretty_json( self, ids, data, indent=0, context=None ):
        return json.dumps( data, sort_keys=False, indent=4 )

    def prepare_orderjson( self, meli=None, config=None ):
        ptags = (self.pack_order and "pack_order") or ""
        order_items = []
        for oitem in self.order_items:
            order_items.append({
                "item": {
                    "id": oitem.order_item_id,
                    "variation_id": oitem.order_item_variation_id or oitem.seller_sku,
                    "title": oitem.order_item_title,
                    "category_id": oitem.order_item_category_id,
                    'seller_sku': oitem.seller_sku,
                    'seller_custom_field': oitem.seller_custom_field,
                },
                "unit_price": oitem.unit_price,
                "currency_id": oitem.currency_id,
                'quantity': oitem.quantity,

            })
        orderjson = {
            "id": self.order_id,
            "status": self.status,
            "status_detail": self.status_detail,
            "total_amount": self.total_amount,
            "paid_amount": self.paid_amount,
            "coupon_amount": self.coupon_amount,
            "financing_fee_amount": self.financing_fee_amount,

            "date_created": self.date_created,
            "date_closed": self.date_closed,
            "pack_id": self.pack_id,
            "seller": "Bereket",
            "buyer": {
                "id": "GLOBALCOMPRADOR",
                "name": "Comprador De MercadoLibre",
                "nickname": "CLIENTEML",
                "first_name": "Comprador",
                "last_name": "De MercadoLibre",
            },
            "tags": [ptags],
            "currency_id": self.currency_id,
            "shipping": {
                "id": "SHP-"+str(self.pack_id or self.order_id),
                "cost": self.shipping_cost,
                "logistic_type": "fulfillment"
            },
            "order_items": order_items
        }
        return orderjson

    def prepare_ml_order_vals( self, meli=None, order_json=None, config=None ):

        company = self.env.user.company_id

        if not config:
            config = company

        seller_id = None
        if config.mercadolibre_seller_user:
            seller_id = config.mercadolibre_seller_user.id

        financing_fee_amount = 0

        cancel_detail = order_json.get("cancel_detail") or {}
        cancel_detail_text = ""
        if cancel_detail:
            cancel_detail_text = " | %s: %s (solicitado por: %s, fecha: %s)" % (
                cancel_detail.get("code", ""),
                cancel_detail.get("description", ""),
                cancel_detail.get("requested_by", ""),
                cancel_detail.get("date", ""),
            )

        order_fields = {
            'name': "MO [%s]" % ( str(order_json["id"]) ),
            'company_id': company.id,
            'seller_id': seller_id,
            'order_id': '%s' % (str(order_json["id"])),
            'status': order_json["status"],
            'status_detail': (order_json.get("status_detail") or '') + cancel_detail_text,
            'fee_amount': 0.0,
            'total_amount': order_json["total_amount"],
            'paid_amount': order_json["paid_amount"],
            'coupon_amount': ("coupon" in order_json and order_json["coupon"] and "amount" in order_json["coupon"] and order_json["coupon"]["amount"]) or 0.0,
            'financing_fee_amount': financing_fee_amount,
            'currency_id': order_json["currency_id"],
            'date_created': ml_datetime(order_json["date_created"]),
            'date_closed': ml_datetime(order_json["date_closed"]),
            'pack_order': False,
            'catalog_order': False,
            'seller': ("seller" in order_json and str(order_json["seller"])) or ''
        }
        if "pack_id" in order_json and order_json["pack_id"]:
            order_fields['pack_id'] = order_json["pack_id"]
        if 'tags' in order_json:
            order_fields["tags"] = order_json["tags"]
            if 'pack_order' in order_json["tags"]:
                order_fields["pack_order"] = True
            if 'catalog' in order_json["tags"]:
                order_fields["catalog_order"] = True
                #debemos buscar el codigo relacionado pero al producto real del catalogo: que se encuentra.

        if 'context' in order_json:
            if 'channel' in order_json["context"]:
                order_fields["context"] = order_json["context"]["channel"]

        if meli.access_token=="PASIVA":
            if (self):
                order_fields["fee_amount"] = self.payments and self.payments[0].fee_amount
                if (self.sale_order):
                    self.sale_order.meli_fee_amount = order_fields["fee_amount"]
        return order_fields

    def prepare_sale_order_vals( self, meli=None, order_json=None, config=None, sale_order=None, shipment=None ):
        if not order_json:
            return {}
        financing_fee_amount = ("financing_fee_amount" in order_json and order_json["financing_fee_amount"]) or 0
        cancel_detail = order_json.get("cancel_detail") or {}
        cancel_detail_text = ""
        if cancel_detail:
            cancel_detail_text = " | %s: %s (solicitado por: %s, fecha: %s)" % (
                cancel_detail.get("code", ""),
                cancel_detail.get("description", ""),
                cancel_detail.get("requested_by", ""),
                cancel_detail.get("date", ""),
            )
        meli_order_fields = {
            #TODO: "add parameter for":
            'name': "ML %s" % ( str(order_json["id"]) ),
            #'partner_id': partner_id.id,
            #'pricelist_id': plistid.id,
            'meli_order_id': '%s' % (str(order_json["id"])),
            'meli_status': ("status" in order_json and order_json["status"]) or '',
            'meli_status_detail': (order_json.get("status_detail") or '') + cancel_detail_text,
            'meli_total_amount': ("total_amount" in order_json and order_json["total_amount"]),
            'meli_paid_amount': ("paid_amount" in order_json and order_json["paid_amount"]),
            'meli_coupon_amount': ("coupon" in order_json and order_json["coupon"] and "amount" in order_json["coupon"] and order_json["coupon"]["amount"]) or 0.0,
            'meli_financing_fee_amount': financing_fee_amount,
            'meli_currency_id': ("currency_id" in order_json and order_json["currency_id"]),
            'meli_date_created': ml_datetime(order_json["date_created"]),
            'meli_date_closed': ml_datetime(order_json["date_closed"]),
        }
        return meli_order_fields

    def search_sale_order( self, order_id, meli=None, rjson=None ):
        sorder = None

        return sorder

    def search_ml_order( self, order_id, meli=None, rjson=None ):
        mlorder = None

        return mlorder

    def search_meli_product( self, meli=None, meli_item=None, config=None ):
        company = (config and 'company_id' in config._fields and config.company_id) or self.env.user.company_id
        company_domain = ['|',('company_id','=',False),('company_id','=',company.id)]
        product_related = False
        product_obj = self.env['product.product']
        if not meli_item:
            return None
        meli_id = meli_item['id']
        meli_id_variation = ("variation_id" in meli_item and meli_item['variation_id'])
        meli_seller_sku = "seller_sku" in meli_item and meli_item["seller_sku"]
        if meli_seller_sku:
            product_related = product_obj.search([ ('default_code','=ilike',meli_seller_sku)]
                                                   +company_domain)
            #search by barcode
            if ((not product_related) or len(product_related)>1):
                product_related = product_obj.search([ ('barcode','=ilike',meli_seller_sku)]
                                                        +company_domain)

        if ((not product_related) or len(product_related)>1):
            if (meli_id_variation):
                product_related = product_obj.search([ ('meli_id','=',meli_id), ('meli_id_variation','=',meli_id_variation)]
                                                        +company_domain)
            else:
                product_related = product_obj.search([('meli_id','=', meli_id)]
                                                      +company_domain)

        return product_related

    def update_partner_billing_info( self, partner_id, meli_buyer_fields, Receiver):

        partner_update = {}

        if not partner_id or not meli_buyer_fields:
            #_logger.info(update_partner_billing_info: no partner id or no meli_buyer_fields")
            return partner_update

        if "activity_description" in meli_buyer_fields:
            partner_update.update(meli_buyer_fields)

        if "city_id" in meli_buyer_fields or "city" in meli_buyer_fields:
            partner_update.update(meli_buyer_fields)            

        if "documento" in meli_buyer_fields:
            partner_update.update(meli_buyer_fields)

        #TODO: re DO with, self.update_billing_data( partner_id, meli_buyer_fields )
        if "document_type_id" in meli_buyer_fields and str(meli_buyer_fields['document_type_id'])!=str(partner_id.document_type_id and partner_id.document_type_id.id):
            partner_update.update(meli_buyer_fields)

        if "document_number" in meli_buyer_fields and str(meli_buyer_fields['document_number'])!=str(partner_id.document_number):
            partner_update.update(meli_buyer_fields)

        if "company_type" in meli_buyer_fields and str(meli_buyer_fields['company_type'])!=str(partner_id.company_type):
            partner_update.update(meli_buyer_fields)

        if ("vat" in meli_buyer_fields and meli_buyer_fields["vat"]!=str(partner_id.vat) ):
            partner_update.update(meli_buyer_fields)

        if ("street" in meli_buyer_fields and meli_buyer_fields["street"]!=str(partner_id.street) ):
            partner_update.update(meli_buyer_fields)

        if "l10n_co_document_type" in meli_buyer_fields and str(meli_buyer_fields['l10n_co_document_type'])!=str(partner_id.l10n_co_document_type):
            partner_update.update(meli_buyer_fields)

        if "l10n_latam_identification_type_id" in meli_buyer_fields and str(meli_buyer_fields['l10n_latam_identification_type_id'])!=str(partner_id.l10n_latam_identification_type_id and partner_id.l10n_latam_identification_type_id.id):
            partner_update.update(meli_buyer_fields)

        if "l10n_cl_sii_taxpayer_type" in meli_buyer_fields and str(meli_buyer_fields['l10n_cl_sii_taxpayer_type'])!=str(partner_id.l10n_cl_sii_taxpayer_type):
            partner_update.update(meli_buyer_fields)

        if "fe_tipo_documento" in meli_buyer_fields and str(meli_buyer_fields['fe_tipo_documento'])!=str(partner_id.fe_tipo_documento):
            partner_update.update(meli_buyer_fields)

        if "fe_nit" in meli_buyer_fields and str(meli_buyer_fields['fe_nit'])!=str(partner_id.fe_nit):
            partner_update.update(meli_buyer_fields)

        if "main_id_number" in meli_buyer_fields and str(meli_buyer_fields['main_id_number'])!=str(partner_id.main_id_number):
            partner_update.update(meli_buyer_fields)

        if "afip_responsability_type_id" in meli_buyer_fields and str(meli_buyer_fields['afip_responsability_type_id'])!=str(partner_id.afip_responsability_type_id and partner_id.afip_responsability_type_id.id):
            partner_update.update(meli_buyer_fields)

        if "property_account_position_id" in meli_buyer_fields and str(meli_buyer_fields['property_account_position_id'])!=str(partner_id.property_account_position_id and partner_id.property_account_position_id.id):
            partner_update.update(meli_buyer_fields)

        if "main_id_category_id" in meli_buyer_fields and str(meli_buyer_fields['main_id_category_id'])!=str(partner_id.main_id_category_id and partner_id.main_id_category_id.id):
            partner_update.update(meli_buyer_fields)

        if ("name" in meli_buyer_fields and meli_buyer_fields["name"]!=str(partner_id.name) ):
            partner_update.update(meli_buyer_fields)

        if ("x_name1" in meli_buyer_fields and meli_buyer_fields["x_name1"]!=str(partner_id.x_name1) ):
            partner_update.update(meli_buyer_fields)

        if "fiscal_responsibility_ids" in meli_buyer_fields:
            partner_update.update(meli_buyer_fields)

        if "tribute_id" in meli_buyer_fields:
            partner_update.update(meli_buyer_fields)

        if not partner_id.country_id:
            partner_update.update({'country_id': self.country(Receiver)})

        if not partner_id.state_id:
            partner_update.update({ 'state_id': self.state(self.country(Receiver), Receiver)})

        if not partner_id.street or partner_id.street=="no street":
            partner_update.update({ 'street': self.street(Receiver)})

        if not partner_id.city or partner_id.city=="":
            partner_update.update({ 'city': self.city(Receiver) })

        if "cities" in meli_buyer_fields and partner_id.cities and partner_id.cities.state_id!=partner_id.state_id:
            partner_update.update({ 'cities': meli_buyer_fields["cities"] })
            partner_update.update({ 'postal_id': meli_buyer_fields["postal_id"] })

        return partner_update

    def fetchIVA( self, meli_id, meli=None, config=None, rjson=None ):
        
        order_item_iva = ""

        if not meli_id:
            return order_item_iva


        if not rjson:
            response = meli.get("/items/"+str(meli_id), {'access_token':meli.access_token, 'include_attributes': 'all'})
            rjson = response and response.json()            
        tax_found = False
        if rjson:
            for att in rjson['attributes']:
                # att["name"] == "IVA"
                if att["id"] == "VALUE_ADDED_TAX":
                    tax_found = True
                    order_item_iva = (att["value_name"]) or (att["values"] and att["values"][0] and att["values"][0]["name"])
                    break;
            if not tax_found:
                #TODO: check other taxes for IVA for this product...
                pass;        

        return order_item_iva

    def fetchImpuestoInterno( self, meli_id, meli=None, config=None, rjson=None ):
        
        order_item_impuesto_interno = ""

        if not meli_id:
            return order_item_impuesto_interno


        if not rjson:
            response = meli.get("/items/"+str(meli_id), {'access_token':meli.access_token, 'include_attributes': 'all'})
            rjson = response and response.json()            

        tax_found = False
        if rjson:
            for att in rjson['attributes']:
                # att["name"] == "Impuesto interno"
                if att["id"] == "IMPORT_DUTY":
                    tax_found = True
                    order_item_impuesto_interno = (att["value_name"]) or (att["values"] and att["values"][0] and att["values"][0]["name"])
                    break;
            if not tax_found:
                #TODO: check other taxes for IVA for this product...
                pass;  


        return order_item_impuesto_interno

    def orders_update_order_json( self, data, context=None, config=None, meli=None ):

        oid = data["id"]
        order_json = data["order_json"]
        #_logger.info( "data:" + str(data) )
        context = context or self.env.context
        #_logger.info( "context:" + str(context) )
        company = (config and "company_id" in config._fields and config.company_id) or config or self.env.user.company_id
        company_domain = ['|',('company_id','=',False),('company_id','=',company.id)]
        company_only_domain = [('company_id','=',company.id)]
        company_none_domain = [('company_id','=',False)]        
        if not config:
            config = company
        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)

        saleorder_obj = self.env['sale.order']
        saleorderline_obj = self.env['sale.order.line']
        product_obj = self.env['product.product']

        pricelist_obj = self.env['product.pricelist']
        respartner_obj = self.env['res.partner']

        plistid = None
        if (config and config.mercadolibre_pricelist):
            plistid = config.mercadolibre_pricelist
        else:
            error = { "error": "orders_update_order_json > no pricelist defined. Check config pricelist config: " + str(config and config.name)+" pricelist: "+str(config and config.mercadolibre_pricelist) }
            _logger.error(error)
            #_logger.info( "orders_update_order_json > filter:" + str(error) )
            return error
            #plistids = pricelist_obj.search([('currency_id','=','ARS')])[0]
            #if plistids:
            #    plistid = plistids

        order_obj = self.env['mercadolibre.orders']
        buyers_obj = self.env['mercadolibre.buyers']
        posting_obj = self.env['mercadolibre.posting']
        order_items_obj = self.env['mercadolibre.order_items']
        payments_obj = self.env['mercadolibre.payments']
        shipment_obj = self.env['mercadolibre.shipment']

        order = None
        sorder = None

        if meli.access_token=="PASIVA":
            order_json = self.prepare_orderjson(meli=meli, config=config)
            data["order_json"] = order_json
            #_logger.info(order_json: "+str(order_json))

        order_fields = self.prepare_ml_order_vals( order_json=order_json, meli=meli, config=config )

        if ( "mercadolibre_channel_mkt" in config._fields and config.mercadolibre_channel_mkt and order_fields["context"] ):
            
            channel_block = True

            for channel in config.mercadolibre_channel_mkt:
                if channel.code == order_fields["context"]:
                    channel_block = False

            if channel_block:
                error = { "error": "orden filtrada por canal "+str(order_fields["context"]) }
                #_logger.info( "orders_update_order_json > filter:" + str(error) )
                return error


        if (    "mercadolibre_filter_order_datetime_start" in config._fields
                and "date_closed" in order_fields
                and order_fields["date_closed"]
                and config.mercadolibre_filter_order_datetime_start
                and config.mercadolibre_filter_order_datetime_start>parse(order_fields["date_closed"]) ):
            error = { "error": "orden filtrada por fecha START > " + str(order_fields["date_closed"]) + " inferior a "+str(ml_datetime(config.mercadolibre_filter_order_datetime_start)) }
            #_logger.info( "orders_update_order_json > filter:" + str(error) )
            return error


        if (    "mercadolibre_filter_order_datetime" in config._fields
                and "date_closed" in order_fields
                and order_fields["date_closed"]
                and config.mercadolibre_filter_order_datetime
                and config.mercadolibre_filter_order_datetime>parse(order_fields["date_closed"]) ):
            error = { "error": "orden filtrada por FROM > " + str(order_fields["date_closed"]) + " inferior a "+str(ml_datetime(config.mercadolibre_filter_order_datetime)) }
            #_logger.info( "orders_update_order_json > filter:" + str(error) )
            return error

        if (    "mercadolibre_filter_order_datetime_to" in config._fields
                and "date_closed" in order_fields
                and order_fields["date_closed"]
                and config.mercadolibre_filter_order_datetime_to
                and config.mercadolibre_filter_order_datetime_to<parse(order_fields["date_closed"]) ):
            error = { "error": "orden filtrada por fecha TO > " + str(order_fields["date_closed"]) + " superior a "+str(ml_datetime(config.mercadolibre_filter_order_datetime_to)) }
            #_logger.info( "orders_update_order_json > filter:" + str(error) )
            return error

        #_logger.info(orders_update_order_json > data "+str(data['id']) + " json:" + str(data['order_json']['id']) )

        # if id is defined, we are updating existing one
        if (oid):
            order = order_obj.browse(oid )
            if (order):
                #_logger.info(order)
                sorder_s = saleorder_obj.search([ ('meli_order_id','=',order.order_id) ] )
                if (sorder_s):
                    #_logger.info(sorder_s)
                    if (len(sorder_s)>1):
                        sorder = sorder_s[0]
                    else:
                        sorder = sorder_s
        else:
        #we search for existing order with same order_id => "id"
            order_s = order_obj.search([ ('order_id','=','%s' % (str(order_json["id"]))) ] )
            if (order_s):
                if (len(order_s)>1):
                    order = order_s[0]
                else:
                    order = order_s
            #    order = order_obj.browse(order_s[0] )

            sorder_s = saleorder_obj.search([ ('meli_order_id','=','%s' % (str(order_json["id"]))) ] )
            if (sorder_s):
                if (len(sorder_s)>1):
                    sorder = sorder_s[0]
                else:
                    sorder = sorder_s
            #if (sorder_s and len(sorder_s)>0):
            #    sorder = saleorder_obj.browse(sorder_s[0] )

        if (sorder and sorder.meli_update_forbidden):
            _logger.error("Forbidden to upate by meli_oerp" )
            return {'error': 'Forbidden to upate by meli_oerp' }

        seller_id = None
        if config.mercadolibre_seller_user:
            seller_id = config.mercadolibre_seller_user.id


        partner_id = False
        partner_shipping_id = False

        if not 'buyer' in order_json or not 'name' in order_json['buyer'] or not 'first_name' in order_json['buyer']:
            #_logger.info("Buyer not present, fetch order")
            response = meli.get("/orders/"+str(order_json['id']), {'access_token':meli.access_token})
            order_json = response.json()
            #_logger.info(order_json)

        if 'buyer' in order_json:
            Buyer = order_json['buyer']

            # --- ALERTA: comprador genérico (GLOBALCOMPRADOR) ---
            # Este comprador ficticio se usa en órdenes internas/fulfillment sin datos reales.
            # En Brasil y otros países con facturación electrónica, esto impide emitir NFe/XML
            # porque el contacto no tiene CPF/CNPJ ni nombre fiscal real.
            # Los errores de NCM que aparecen suelen ser consecuencia de este mismo problema.
            _buyer_id_raw = str(Buyer.get('id', '') or '')
            if _buyer_id_raw.upper() in ('GLOBALCOMPRADOR', 'CLIENTEML'):
                _logger.warning(
                    "BUYER_GENERICO: order %s usa comprador ficticio id='%s'. "
                    "No habra CPF/CNPJ ni nombre fiscal real. "
                    "En Brasil esto bloquea la emision de NFe. "
                    "Revisar manualmente el contacto de facturacion del pedido.",
                    order_json.get('id', '?'), _buyer_id_raw
                )
                if order:
                    order.message_post(
                        body=(
                            "⚠️ COMPRADOR GENÉRICO detectado (id: %s). "
                            "Este pedido no tiene datos fiscales reales del comprador. "
                            "Para emitir NFe/Nota Fiscal es necesario corregir manualmente "
                            "el contacto de facturación (CPF/CNPJ, nombre legal)."
                        ) % _buyer_id_raw,
                        message_type='comment'
                    )

            Buyer['billing_info'] = self.get_billing_info(order_id=order_json['id'],meli=meli,data=order_json)
            _logger.info("BUYER_DATA: order=%s buyer_id=%s billing_info_keys=%s doc_type=%s doc_number=%s",
                         order_json.get('id','?'), _buyer_id_raw,
                         list(Buyer.get('billing_info', {}).keys()),
                         Buyer.get('billing_info', {}).get('doc_type', 'N/A'),
                         Buyer.get('billing_info', {}).get('doc_number', 'N/A'))
            # Nombre para contacto principal: usar nombre del buyer de MeLi (de la orden)
            Buyer['first_name'] = ('first_name' in Buyer and Buyer['first_name']) or ''
            Buyer['last_name'] = ('last_name' in Buyer and Buyer['last_name']) or ''
            # Fallback a nickname si el buyer no tiene first/last name
            if not Buyer['first_name'] and not Buyer['last_name']:
                Buyer['first_name'] = ('nickname' in Buyer and Buyer['nickname']) or ''
            Buyer['first_name'] = Buyer['first_name'] and Buyer['first_name'].strip().title()
            Buyer['last_name'] = Buyer['last_name'] and Buyer['last_name'].strip().title()
            Buyer['business_name'] = ('business_name' in Buyer and Buyer['business_name']) or ''

            # Nombre para facturación: priorizar billing_info (nombre legal/fiscal)
            _billing_fn = ('FIRST_NAME' in Buyer['billing_info'] and Buyer['billing_info']['FIRST_NAME']) or ''
            _billing_ln = ('LAST_NAME' in Buyer['billing_info'] and Buyer['billing_info']['LAST_NAME']) or ''
            _billing_bn = ('BUSINESS_NAME' in Buyer['billing_info'] and Buyer['billing_info']['BUSINESS_NAME']) or ''
            billing_full_name = ''
            if _billing_fn:
                billing_full_name = _billing_fn.strip().title()
                if _billing_ln:
                    billing_full_name += ' ' + _billing_ln.strip().title()
            billing_full_name = billing_full_name or _billing_bn or self.buyer_full_name(Buyer)
            Receiver = False
            if ('shipping' in order_json and order_json['shipping']):
                if ('receiver_address' in order_json['shipping']):
                    Receiver = order_json['shipping']['receiver_address']
                elif ('id' in order_json['shipping']):
                    Shipment = self.env["mercadolibre.shipment"].search([('shipping_id','=',order_json['shipping']["id"])],limit=1)
                    #_logger.info("Shipment:"+str(Shipment))
                    if (len(Shipment)==1):
                        Receiver = {
                            'receiver_address': Shipment.receiver_address_line,
                            'address_line': Shipment.receiver_address_line,
                            'receiver_name': Shipment.receiver_address_name,
                            'receiver_phone': Shipment.receiver_address_phone,
                            'country': {
                                'id': Shipment.receiver_country_code,
                                'name': Shipment.receiver_country
                            },
                            'state': {
                                'name': Shipment.receiver_state,
                                'id': Shipment.receiver_state_code
                            },
                            'city': {
                                'name': Shipment.receiver_city,
                                'id': Shipment.receiver_city_code
                            }
                        }
                    else:
                        shipres = meli.get("/shipments/"+ str(order_json['shipping']['id']),  {'access_token':meli.access_token })
                        if shipres:
                            shpjson = shipres.json()
                            if "receiver_address" in shpjson:
                                Receiver = shpjson["receiver_address"]
            #_logger.info("Buyer:"+str(Buyer) )
            #_logger.info(order_json)
            #_logger.info("Buyer:"+str(Buyer) )
            #_logger.info("Receiver:"+str(Receiver) )
            meli_buyer_fields = {
                'name': self.buyer_full_name(Buyer),
                'street': self.street(Receiver,Buyer),
                'city': self.city(Receiver,Buyer),
                'country_id': self.country(Receiver,Buyer),
                'state_id': self.state(self.country(Receiver,Buyer),Receiver,Buyer),
                'zip': self.zip_code(Receiver,Buyer),
                'phone': self.full_phone( Buyer ),
                #'email': Buyer['email'],
                'meli_buyer_id': Buyer['id'],
            }
            set_client_company = "mercadolibre_cron_get_orders_client_set_company" in config._fields and config.mercadolibre_cron_get_orders_client_set_company
            if company and company.id and set_client_company:
                meli_buyer_fields["company_id"] = company.id
            meli_buyer_fields.update(self.fix_locals(Receiver=Receiver,Buyer=Buyer))
            if company:
                meli_buyer_fields["lang"] =  company.partner_id.lang

            buyer_fields = {
                'buyer_id': Buyer['id'],
                'nickname': ('nickname' in Buyer and Buyer['nickname']) or "",
                'email': ('email' in Buyer and Buyer['email']) or "",
                'phone': self.full_phone( Buyer ),
                'alternative_phone': self.full_alt_phone( Buyer ),
                'first_name': ('first_name' in Buyer and Buyer['first_name']) or "",
                'last_name': ('last_name' in Buyer and Buyer['last_name']) or "",
                'billing_info': self.billing_info(Buyer['billing_info']),
            }
            buyer_fields.update(self.buyer_additional_info(Buyer['billing_info']))
            buyer_fields.update({'name': self.buyer_full_name(Buyer) })

            #buyer_ids = buyers_obj.sudo().search([  ('buyer_id','=',buyer_fields['buyer_id'] ) ] + company_domain, limit=1 )

            query = """SELECT id
            FROM   mercadolibre_buyers
            WHERE
            buyer_id = '%s'
            """ % (buyer_fields['buyer_id'])
            cr = MeliCr( self )
            respquery = cr.execute(query)
            results = cr.fetchall()
            buyer_ids = results
            #_logger.info("Buyer ids: "+str(buyer_ids))
            buyer_id = False
            if ( not buyer_ids ):
                #_logger.info( "creating buyer "+str(buyer_fields['buyer_id'])+" order id:" + str(order and order.name))
                #_logger.info(buyer_fields)
                # Use savepoint to handle race condition gracefully
                # If another transaction creates the buyer, we can rollback to savepoint and search
                try:
                    self.env.cr.execute("SAVEPOINT buyer_create")
                    buyer_id = buyers_obj.sudo().create(( buyer_fields ))
                    self.env.cr.execute("RELEASE SAVEPOINT buyer_create")
                except Exception as e:
                    # Handle race condition: another transaction may have created the buyer
                    if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
                        self.env.cr.execute("ROLLBACK TO SAVEPOINT buyer_create")
                        _logger.info("Buyer %s created by concurrent transaction, fetching...", buyer_fields['buyer_id'])
                        buyer_id = buyers_obj.sudo().search([('buyer_id', '=', buyer_fields['buyer_id'])], limit=1)
                        if buyer_id:
                            buyer_id.sudo().write(buyer_fields)
                    else:
                        self.env.cr.execute("ROLLBACK TO SAVEPOINT buyer_create")
                        raise
            else:
                buyer_id = buyers_obj.sudo().browse(buyer_ids and buyer_ids[0])
                #buyer_id = buyer_ids[0]
                if buyer_id:
                    buyer_id.sudo().write( ( buyer_fields ) )
                #if (len(buyer_ids)>0):
                #      buyer_id = buyer_ids[0]
            if (buyer_id):
                meli_buyer_fields['meli_buyer'] = buyer_id.id
                if (('doc_type' in Buyer['billing_info']) and ('afip.responsability.type' in self.env)):
                    doctypeid = self.env['res.partner.id_category'].search([('code','=',Buyer['billing_info']['doc_type'])]).id
                    if (doctypeid):
                        meli_buyer_fields['main_id_category_id'] = doctypeid
                        meli_buyer_fields['main_id_number'] = Buyer['billing_info']['doc_number']
                        if (Buyer['billing_info']['doc_type']=="CUIT"):
                            #IVA Responsable Inscripto
                            if ('business_name' in Buyer and Buyer['business_name']):
                                meli_buyer_fields['company_type'] = 'company'
                                #TODO: add company contact
                            if ('TAXPAYER_TYPE_ID' in Buyer['billing_info'] and Buyer['billing_info']['TAXPAYER_TYPE_ID'] and Buyer['billing_info']['TAXPAYER_TYPE_ID']=="IVA Responsable Inscripto"):
                                afipid = self.env['afip.responsability.type'].search([('code','=',1)]).id
                                meli_buyer_fields["afip_responsability_type_id"] = afipid
                        else:
                            #if (Buyer['billing_info']['doc_type']=="DNI"):
                            #Consumidor Final
                            afipid = self.env['afip.responsability.type'].search([('code','=',5)]).id
                            meli_buyer_fields["afip_responsability_type_id"] = afipid
                    else:
                        _logger.error("res.partner.id_category:" + str(Buyer['billing_info']['doc_type']))

                #Mexico
                if (('doc_type' in Buyer['billing_info']) and ('l10n_mx_edi_fiscal_regime' in self.env['res.partner']._fields)):
                    if ( Buyer['billing_info']['doc_type'] and Buyer['billing_info']['doc_type'] != "CURP" ):
                        meli_buyer_fields['vat'] = Buyer['billing_info']['doc_number']
                    

                # Tracking: campos fiscales seteados EXPLÍCITAMENTE por datos de ML
                # (vs defaults como CF code=5). Se usa en el UPDATE path para no
                # sobreescribir datos fiscales buenos con defaults del cron.
                _ml_explicit_fiscal_fields = set()

                #Chile/Arg/Latam
                if ( ('doc_type' in Buyer['billing_info']) and ('l10n_latam_identification_type_id' in self.env['res.partner']._fields) ):
                    _doc_type = Buyer['billing_info']['doc_type']
                    doc_type_id = self.env["l10n_latam.identification.type"].search([('country_id','=',company.country_id.id),('name','ilike',_doc_type)],limit=1)

                    # Fallback para Argentina: buscar por código AFIP si no se encontró por nombre
                    if not doc_type_id and company.country_id.code == "AR" and 'l10n_ar_afip_code' in self.env["l10n_latam.identification.type"]._fields:
                        afip_code_map = {'DNI': '96', 'CUIT': '80', 'CUIL': '86', 'CDI': '87', 'LE': '89', 'LC': '90', 'CI': '91', 'PASAPORTE': '94'}
                        afip_code = afip_code_map.get(_doc_type.upper())
                        if afip_code:
                            doc_type_id = self.env["l10n_latam.identification.type"].search([
                                ('country_id','=',company.country_id.id),
                                ('l10n_ar_afip_code','=',afip_code)
                            ],limit=1)
                            # Fallback: buscar por código AFIP sin filtro de país
                            if not doc_type_id:
                                doc_type_id = self.env["l10n_latam.identification.type"].search([
                                    ('l10n_ar_afip_code','=',afip_code)
                                ],limit=1)

                    # Fallback: buscar por nombre sin filtro de país
                    if not doc_type_id:
                        doc_type_id = self.env["l10n_latam.identification.type"].search([('name','ilike',_doc_type)],limit=1)

                    if not doc_type_id:
                        _logger.warning("l10n_latam.identification.type no encontrado para doc_type=%s country=%s", _doc_type, company.country_id.code)

                    if (_doc_type=="RUT"):
                        meli_buyer_fields['l10n_latam_identification_type_id'] = (doc_type_id and doc_type_id.id) or 4
                    if (_doc_type=="RUN"):
                        meli_buyer_fields['l10n_latam_identification_type_id'] = (doc_type_id and doc_type_id.id) or 5
                    if (doc_type_id):
                        meli_buyer_fields['l10n_latam_identification_type_id'] = (doc_type_id and doc_type_id.id)

                    if (company.country_id.code == "AR" and 'l10n_ar.afip.responsibility.type' in self.env
                        and 'l10n_ar_afip_responsibility_type_id' in self.env['res.partner']._fields):
                        _taxpayer_raw = Buyer['billing_info'].get('TAXPAYER_TYPE_ID', '') or ''
                        _taxpayer_upper = _taxpayer_raw.strip().upper()
                        _afip_code_map = {
                            'IVA RESPONSABLE INSCRIPTO': 1,
                            'RESPONSABLE INSCRIPTO': 1,
                            # ML can send 'IVA Sujeto Exento' or just 'IVA Exento' — both map to code=4
                            'IVA SUJETO EXENTO': 4,
                            'IVA EXENTO': 4,
                            'EXENTO': 4,
                            'SUJETO EXENTO': 4,
                            'RESPONSABLE MONOTRIBUTO': 6,
                            'MONOTRIBUTO': 6,
                        }
                        if _taxpayer_upper and _taxpayer_upper in _afip_code_map:
                            _afip_code = _afip_code_map[_taxpayer_upper]
                            _ml_explicit_fiscal_fields.add('l10n_ar_afip_responsibility_type_id')
                        else:
                            _afip_code = 5  # Default: Consumidor Final
                        afipid = self.env['l10n_ar.afip.responsibility.type'].search([('code','=',_afip_code)], limit=1).id
                        if afipid:
                            meli_buyer_fields["l10n_ar_afip_responsibility_type_id"] = afipid

                    if Buyer['billing_info'].get('doc_type'):
                        _ml_explicit_fiscal_fields.add('l10n_latam_identification_type_id')
                    if Buyer['billing_info'].get('doc_number'):
                        _ml_explicit_fiscal_fields.add('vat')
                    meli_buyer_fields['vat'] = Buyer['billing_info']['doc_number']

                #Arg 15.0/17.0 CER BlueOrange Blue Orange
                if (('doc_type' in Buyer['billing_info']) and ('partner_document_type_id' in self.env['res.partner']._fields) ):
                    doc_type = Buyer['billing_info']['doc_type']
                    doc_type_id = self.env["partner.document.type"].search([('name','ilike',doc_type)],limit=1)
                    if (doc_type_id):
                        meli_buyer_fields['partner_document_type_id'] = (doc_type_id and doc_type_id.id)
                    _logger.info("CER_BLOCK: doc_type=%s doc_type_id=%s", doc_type, doc_type_id.id if doc_type_id else None)

                    tax_type = 'TAXPAYER_TYPE_ID' in Buyer['billing_info'] and Buyer['billing_info']['TAXPAYER_TYPE_ID']
                    _cer_taxpayer_explicit = False
                    if (tax_type):
                        _cer_taxpayer_explicit = True
                        if (tax_type=="Monotributo"):
                            tax_type = "Responsable Monotributo"
                        if (tax_type=="IVA Exento"):
                            tax_type = "Exento"
                    else:
                        if (doc_type=="DNI"):
                            tax_type = "Consumidor Final"

                    tax_type_id = self.env["account.fiscal.position"].search([('name','ilike',tax_type),('company_id','=',company.id)],limit=1)
                    if (tax_type_id and 'property_account_position_id' in self.env['res.partner']._fields):
                        meli_buyer_fields['property_account_position_id'] = (tax_type_id and tax_type_id.id)
                        if _cer_taxpayer_explicit:
                            _ml_explicit_fiscal_fields.add('property_account_position_id')

                    if doc_type:
                        _ml_explicit_fiscal_fields.add('partner_document_type_id')

                    # CER/Blue Orange: también setear l10n_ar_afip_responsibility_type_id
                    # si el campo existe (requerido por AFIP WSFE para validar facturas)
                    _has_afip_model = 'l10n_ar.afip.responsibility.type' in self.env
                    _has_afip_field = 'l10n_ar_afip_responsibility_type_id' in self.env['res.partner']._fields
                    _already_set = 'l10n_ar_afip_responsibility_type_id' in meli_buyer_fields
                    _logger.info("CER_BLOCK AFIP: country=%s has_model=%s has_field=%s already_set=%s tax_type=%s",
                                 company.country_id.code, _has_afip_model, _has_afip_field, _already_set, tax_type)
                    if (company.country_id.code == "AR"
                        and _has_afip_model and _has_afip_field and not _already_set):
                        # Default: Consumidor Final (code=5)
                        afip_resp = self.env['l10n_ar.afip.responsibility.type'].search([('code','=',5)], limit=1)
                        if tax_type and afip_resp:
                            _afip_map_cer = {
                                'IVA RESPONSABLE INSCRIPTO': 1,
                                'RESPONSABLE INSCRIPTO': 1,
                                'RESPONSABLE MONOTRIBUTO': 6,
                                'MONOTRIBUTO': 6,
                                'IVA SUJETO EXENTO': 4,
                                'EXENTO': 4,
                                'CONSUMIDOR FINAL': 5,
                            }
                            afip_code = _afip_map_cer.get((tax_type or '').strip().upper(), 5)
                            afip_resp = self.env['l10n_ar.afip.responsibility.type'].search([('code','=',afip_code)], limit=1)
                        if afip_resp:
                            meli_buyer_fields['l10n_ar_afip_responsibility_type_id'] = afip_resp.id
                            if _cer_taxpayer_explicit:
                                _ml_explicit_fiscal_fields.add('l10n_ar_afip_responsibility_type_id')
                            _logger.info("CER_BLOCK AFIP: SET l10n_ar_afip_responsibility_type_id=%s (code=%s, tax_type=%s, explicit=%s)",
                                         afip_resp.id, afip_resp.code, tax_type, _cer_taxpayer_explicit)
                        else:
                            _logger.warning("CER_BLOCK AFIP: no se encontró l10n_ar.afip.responsibility.type para tax_type=%s", tax_type)
                    elif company.country_id.code == "AR" and _already_set:
                        _logger.info("CER_BLOCK AFIP: SKIP (ya seteado por bloque l10n_latam)")
                    elif company.country_id.code == "AR":
                        _logger.warning("CER_BLOCK AFIP: SKIP (has_model=%s has_field=%s)", _has_afip_model, _has_afip_field)

                    meli_buyer_fields['vat'] = Buyer['billing_info']['doc_number']

                #Chile YNext
                if (1==2 and  ('doc_type' in Buyer['billing_info']) and ('dte_email' in self.env['res.partner']._fields)):

                    meli_buyer_fields['dte_email'] = 'nomail@fake.com'
                    
                    if ('giro' in self.env['res.partner']._fields):
                        meli_buyer_fields['giro'] = 'SIN GIRO'

                    vatn = Buyer['billing_info']['doc_number']
                    if (len(vatn)==9):
                        vatn = vatn[:2]+"."+vatn[2:5]+"."+vatn[5:8]+"-"+vatn[8:9]
                    if (len(vatn)==8):
                        vatn = vatn[:1]+"."+vatn[1:4]+"."+vatn[4:7]+"-"+vatn[7:8]
                    meli_buyer_fields['vat'] = vatn

                #latam Chile - l10n_cl_edi
                if ( company.country_id.code=="CL" and ('doc_type' in Buyer['billing_info']) and ('l10n_latam_identification_type_id' in self.env['res.partner']._fields ) ):

                    if (Buyer['billing_info']['doc_type']=="RUT"):
                        #rut
                        meli_buyer_fields['l10n_latam_identification_type_id'] = self.env['l10n_latam.identification.type'].search([('name','=','RUT'),('country_id','=',company.country_id.id)],limit=1).id

                    if (Buyer['billing_info']['doc_type']=="RUN"):
                        #rut
                        meli_buyer_fields['l10n_latam_identification_type_id'] = self.env['l10n_latam.identification.type'].search([('name','=','RUN'),('country_id','=',company.country_id.id)],limit=1).id

                    if (Buyer['billing_info']['doc_type']=="DNI"):
                        #rut
                        meli_buyer_fields['l10n_latam_identification_type_id'] = self.env['l10n_latam.identification.type'].search([('name','=','DNI'),('country_id','=',company.country_id.id)],limit=1).id


                    vatn = Buyer['billing_info']['doc_number']
                    is_business = False
                    sep_millon = cl_vat_sep_million
                    if (len(vatn)==9):
                        vatn = vatn[:2]+str(sep_millon)+vatn[2:5]+""+vatn[5:8]+"-"+vatn[8:9]
                        isb = float(vatn[:2])
                        #_logger.info(Chile VAT: is business:"+str(isb))
                        is_business = (isb >= 50)
                        #_logger.info(Chile VAT: is business? "+str(is_business))
                    if (len(vatn)==8):
                        vatn = str("0")+vatn[:1]+str(sep_millon)+vatn[1:4]+""+vatn[4:7]+"-"+vatn[7:8]
                    meli_buyer_fields['vat'] = vatn

                    if "l10n_cl_sii_taxpayer_type" in self.env['res.partner']._fields:
                        if is_business:
                            meli_buyer_fields['l10n_cl_sii_taxpayer_type'] = "1"
                            meli_buyer_fields['company_type'] = "company"
                        else:
                            meli_buyer_fields['l10n_cl_sii_taxpayer_type'] = "3"
                            meli_buyer_fields['company_type'] = "person"


                #CHILE, Daniel Santibañez localization
                if ( ('doc_type' in Buyer['billing_info']) and ('document_type_id' in self.env['res.partner']._fields) and ('document_number' in self.env['res.partner']._fields) ):

                    if (Buyer['billing_info']['doc_type']=="RUT"):
                        meli_buyer_fields['document_type_id'] = self.env['sii.document_type'].search([('code','=','RUT')],limit=1).id
                    elif (Buyer['billing_info']['doc_type']):
                        meli_buyer_fields['document_type_id'] = self.env['sii.document_type'].search([('code','=',Buyer['billing_info']['doc_type'])],limit=1).id

                    meli_buyer_fields['es_mipyme'] = True
                    vatn = Buyer['billing_info']['doc_number']
                    is_business = False
                    sep_millon = cl_vat_sep_million
                    if (len(vatn)==9):
                        vatn = vatn[:2]+"."+vatn[2:5]+"."+vatn[5:8]+"-"+vatn[8:9]
                        isb = float(vatn[:2])
                        #_logger.info(Chile VAT: is business:"+str(isb))
                        is_business = (isb >= 50)
                        #_logger.info(Chile VAT: is business? "+str(is_business))
                    if (len(vatn)==8):
                        vatn = str("0")+vatn[:1]+"."+vatn[1:4]+"."+vatn[4:7]+"-"+vatn[7:8]
                    #meli_buyer_fields['vat'] = vatn
                    meli_buyer_fields['document_number'] = vatn
                    meli_buyer_fields['vat'] = ""
                    del meli_buyer_fields['vat']
                    try:
                        #('activity_description' in self.env['res.partner']._fields) and meli_buyer_fields.update({"activity_description": self.env["sii.activity.description"].search([('name','=','NCP')],limit=1).id })

                        if ("billing_info_economic_activity" in buyer_fields and 'activity_description' in self.env['res.partner']._fields):
                            acti_desc = buyer_fields["billing_info_economic_activity"]
                            sii_giro = self.env["sii.activity.description"].search([('name','=',acti_desc)], limit=1 )
                            _logger.error("sii_giro: "+str(sii_giro))
                            if (not sii_giro):
                                sii_giro = self.env["sii.activity.description"].create(({
                                    "name": acti_desc
                                }))
                                _logger.error("creando sii_giro: "+str(sii_giro))

                            meli_buyer_fields['activity_description'] = (sii_giro and sii_giro.id) or None
                    except Exception as E:
                        _logger.error("billing_info_economic_activity"+str(E))
                        pass;

                    if ("billing_info_neighborhood" in buyer_fields or "billing_info_city_name" in buyer_fields):
                        #meli_buyer_fields['city_id'] = ""
                        comuna = buyer_fields["billing_info_neighborhood"] or buyer_fields["billing_info_city_name"]
                        res_city = self.env["res.city"].search([('name','ilike',comuna)], limit=1 )
                        if (res_city):
                            meli_buyer_fields['city_id'] = (res_city and res_city.id) or None
                        pass;
                
                    if ("billing_info_state_name" in buyer_fields and buyer_fields["billing_info_state_name"]):
                        if ("RM" in buyer_fields["billing_info_state_name"]):
                            meli_buyer_fields['city'] = "Santiago"



                #Colombia
                if ( ('doc_type' in Buyer['billing_info']) and ('l10n_co_document_type' in self.env['res.partner']._fields) ):
                    if ("fe_es_compania" in self.env['res.partner']._fields ):
                        meli_buyer_fields['fe_es_compania'] = '2'
                    if ("fe_correo_electronico" in self.env['res.partner']._fields ):
                        meli_buyer_fields['fe_correo_electronico'] = ('email' in Buyer and Buyer['email']) or ""

                    if (Buyer['billing_info']['doc_type']=="CC" or Buyer['billing_info']['doc_type']=="C.C."):
                        meli_buyer_fields['l10n_co_document_type'] = 'national_citizen_id'
                        if ("fe_tipo_documento" in self.env['res.partner']._fields):
                            meli_buyer_fields['fe_tipo_documento'] = '13'
                        if ("fe_tipo_regimen" in self.env['res.partner']._fields ):
                            meli_buyer_fields['fe_tipo_regimen'] = '00'
                        if ("fe_regimen_fiscal" in self.env['res.partner']._fields ):
                            meli_buyer_fields['fe_regimen_fiscal'] = '49'
                        if ("responsabilidad_fiscal_fe" in self.env['res.partner']._fields ):
                            R_99_PN_noaplica = self.env["l10n_co_cei_settings.responsabilidad_fiscal"].search([('codigo_fe_dian','=','R-99-PN')],limit=1)
                            if R_99_PN_noaplica:
                                meli_buyer_fields['responsabilidad_fiscal_fe'] = [ ( 6, 0, [R_99_PN_noaplica.id] ) ]

                    if (Buyer['billing_info']['doc_type']=="NIT"):
                        meli_buyer_fields['l10n_co_document_type'] = 'rut'
                        if ("fe_tipo_documento" in self.env['res.partner']._fields):
                            meli_buyer_fields['fe_tipo_documento'] = '31'
                        if ("fe_es_compania" in self.env['res.partner']._fields ):
                            meli_buyer_fields['fe_es_compania'] = '1'
                        #if ("fe_tipo_regimen" in self.env['res.partner']._fields ):
                        #    meli_buyer_fields['fe_tipo_regimen'] = '04'
                        #if ("fe_regimen_fiscal" in self.env['res.partner']._fields ):
                        #    meli_buyer_fields['fe_regimen_fiscal'] = '48'

                    if (Buyer['billing_info']['doc_type']=="CE"):
                        meli_buyer_fields['l10n_co_document_type'] = 'foreign_id_card'
                        if ("fe_tipo_documento" in self.env['res.partner']._fields):
                            meli_buyer_fields['fe_tipo_documento'] = '22'
                        if ("fe_tipo_regimen" in self.env['res.partner']._fields ):
                            meli_buyer_fields['fe_tipo_regimen'] = '00'
                        if ("fe_regimen_fiscal" in self.env['res.partner']._fields ):
                            meli_buyer_fields['fe_regimen_fiscal'] = '49'
                        if ("responsabilidad_fiscal_fe" in self.env['res.partner']._fields ):
                            R_99_PN_noaplica = self.env["l10n_co_cei_settings.responsabilidad_fiscal"].search([('codigo_fe_dian','=','R-99-PN')],limit=1)
                            if R_99_PN_noaplica:
                                meli_buyer_fields['responsabilidad_fiscal_fe'] = [ ( 6, 0, [R_99_PN_noaplica.id] ) ]

                    meli_buyer_fields['vat'] = Buyer['billing_info']['doc_number']

                    if ("xidentification" in self.env['res.partner']._fields):
                        meli_buyer_fields['xidentification'] = Buyer['billing_info']['doc_number']

                    if ("fe_nit" in self.env['res.partner']._fields):
                        meli_buyer_fields['fe_nit'] = Buyer['billing_info']['doc_number']
                        if (Buyer['billing_info']['doc_type']=="NIT"):
                            meli_buyer_fields['fe_nit'] = Buyer['billing_info']['doc_number'][0:10]
                            if ("fe_digito_verificacion" in self.env['res.partner']._fields):
                                meli_buyer_fields['fe_digito_verificacion'] = Buyer['billing_info']['doc_number'][-1]

                    if ("fe_primer_nombre" in self.env['res.partner']._fields):
                        nn = Buyer['first_name'].split(" ")
                        if (len(nn)>1):
                            meli_buyer_fields['fe_primer_nombre'] = nn[0]
                            meli_buyer_fields['fe_segundo_nombre'] = nn[1]
                        else:
                            meli_buyer_fields['fe_primer_nombre'] = Buyer['first_name']
                    if ("fe_primer_apellido" in self.env['res.partner']._fields):
                        nn = Buyer['last_name'].split(" ")
                        if (len(nn)>1):
                            meli_buyer_fields['fe_primer_apellido'] = nn[0]
                            meli_buyer_fields['fe_segundo_apellido'] = nn[1]
                        else:
                            meli_buyer_fields['fe_primer_apellido'] = Buyer['last_name']

                #Colombia2
                if ( ('doc_type' in Buyer['billing_info']) and ('l10n_co_document_typee' in self.env['res.partner']._fields) ):

                    if ("fe_es_compania" in self.env['res.partner']._fields ):
                        meli_buyer_fields['fe_es_compania'] = '2'

                    if ("fe_correo_electronico" in self.env['res.partner']._fields ):
                        meli_buyer_fields['fe_correo_electronico'] = ('email' in Buyer and Buyer['email']) or ""

                    meli_buyer_fields['email'] = ('email' in Buyer and Buyer['email']) or ""

                    if ("tribute_id" in self.env['res.partner']._fields ):
                        tributeIVA01 = self.env['dian.tributes'].search([("code","like","01")],limit=1)
                        if tributeIVA01:
                            meli_buyer_fields['tribute_id'] = tributeIVA01.id
                            #_logger.info(tribute_id: tributeIVA01:"+str(tributeIVA01 and tributeIVA01.name))

                    fisc_noresp = False
                    fisc_simple = False
                    if ("fiscal_responsability_ids" in self.env['res.partner']._fields ):
                        fisc_noresp = self.env['dian.fiscal.responsability'].search([("name","like","No responsable")],limit=1)
                        fisc_simple = self.env['dian.fiscal.responsability'].search([("name","like","Simple")],limit=1)
                        #_logger.info(fiscal_responsability_ids: fisc_noresp:"+str(fisc_noresp and fisc_noresp.name)+" fisc_simple:"+str(fisc_simple and fisc_simple.name))



                    if (Buyer['billing_info']['doc_type']=="CC" or Buyer['billing_info']['doc_type']=="C.C."):
                        meli_buyer_fields['l10n_co_document_typee'] = 'national_citizen_id'
                        meli_buyer_fields['x_pn_retri'] = '23'

                        if ("fe_tipo_documento" in self.env['res.partner']._fields):
                            meli_buyer_fields['fe_tipo_documento'] = '13'
                        if ("fe_tipo_regimen" in self.env['res.partner']._fields ):
                            meli_buyer_fields['fe_tipo_regimen'] = '00'
                        if ("fe_regimen_fiscal" in self.env['res.partner']._fields ):
                            meli_buyer_fields['fe_regimen_fiscal'] = '49'
                        if ("responsabilidad_fiscal_fe" in self.env['res.partner']._fields ):
                            R_99_PN_noaplica = self.env["l10n_co_cei_settings.responsabilidad_fiscal"].search([('codigo_fe_dian','=','R-99-PN')],limit=1)
                            if R_99_PN_noaplica:
                                meli_buyer_fields['responsabilidad_fiscal_fe'] = [ ( 6, 0, [R_99_PN_noaplica.id] ) ]

                        if fisc_noresp:
                            meli_buyer_fields['fiscal_responsability_ids'] = [ ( 6, 0, [fisc_noresp.id] ) ]

                    if (Buyer['billing_info']['doc_type']=="NIT"):
                        meli_buyer_fields['l10n_co_document_typee'] = 'rut'
                        meli_buyer_fields['x_pn_retri'] = '6'

                        if ("fe_tipo_documento" in self.env['res.partner']._fields):
                            meli_buyer_fields['fe_tipo_documento'] = '31'
                        if ("fe_es_compania" in self.env['res.partner']._fields ):
                            meli_buyer_fields['fe_es_compania'] = '1'
                        #if ("fe_tipo_regimen" in self.env['res.partner']._fields ):
                        #    meli_buyer_fields['fe_tipo_regimen'] = '04'
                        #if ("fe_regimen_fiscal" in self.env['res.partner']._fields ):
                        #    meli_buyer_fields['fe_regimen_fiscal'] = '48'

                        if fisc_simple:
                            meli_buyer_fields['fiscal_responsability_ids'] = [ ( 6, 0, [fisc_simple.id] ) ]

                    if (Buyer['billing_info']['doc_type']=="CE"):
                        meli_buyer_fields['l10n_co_document_typee'] = 'foreign_id_card'

                        if ("fe_tipo_documento" in self.env['res.partner']._fields):
                            meli_buyer_fields['fe_tipo_documento'] = '22'
                        if ("fe_tipo_regimen" in self.env['res.partner']._fields ):
                            meli_buyer_fields['fe_tipo_regimen'] = '00'
                        if ("fe_regimen_fiscal" in self.env['res.partner']._fields ):
                            meli_buyer_fields['fe_regimen_fiscal'] = '49'
                        if ("responsabilidad_fiscal_fe" in self.env['res.partner']._fields ):
                            R_99_PN_noaplica = self.env["l10n_co_cei_settings.responsabilidad_fiscal"].search([('codigo_fe_dian','=','R-99-PN')],limit=1)
                            if R_99_PN_noaplica:
                                meli_buyer_fields['responsabilidad_fiscal_fe'] = [ ( 6, 0, [R_99_PN_noaplica.id] ) ]

                        if fisc_noresp:
                            meli_buyer_fields['fiscal_responsability_ids'] = [ ( 6, 0, [fisc_noresp.id] ) ]

                    meli_buyer_fields['vat'] = Buyer['billing_info']['doc_number']

                    if ("xidentification" in self.env['res.partner']._fields):
                        meli_buyer_fields['xidentification'] = Buyer['billing_info']['doc_number']

                    if ("fe_nit" in self.env['res.partner']._fields):
                        meli_buyer_fields['fe_nit'] = Buyer['billing_info']['doc_number']
                        if (Buyer['billing_info']['doc_type']=="NIT"):
                            meli_buyer_fields['fe_nit'] = Buyer['billing_info']['doc_number'][0:10]
                            if ("fe_digito_verificacion" in self.env['res.partner']._fields):
                                meli_buyer_fields['fe_digito_verificacion'] = Buyer['billing_info']['doc_number'][-1]

                    if ("x_name1" in self.env['res.partner']._fields) and Buyer['first_name']:
                        nn = Buyer['first_name'].split(" ")
                        if (len(nn)>1):
                            meli_buyer_fields['x_name1'] = nn[0]
                            meli_buyer_fields['x_name2'] = nn[1]
                        else:
                            meli_buyer_fields['x_name1'] = Buyer['first_name']


                    if ("x_lastname1" in self.env['res.partner']._fields) and Buyer['last_name']:
                        nn = Buyer['last_name'].split(" ")
                        if (len(nn)>1):
                            meli_buyer_fields['x_lastname1'] = nn[0]
                            meli_buyer_fields['x_lastname2'] = nn[1]
                        else:
                            meli_buyer_fields['x_lastname1'] = Buyer['last_name']

                    if not Buyer['first_name'] and ("x_name1" in self.env['res.partner']._fields):
                        nn = Buyer['name'].split(" ")
                        if (len(nn)==2):
                            meli_buyer_fields['x_name1'] = nn[0]
                            meli_buyer_fields['x_lastname1'] = nn[1]

                        if (len(nn)==3):
                            meli_buyer_fields['x_name1'] = nn[0]
                            meli_buyer_fields['x_name2'] = nn[1]
                            meli_buyer_fields['x_lastname1'] = nn[2]

                        if (len(nn)==4):
                            meli_buyer_fields['x_name1'] = nn[0]
                            meli_buyer_fields['x_name2'] = nn[1]
                            meli_buyer_fields['x_lastname1'] = nn[2]
                            meli_buyer_fields['x_lastname2'] = nn[3]

                if ( ('doc_type' in Buyer['billing_info']) and ('l10n_latam_identification_type_id' in self.env['res.partner']._fields ) and ('l10n_co_document_code' in self.env['l10n_latam.identification.type']._fields) ):
                    if (Buyer['billing_info']['doc_type']=="CC" or Buyer['billing_info']['doc_type']=="C.C."):
                        #national_citizen_id
                        meli_buyer_fields['l10n_latam_identification_type_id'] = self.env['l10n_latam.identification.type'].search([('l10n_co_document_code','=','national_citizen_id'),('country_id','=',company.country_id.id)],limit=1).id
                    if (Buyer['billing_info']['doc_type']=="CE" or Buyer['billing_info']['doc_type']=="C.E."):
                        #foreign_id_card
                        meli_buyer_fields['l10n_latam_identification_type_id'] = self.env['l10n_latam.identification.type'].search([('l10n_co_document_code','=','foreign_id_card'),('country_id','=',company.country_id.id)],limit=1).id
                    if (Buyer['billing_info']['doc_type']=="NIT" or Buyer['billing_info']['doc_type']=="N.I.T." or Buyer['billing_info']['doc_type']=="RUT"):
                        #rut
                        meli_buyer_fields['l10n_latam_identification_type_id'] = self.env['l10n_latam.identification.type'].search([('l10n_co_document_code','=','rut'),('country_id','=',company.country_id.id)],limit=1).id


                #Uruguay 13.0
                if ("tipodocumento_ids" in self.env['res.partner']._fields):

                    #OTROS
                    sibra_ci = self.env['sibra_addon_fe.tipodocumento'].search([('codigo','=',4)],limit=1)

                    if (Buyer['billing_info']['doc_type']=="CI"):

                        sibra_ci = self.env['sibra_addon_fe.tipodocumento'].search([('codigo','=',3)],limit=1)
                        if sibra_ci:
                            meli_buyer_fields['tipodocumento_ids'] = sibra_ci.id

                    elif (Buyer['billing_info']['doc_type']=="RUT"):

                        sibra_ci = self.env['sibra_addon_fe.tipodocumento'].search([('codigo','=',2)],limit=1)
                        if sibra_ci:
                            meli_buyer_fields['tipodocumento_ids'] = sibra_ci.id

                    else:
                        if sibra_ci:
                            meli_buyer_fields['tipodocumento_ids'] = sibra_ci.id

                    if ("documento" in self.env['res.partner']._fields and Buyer['billing_info']['doc_number']):
                        meli_buyer_fields['documento'] = Buyer['billing_info']['doc_number']

                    if ("property_payment_term_id" in self.env['res.partner']._fields) and config.mercadolibre_payment_term:
                        meli_buyer_fields['property_payment_term_id'] = config.mercadolibre_payment_term and config.mercadolibre_payment_term.id

                # ============================================================
                # BRASIL - CPF / CNPJ
                # MercadoLibre envia doc_type = "CPF" ou "CNPJ" en billing_info.
                # Odoo localizacion Brasil (l10n_br) usa:
                #   - cnpj_cpf  (campo propio del modulo l10n_br)
                #   - l10n_latam_identification_type_id (l10n_latam standard)
                #   - vat (fallback generico)
                # ============================================================
                if company.country_id.code == "BR" and 'doc_type' in Buyer['billing_info']:
                    _br_doc_type   = Buyer['billing_info'].get('doc_type', '') or ''
                    _br_doc_number = Buyer['billing_info'].get('doc_number', '') or ''
                    _logger.info("BR_BLOCK: doc_type=%s doc_number=%s", _br_doc_type, _br_doc_number)

                    if _br_doc_number:
                        # 1) Campo cnpj_cpf propio de l10n_br
                        if 'cnpj_cpf' in self.env['res.partner']._fields:
                            meli_buyer_fields['cnpj_cpf'] = _br_doc_number
                            _logger.info("BR_BLOCK: cnpj_cpf=%s", _br_doc_number)
                        else:
                            # Fallback: campo vat generico
                            meli_buyer_fields['vat'] = _br_doc_number
                            _logger.info("BR_BLOCK: vat (fallback)=%s", _br_doc_number)

                        # 2) Tipo de identificacion l10n_latam (Odoo 17+/19)
                        if 'l10n_latam_identification_type_id' in self.env['res.partner']._fields:
                            _br_latam_type = self.env['l10n_latam.identification.type'].search([
                                ('country_id', '=', company.country_id.id),
                                ('name', 'ilike', _br_doc_type),
                            ], limit=1)
                            if not _br_latam_type:
                                _br_latam_type = self.env['l10n_latam.identification.type'].search([
                                    ('name', 'ilike', _br_doc_type),
                                ], limit=1)
                            if _br_latam_type:
                                meli_buyer_fields['l10n_latam_identification_type_id'] = _br_latam_type.id
                                _logger.info("BR_BLOCK: l10n_latam_identification_type_id=%s (%s)", _br_latam_type.id, _br_latam_type.name)
                            else:
                                _logger.warning("BR_BLOCK: l10n_latam.identification.type nao encontrado para doc_type=%s", _br_doc_type)

                    # 3) Tipo de empresa: CNPJ = empresa, CPF = pessoa fisica
                    if _br_doc_type.upper() == 'CNPJ':
                        meli_buyer_fields['company_type'] = 'company'
                        _logger.info("BR_BLOCK: company_type=company (CNPJ)")
                    elif _br_doc_type.upper() == 'CPF':
                        meli_buyer_fields['company_type'] = 'person'
                        _logger.info("BR_BLOCK: company_type=person (CPF)")

            # ================================================================
            # ARQUITECTURA DE CONTACTOS:
            # - Contacto PADRE: identidad del buyer MeLi (nombre MeLi, phone, meli_buyer_id)
            #   No se modifican nombre ni datos fiscales una vez creado.
            # - Contacto HIJO (type=invoice): datos de facturación (nombre legal,
            #   VAT, tipo doc, posición fiscal, dirección fiscal).
            #   Uno por cada VAT único bajo el mismo padre. Se crea desde la primera compra.
            # ================================================================

            # --- Separar datos fiscales/facturación del contacto principal ---
            BILLING_ONLY_FIELDS = {
                'vat', 'main_id_category_id', 'main_id_number',
                'afip_responsability_type_id',
                'l10n_latam_identification_type_id', 'l10n_ar_afip_responsibility_type_id',
                'partner_document_type_id', 'property_account_position_id',
                'l10n_cl_sii_taxpayer_type', 'document_type_id', 'document_number',
                'es_mipyme', 'activity_description', 'city_id', 'dte_email', 'giro',
                'l10n_co_document_type', 'l10n_co_document_typee',
                'fiscal_responsibility_ids', 'fiscal_responsability_ids',
                'responsabilidad_fiscal_fe',
                'tribute_id', 'tipodocumento_ids', 'documento',
                'property_payment_term_id', 'company_type',
                'xidentification',
                'x_name1', 'x_name2', 'x_lastname1', 'x_lastname2', 'x_pn_retri',
                # Brasil
                'cnpj_cpf',
            }

            billing_child_fields = {}
            for _bf in list(meli_buyer_fields.keys()):
                # fe_* = todos los campos de facturación electrónica (Colombia)
                if _bf in BILLING_ONLY_FIELDS or _bf.startswith('fe_'):
                    billing_child_fields[_bf] = meli_buyer_fields.pop(_bf)
            billing_child_fields['name'] = billing_full_name
            _logger.info("BILLING_SPLIT: billing_child_fields=%s | buyer_fields_remaining=%s",
                         list(billing_child_fields.keys()), list(meli_buyer_fields.keys()))

            # Dirección de facturación (va al contacto hijo)
            if ("billing_info_street_name" in buyer_fields and buyer_fields["billing_info_street_name"]):
                billing_child_fields.update({
                    'street': self.street(Receiver, Buyer),
                    'city': self.city(Receiver, Buyer),
                    'country_id': self.country(Receiver, Buyer),
                    'state_id': self.state(self.country(Receiver, Buyer), Receiver, Buyer),
                    'zip': self.zip_code(Receiver, Buyer),
                })

            if ("fe_regimen_fiscal" in self.env['res.partner']._fields):
                billing_child_fields['fe_regimen_fiscal'] = '49'

            # --- Parsear lista de VATs genéricos (ej: XAXX010101000 en MX) ---
            # Defaults por país cuando el campo está vacío
            _GENERIC_VATS_DEFAULTS = {
                'MX': 'XAXX010101000,XEXX010101000',  # Público en general / Extranjeros
            }
            _generic_vats_raw = (
                config.mercadolibre_generic_vats
                if 'mercadolibre_generic_vats' in config._fields and config.mercadolibre_generic_vats
                else ''
            )
            if not _generic_vats_raw and company and company.country_id:
                _generic_vats_raw = _GENERIC_VATS_DEFAULTS.get(company.country_id.code, '')
            _generic_vats = [v.strip().upper() for v in _generic_vats_raw.split(',') if v.strip()]

            # --- Buscar contacto principal (padre) por meli_buyer_id ---
            partner_invoice_id = None
            partner_invoice_meli_order_id = str(order_json['pack_id'] or order_json['id'])
            # Buyer['id'] llega como ENTERO del JSON de Meli, pero meli_buyer_id es Char y se
            # guarda como string. Hay que castear a str() o el search (varchar = int) no matchea
            # → no encuentra el partner existente → intenta crear → choca la constraint única.
            _buyer_id_str = str(buyer_fields['buyer_id'])
            # NOTA: usamos with_user(1) (SUPERUSER) en las búsquedas de partner para bypasear
            # overrides de search() en módulos de terceros (ej: exe_restriction_user_16) que
            # filtran por user_id del cron y bloquean la visibilidad de partners sin vendedor.
            # sudo() NO es suficiente: solo bypasea ir.rules, pero NO los overrides de search()
            # que usan has_group() sobre self.env.user (que sigue siendo uid=29 con sudo=True).
            # with_user(1) cambia uid→1, haciendo que has_group() devuelva False y el override
            # no aplique. El cron no requiere ir.rules propias para buscar sus propios partners.
            respartner_su = respartner_obj.with_user(1)
            partner_id = respartner_su.search([('meli_buyer_id', '=', _buyer_id_str)] + company_only_domain, limit=1)
            if not partner_id:
                partner_id = respartner_su.search([('meli_buyer_id', '=', _buyer_id_str)] + company_none_domain, limit=1)

            # Fallback: buscar por VAT si no se encontró por meli_buyer_id
            # (no buscar por VATs genéricos — matchearían miles de contactos)
            _fallback_vat = buyer_fields.get('billing_info_doc_number', '')
            _is_generic_vat = _generic_vats and _fallback_vat and _fallback_vat.strip().upper() in _generic_vats
            if (search_partner_vat_match and (not partner_id and _fallback_vat and not _is_generic_vat)):
                partner_id = respartner_su.search([('vat', '=', _fallback_vat)] + company_only_domain, limit=1)
                if partner_id:
                    partner_id.meli_buyer_id = buyer_fields['buyer_id']
                else:
                    partner_id = respartner_su.search([('vat', '=', _fallback_vat)] + company_none_domain, limit=1)

            # --- Crear contacto principal si no existe (solo datos de identidad MeLi) ---
            if not partner_id:
                try:
                    if config.mercadolibre_cron_get_orders_shipment_client:
                        # savepoint: si el INSERT choca la constraint única
                        # (meli_buyer_id, active, company_id), se revierte SOLO este create
                        # y la transacción del batch sigue sana (no se abortan las demás órdenes).
                        with self.env.cr.savepoint():
                            partner_id = respartner_obj.create(meli_buyer_fields)
                            partner_id.flush_recordset()  # forzar el INSERT dentro del savepoint
                        _logger.info("Contacto principal creado: %s (meli_buyer_id: %s)", partner_id.name, buyer_fields['buyer_id'])
                except Exception as e:
                    _logger.info("orders_update_order > Error creando Partner: " + str(e))
                    _logger.error(e, exc_info=True)
                    # Self-heal (red de seguridad): el create chocó la constraint → el partner
                    # YA existe. Se reusa con with_user(1) + active_test=False para bypasear
                    # tanto ir.rules como overrides de search() de módulos de terceros.
                    partner_id = respartner_su.with_context(active_test=False).search(
                        [('meli_buyer_id', '=', _buyer_id_str)], limit=1)
                    if partner_id:
                        _logger.info("orders_update_order > Partner existente reusado (su) tras colisión meli_buyer_id=%s: %s",
                                     buyer_fields['buyer_id'], partner_id.name)
                    else:
                        _logger.warning("orders_update_order > colisión meli_buyer_id=%s pero el partner no aparece ni con su (revisar)",
                                        buyer_fields['buyer_id'])
            elif ("meli_update_forbidden" in partner_id._fields and not partner_id.meli_update_forbidden):
                # Actualizar contacto principal: solo campos de identidad, NO nombre ni datos fiscales
                parent_update = {}
                if not partner_id.country_id:
                    parent_update['country_id'] = self.country(Receiver, Buyer)
                if not partner_id.state_id:
                    parent_update['state_id'] = self.state(self.country(Receiver, Buyer), Receiver, Buyer)
                if not partner_id.street or partner_id.street == "no street":
                    parent_update['street'] = self.street(Receiver, Buyer)
                if not partner_id.city or partner_id.city == "":
                    parent_update['city'] = self.city(Receiver, Buyer)
                if not partner_id.phone and 'phone' in meli_buyer_fields and meli_buyer_fields['phone']:
                    parent_update['phone'] = meli_buyer_fields['phone']
                if partner_id.email and (partner_id.email == buyer_fields.get("email", "") or "mercadolibre.com" in str(partner_id.email)):
                    parent_update['email'] = ''

                if parent_update:
                    _logger.info("Actualizando contacto principal (sin datos fiscales): %s", str(parent_update))
                    try:
                        partner_id.write(parent_update)
                        MeliCommit(self)
                    except builtins.Exception as e:
                        _logger.info("orders_update_order > Error actualizando Partner: " + str(e))
                        _logger.error(e, exc_info=True)
                        if order:
                            meli_message_post(order, "Error actualizando Partner: " + str(e), config=config)

            # --- Buscar/crear contacto de facturación (entidad fiscal) ---
            # Modo 3: contacto independiente (sin parent_id), un CUIT = un contacto.
            # Varios buyers pueden compartir la misma entidad fiscal.
            #
            # Excepción: VATs genéricos (ej: XAXX010101000 en MX) se asignan
            # al buyer directamente — no generan entidad fiscal independiente.
            _logger.debug("Billing fields: vat=%s keys=%s billing_info_keys=%s",
                         billing_child_fields.get('vat', 'NO_VAT'),
                         list(billing_child_fields.keys()),
                         list(Buyer.get('billing_info', {}).keys()) if Buyer else 'NO_BUYER')

            # --- Deduplicación: si el nombre de facturación es igual al del buyer
            # (difieren solo en mayúsculas/acentos), poner los datos fiscales
            # directamente en el contacto principal y evitar crear un hijo duplicado.
            _skip_billing_child = False
            if partner_id and billing_child_fields.get('vat'):
                _skip_same_name = (
                    'mercadolibre_skip_same_name_billing_contact' in config._fields
                    and config.mercadolibre_skip_same_name_billing_contact
                )
                # ESTRATEGIA B: forzar los datos fiscales al contacto principal SIEMPRE
                # (aunque el nickname del buyer difiera de la razón social). El dato de
                # facturación (razón social + DOC) es el autoritativo y va al principal,
                # corrigiendo el nombre al legal. Opt-in por cuenta (B2B/multi-CUIT: False).
                _force_on_main = (
                    'mercadolibre_billing_force_on_main' in config._fields
                    and config.mercadolibre_billing_force_on_main
                )
                if _skip_same_name or _force_on_main:
                    import unicodedata, re as _re
                    def _norm(s):
                        s = (s or '').lower().strip()
                        s = unicodedata.normalize('NFD', s)
                        s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
                        return _re.sub(r'\s+', ' ', s)
                    _buyer_norm = _norm(partner_id.name)
                    _billing_norm = _norm(billing_full_name)
                    if _billing_norm and (_force_on_main or (_buyer_norm and _buyer_norm == _billing_norm)):
                        _logger.info(
                            "BILLING_DEDUP: nombre buyer '%s' == billing '%s' — "
                            "datos fiscales al contacto principal, sin crear hijo.",
                            partner_id.name, billing_full_name
                        )
                        _skip_billing_child = True
                        # Actualizar nombre del buyer al nombre legal (title-cased)
                        if partner_id.name != billing_full_name:
                            try:
                                partner_id.write({'name': billing_full_name})
                            except Exception as _e:
                                _logger.warning("BILLING_DEDUP: no se pudo actualizar nombre del buyer: %s", _e)
                        # Poner datos fiscales directamente en el contacto principal
                        _FISCAL_PROTECTED_DEDUP = {
                            'l10n_ar_afip_responsibility_type_id',
                            'l10n_latam_identification_type_id',
                            'afip_responsability_type_id',
                            'property_account_position_id',
                            'partner_document_type_id',
                            'vat',
                        }
                        _fiscal_update = {}
                        for k, v in billing_child_fields.items():
                            if k in ('name', 'type', 'meli_buyer_id', 'meli_order_id', 'meli_buyer_partner_id'):
                                continue
                            if (k in _FISCAL_PROTECTED_DEDUP
                                    and k not in _ml_explicit_fiscal_fields
                                    and k in partner_id._fields
                                    and partner_id[k]):
                                continue
                            _fiscal_update[k] = v
                        if _fiscal_update:
                            try:
                                partner_id.write(_fiscal_update)
                            except Exception as _e:
                                _logger.warning("BILLING_DEDUP: no se pudo escribir datos fiscales en buyer: %s", _e)
                        partner_invoice_id = partner_id

            if not _skip_billing_child and partner_id and billing_child_fields.get('vat'):
                billing_vat = billing_child_fields['vat']

                # VAT genérico: asignar al buyer, no crear entidad fiscal
                if _generic_vats and billing_vat.strip().upper() in _generic_vats:
                    _logger.info(
                        "VAT genérico detectado: %s — se asigna al buyer %s, "
                        "sin crear entidad fiscal independiente",
                        billing_vat, partner_id.name,
                    )
                    if not partner_id.vat:
                        try:
                            partner_id.write({'vat': billing_vat})
                        except Exception as e:
                            _logger.warning("Error asignando VAT genérico al buyer: %s", e)
                    partner_invoice_id = None
                    billing_vat = None  # Impedir que el bloque posterior cree entidad fiscal

                # 1) Buscar entidad fiscal por VAT global (un CUIT = un contacto fiscal)
                if billing_vat:
                    partner_invoice_id = respartner_obj.search([
                        ('vat', '=', billing_vat),
                        ('type', '=', 'invoice'),
                        ('company_id', 'in', [company.id, False] if company else [False]),
                    ], limit=1)

                # 2) Fallback legacy: buscar por parent_id + VAT (contactos existentes pre-Modo 3)
                if billing_vat and not partner_invoice_id:
                    partner_invoice_id = respartner_obj.search([
                        ('parent_id', '=', partner_id.id),
                        ('type', '=', 'invoice'),
                        ('vat', '=', billing_vat),
                    ], limit=1)

                # 3) Fallback legacy: buscar por meli_order_id + parent_id
                if billing_vat and not partner_invoice_id:
                    partner_invoice_id = respartner_obj.search([
                        ('meli_order_id', '=', partner_invoice_meli_order_id),
                        ('parent_id', '=', partner_id.id),
                        ('type', '=', 'invoice'),
                    ], limit=1)

                if billing_vat and partner_invoice_id:
                    # Actualizar contacto de facturación existente
                    invoice_update = dict(billing_child_fields)
                    invoice_update.pop('name', None)
                    if ("billing_info_business_name" in buyer_fields and buyer_fields["billing_info_business_name"]):
                        invoice_update['name'] = buyer_fields["billing_info_business_name"]
                    # Vincular al buyer actual si no tiene vínculo
                    if 'meli_buyer_partner_id' in partner_invoice_id._fields and not partner_invoice_id.meli_buyer_partner_id:
                        invoice_update['meli_buyer_partner_id'] = partner_id.id

                    # PROTECCIÓN: no sobreescribir campos fiscales que ya tienen
                    # valor en el contacto existente si ML no los envió explícitamente
                    # en esta corrida (evita que el default CF borre datos fiscales
                    # configurados manualmente por el operador).
                    _FISCAL_PROTECTED = {
                        'l10n_ar_afip_responsibility_type_id',
                        'l10n_latam_identification_type_id',
                        'afip_responsability_type_id',
                        'property_account_position_id',
                        'partner_document_type_id',
                        'vat',
                    }
                    _protected_skipped = []
                    for _fp in _FISCAL_PROTECTED:
                        if (_fp in invoice_update
                                and _fp not in _ml_explicit_fiscal_fields
                                and _fp in partner_invoice_id._fields
                                and partner_invoice_id[_fp]):
                            _protected_skipped.append(_fp)
                            del invoice_update[_fp]
                    if _protected_skipped:
                        _logger.info(
                            "FISCAL_PROTECT: contacto id:%s ya tiene valores para %s "
                            "— no sobreescritos (ML no envió datos explícitos en esta corrida)",
                            partner_invoice_id.id, _protected_skipped)

                    # RESCUE: Si este update no trae l10n_latam_identification_type_id (porque
                    # ML no envió el doc_type en esta orden) Y el contacto existente lo tiene vacío
                    # ("SIN REGISTROS"), intentar inferirlo del VAT para no dejar el campo vacío.
                    _id_type_field = None
                    if 'l10n_latam_identification_type_id' in partner_invoice_id._fields:
                        _id_type_field = 'l10n_latam_identification_type_id'
                    elif 'partner_document_type_id' in partner_invoice_id._fields:
                        _id_type_field = 'partner_document_type_id'
                    if (_id_type_field
                            and _id_type_field not in invoice_update
                            and not partner_invoice_id[_id_type_field]
                            and billing_vat):
                        _vat_digits = ''.join(c for c in billing_vat if c.isdigit())
                        _country_code = (partner_invoice_id.country_id.code
                                         or (company and company.country_id.code)
                                         or '')
                        _inferred_type = None
                        if _country_code == 'AR':
                            if len(_vat_digits) == 11:
                                _inferred_type = self.env['l10n_latam.identification.type'].search(
                                    [('l10n_ar_afip_code', '=', '80')], limit=1
                                ) if 'l10n_ar_afip_code' in self.env['l10n_latam.identification.type']._fields else \
                                self.env['l10n_latam.identification.type'].search(
                                    [('name', 'in', ['CUIT', 'Clave Única de Identificación Tributaria'])], limit=1
                                )
                            elif len(_vat_digits) in (7, 8):
                                _inferred_type = self.env['l10n_latam.identification.type'].search(
                                    [('l10n_ar_afip_code', '=', '96')], limit=1
                                ) if 'l10n_ar_afip_code' in self.env['l10n_latam.identification.type']._fields else \
                                self.env['l10n_latam.identification.type'].search(
                                    [('name', 'in', ['DNI', 'Documento Nacional de Identidad'])], limit=1
                                )
                        if _inferred_type:
                            invoice_update[_id_type_field] = _inferred_type.id
                            _logger.info(
                                "SIN REGISTROS rescue: tipo de doc inferido '%s' (AFIP code=%s) "
                                "desde VAT %s para contacto id:%s '%s'",
                                _inferred_type.name,
                                getattr(_inferred_type, 'l10n_ar_afip_code', '?'),
                                billing_vat, partner_invoice_id.id, partner_invoice_id.display_name
                            )
                        else:
                            _logger.warning(
                                "SIN REGISTROS: no se pudo inferir tipo de documento para VAT %s "
                                "(país: %s, dígitos: %d) en contacto id:%s",
                                billing_vat, _country_code, len(_vat_digits), partner_invoice_id.id
                            )

                    if invoice_update:
                        _logger.info("Actualizando contacto facturación id:%s vat:%s campos:%s",
                                     partner_invoice_id.id, invoice_update.get('vat', '-'), list(invoice_update.keys()))
                        try:
                            partner_invoice_id.write(invoice_update)
                        except ValidationError as ve:
                            bad_vat = invoice_update.pop("vat", None)
                            if bad_vat:
                                try:
                                    partner_invoice_id.write(invoice_update)
                                except Exception as e2:
                                    _logger.error("Error actualizando contacto facturación (sin VAT): %s", str(e2))
                        except Exception as e:
                            _logger.error("Error actualizando contacto de facturación: %s", str(e))
                            _logger.error(e, exc_info=True)
                elif billing_vat:
                    # Crear nueva entidad fiscal (sin parent_id — contacto independiente)
                    try:
                        if config.mercadolibre_cron_get_orders_shipment_client:
                            billing_child_fields.update({
                                'type': 'invoice',
                                'meli_buyer_partner_id': partner_id.id,
                                'meli_buyer_id': None,
                                'meli_order_id': partner_invoice_meli_order_id,
                            })
                            if company and company.id:
                                billing_child_fields['company_id'] = company.id
                            partner_invoice_id = respartner_obj.create(billing_child_fields)
                            _logger.info("Entidad fiscal creada: %s (VAT: %s) vinculada a buyer: %s",
                                         partner_invoice_id.name, billing_vat, partner_id.name)
                    except ValidationError as ve:
                        bad_vat = billing_child_fields.pop("vat", None)
                        if bad_vat:
                            try:
                                partner_invoice_id = respartner_obj.create(billing_child_fields)
                            except Exception as e2:
                                _logger.error("Error creando entidad fiscal (sin VAT): %s", str(e2))
                    except Exception as e:
                        _logger.info("orders_update_order > Error creando entidad fiscal: " + str(e))
                        _logger.error(e, exc_info=True)

            # Verificación post-update: confirmar que vat y tipo de documento se guardaron
            if partner_invoice_id and partner_invoice_id != partner_id:
                partner_invoice_id.invalidate_recordset()
                _saved_vat = partner_invoice_id.vat
                _saved_doc_type = None
                _doc_type_field = None
                _saved_afip_resp = None
                if 'partner_document_type_id' in partner_invoice_id._fields:
                    _saved_doc_type = partner_invoice_id.partner_document_type_id
                    _doc_type_field = 'partner_document_type_id'
                elif 'l10n_latam_identification_type_id' in partner_invoice_id._fields:
                    _saved_doc_type = partner_invoice_id.l10n_latam_identification_type_id
                    _doc_type_field = 'l10n_latam_identification_type_id'
                if 'l10n_ar_afip_responsibility_type_id' in partner_invoice_id._fields:
                    _saved_afip_resp = partner_invoice_id.l10n_ar_afip_responsibility_type_id
                if not _saved_vat or not _saved_doc_type:
                    _logger.warning("POST-CHECK contacto facturación id:%s - vat:%s %s:%s afip_resp:%s - DATOS FISCALES INCOMPLETOS",
                                    partner_invoice_id.id,
                                    _saved_vat or 'FALTA',
                                    _doc_type_field or 'doc_type_field',
                                    (_saved_doc_type.name if _saved_doc_type else 'FALTA'),
                                    (_saved_afip_resp.name if _saved_afip_resp else 'FALTA'))
                else:
                    _logger.info("POST-CHECK contacto facturación id:%s - vat:%s %s:%s afip_resp:%s - OK",
                                 partner_invoice_id.id, _saved_vat,
                                 _doc_type_field, _saved_doc_type.name,
                                 (_saved_afip_resp.name if _saved_afip_resp else 'NO_FIELD'))

            # Safety net SQL: forzar datos fiscales en columnas del billing child
            # vía SQL directo. El override de _commercial_sync_from_company en
            # res_partner.py es el fix de raíz, pero este SQL actúa como red de
            # seguridad para asegurar que los valores persistan tras cr.commit().
            # NOTA: solo se escribe al CHILD, no al parent. Cada billing child
            # tiene datos fiscales propios (un mismo buyer puede facturar con
            # diferentes entidades fiscales por compra).
            if partner_invoice_id and partner_invoice_id != partner_id:
                _fix_fields = []
                _fix_vals = []
                if 'partner_document_type_id' in partner_invoice_id._fields and partner_invoice_id.partner_document_type_id:
                    _fix_fields.append("partner_document_type_id = %s")
                    _fix_vals.append(partner_invoice_id.partner_document_type_id.id)
                elif 'l10n_latam_identification_type_id' in partner_invoice_id._fields and partner_invoice_id.l10n_latam_identification_type_id:
                    _fix_fields.append("l10n_latam_identification_type_id = %s")
                    _fix_vals.append(partner_invoice_id.l10n_latam_identification_type_id.id)
                if partner_invoice_id.vat:
                    _fix_fields.append("vat = %s")
                    _fix_vals.append(partner_invoice_id.vat)
                if 'l10n_ar_afip_responsibility_type_id' in partner_invoice_id._fields and partner_invoice_id.l10n_ar_afip_responsibility_type_id:
                    _fix_fields.append("l10n_ar_afip_responsibility_type_id = %s")
                    _fix_vals.append(partner_invoice_id.l10n_ar_afip_responsibility_type_id.id)
                if _fix_fields:
                    self.env.cr.execute(
                        "UPDATE res_partner SET " + ", ".join(_fix_fields) + " WHERE id = %s",
                        tuple(_fix_vals + [partner_invoice_id.id])
                    )
                    _logger.info("COMMERCIAL_FIELDS_FIX SQL: datos fiscales en billing child id:%s (%s)",
                                 partner_invoice_id.id, ", ".join(_fix_fields))

            # Modo 3: detectar VAT duplicado en buyer y limpiar / avisar
            if partner_invoice_id and partner_invoice_id != partner_id and partner_id.vat:
                billing_vat = partner_invoice_id.vat
                if billing_vat and partner_id.vat == billing_vat:
                    # El buyer tiene el mismo VAT que la entidad fiscal.
                    # En Modo 3 el VAT solo debe estar en la entidad fiscal.
                    # Buscar si hay otros contactos (excluyendo la entidad fiscal
                    # y el buyer) con el mismo VAT que podrían fusionarse.
                    _dup_contacts = respartner_obj.search([
                        ('vat', '=', billing_vat),
                        ('id', 'not in', [partner_invoice_id.id, partner_id.id]),
                    ])

                    if _dup_contacts:
                        _dup_names = ", ".join(["%s (id:%s, type:%s)" % (c.name, c.id, c.type) for c in _dup_contacts[:5]])
                        _logger.warning(
                            "MELI_DUPLICATE_VAT: VAT %s existe en buyer id:%s y en %d contacto(s) adicional(es): %s. "
                            "Considerar fusionar con entidad fiscal id:%s",
                            billing_vat, partner_id.id, len(_dup_contacts), _dup_names, partner_invoice_id.id)
                        if order:
                            order.message_post(
                                body=(
                                    "Contacto fiscal duplicado detectado: VAT %s existe en %d contacto(s) "
                                    "además de la entidad fiscal [%s] (id:%s). "
                                    "Contactos duplicados: %s. "
                                    "Considerar fusionar desde Contactos > Acción > Fusionar contactos."
                                ) % (billing_vat, len(_dup_contacts),
                                     partner_invoice_id.name, partner_invoice_id.id, _dup_names),
                                message_type=order_message_type)

                    # Limpiar VAT del buyer para evitar la advertencia de NIF duplicado.
                    # El VAT pertenece a la entidad fiscal, no al buyer.
                    # PERO: no limpiar si hay hijos sin VAT propio, porque
                    # _commercial_sync_to_children propagaría vat=False y
                    # constraints como kc_l10n_uy.check_vat lo impedirían.
                    _children_without_vat = respartner_obj.search_count([
                        ('parent_id', '=', partner_id.id),
                        ('id', '!=', partner_invoice_id.id),
                        ('vat', 'in', [False, '']),
                    ])
                    if _children_without_vat:
                        _logger.info(
                            "MELI_DUPLICATE_VAT: NO se limpia VAT %s del buyer id:%s porque tiene %d hijo(s) sin VAT propio "
                            "(limpiar causaría error en constraints de terceros)",
                            billing_vat, partner_id.id, _children_without_vat)
                    else:
                        try:
                            with self.env.cr.savepoint():
                                partner_id.write({'vat': False})
                            _logger.info("MELI_DUPLICATE_VAT: limpiado VAT %s del buyer id:%s (ahora solo en entidad fiscal id:%s)",
                                         billing_vat, partner_id.id, partner_invoice_id.id)
                        except Exception as e:
                            _logger.warning("MELI_DUPLICATE_VAT: no se pudo limpiar VAT del buyer id:%s: %s",
                                            partner_id.id, str(e))

            # Si no hay VAT en billing_info, usar contacto principal para facturación
            if not partner_invoice_id:
                partner_invoice_id = partner_id

            # fe_habilitada va al contacto que se usa para facturación
            if partner_invoice_id:
                if ("fe_habilitada" in self.env['res.partner']._fields):
                    try:
                        partner_invoice_id.write({"fe_habilitada": True})
                    except:
                        _logger.error("No se pudo habilitar la Facturacion Electronica para este usuario")

            if order and buyer_id:
                return_id = order.write({'buyer': buyer_id.id})
        else:
            _logger.error("Buyer not fetched!")

        if (not partner_id):
            if config.mercadolibre_cron_get_orders_shipment_client:
                _logger.error("No partner founded or created for ML Order" )
                return {'error': 'No partner founded or created for ML Order' }

        original_contact_partner_id = partner_id
        if original_contact_partner_id:
            #fix Just, fijar la lista de precio predeterminada de cada cliente
            try:
                with self.env.cr.savepoint():
                    original_contact_partner_id.property_product_pricelist = (config and config.mercadolibre_pricelist)
            except Exception as e:
                _logger.warning('Could not set pricelist on partner %s (id:%s): %s',
                                original_contact_partner_id.name, original_contact_partner_id.id, e)


        if (original_contact_partner_id):
            if config.mercadolibre_cron_get_orders_shipment_client:
                partner_shipping_id = self.env["mercadolibre.shipment"].partner_delivery_id( partner_id=original_contact_partner_id,
                                                                                            Receiver=Receiver,
                                                                                            config=config)

        #process base order fields
        #asignar datos de invoicing predeterminado....(mexico)
        mercadolibre_contact_partner_id = ("mercadolibre_contact_partner" in config._fields and config.mercadolibre_contact_partner)
        if (mercadolibre_contact_partner_id):
            mercadolibre_contact_partner_id.meli_update_forbidden = True

        mercadolibre_invoice_partner_id = ("mercadolibre_invoice_partner" in config._fields and config.mercadolibre_invoice_partner)
        if (mercadolibre_invoice_partner_id):
            mercadolibre_invoice_partner_id.meli_update_forbidden = True

        mercadolibre_shipping_partner_id = ("mercadolibre_shipping_partner" in config._fields and config.mercadolibre_shipping_partner)
        if (mercadolibre_shipping_partner_id):
            mercadolibre_shipping_partner_id.meli_update_forbidden = True

        partner_id =  mercadolibre_contact_partner_id or partner_id
        partner_invoice_id = mercadolibre_invoice_partner_id or partner_invoice_id
        partner_shipping_id = mercadolibre_shipping_partner_id or partner_shipping_id

        # Unificar los 3 contactos cuando todos comparten el mismo nombre (modo Brasil)
        _merge_flag = ('mercadolibre_merge_same_name_contacts' in config._fields
                       and config.mercadolibre_merge_same_name_contacts)
        if _merge_flag and partner_id and not (sorder and sorder.id):
            import unicodedata as _ud_m, re as _re_m
            def _norm_m(s):
                s = (s or '').lower().strip()
                s = _ud_m.normalize('NFD', s)
                s = ''.join(c for c in s if _ud_m.category(c) != 'Mn')
                return _re_m.sub(r'\s+', ' ', s)
            _pnorm = _norm_m(partner_id.name)
            _inv_diff = partner_invoice_id and partner_invoice_id.id != partner_id.id
            _shp_diff = partner_shipping_id and partner_shipping_id.id != partner_id.id
            _all_names_match = True
            if _inv_diff and _norm_m(partner_invoice_id.name) != _pnorm:
                _all_names_match = False
            if _shp_diff and _norm_m(partner_shipping_id.name) != _pnorm:
                _all_names_match = False
            if _all_names_match and (_inv_diff or _shp_diff):
                _logger.info("merge_same_name_contacts: unificando contactos para '%s'", partner_id.name)
                if _inv_diff:
                    # Before reassigning, copy fiscal fields from billing child
                    # to parent — otherwise the parent stays without the DNI /
                    # Consumidor Final / vat that the billing child had, and
                    # AFIP rejects the invoice for missing fiscal data.
                    _fiscal_fields_to_copy = {}
                    _src = partner_invoice_id  # the billing child being merged away
                    # ALWAYS copy doc type and AFIP responsibility from the
                    # billing child — it has the correct values straight from
                    # ML's billing_info. The parent may have defaults (e.g.
                    # "IVA" instead of "DNI") or stale values from Odoo's
                    # _commercial_sync which propagates `vat` but NOT
                    # `l10n_latam_identification_type_id`.
                    if _src.vat:
                        _fiscal_fields_to_copy['vat'] = _src.vat
                    if ('l10n_latam_identification_type_id' in _src._fields
                            and _src.l10n_latam_identification_type_id):
                        _fiscal_fields_to_copy['l10n_latam_identification_type_id'] = _src.l10n_latam_identification_type_id.id
                    if ('l10n_ar_afip_responsibility_type_id' in _src._fields
                            and _src.l10n_ar_afip_responsibility_type_id):
                        _fiscal_fields_to_copy['l10n_ar_afip_responsibility_type_id'] = _src.l10n_ar_afip_responsibility_type_id.id
                    if ('property_account_position_id' in _src._fields
                            and _src.property_account_position_id
                            and not partner_id.property_account_position_id):
                        _fiscal_fields_to_copy['property_account_position_id'] = _src.property_account_position_id.id
                    if _fiscal_fields_to_copy:
                        try:
                            # Write identification type FIRST, then VAT in a
                            # separate call. Odoo's l10n_ar VAT constraint
                            # validates the number against the CURRENT doc type
                            # on the record — if we write both in one call, the
                            # constraint may fire before the type changes from
                            # CUIT (default) to DNI, rejecting a valid DNI
                            # number with "el número CUIT no es válido".
                            _type_fields = {}
                            _vat_fields = {}
                            for k, v in _fiscal_fields_to_copy.items():
                                if k == 'vat':
                                    _vat_fields[k] = v
                                else:
                                    _type_fields[k] = v
                            if _type_fields:
                                partner_id.sudo().write(_type_fields)
                            if _vat_fields:
                                partner_id.sudo().write(_vat_fields)
                            _logger.info(
                                "merge_same_name_contacts: copied fiscal fields from billing child id:%s to parent id:%s: %s",
                                _src.id, partner_id.id, list(_fiscal_fields_to_copy.keys()),
                            )
                        except Exception as _merge_err:
                            _logger.warning(
                                "merge_same_name_contacts: could not copy fiscal fields from id:%s to id:%s: %s",
                                _src.id, partner_id.id, _merge_err,
                            )
                    partner_invoice_id = partner_id
                if _shp_diff:
                    partner_shipping_id = partner_id

        meli_order_fields = self.prepare_sale_order_vals( order_json=order_json, meli=meli, config=config, sale_order=sorder )
        meli_order_fields.update({'pricelist_id': plistid.id })

        if partner_id:
            partner_already_set = (sorder and sorder.partner_id and sorder.partner_id.id == partner_id.id)
            if not partner_already_set:
                meli_order_fields.update({'partner_id': (partner_id and partner_id.id)})

        if partner_invoice_id:
            partner_invoice_already_set = (sorder and sorder.partner_invoice_id and sorder.partner_invoice_id.id == partner_invoice_id.id)
            if not partner_invoice_already_set:
                meli_order_fields.update({'partner_invoice_id': (partner_invoice_id and partner_invoice_id.id)})

            # Blue Orange / CER: set fiscal_position_id from billing partner's property_account_position_id
            # This ensures the sale order has the correct fiscal position for invoice document type selection.
            # Gateado por config: si mercadolibre_set_fiscal_position=False, la venta queda con
            # posición fiscal EN BLANCO (no la fuerza el conector).
            _set_fp = ('mercadolibre_set_fiscal_position' not in config._fields
                       or config.mercadolibre_set_fiscal_position)
            if _set_fp:
                if 'property_account_position_id' in partner_invoice_id._fields and partner_invoice_id.property_account_position_id:
                    meli_order_fields['fiscal_position_id'] = partner_invoice_id.property_account_position_id.id
            else:
                meli_order_fields['fiscal_position_id'] = False

        if partner_shipping_id:
            shipping_partner_already_set = (sorder and sorder.partner_shipping_id and sorder.partner_shipping_id.id == partner_shipping_id.id)
            update_shipping = not sorder or (sorder and not sorder.partner_shipping_id)
            update_shipping = update_shipping or not shipping_partner_already_set
            if (update_shipping):
                meli_order_fields['partner_shipping_id'] = partner_shipping_id.id

        if ("pack_id" in order_json and order_json["pack_id"]):
            meli_order_fields['name'] = "ML %s" % ( str(order_json["pack_id"]) )
            #meli_order_fields['pack_id'] = order_json["pack_id"]

        if ('account.payment.term' in self.env):
            inmediate_or_not = ('mercadolibre_payment_term' in config._fields and config.mercadolibre_payment_term) or ('mercadolibre_payment_term' in company._fields and company.mercadolibre_payment_term) or None
            if inmediate_or_not:
                meli_order_fields["payment_term_id"] = inmediate_or_not.id

        if ("shipping" in order_json and order_json["shipping"]):
            order_fields['shipping'] = self.pretty_json( id, order_json["shipping"] )
            meli_order_fields['meli_shipping'] = self.pretty_json( id, order_json["shipping"] )

            if ("logistic_type" in order_json["shipping"]):
                order_fields['shipment_logistic_type'] = order_json["shipping"]["logistic_type"]
                meli_order_fields["meli_shipment_logistic_type"] = order_json["shipping"]["logistic_type"]
                meli_order_fields["meli_shipment_free"] = order_json["shipping"]["free_shipping"]

            if ("cost" in order_json["shipping"]):
                order_fields["shipping_cost"] = float(order_json["shipping"]["cost"])
                meli_order_fields["meli_shipping_cost"] = float(order_json["shipping"]["cost"])

            if ("id" in order_json["shipping"] and order_json["shipping"]["id"]):
                order_fields['shipping_id'] = order_json["shipping"]["id"]
                meli_order_fields['meli_shipping_id'] = order_json["shipping"]["id"]

                # Agregar ID envío o nro seguimiento al nombre de la venta (opcional)
                _include_tracking = (
                    'mercadolibre_so_name_tracking' in config._fields
                    and config.mercadolibre_so_name_tracking
                )
                if _include_tracking:
                    shipping_label = str(order_json["shipping"]["id"])
                    if order and order.shipment and order.shipment.tracking_number:
                        shipping_label = str(order.shipment.tracking_number)
                    current_name = meli_order_fields.get('name', '')
                    if current_name:
                        meli_order_fields['name'] = current_name + " | " + shipping_label

        #create or update order
        if (order and order.id):
            #_logger.info("Updating order: %s" % (order.id))
            order.write( order_fields )
        else:
            #_logger.info(Adding new order: " )
            #_logger.info(order_fields)
            order = order_obj.create( (order_fields))

        # Fetch discount details from ML API to determine seller-funded portion
        if order and order.coupon_amount > 0:
            order._fetch_order_discounts(meli=meli)
            meli_order_fields['meli_discount_seller_amount'] = order.discount_seller_amount or 0.0

        if (sorder and sorder.id):
            #_logger.info("Updating sale.order: %s" % (sorder.id))
            if (sorder.state in ['sale','done']) or ("locked" in sorder._fields and sorder.locked):
                del meli_order_fields["pricelist_id"]
            #_logger.info(meli_order_fields)
            sorder.meli_fix_team( meli=meli, config=config )
            sorder.write( meli_order_fields )
            sorder.meli_fix_team( meli=meli, config=config )
        else:
            #_logger.info(meli_order_fields)
            #user
            if (config.mercadolibre_seller_user):
                meli_order_fields["user_id"] = config.mercadolibre_seller_user.id
            if (config.mercadolibre_seller_team):
                meli_order_fields["team_id"] = config.mercadolibre_seller_team.id

            if 'pack_order' in order_json["tags"] and order and order.shipping_id:
                #_logger.info("Pack Order, dont create sale.order, leave it to mercadolibre.shipment")
                if not order.sale_order:
                    meli_message_post(order, "Pack Order, dont create sale.order, leave it to mercadolibre.shipment", config=config)
            elif not meli_order_fields.get('partner_id'):
                # SAFETY GUARD: sale.order.partner_id is NOT NULL en la BD. Si
                # llegamos aca sin partner_id, llamar a create() levanta
                # psycopg2 NotNullViolation y deja la transaccion abortada,
                # provocando cascada de errores "current transaction is aborted"
                # en los siguientes pedidos del mismo batch.
                #
                # Causas tipicas de partner_id vacio:
                #   - config.mercadolibre_cron_get_orders_shipment_client = False
                #     (no se importa el cliente) y ademas mercadolibre_contact_partner
                #     no esta configurado como fallback.
                #   - Buyer sin meli_buyer_id/VAT valido y la busqueda no matcheo.
                #   - Error silencioso al crear res.partner mas arriba.
                _logger.error(
                    "Skipping sale.order create for ML order %s: partner_id is missing. "
                    "Revisar 'Importar clientes' (mercadolibre_cron_get_orders_shipment_client) "
                    "y/o el 'Contacto para MercadoLibre' (mercadolibre_contact_partner) en la configuracion.",
                    order_json.get('id', '?'))
                if order:
                    meli_message_post(
                        order,
                        "No se creo sale.order: falta partner_id del comprador. "
                        "Activar 'Importar clientes' o configurar un 'Contacto para MercadoLibre' "
                        "en la configuracion de la cuenta MeLi.",
                        config=config)
            else:
                # Sanitize vals for compatibility with auditlog (copy.deepcopy)
                safe_meli_fields = {}
                for k, v in meli_order_fields.items():
                    if hasattr(v, '_ids'):
                        safe_meli_fields[k] = v.id if len(v) == 1 else v.ids
                    else:
                        safe_meli_fields[k] = v
                sorder = saleorder_obj.create(safe_meli_fields)
                if sorder:
                    sorder.meli_fix_team( meli=meli, config=config )
                    if order:
                        meli_message_post(order, "Sale order created!", config=config)


        #check error
        if not order:
            _logger.error("Error adding mercadolibre.order. " )
            return {'error': 'Error adding mercadolibre.order' }

        #check error
        if not sorder:
            _logger.warning("Warning adding sale.order. Normally a pack order." )
            # Pack sub-order: meli_order_fields was not written to any SO.
            # If we resolved a billing child different from the buyer parent,
            # propagate partner_invoice_id to the pack SO so meli_create_invoice
            # finds the billing child (with fiscal data) instead of the parent.
            if order and order.sale_order and partner_invoice_id and partner_id and partner_invoice_id.id != partner_id.id:
                _pack_so = order.sale_order
                if not _pack_so.partner_invoice_id or _pack_so.partner_invoice_id.id != partner_invoice_id.id:
                    try:
                        _pack_so.write({'partner_invoice_id': partner_invoice_id.id})
                        _logger.info("Pack sub-order: actualizado partner_invoice_id en SO id:%s -> billing child id:%s (%s)",
                                     _pack_so.id, partner_invoice_id.id, partner_invoice_id.name)
                    except Exception as _e:
                        _logger.warning("Pack sub-order: no se pudo actualizar partner_invoice_id en SO id:%s: %s",
                                        _pack_so.id, _e)
        else:
            #assign mercadolibre.order to sale.order (its only one product)
            sorder.meli_orders = [(6, 0, [order.id])]
            order.sale_order = sorder
            #return {'error': 'Error adding sale.order' }

        #update internal fields (items, payments, buyers)
        if 'order_items' in order_json:
            items = order_json['order_items']
            #_logger.info( items )
            cn = 0
            for Item in items:
                cn = cn + 1
                #_logger.info(cn)
                #_logger.info(Item )
                post_related_obj = ''
                product_related_obj = ''
                product_related_obj_id = False

                #prepare for iva, catalogs, etc...
                order_item_iva = ""
                response3 = meli.get("/items/"+str(Item['item']['id']), {'access_token':meli.access_token, 'include_attributes': 'all'})
                rjson3 = response3 and response3.json()
                if rjson3:
                    #check IVA and impuesto interno:
                    #order_item_iva = "21 %" or "10 %"                    
                    order_item_iva = self.fetchIVA( meli_id=str(Item['item']['id']),
                                                    meli=meli,
                                                    config=config,
                                                    rjson=rjson3 )


                post_related = posting_obj.search([
                                                ('meli_id','=',Item['item']['id']),
                                                ('meli_variation_id','=',Item['item']['variation_id'])
                                                ],limit=1)
                if (post_related):
                    pass;
                    #_logger.info("order post related by meli_id:"+str(post_related))
                else:
                    #create post!
                    posting_fields = {
                        'posting_date': str(datetime.now()),
                        'meli_id': Item['item']['id'],
                        'meli_variation_id': Item['item']['variation_id'],
                        'name': 'Order: ' + Item['item']['title']
                    }

                    post_related = self.env['mercadolibre.posting'].create((posting_fields))

                if len(post_related)==1:
                    post_related_obj = post_related
                else:
                    error =  { 'error': 'No post related or too much posts related, exiting '+str(post_related)}
                    _logger.error( str(error) )
                    return error

                product_related = order.search_meli_product( meli=meli, meli_item=Item['item'], config=config )
                #_logger.info(1st attempt: "+str(product_related)+" Item: "+str(Item["item"]) )
                if ( ( (not product_related) or len(product_related)==0 ) and ('seller_custom_field' in Item['item'] or 'seller_sku' in Item['item'])):
                    #_logger.info(2nd attempt: "+str(Item["item"]) )
                    #1ST attempt "seller_sku" or "seller_custom_field"
                    seller_sku = ('seller_sku' in Item['item'] and Item['item']['seller_sku']) or ('seller_custom_field' in Item['item'] and Item['item']['seller_custom_field'])
                    if (seller_sku):
                        product_related = product_obj.search([('default_code','=ilike',seller_sku)]
                                                              +company_domain)
                    #2ND attempt only old "seller_custom_field"
                    if (not product_related and 'seller_custom_field' in Item['item']):
                        seller_sku = ('seller_custom_field' in Item['item'] and Item['item']['seller_custom_field'])
                    if (seller_sku):
                        product_related = product_obj.search([('default_code','=ilike',seller_sku)]
                                                                +company_domain)
                    else:
                        seller_sku = ('seller_sku' in Item['item'] and Item['item']['seller_sku']) or ('seller_custom_field' in Item['item'] and Item['item']['seller_custom_field'])


                    #TODO: 3RD attempt using barcode
                    #if (not product_related):
                    #   search using item attributes GTIN and SELLER_SKU
                    #_logger.info(2nd attempt: "+str(Item["item"]) + " seller_sku:"+str(seller_sku))

                    if (len(product_related)):
                        #_logger.info(order product related by seller_custom_field and default_code:"+str(seller_sku) )

                        if (len(product_related)>1):
                            product_related = product_related[0]

                        if (not product_related.meli_id and config.mercadolibre_create_product_from_order):
                            prod_fields = {
                                'meli_id': Item['item']['id'],
                                'meli_pub': True,
                            }
                            product_related.sudo().write((prod_fields))  # bind meli_id con privilegios (cron Vendedor ML sin grupo productos)
                            if (product_related.product_tmpl_id):
                                product_related.product_tmpl_id.meli_pub = True
                            product_related.product_meli_get_product()
                            #if (seller_sku):
                            #    prod_fields['default_code'] = seller_sku
                    else:
                        combination = []
                        if ('variation_id' in Item['item'] and Item['item']['variation_id'] ):
                            combination = [( 'meli_id_variation','=',Item['item']['variation_id'])]
                        product_related = product_obj.search([('meli_id','=',Item['item']['id'])]
                                                              +company_domain
                                                              +combination)
                        if (product_related and len(product_related)):
                            #_logger.info(Product founded:"+str(Item['item']['id']))
                            pass;
                        else:
                            #optional, get product
                            productcreated = None
                            product_related = None

                            try:
                                if rjson3 and 'variations' in rjson3['variations'] and len(rjson3['variations'])>0:
                                    if len(rjson3['variations'])==1:
                                        #only 1, usually added variation by ML
                                        product_related = product_obj.search([('meli_id','=', Item['item']['id'])]
                                                                              +company_domain, order='id asc',limit=1)
                                        if (product_related):
                                            productcreated = product_related

                                    if len(rjson3['variations'])>1:
                                        #check missings
                                        product_related = product_obj.search([('meli_id','=', Item['item']['id'])]
                                                                             +company_domain, order='id asc')
                                        if product_related and len(product_related)>=1:
                                            return {'error': 'variations id missing for :'+str(Item['item']['id'])}

                                prod_fields = {
                                    'name': rjson3['title'].encode("utf-8"),
                                    'description': rjson3['title'].encode("utf-8"),
                                    'meli_id': rjson3['id'],
                                    'meli_pub': True,
                                }
                                prod_fields.update(ProductType())
                                if (seller_sku):
                                    prod_fields['default_code'] = seller_sku
                                #prod_fields['default_code'] = rjson3['id']
                                #productcreated = False
                                if seller_sku and config.mercadolibre_create_product_from_order and not productcreated:
                                    # sudo: crear el producto on-the-fly al importar una orden es una INTEGRACIÓN DE SISTEMA, no una acción de usuario. El cron puede correr como el Vendedor ML (with_user) que NO tiene grupo de creación de productos → sin sudo lanza AccessError (product.template/product.product). Gate de negocio: config.mercadolibre_create_product_from_order.
                                    productcreated = self.env['product.product'].sudo().create((prod_fields))
                                if (productcreated):
                                    if (productcreated.product_tmpl_id):
                                        productcreated.product_tmpl_id.meli_pub = True
                                    #_logger.info( "product created: " + str(productcreated) + " >> meli_id:" + str(rjson3['id']) + "-" + str( rjson3['title'].encode("utf-8")) )
                                    #pdb.set_trace()
                                    #_logger.info(productcreated)
                                    productcreated.product_meli_get_product()
                                else:
                                    _logger.info( "product couldnt be created or updated")
                                    pass;
                                product_related = productcreated
                            except Exception as e:
                                _logger.info("Error creando producto.")
                                _logger.error(e, exc_info=True)
                                pass;

                        if ('variation_attributes' in Item['item']):
                            #_logger.info(TODO: search by attributes")
                            pass;

                if product_related and len(product_related):
                    if len(product_related)>1:
                        last_p = False
                        for p in product_related:
                            last_p = p
                            if (p.product_tmpl_id.meli_pub_principal_variant):
                                product_related_obj = p.product_tmpl_id.meli_pub_principal_variant
                            if (p.meli_default_stock_product):
                                product_related_obj = p.meli_default_stock_product

                        if (product_related_obj):
                            product_related_obj = product_related_obj
                        else:
                            product_related_obj = last_p
                    else:
                        product_related_obj = product_related

                if (post_related and product_related):
                    #only assign to post if no object is already assigned
                    if ( len(post_related)==1 and not post_related.product_id ):
                        post_related.product_id = product_related

                    if (product_related and product_related.product_tmpl_id):
                        UpdateProductType(product=product_related.product_tmpl_id)

                order_item_fields = {
                    'order_id': order.id,
                    'posting_id': post_related_obj.id,
                    'order_item_id': Item['item']['id'],
                    'order_item_iva': order_item_iva or None,
                    'order_item_variation_id': Item['item']['variation_id'],
                    'order_item_title': Item['item']['title'],
                    'order_item_category_id': Item['item']['category_id'],
                    'unit_price': Item['unit_price'],
                    'quantity': Item['quantity'],
                    'currency_id': Item['currency_id'],
                    'seller_sku': ('seller_sku' in Item['item'] and Item['item']['seller_sku']) or '',
                    'seller_custom_field': ('seller_custom_field' in Item['item'] and Item['item']['seller_custom_field']) or '',
                    'sale_fee': ("sale_fee" in Item and Item["sale_fee"]) or 0.0
                }

                # CAPTURA depósito ML por ítem (surtido multi-almacén): la orden trae el
                # nodo logístico de origen en Item['stock'] = {store_id, node_id}. Se persiste
                # para el ruteo entrante en _meli_get_stock_location_from_mapping (meli_oerp_stock).
                _item_stock = ("stock" in Item and isinstance(Item.get("stock"), dict) and Item["stock"]) or {}
                if ("meli_stock_node_id" in order_items_obj._fields):
                    order_item_fields['meli_stock_node_id'] = _item_stock.get("node_id") or ''
                if ("meli_stock_store_id" in order_items_obj._fields):
                    order_item_fields['meli_stock_store_id'] = _item_stock.get("store_id") or ''

                order.fee_amount = order_item_fields["sale_fee"] or 0.0

                if ("full_unit_price" in Item and "full_unit_price" in order_items_obj._fields):
                    order_item_fields['full_unit_price'] = Item['full_unit_price']

                if (product_related):
                    if (len(product_related)>1):
                        error = { 'error': "Error products duplicated for item:"+str(Item and 'item' in Item and Item['item']) }
                        _logger.error(error)
                        order and meli_message_post(order, error["error"], config=config)
                        #return error
                    else:
                        order_item_fields['product_id'] = product_related.id

                #order_item_ids = order_items_obj.search( [('order_item_id','=',order_item_fields['order_item_id']),
                #                                            ('order_id','=',order.id)] )

                query = """SELECT id
                FROM   mercadolibre_order_items
                WHERE
                order_item_id = '%s'
                AND order_id = %i
                """ % ( order_item_fields['order_item_id'], order and order.id)
                cr = MeliCr( self )
                respquery = cr.execute(query)
                results = cr.fetchall()
                order_item_ids = results

                #### CREATE ORDER ITEM !!! ####

                #_logger.info("Order item ids: "+str(order_item_ids))
                order_item_id = False
                #_logger.info( order_item_fields )
                if (not order_item_ids):
                    #_logger.info( "Creating order_item_fields: " + str(order_item_fields) )
                    order_item_ids = order_items_obj.create( ( order_item_fields ))
                else:
                    order_item_id = order_items_obj.sudo().browse(order_item_ids and order_item_ids[0])
                    if order_item_id:
                        #_logger.info("writing order_item_fields: "+str(order_item_ids[0]))
                        order_item_id.write( ( order_item_fields ) )

                if (product_related_obj == False or len(product_related_obj)==0):
                    _item_sku = Item['item'].get('seller_sku', '') or Item['item'].get('seller_custom_field', '') or ''
                    _item_title = Item['item'].get('title', '') or ''
                    _item_meli_id = str(Item['item'].get('id', ''))
                    _item_variation = str(Item['item'].get('variation_id', '') or '')
                    error = { 'error': 'No product related to meli_id '+_item_meli_id, 'item': str(Item['item']), 'product_related_obj': str(product_related_obj) }
                    _logger.error(error)
                    order and meli_message_post(order, str(error["error"])+"\n"+str(error["item"]), config=config)
                    _sku_html = (
                        '<span style="font-size:16px;font-weight:bold;">%s</span>' % _item_sku
                    ) if _item_sku else (
                        '<span style="color:#dc3545;font-size:16px;font-weight:bold;">SIN SKU</span>'
                    )
                    _barcode_html = ''
                    if _item_sku:
                        _barcode_html = (
                            '<tr><td style="padding:4px 8px;font-weight:bold;">Barcode:</td>'
                            '<td style="padding:4px 8px;">%s</td></tr>' % _item_sku
                        )
                    _missing_html = (
                        '<div style="border:2px solid #dc3545;border-radius:8px;padding:12px;margin:8px 0;background:#fff3f3;">'
                        '<div style="font-size:18px;font-weight:bold;color:#dc3545;margin-bottom:8px;">'
                        '&#9888; PRODUCTO NO ENCONTRADO</div>'
                        '<p style="margin:4px 0;">No se encontró un producto en Odoo para la publicación de MercadoLibre.</p>'
                        '<table style="margin:8px 0;border-collapse:collapse;">'
                        '<tr><td style="padding:4px 8px;font-weight:bold;">SKU:</td>'
                        '<td style="padding:4px 8px;">%(sku_html)s</td></tr>'
                        '%(barcode_row)s'
                        '<tr><td style="padding:4px 8px;font-weight:bold;">ML Item ID:</td>'
                        '<td style="padding:4px 8px;">%(meli_id)s</td></tr>'
                        '<tr><td style="padding:4px 8px;font-weight:bold;">Variación:</td>'
                        '<td style="padding:4px 8px;">%(variation)s</td></tr>'
                        '<tr><td style="padding:4px 8px;font-weight:bold;">Título:</td>'
                        '<td style="padding:4px 8px;">%(title)s</td></tr>'
                        '</table>'
                        '<p style="margin:8px 0 0 0;padding:8px;background:#fff8e1;border-radius:4px;">'
                        '<b>Para resolver:</b> vincule la publicación al producto en Odoo desde '
                        '<b>MercadoLibre &gt; Product Maestro</b>, o cree el producto con el SKU '
                        '<code style="background:#f0f0f0;padding:2px 6px;border-radius:3px;">%(sku_raw)s</code>.</p>'
                        '</div>'
                    ) % {
                        'sku_html': _sku_html,
                        'barcode_row': _barcode_html,
                        'meli_id': _item_meli_id,
                        'variation': _item_variation or '-',
                        'title': _item_title,
                        'sku_raw': _item_sku or _item_meli_id,
                    }
                    if sorder:
                        # FIX #415 (NipSkin/Inity 520, tickets #414/#415): evitar spam en chatter.
                        # Postear "PRODUCTO NO ENCONTRADO" una sola vez por item ML: el cron de
                        # import re-procesa la orden cada ciclo y re-posteaba el mismo aviso.
                        # Slice acotado por performance (no recorrer miles de mensajes).
                        _missing_seen = sorder.message_ids[:50].filtered(
                            lambda m: m.body and "PRODUCTO NO ENCONTRADO" in (m.body or "")
                            and _item_meli_id in (m.body or "")
                        )
                        if not _missing_seen:
                            meli_message_post(sorder, _missing_html, config=config)

                #Short cut to meli id and sku
                order._order_product_sku()
                order._order_product_iva()
                order._order_product_meli_id()

                prod_name = ( not product_related_obj and str("(NO ENCONTRADO) ["+order.order_product_sku+"] "+str(Item['item']['title']))) or product_related_obj.display_name
                #_logger.info(prod_name: "+str(prod_name))
                order.name = "MO [%s] %s" % ( str(order.order_id), prod_name )

                #only when not a pack
                if (sorder and product_related_obj):
                    
                    tax_field = SaleOrderLineTaxField( self )
                    uom_field = SaleOrderLineUomField( self )
                    saleorderline_item_fields = {
                        'company_id': company.id,
                        'order_id': sorder.id,
                        'meli_order_item_id': Item['item']['id'],
                        'meli_order_item_iva': order_item_iva,
                        'meli_order_item_variation_id': Item['item']['variation_id'],
                        'product_id': product_related_obj.id,
                        'product_uom_qty': Item['quantity'],
                        'name': product_related_obj.display_name or Item['item']['title'],
                    }
                    saleorderline_item_fields[uom_field] = product_related_obj.uom_id.id
                    saleorderline_item_fields.update( self._set_product_unit_price( product_related_obj=product_related_obj, Item=Item, config=config ) )

                    #TODO: agregar meli_order_id !!! (mismo item dos ordenes diferentes...puede pasar...)
                    saleorderline_item_ids = saleorderline_obj.search( [('meli_order_item_id','=',saleorderline_item_fields['meli_order_item_id']),
                                                                        ('meli_order_item_variation_id','=',saleorderline_item_fields['meli_order_item_variation_id']),
                                                                        ('order_id','=',sorder.id)], limit=1 )

                    if not saleorderline_item_ids:
                        if sorder.meli_paid_amount==0.0 or 1.1<abs((sorder.meli_paid_amount-(sorder.meli_discount_seller_amount or 0))-sorder.amount_total):
                            saleorderline_item_ids = saleorderline_obj.create( ( saleorderline_item_fields ))
                    
                    if saleorderline_item_ids:
                        #_logger.info(saleorderline_item_ids:"+str(saleorderline_item_ids))
                        #_logger.info(product_related_obj taxes_id:"+str(product_related_obj.taxes_id))
                        #_logger.info(product_related_obj taxes_id:"+str(product_related_obj.taxes_id and product_related_obj.taxes_id.company_id))
                        #_logger.info(saleorderline_item_ids tax:"+str(saleorderline_item_ids[tax_field]))
                        #_logger.info(saleorderline_item_ids tax company_id:"+str(saleorderline_item_ids[tax_field].company_id))
                        tax_iva_name = saleorderline_item_ids.meli_order_item_iva
                        tax_iva_name = tax_iva_name
                        tax_iva_id = None
                        if tax_iva_name and product_related_obj.taxes_id:
                            for txid in product_related_obj.taxes_id:
                                if ( tax_names_equivalent(txid.name,tax_iva_name) ):
                                    tax_iva_id = txid

                        for tid in saleorderline_item_ids[tax_field]:

                            if (tid.company_id.id!=sorder.company_id.id 
                                or (tax_iva_id and tax_iva_id!=tid) ):
                                #remove
                                saleorderline_item_ids[tax_field] = [(3, tid.id)]

                        if not saleorderline_item_ids[tax_field] and product_related_obj.taxes_id:
                            for txid in product_related_obj.taxes_id:
                                if (txid.company_id.id==sorder.company_id.id):
                                    if (tax_iva_id):
                                        if (tax_iva_id!=tid):
                                            #add
                                            saleorderline_item_ids[tax_field] = [(4, txid.id)]
                                    else:
                                        #add
                                        saleorderline_item_ids[tax_field] = [(4, txid.id)]

                        if (sorder.state and sorder.state in ['done','sale']) or ("locked" in sorder._fields and sorder.locked):
                            #_logger.warning("Orden bloqueada no se puede actualizar")
                            pass;
                        else:
                            _logger.info("Sale Order line write")
                            saleorderline_item_ids.write( ( saleorderline_item_fields ) )

        if 'payments' in order_json:
            payments = order_json['payments']
            #sumar los financing fee aprobados
            financing_fee_amount = 0
            cn = 0
            for Payment in payments:
                cn = cn + 1

                mp_payment_url = "https://api.mercadopago.com/v1/payments/"+str(Payment['id'])

                payment_fields = {
                    'order_id': order.id,
                    'payment_id': Payment['id'],
                    'transaction_amount': Payment['transaction_amount'] or '',
                    'total_paid_amount': Payment['total_paid_amount'] or '',
                    'currency_id': Payment['currency_id'] or '',
                    'status': Payment['status'] or '',
                    'date_created': ml_datetime(Payment['date_created']),
                    'date_last_modified': ml_datetime(Payment['date_last_modified']),
                    'mercadopago_url': mp_payment_url+'?access_token='+str(meli.access_token),
                    'full_payment': '',
                    'fee_amount': 0,
                    'shipping_amount': 0,
                    'taxes_amount': 0,
                    'financing_fee_amount': 0
                }

                headers = {'Accept': 'application/json', 'User-Agent': 'Odoo', 'Content-type':'application/json'}
                params = { 'access_token': meli.access_token }

                # Wrap API call in try/except to handle network errors gracefully
                # Order processing should continue even if MP API is unreachable
                mp_response = None
                try:
                    mp_response = requests.get( mp_payment_url, params=urlencode(params), headers=headers, timeout=10 )
                except requests.exceptions.RequestException as e:
                    _logger.warning("MELI: Could not fetch payment details from MercadoPago API (order will continue): %s", str(e))

                if (mp_response):
                    payment_fields["full_payment"] = mp_response.json()
                    payment_fields["shipping_amount"] = payment_fields["full_payment"]["shipping_amount"]
                    payment_fields["shipping_seller_cost"] = 0
                    payment_fields["total_paid_amount"] = payment_fields["full_payment"]["transaction_details"]["total_paid_amount"]

                    # Extract payment method and card details from MercadoPago response
                    fp = payment_fields["full_payment"]
                    payment_fields["payment_method_id"] = fp.get("payment_method_id", "")
                    payment_fields["payment_type"] = fp.get("payment_type_id", "")
                    payment_fields["installments"] = fp.get("installments", 0)
                    payment_fields["installment_amount"] = fp.get("installment_amount", 0)
                    payment_fields["operation_type"] = fp.get("operation_type", "")
                    payment_fields["date_approved"] = ml_datetime(fp.get("date_approved"))
                    payment_fields["authorization_code"] = fp.get("authorization_code", "")
                    payment_fields["statement_descriptor"] = fp.get("statement_descriptor", "")
                    payment_fields["coupon_amount"] = fp.get("coupon_amount", 0)
                    payment_fields["overpaid_amount"] = fp.get("overpaid_amount", 0)
                    payment_fields["payer_id"] = str(fp.get("payer", {}).get("id", "")) if fp.get("payer") else ""
                    payment_fields["issuer_id"] = str(fp.get("issuer_id", ""))
                    payment_fields["marketplace_fee"] = fp.get("marketplace_fee", 0)
                    card = fp.get("card") or {}
                    if card:
                        payment_fields["card_first_six_digits"] = card.get("first_six_digits", "")
                        payment_fields["card_last_four_digits"] = card.get("last_four_digits", "")

                    if ("fee_details" in payment_fields["full_payment"] and len(payment_fields["full_payment"]["fee_details"])>0):
                        fee_details = payment_fields["full_payment"]["fee_details"]
                        for fee_detail in fee_details:
                            #fee_detail = fee_details[index]
                            if fee_detail and "amount" in fee_detail:
                                fee_type = fee_detail["type"]
                                fee_payer = fee_detail["fee_payer"]
                                if (fee_payer and fee_payer == "collector" and fee_type == "application_fee"):
                                    payment_fields["fee_amount"] = fee_detail["amount"]
                                    if (order):
                                        order.fee_amount = payment_fields["fee_amount"]
                                if (fee_payer and fee_payer == "payer" and fee_type == "financing_fee"):
                                    payment_fields["financing_fee_amount"] = fee_detail["amount"]
                                    if ('status' in Payment and Payment['status'] == "approved"):
                                        financing_fee_amount+= payment_fields["financing_fee_amount"]
                        if (order):
                            order.financing_fee_amount = financing_fee_amount
                            if (sorder):
                                sorder.meli_fee_amount = order.fee_amount
                                sorder.meli_financing_fee_amount = order.financing_fee_amount


                    if ("charges_details" in payment_fields["full_payment"] and len(payment_fields["full_payment"]["charges_details"])>0):
                        fee_details = payment_fields["full_payment"]["charges_details"]
                        
                        payment_fields["fee_amount"] = 0

                        for fee_detail in fee_details:
                            
                            #fee_detail = fee_details[index]

                            if fee_detail and "amounts" in fee_detail:
                                #_logger.info("fee_detail:"+str(fee_detail))
                                fee_type = fee_detail["type"]
                                #fee_payer = fee_detail["fee_payer"]
                                fee_name = fee_detail["name"]
                                #_logger.info( "fee_type:" + str(fee_type) + " fee_name:" + str(fee_name) )
                                if ( fee_type=="fee" and (fee_name == "meli_percentage_fee" or fee_name=="flat_fee" or fee_name=="financing_add_on_fee" ) ):
                                    payment_fields["fee_amount"]+= fee_detail["amounts"] and fee_detail["amounts"]["original"]
                                    #_logger.info("fee_amount:"+str(payment_fields["fee_amount"]))
                                    if (order):
                                        order.fee_amount = payment_fields["fee_amount"]

                                if ( fee_type=="shipping" or (fee_name == "shp_fulfillment") ):
                                    #put in shipping_seller_cost
                                    payment_fields["shipping_seller_cost"]+= fee_detail["amounts"] and fee_detail["amounts"]["original"]
                                    if (order):
                                        order.shipping_seller_cost = payment_fields["shipping_seller_cost"]

                                # Handle coupon as fee (seller absorbs the coupon cost)
                                # When type is 'coupon' and accounts.from='ml' and accounts.to='payer'
                                # it means ML gives discount to buyer, seller must absorb it as cost
                                if ( fee_type=="coupon" ):
                                    coupon_fee_amount = fee_detail["amounts"] and fee_detail["amounts"]["original"] or 0
                                    if coupon_fee_amount > 0:
                                        payment_fields["fee_amount"]+= coupon_fee_amount
                                        _logger.info("MELI: Adding coupon as fee: %.2f (name: %s)", coupon_fee_amount, fee_name)
                                        if (order):
                                            order.fee_amount = payment_fields["fee_amount"]
                                            if not order.coupon_amount:
                                                order.coupon_amount = coupon_fee_amount

                                #if (fee_payer and fee_payer == "collector" and fee_type == "application_fee"):
                                #    payment_fields["fee_amount"] = fee_detail["amount"]
                                #    if (order):
                                #        order.fee_amount = payment_fields["fee_amount"]
                                #if (fee_payer and fee_payer == "payer" and fee_type == "financing_fee"):
                                #    payment_fields["financing_fee_amount"] = fee_detail["amount"]
                                #    if ('status' in Payment and Payment['status'] == "approved"):
                                #        financing_fee_amount+= payment_fields["financing_fee_amount"]

                        if (order):
                            order.financing_fee_amount = financing_fee_amount
                            if (sorder):
                                sorder.meli_fee_amount = order.fee_amount
                                sorder.meli_financing_fee_amount = order.financing_fee_amount
                                sorder.meli_shipping_seller_cost = order.shipping_seller_cost

                    payment_fields["taxes_amount"] = payment_fields["full_payment"]["taxes_amount"]

                payment_ids = payments_obj.search( [  ('payment_id','=',payment_fields['payment_id']),
                                                            ('order_id','=',order.id ) ] )
                if not payment_ids:
                    #_logger.info("Creating payment fields:"+str(payment_fields) )
                    payment_ids = payments_obj.create( ( payment_fields ) )
                else:
                    #_logger.info("Upading payment fields:"+str(payment_fields))
                    payment_ids.write( ( payment_fields ) )

        # coupon_amount = descuento que ML financia DE SU PROPIO COSTO al comprador.
        # El vendedor cobra el precio completo — este campo NO es un descuento del vendedor.
        # config.meli_coupon_discount_on_invoice controla si se refleja en la factura:
        #   False (default): sin descuento en líneas → factura por precio de venta completo.
        #   True: aplica el cupón ML como % de descuento sobre el precio bruto (con IVA)
        #         → factura queda exactamente en (total_bruto - coupon_amount).
        # En ningún caso se tocan descuentos del vendedor ni descuentos manuales preexistentes.
        if order and order.coupon_amount and sorder:
            if not sorder.meli_coupon_amount:
                sorder.meli_coupon_amount = order.coupon_amount
            # Modo de facturación del cupón ML (tri-estado meli_coupon_invoice_mode):
            #   full (default): NO se imputa a ninguna línea → factura a precio pleno. Correcto
            #       cuando ML reembolsa el cupón al vendedor (made-whole). [#433 Elvimarta]
            #   product_discount: cupón como descuento (%) sobre líneas de PRODUCTO (= flag ON).
            #   separate_line: cupón como línea(s) de descuento separada(s) por grupo de impuesto
            #       (OPT-IN, riesgos AFIP/CL — validar antes de habilitar).
            # El FIX #399 forzaba product_discount aun con el flag OFF cuando el comprador pagaba
            # el flete entero; eso pisaba la preferencia del cliente (regresión #433). Ahora el
            # reparto depende SOLO del modo declarado en la config.
            _coupon_mode = meli_resolve_coupon_invoice_mode(config)
            _so_editable = sorder.state not in ('done',) and not ("locked" in sorder._fields and sorder.locked)
            if _coupon_mode == 'product_discount':
                if _so_editable:
                    non_delivery_lines = sorder.order_line.filtered(lambda l: not l.is_delivery)
                    total_gross = 0.0
                    for line in non_delivery_lines:
                        tax_pct = sum(
                            t.amount for t in (line.tax_ids if hasattr(line, 'tax_ids') else line.tax_id)
                            if t.amount_type == 'percent' and not t.price_include
                        )
                        total_gross += line.price_unit * line.product_uom_qty * (1.0 + tax_pct / 100.0)
                    if total_gross > 0:
                        discount_pct = round((order.coupon_amount / total_gross) * 100.0, 6)
                        for line in non_delivery_lines:
                            line.discount = discount_pct
                        _logger.info(
                            "MELI: Applied coupon discount %.4f%% (coupon=%.2f / gross_total=%.2f) "
                            "to %d lines on SO %s",
                            discount_pct, order.coupon_amount, total_gross,
                            len(non_delivery_lines), sorder.name,
                        )
            elif _coupon_mode == 'separate_line':
                if _so_editable:
                    meli_apply_coupon_separate_line(sorder, order.coupon_amount)
            else:
                # modo 'full': sin descuento. Limpiar cualquier descuento de cupón previo.
                if _so_editable:
                    non_delivery_lines = sorder.order_line.filtered(lambda l: not l.is_delivery)
                    total_gross = 0.0
                    for line in non_delivery_lines:
                        tax_pct = sum(
                            t.amount for t in (line.tax_ids if hasattr(line, 'tax_ids') else line.tax_id)
                            if t.amount_type == 'percent' and not t.price_include
                        )
                        total_gross += line.price_unit * line.product_uom_qty * (1.0 + tax_pct / 100.0)
                    if total_gross > 0:
                        prev_pct_bug = round((order.coupon_amount / sum(
                            line.price_unit * line.product_uom_qty
                            for line in non_delivery_lines
                        )) * 100.0, 6) if sum(
                            line.price_unit * line.product_uom_qty for line in non_delivery_lines
                        ) > 0 else 0
                        prev_pct_ok = round((order.coupon_amount / total_gross) * 100.0, 6)
                        for line in non_delivery_lines:
                            if (abs(line.discount - prev_pct_bug) < 0.01
                                    or abs(line.discount - prev_pct_ok) < 0.01):
                                line.discount = 0.0
                                _logger.info(
                                    "MELI: Removed coupon discount from line %s on SO %s "
                                    "(coupon_invoice_mode=full)",
                                    line.id, sorder.name,
                                )
                    meli_remove_coupon_separate_line(sorder)

        if (1==1 or config.mercadolibre_cron_get_orders_shipment):
            #_logger.info("Updating order: Shipment: "+str(order.shipping_id))
            if (order and order.shipping_id):
                shipment = shipment_obj.fetch_shipment( order, meli=meli, config=config )
                if shipment and not isinstance(shipment, dict):
                    order.shipment = shipment
                    # NOTE: shipping_seller_cost copy is now also done inside fetch_shipment
                    # (before _update_sale_order_shipping_info) so purchase_price gets the correct value.
                    # We keep this as a safety net for edge cases where order is updated after fetch.
                    if (order.shipping_seller_cost):
                        shipment.shipping_seller_cost = order.shipping_seller_cost
                    #TODO: enhance with _order_update_pack()...
                    #Updated sorder because shipment could create sorder pack...
                    if (sorder):
                        shipment.sale_order = sorder
                    else:
                        sorder = shipment.sale_order
                        if sorder:
                            #_logger.info("fixing meli_date_created")
                            sorder.meli_date_created = order.date_created
                            sorder.meli_date_closed = order.date_closed

        #could be packed sorder or standard one product item order
        if sorder:
            for line in sorder.order_line:
                if (sorder.meli_order_id and line.is_delivery and line.price_unit<=0.0 and line.qty_to_invoice>0):
                    #_logger.info(line)
                    line.write({ "qty_to_invoice": 0.0 })
                    pass;

            #if (config.mercadolibre_order_confirmation!="manual"):
            sorder.confirm_ml( meli=meli, config=config )

            if (sorder.meli_status=="cancelled" and sorder.state in ["draft","sale","sent","done"]):
                cancel_msg = "Orden cancelada por MercadoLibre."
                if sorder.meli_status_detail:
                    cancel_msg += " Motivo: %s" % sorder.meli_status_detail
                sorder.meli_cancel_with_detail(cancel_msg)

            #if "confirm_ml_financial" in self.env["mercadolibre.orders"]:
            #sorder.confirm_ml_financial( meli=meli, config=config )

            if meli.access_token=="PASIVA":
                if (sorder):
                    sorder.meli_fee_amount = order_fields["fee_amount"]

            if (1==2 and sorder.meli_orders):
                #process payments
                for meli_order in sorder.meli_orders:
                    for payment in meli_order.payments:
                        try:
                            if config.mercadolibre_process_payments_customer:


                                if 1==2 and payment.account_payment_id:
                                    fix = payment.account_payment_id and (payment.transaction_amount!=payment.total_paid_amount)
                                    fix = fix and (payment.account_payment_id.amount!=payment.transaction_amount)
                                    fix = fix and str(payment.account_payment_id.payment_date) == '2021-07-05'

                                    if (fix):
                                        #_logger.info(payment fixing: "+str(payment.account_payment_id))
                                        #self.account_payment_id.cancel()
                                        payment.account_payment_id.action_draft()
                                        payment.account_payment_id.unlink()
                                        payment.account_payment_id = False

                                if not payment.account_payment_id:
                                    payment.create_payment( meli=meli, config=config )

                        except Exception as e:
                            _logger.info("Error creating customer payment")
                            _logger.info(e, exc_info=True)
                            pass;

                        try:
                            if config.mercadolibre_process_payments_supplier_fea and not payment.account_supplier_payment_id:
                                payment.create_supplier_payment( meli=meli, config=config )
                        except Exception as e:
                            _logger.info("Error creating supplier fee payment")
                            _logger.info(e, exc_info=True)
                            pass;

                        try:
                            if ( config.mercadolibre_process_payments_supplier_shipment and not payment.account_supplier_payment_shipment_id 
                                and (payment.order_id and (payment.order_id.payments_shipment_amount>0.0 or payment.order_id.shipping_seller_cost>0.0) )):
                                payment.create_supplier_payment_shipment( meli=meli, config=config )
                        except Exception as e:
                            _logger.info("Error creating supplier shipment payment")
                            _logger.info(e, exc_info=True)
                            pass;

        else:
            _logger.error("Warning: sale order not created!")
            if order:
                meli_message_post(order, "Warning: sale order not created!", config=config)

        try:
            self.orders_get_invoice( meli=meli, config=config )
        except:
            pass;

        return {}

    def orders_import_order( self, order_id, context=None, meli=None, config=None ):
        if not order_id:
            return {"error": "order_id missing"}

        context = context or self.env.context
        warningobj = self.env['meli.warning']

        #_logger.info( "context:" + str(context) )
        company = self.env.user.company_id

        order_obj = self.env['mercadolibre.orders']

        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)

        if not config:
            config = company

        morder = order_obj.search( [('order_id','=',str(order_id))], limit=1 )
        if morder:
            return { "error": str(order_id)+" already in Odoo" }

        response = meli.get("/orders/"+str(order_id), {'access_token':meli.access_token})
        order_json = response.json()

        if order_json:
            if "error" in order_json:
                return { "error": order_json }
            else:
                ret = self.orders_update_order_json( {"id": False, "order_json": order_json }, meli=meli, config=config )
                if ret:
                    #_logger.info(ret)
                    return { "ret": ret }
        else:
            return { "error": "no order json "+str(order_json) }

        return {}


    def orders_update_order( self, context=None, meli=None, config=None ):

        #get with an item id
        context = context or self.env.context
        warningobj = self.env['meli.warning']

        #_logger.info( "context:" + str(context) )
        company = self.env.user.company_id

        order_obj = self.env['mercadolibre.orders']
        order = self

        log_msg = 'orders_update_order: %s' % (order.order_id)
        #_logger.info(log_msg)

        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)

        if not config:
            config = company

        response = meli.get("/orders/"+str(order.order_id), {'access_token':meli.access_token})
        order_json = response.json()
        #_logger.info( order_json )
        rets = []

        if "error" in order_json and meli.access_token!="PASIVA":
            _logger.error( order_json["error"] )
            _logger.error( order_json["message"] )
        else:
            try:
                if meli.access_token=="PASIVA":
                    order_json = None

                ret = self.orders_update_order_json( {"id": order.id, "order_json": order_json }, meli=meli, config=config )
                MeliCommit( self )
                if ret and "error" in ret:
                    rets.append(ret)
            except Exception as e:
                _logger.info("orders_update_order > Error actualizando ORDEN")
                _logger.error(e, exc_info=True)
                MeliRollback( self )

                #_logger.info(orders_update_order journal_id: "+str(order.name))
                if order.sale_order and "mercadolibre_invoice_journal_id" in config._fields and config.mercadolibre_invoice_journal_id:
                    #_logger.info(order.sale_order > config.mercadolibre_invoice_journal_id: "+str(config.mercadolibre_invoice_journal_id))
                    if "journal_id" in order.sale_order._fields:
                        #_logger.info(order.sale_order.journal_id: "+str(order.sale_order.journal_id))
                        order.sale_order.journal_id = config.mercadolibre_invoice_journal_id
                        #_logger.info(orders_update_order order.journal_id: "+str(order.sale_order.journal_id))
                if order.sale_order:
                    if (config.mercadolibre_order_confirmation!="manual"):
                        order.sale_order.confirm_ml( meli=meli, config=config )
                pass;
                #raise e

        if rets and len(rets)==1:
            return warningobj.info( title='MELI WARNING', message = "update order errors: "+str(len(rets)), message_html = str(rets))


        return {}


    def orders_query_iterate( self, offset=0, context=None, config=None, meli=None, fetch_id_only=False, fetch_ids=[] ):

        #_logger.info(mercadolibre.orders >> orders_query_iterate: meli: "+str(meli)+" config:"+str(config)+' fetch_id_only:'+str(fetch_id_only))
        offset_next = 0
        __fetch_ids = fetch_ids

        company = self.env.user.company_id
        if not config:
            config = company

        orders_obj = self.env['mercadolibre.orders']

        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)

        orders_query = "/orders/search?seller="+str(meli.seller_id)+"&sort=date_desc"

        # Use orders limit from config if available (default API limit is 50)
        orders_limit = None
        if hasattr(config, 'mercadolibre_cron_orders_limit') and config.mercadolibre_cron_orders_limit:
            orders_limit = config.mercadolibre_cron_orders_limit
            orders_query += "&limit=" + str(orders_limit)

        if (offset):
            orders_query = orders_query + "&offset="+str(offset).strip()

        response = meli.get( orders_query, {'access_token': meli.access_token})
        orders_json = response.json()

        if "error" in orders_json:
            _logger.error( orders_query )
            _logger.error( orders_json["error"] )
            if (orders_json["message"]=="invalid_token"):
                _logger.error( orders_json["message"] )
            if __fetch_ids:
                return __fetch_ids
            return {}

        order_date_filter = ("mercadolibre_filter_order_datetime" in config._fields and config.mercadolibre_filter_order_datetime)

        if "paging" in orders_json:
            if "total" in orders_json["paging"]:
                if (orders_json["paging"]["total"]==0):
                    return {}
                else:
                    if (orders_json["paging"]["total"]>=(offset+orders_json["paging"]["limit"])):
                        # Don't paginate if explicit limit is set or no date filter
                        if orders_limit or not order_date_filter:
                            offset_next = 0
                        else:
                            offset_next = offset + orders_json["paging"]["limit"]
                        #_logger.info(offset_next:"+str(offset_next))

        #_logger.info( orders_json )
        if "results" in orders_json:
            for order_json in orders_json["results"]:
                if order_json:
                    pdata = {"id": False, "order_json": order_json}
                    if "id" in order_json and fetch_id_only:

                        #_logger.info( order_json["id"] )
                        order_fields = self.prepare_ml_order_vals( order_json=order_json, meli=meli, config=config )
                        in_range = True
                        if (    "mercadolibre_filter_order_datetime_start" in config._fields
                                and "date_closed" in order_fields
                                and order_fields["date_closed"]
                                and config.mercadolibre_filter_order_datetime_start
                                and config.mercadolibre_filter_order_datetime_start>parse(order_fields["date_closed"]) ):
                            #error = { "error": "orden filtrada por fecha START > " + str(order_fields["date_closed"]) + " inferior a "+str(ml_datetime(config.mercadolibre_filter_order_datetime_start)) }
                            #_logger.info( "orders_update_order_json > filter:" + str(error) )
                            #return error
                            in_range = False


                        if (    "mercadolibre_filter_order_datetime" in config._fields
                                and "date_closed" in order_fields
                                and order_fields["date_closed"]
                                and config.mercadolibre_filter_order_datetime
                                and config.mercadolibre_filter_order_datetime>parse(order_fields["date_closed"]) ):
                            #error = { "error": "orden filtrada por FROM > " + str(order_fields["date_closed"]) + " inferior a "+str(ml_datetime(config.mercadolibre_filter_order_datetime)) }
                            #_logger.info( "orders_update_order_json > filter:" + str(error) )
                            in_range = False

                        if (    "mercadolibre_filter_order_datetime_to" in config._fields
                                and "date_closed" in order_fields
                                and order_fields["date_closed"]
                                and config.mercadolibre_filter_order_datetime_to
                                and config.mercadolibre_filter_order_datetime_to<parse(order_fields["date_closed"]) ):
                            #error = { "error": "orden filtrada por fecha TO > " + str(order_fields["date_closed"]) + " superior a "+str(ml_datetime(config.mercadolibre_filter_order_datetime_to)) }
                            #_logger.info( "orders_update_order_json > filter:" + str(error) )
                            in_range = False

                        if in_range:
                            __fetch_ids.append(str(order_json["id"]))
                    else:
                        _serialization_ex = psycopg2_errors.SerializationFailure if psycopg2_errors else ()
                        for _attempt in range(3):
                            try:
                                ret = self.orders_update_order_json( data=pdata, config=config, meli=meli )
                                MeliCommit( self )
                                break
                            except _serialization_ex as e:
                                MeliRollback( self )
                                if _attempt < 2:
                                    import time as _time; _time.sleep(0.3 * (_attempt + 1))
                                else:
                                    _logger.warning("orders_query_iterate > SerializationFailure tras 3 intentos, orden omitida")
                            except Exception as e:
                                _logger.info("orders_query_iterate > Error actualizando ORDEN")
                                _logger.error(e, exc_info=True)
                                MeliRollback( self )
                                break

        if (offset_next>0):
            __fetch_ids = self.orders_query_iterate( offset=offset_next, meli=meli, config=config, fetch_id_only=fetch_id_only, fetch_ids=__fetch_ids )

        return __fetch_ids

    def orders_query_recent( self, meli=None, config=None, fetch_id_only=False ):

        company = self.env.user.company_id
        if not config:
            config = company

        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)

        #_logger.info(mercadolibre.orders >> orders_query_recent: meli: "+str(meli)+" config:"+str(config)+' fetch_id_only:'+str(fetch_id_only))
        Autocommit(self, False)
        __fetch_ids = None
        try:
            __fetch_ids = self.orders_query_iterate( offset=0, meli=meli, config=config, fetch_id_only=fetch_id_only )
        except Exception as e:
            _logger.info("orders_query_recent > Error iterando ordenes")
            _logger.error(e, exc_info=True)
            MeliRollback( self )

        if __fetch_ids:
            #_logger.info( "__fetch_ids:"+str(__fetch_ids) )
            return { "fetch_ids": __fetch_ids }

        return {}

    def update_order_status( self, meli=None, config=None):
        for order in self:
            company = (config and "company_id" in config._fields and config.company_id) or self.env.user.company_id
            if not config:
                config = company
            if not meli:
                meli = self.env['meli.util'].get_new_instance(company)
            if not meli:
                return {}
            response = meli.get("/orders/"+str(order.order_id), {'access_token':meli.access_token})
            order_json = response.json()
            if "id" in order_json:
                if (str(order.status)!=str(order_json["status"])):
                    #full update if status changed!
                    order.orders_update_order(meli=meli,config=config)
                order.status = order_json["status"] or ''
                cancel_detail = order_json.get("cancel_detail") or {}
                cancel_detail_text = ""
                if cancel_detail:
                    cancel_detail_text = " | %s: %s (solicitado por: %s, fecha: %s)" % (
                        cancel_detail.get("code", ""),
                        cancel_detail.get("description", ""),
                        cancel_detail.get("requested_by", ""),
                        cancel_detail.get("date", ""),
                    )
                order.status_detail = (order_json.get("status_detail") or '') + cancel_detail_text
                if order.sale_order:
                    order.sale_order.meli_status_detail = order.status_detail
                    order.sale_order.confirm_ml(meli=meli,config=config)

    def orders_resync_status( self, meli=None, config=None, account=None ):
        """#475 - Re-sincroniza el ESTADO de los pedidos MeLi recientes que siguen
        ABIERTOS en Odoo, para reflejar cancelaciones (y otros cambios de estado)
        que el cron de importacion (orders_query_iterate, sort=date_desc) no alcanza
        cuando la orden es mas vieja que la ventana de las ~50 mas nuevas por creacion.

        Barrido ACOTADO (rate-limit safe): solo pedidos con sale.order NO cancelada,
        creados en los ultimos N dias (mercadolibre_cron_orders_status_days), con tope
        mercadolibre_cron_orders_status_limit. Por pedido hace UN GET /orders/<id> (ligero)
        y solo procesa (confirm_ml / meli_cancel_with_detail) cuando el estado CAMBIO.

        #475 multi-cuenta: `account` (mercadolibre.account) es opcional. Cuando el
        dispatcher de meli_oerp_multiple lo pasa, el barrido se scopea por esa cuenta
        (connection_account) y toma la compañia del `config` (connection_configuration).
        Sin `account` el comportamiento es identico al mono-cuenta historico."""
        company = self.env.user.company_id
        if not config:
            config = company
        # #475 multi-cuenta: si el config trae su propia compania (connection_configuration
        # en meli_oerp_multiple), usarla para scopear; si es res.company (mono-cuenta) o no
        # la expone, se cae al company del usuario del cron (retrocompat total).
        if config is not None and "company_id" in config._fields and config.company_id:
            company = config.company_id
        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)
        if not meli or meli.needlogin_state:
            return {}

        days = 7
        if "mercadolibre_cron_orders_status_days" in config._fields and config.mercadolibre_cron_orders_status_days:
            days = config.mercadolibre_cron_orders_status_days
        query_limit = 100
        if "mercadolibre_cron_orders_status_limit" in config._fields and config.mercadolibre_cron_orders_status_limit:
            query_limit = config.mercadolibre_cron_orders_status_limit

        cutoff = fields.Datetime.now() - timedelta(days=days)
        domain = [
            ("date_created", ">=", cutoff),
            ("sale_order", "!=", False),
            ("sale_order.state", "!=", "cancel"),
            ("status", "not in", ("cancelled", "invalid")),
        ]
        if "company_id" in self._fields:
            domain.append(("company_id", "in", (company.id, False)))
        # #475 multi-cuenta: scope preciso por cuenta ML cuando el dispatcher lo pasa,
        # para no re-consultar con el token de una cuenta ordenes de otra.
        if account is not None and "connection_account" in self._fields:
            domain.append(("connection_account", "=", account.id))
        candidates = self.search(domain, order="date_created desc", limit=query_limit)

        Autocommit(self, False)
        checked = changed = cancelled = 0
        for order in candidates:
            try:
                response = meli.get("/orders/"+str(order.order_id), {'access_token': meli.access_token})
                order_json = response.json()
                checked += 1
                if "id" not in order_json:
                    continue
                new_status = order_json.get("status") or ''
                if str(order.status) == str(new_status):
                    # sin cambios -> sin side effects (idempotente, barato: 1 GET)
                    continue
                changed += 1
                cancel_detail = order_json.get("cancel_detail") or {}
                cancel_detail_text = ""
                if cancel_detail:
                    cancel_detail_text = " | %s: %s (solicitado por: %s, fecha: %s)" % (
                        cancel_detail.get("code", ""),
                        cancel_detail.get("description", ""),
                        cancel_detail.get("requested_by", ""),
                        cancel_detail.get("date", ""),
                    )
                order.status = new_status
                order.status_detail = (order_json.get("status_detail") or '') + cancel_detail_text
                sorder = order.sale_order
                if sorder:
                    sorder.meli_status_detail = order.status_detail
                    if new_status == "cancelled" and sorder.state in ("draft", "sent", "sale", "done"):
                        cancel_msg = "Orden cancelada por MercadoLibre."
                        if sorder.meli_status_detail:
                            cancel_msg += " Motivo: %s" % sorder.meli_status_detail
                        sorder.meli_cancel_with_detail(cancel_msg)
                        cancelled += 1
                    else:
                        # otro cambio de estado -> resync completo por ID
                        order.orders_update_order(meli=meli, config=config)
                MeliCommit(self)
            except Exception as e:
                _logger.error("orders_resync_status > error en orden %s: %s", order.order_id, e, exc_info=True)
                MeliRollback(self)
        _logger.info("orders_resync_status: cuenta=%s checked=%s changed=%s cancelled=%s (days=%s limit=%s)", (account and account.name) or "-", checked, changed, cancelled, days, query_limit)
        return {"checked": checked, "changed": changed, "cancelled": cancelled}

    def _get_config( self, config=None ):
        
        _logger.info("_get_config from meli_oerp")

        if ("connection_account" in self._fields):
            config = config or (self and self.connection_account and self.connection_account.configuration) or (self and self.company_id)
            return config

        config = config or (self and self.company_id)
        return config

    def orders_get_invoice(self, context=None, meli=None, config=None):
        #_logger.info("orders_get_invoice")
        pass;

    def meli_confirm_ready(self, meli=None, config=None):
        """Versión read-only a nivel de orden ML: indica si la venta está lista
        para confirmar. Devuelve (ready: bool, reason: str).

        Delega en el helper homónimo de la `sale.order` vinculada (donde vive la
        matemática de confirm_ml). Motivos posibles:
          - "Cancelada en MercadoLibre" -> NO es incompleta (ready=True, el llamador
             la excluye usando el flag self.status/meli_status).
          - "Sin pedido de venta (sale.order)" -> orden ML importada sin SO.
          - "Total $0 (sin monto a facturar)" -> amount_total del SO en cero.
          - el mensaje MELI de mismatch (amount_to_invoice vs amount_total) cuando
             el total no coincide fuera de tolerancia.
        """
        self.ensure_one()
        # Cancelada: no es "incompleta", la maneja confirm_ml/cancel aparte.
        if self.status == "cancelled":
            return (True, "")
        so = self.sale_order
        if not so:
            return (False, "Sin pedido de venta (sale.order)")
        # Total 0: la venta no es confirmable (sin monto a facturar). Lo detectamos
        # aquí explícitamente para dar un motivo claro distinto del mismatch.
        if not so.amount_total:
            return (False, "Total $0 (sin monto a facturar): revisar productos/precios")
        ready, reason = so.meli_confirm_ready(meli=meli, config=config)
        if not ready and not reason:
            reason = "Venta incompleta: revisar productos faltantes, impuestos y descuentos"
        return (ready, reason)

    name = fields.Char(string='Order Name',index=True)
    order_id = fields.Char(string='Order Id',index=True)
    pack_id = fields.Char(string='Pack Id',index=True)
    sale_order = fields.Many2one('sale.order',string="Sale Order",help='Pedido de venta de Odoo')

    status = fields.Selection( [
        #Initial state of an order, and it has no payment yet.
                                        ("confirmed","Confirmado"),
        #The order needs a payment to become confirmed and show users information.
                                      ("payment_required","Pago requerido"),
        #There is a payment related with the order, but it has not accredited yet
                                    ("payment_in_process","Pago en proceso"),
        #The order has a related payment and it has been accredited.
                                    ("paid","Pagado"),
        #The order has a related partial payment and it has been accredited.
                                    ("partially_paid","Parcialmente Pagado"),
        #The order has not completed by some reason.
                                    ("cancelled","Cancelado"),
        #The order has been invalidated as it came from a malicious buyer.
                                    ("invalid","Invalido: malicious"),
        #The order status is cancelled, but an action is pending to complete the process.
        ("pending_cancel", "Pendiente de cancelar"),

        ("partially_refunded", "Parcialmente reembolsado")
                                    ],
        string='Order Status')

    status_detail = fields.Text(string='Status detail, in case the order was cancelled.')
    date_created = fields.Datetime('Creation date')
    date_closed = fields.Datetime('Closing date')


    def search_order_order_product(self, operator, value):
        if operator == '!=' and value is False:
            operator = '='
            value = True
        elif operator == '!=' and value is True:
            operator = '='
            value = False
        if operator == '=':
            #name = self.env.context.get('name', False)
            #if name is not False:
            id_list = []
            order_items = []
            if value == True:
                order_items = self.env['mercadolibre.order_items'].search([('product_id','!=',False)], limit=10000)
            else:
                order_items = self.env['mercadolibre.order_items'].search([('product_id','=',False)], limit=10000)

            for item in order_items:
                id_list.append(item.order_id.id)

            return [('id', 'in', id_list)]
        else:
            _logger.error(
                'The field name is not searchable'
                ' with the operator: {}',format(operator)
            )
            return [('id', 'in', [])]

    order_items = fields.One2many('mercadolibre.order_items','order_id',string='Order Items' )

    def _order_product( self ):
        for ord in self:
            ord.order_product = False

            if ord.order_items and ord.order_items[0]:
                ord.order_product = ord.order_items[0].product_id

    order_product = fields.Many2one('product.product',string='Order Product',compute=_order_product, search=search_order_order_product )

    def _order_product_sku( self ):
        for ord in self:
            ord.order_product_sku = ""

            if ord.order_items and ord.order_items[0]:
                ord.order_product_sku = ord.order_items[0].seller_sku or ord.order_items[0].seller_custom_field

    order_product_sku = fields.Char(string='Order Product Sku', compute=_order_product_sku, store=True, index=True )

    def _order_product_iva( self ):
        for ord in self:
            ord.order_product_iva = ""

            if ord.order_items and ord.order_items[0]:
                ord.order_product_iva = ord.order_items[0].order_item_iva

    order_product_iva = fields.Char(string='Order Product IVA', compute=_order_product_iva, store=True, index=True )


    def _order_product_meli_id(self):
        for ord in self:
            ord.order_product_meli_id = None
            ord.order_product_meli_variation_id = None
            item = ord.order_items and ord.order_items[0]
            if item:
                ord.order_product_meli_id = item.order_item_id
                ord.order_product_meli_variation_id = item.order_item_variation_id

    order_product_meli_id = fields.Char(string='Order Product Meli Id', compute=_order_product_meli_id, store=True, index=True )
    order_product_meli_variation_id = fields.Char(string='Order Product Meli Full Id', compute=_order_product_meli_id, store=True, index=True )

    payments = fields.One2many('mercadolibre.payments','order_id',string='Payments' )

    def _payments_shipment_amount(self):
        for mor in self:
            sum = 0
            for pay in mor.payments:
                if pay.status == 'approved':
                    sum+= pay.shipping_amount
            mor.payments_shipment_amount = sum

    payments_shipment_amount = fields.Float(string="Payments Shipment Amount", compute="_payments_shipment_amount" )

    def _ensure_payment_shipping_amounts(self, meli=None, config=None):
        """Chequeo final: si un pago aprobado quedó con shipping_amount=0 porque el
        fetch a MercadoPago falló/expiró en la PRIMERA pasada del import, re-consulta
        el detalle del pago en MP y completa shipping_amount. Evita que la línea de
        envío de la venta quede en 0 hasta un 'Actualizar' manual. Solo re-consulta
        los pagos aprobados que tienen shipping_amount=0 (no agrega llamadas si ya
        está cargado)."""
        for order in self:
            _meli = meli
            if not _meli:
                company = order.company_id or self.env.user.company_id
                _meli = self.env['meli.util'].get_new_instance(company)
            if not _meli or _meli.need_login():
                continue
            for pay in order.payments:
                if pay.status != 'approved' or pay.shipping_amount or not pay.payment_id:
                    continue
                url = "https://api.mercadopago.com/v1/payments/" + str(pay.payment_id)
                try:
                    resp = requests.get(
                        url, params=urlencode({'access_token': _meli.access_token}),
                        headers={'Accept': 'application/json', 'User-Agent': 'Odoo'}, timeout=10)
                except Exception as e:
                    _logger.warning("MELI _ensure_payment_shipping_amounts: re-consulta MP del pago %s falló: %s", pay.payment_id, e)
                    continue
                if resp is not None and resp.ok:
                    try:
                        data = resp.json() or {}
                    except Exception:
                        data = {}
                    sa = data.get('shipping_amount') or 0.0
                    if sa:
                        pay.shipping_amount = sa
                        _logger.info("MELI: shipping_amount=%s completado en pago %s (order %s) por chequeo final.",
                                     sa, pay.payment_id, order.order_id)

    shipping = fields.Text(string="Shipping")
    shipping_id = fields.Char(string="Shipping id")
    shipment = fields.Many2one('mercadolibre.shipment',string='Shipment')
    shipment_logistic_type = fields.Char(string="Logistic Type",index=True)

    fee_amount = fields.Float(string='Fee total amount')
    financing_fee_amount = fields.Float(string='Financing fee amount',help="Financiamiento",default=0.0)
    total_amount = fields.Float(string='Total amount')
    shipping_cost = fields.Float(string='Shipping Cost',help='Gastos de envío')
    shipping_seller_cost = fields.Float(string='Shipping Seller Cost',help='Gastos de envío (Vendedor)')
    shipping_list_cost = fields.Float(string='Shipping List Cost',help='Gastos de envío, costo de lista/interno')
    paid_amount = fields.Float(string='Paid amount',help='Includes shipping cost')
    coupon_amount = fields.Float(string='Coupon amount',help='Descuento',default=0.0)
    discount_seller_amount = fields.Float(string='Discount Seller Amount',help='Monto del descuento absorbido por el vendedor',default=0.0)
    currency_id = fields.Char(string='Currency')
    buyer =  fields.Many2one( "mercadolibre.buyers","Buyer")
    buyer_billing_info = fields.Text(string="Billing Info")
    seller = fields.Text( string='Seller Name' )
    tags = fields.Text(string="Tags")
    context = fields.Char(string="Context",index=True)
    pack_order = fields.Boolean(string="Order Pack (Carrito)")
    catalog_order = fields.Boolean(string="Order From Catalog")
    company_id = fields.Many2one("res.company",string="Company")
    seller_id = fields.Many2one("res.users",string="Seller")

    shipment_status = fields.Char(string="Shipment Status",related="shipment.status",index=True)
    shipment_substatus = fields.Char(string="Shipment SubStatus",related="shipment.substatus",index=True)

    _unique_order_id = versions.UniqueIndex('order_id', message='Meli Order id already exists!')


class mercadolibre_order_items(models.Model):
    _name = "mercadolibre.order_items"
    _description = "Producto pedido en MercadoLibre"

    posting_id = fields.Many2one("mercadolibre.posting",string="Posting",index=True)
    product_id = fields.Many2one("product.product",string="Product",help="Product Variant",index=True)
    order_id = fields.Many2one("mercadolibre.orders",string="Order",index=True)
    order_item_id = fields.Char(string='Item Id',index=True)
    order_item_iva = fields.Char(string='Item IVA',index=True)
    order_item_variation_id = fields.Char(string='Item Variation Id',index=True)
    order_item_title = fields.Char(string='Item Title',index=True)
    order_item_category_id = fields.Char(string='Item Category Id',index=True)
    unit_price = fields.Char(string='Unit price',index=True)
    full_unit_price = fields.Float(string='Full Unit price',index=True)
    quantity = fields.Integer(string='Quantity',index=True)
    currency_id = fields.Char(string='Currency',index=True)
    seller_sku = fields.Char(string='SKU',index=True)
    seller_custom_field = fields.Char(string='seller_custom_field',index=True)
    sale_fee = fields.Float(string="Sale Fee",index=True)

    # Surtido multi-almacén: la orden ML trae el depósito logístico de origen a
    # nivel ítem en Item['stock'] = {store_id, node_id}. Se persiste por línea para
    # rutear la entrega al warehouse/ubicación Odoo mapeado en
    # mercadolibre.account.stock_location (network_node_id <- node_id ; meli_store_id <- store_id).
    meli_stock_node_id = fields.Char(string='ML Stock Node ID', index=True,
        help='Network node del depósito ML de origen de esta línea (Item.stock.node_id, ej: MXP4397768091).')
    meli_stock_store_id = fields.Char(string='ML Stock Store ID', index=True,
        help='Store id del depósito ML de origen de esta línea (Item.stock.store_id).')


class mercadolibre_payments(models.Model):
    _name = "mercadolibre.payments"
    _description = "Pagos en MercadoLibre"

    order_id = fields.Many2one("mercadolibre.orders",string="Order")
    payment_id = fields.Char('Payment Id')
    transaction_amount = fields.Float('Transaction Amount')
    total_paid_amount = fields.Float('Total Paid Amount')
    currency_id = fields.Char(string='Currency')
    status = fields.Char(string='Payment Status')
    date_created = fields.Datetime('Creation date')
    date_last_modified = fields.Datetime('Modification date')
    mercadopago_url = fields.Char(string="MercadoPago Payment Url")
    full_payment = fields.Text(string="MercadoPago Payment Details")

    fee_amount = fields.Float('Fee Amount')
    shipping_amount = fields.Float('Shipping Amount')
    shipping_seller_cost = fields.Float('Shipping Seller Cost')
    taxes_amount = fields.Float('Taxes Amount')

    financing_fee_amount = fields.Float('Financing fee amount')

    # Payment method details (from MercadoPago API response)
    payment_method_id = fields.Char(string='Payment Method ID')  # visa, master, amex, account_money, etc.
    payment_type = fields.Char(string='Payment Type')  # credit_card, debit_card, account_money, ticket, etc.
    installments = fields.Integer(string='Installments')
    installment_amount = fields.Float(string='Installment Amount')
    operation_type = fields.Char(string='Operation Type')  # regular_payment
    date_approved = fields.Datetime(string='Date Approved')
    authorization_code = fields.Char(string='Authorization Code')
    card_first_six_digits = fields.Char(string='Card First Six Digits')
    card_last_four_digits = fields.Char(string='Card Last Four Digits')
    statement_descriptor = fields.Char(string='Statement Descriptor')
    coupon_amount = fields.Float(string='Coupon Amount')
    overpaid_amount = fields.Float(string='Overpaid Amount')
    payer_id = fields.Char(string='Payer ID')
    issuer_id = fields.Char(string='Issuer ID')
    marketplace_fee = fields.Float(string='Marketplace Fee')

    def _get_config( self, config=None ):
        config = config or (self and self.order_id and self.order_id._get_config(config=config))
        return config

class mercadolibre_buyers(models.Model):
    _name = "mercadolibre.buyers"
    _description = "Compradores en MercadoLibre"

    name = fields.Char(string='Name',index=True)
    buyer_id = fields.Char(string='Buyer ID',index=True)
    nickname = fields.Char(string='Nickname',index=True)
    email = fields.Char(string='Email',index=True)
    phone = fields.Char( string='Phone')
    alternative_phone = fields.Char( string='Alternative Phone')
    first_name = fields.Char( string='First Name',index=True)
    last_name = fields.Char( string='Last Name',index=True)
    billing_info = fields.Char( string='Billing Info')

    billing_info_doc_type = fields.Char( string='Billing Info Doc Type')
    billing_info_doc_number = fields.Char( string='Billing Info Doc Number')
    billing_info_tax_type = fields.Char( string='Billing Info Tax Type')

    billing_info_business_name = fields.Char( string='Billing Info Business Name')
    billing_info_street_name = fields.Char( string='Billing Info Street Name')
    billing_info_street_number = fields.Char( string='Billing Info Street Number')
    billing_info_city_name = fields.Char( string='Billing Info City Name')
    billing_info_state_name = fields.Char( string='Billing Info State Name')
    billing_info_zip_code = fields.Char( string='Billing Info Zip Code')

    billing_info_economic_activity = fields.Char(string='Billing Info Economic Activity')
    billing_info_neighborhood = fields.Char(string='Billing Info Neighborhood')
    billing_info_vat_discriminating_billing = fields.Char(string='Billing Info Vat Discriminating Billing')
    billing_info_invoice_type = fields.Char(string='Billing Info Invoice Type')

    _unique_buyer_id = versions.UniqueIndex('buyer_id', message='Meli Buyer id already exists!')

class mercadolibre_orders_update(models.TransientModel):
    _name = "mercadolibre.orders.update"
    _description = "Update Order"

    def order_update(self, context=None):
        context = context or self.env.context

        warningobj = self.env['meli.warning']
        orders_obj = self.env['mercadolibre.orders']
        sorders_obj = self.env['sale.order']

        if ("active_model" in context and context["active_model"]=="mercadolibre.orders"):
            orders_ids = ('active_ids' in context and context['active_ids']) or []

        if ("active_model" in context and context["active_model"]=="sale.order"):
            orders_ids = []
            sorders_ids = ('active_ids' in context and context['active_ids']) or []
            for soid in sorders_ids:
                sorder = sorders_obj.browse(soid)
                if sorder and sorder.meli_order:
                    orders_ids.append(sorder.meli_order.id)


        Autocommit(self, False)
        rets = []
        try:

            for order_id in orders_ids:

                #_logger.info(order_update: %s " % (order_id) )

                order = orders_obj.browse(order_id)
                ret = order.orders_update_order()
                #_logger.info("order_update ret:"+str(ret))
                if ret and type(ret)==dict and 'name' in ret:
                    rets.append(ret)
                if ret and len(ret) and type(ret)==list and ret[0] and "error" in ret[0]:
                    rets.append(ret[0])
        except Exception as e:
            _logger.info("order_update > Error actualizando ordenes")
            _logger.error(e, exc_info=True)
            MeliRollback( self )

        #Add warning with all filters errors:
        if rets and len(rets)>0:
            #return warning.
            return warningobj.info( title='MELI WARNING', message = "update order errors: "+str(len(rets)), message_html = str(rets))

        return {}


class mercadolibre_orders_update_invoice(models.TransientModel):
    _name = "mercadolibre.orders.update.invoice"
    _description = "Update Order Invoice"

    def order_update_invoice(self, context=None):
        context = context or self.env.context
        orders_ids = ('active_ids' in context and context['active_ids']) or []
        orders_obj = self.env['mercadolibre.orders']

        Autocommit(self, False)
        try:

            for order_id in orders_ids:

                #_logger.info("order_update: %s " % (order_id) )

                order = orders_obj.browse(order_id)
                #order.orders_update_order()
                if order:
                    order.orders_get_invoice()

        except Exception as e:
            _logger.info("order_update > Error actualizando factura ordenes")
            _logger.error(e, exc_info=True)
            MeliRollback( self )

        return {}

class sale_order_cancel_wiz_meli(models.TransientModel):
    _name = "sale.order.cancel.wiz.meli"
    _description = "Cancel Order"

    cancel_blocked = fields.Boolean(string="Desbloquear y Cancelar", default=True)

    def cancel_order(self, context=None):
        context = context or self.env.context
        orders_ids = ('active_ids' in context and context['active_ids']) or []
        orders_obj = self.env['sale.order']

        Autocommit(self, False)
        try:

            for order_id in orders_ids:

                #_logger.info("cancel_order: %s " % (order_id) )

                order = orders_obj.browse(order_id)
                is_locked = (order and order.state in ["done"]) or ("locked" in order._fields and order.locked)
                if (is_locked and self.cancel_blocked):
                    #asd
                    #_logger.info("cancel_order: unblock")
                    order.action_unlock()
                    order.with_context(disable_cancel_warning=disable_cancel_warning_enabled).action_cancel()

                if (order and order.state in ["draft","sale","sent"]) and not is_locked:
                    order.with_context(disable_cancel_warning=disable_cancel_warning_enabled).action_cancel()

        except Exception as e:
            #_logger.info("order_update > Error cancelando ordenes")
            _logger.error(e, exc_info=True)
            MeliRollback( self )

        return {}
