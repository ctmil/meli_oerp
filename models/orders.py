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

from odoo import fields, osv, models, api
import logging
from .meli_oerp_config import *

from ..melisdk.meli import Meli

import json

import logging
_logger = logging.getLogger(__name__)

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
from .versions import *

class sale_order_line(models.Model):
    _inherit = "sale.order.line"

    meli_order_item_id = fields.Char('Meli Order Item Id')
    meli_order_item_variation_id = fields.Char('Meli Order Item Variation Id')

sale_order_line()

class sale_order(models.Model):
    _inherit = "sale.order"

    meli_order_id =  fields.Char(string='Meli Order Id',index=True)
    meli_orders = fields.Many2many('mercadolibre.orders',string="ML Orders")

    def _meli_status_brief(self):
        for order in self:
            morder = order.meli_orders and order.meli_orders[0]
            if morder:
                morder.update_order_status()
                order.meli_status = morder.status
                order.meli_status_detail = morder.status_detail
                order.meli_status_brief = str(morder.status)+" ship-"+( (morder.shipment_status and str(morder.shipment_status)) or "" ) + ( (morder.shipment_substatus and str(morder.shipment_substatus)) or "")
            else:
                order.meli_status_brief = "-"
                order.meli_status =  order.meli_status
                order.meli_status_detail = order.meli_status_detail

    def search_meli_status_brief(self, operator, value):
        _logger.info("search_meli_status_brief")
        _logger.info(operator)
        _logger.info(value)
        if operator == 'ilike':
            #name = self.env.context.get('name', False)
            #if name is not False:
            id_list = []
            _logger.info(self.env.context)
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
        ], string='Order Status')

    meli_status_brief = fields.Char(string="Meli Status Brief", compute="_meli_status_brief", search=search_meli_status_brief, store=False, index=True)

    meli_status_detail = fields.Text(string='Status detail, in case the order was cancelled.')
    meli_date_created = fields.Datetime('Meli Creation date')
    meli_date_closed = fields.Datetime('Meli Closing date')

#        'meli_order_items': fields.one2many('mercadolibre.order_items','order_id','Order Items' ),
#        'meli_payments': fields.one2many('mercadolibre.payments','order_id','Payments' ),
    meli_shipping = fields.Text(string="Shipping")

    meli_total_amount = fields.Float(string='Total amount')
    meli_shipping_cost = fields.Float(string='Shipping Cost',help='Gastos de envío')
    meli_shipping_list_cost = fields.Float(string='Shipping List Cost',help='Gastos de envío, costo de lista/interno')
    meli_paid_amount = fields.Float(string='Paid amount',help='Paid amount (include shipping cost)')
    meli_fee_amount = fields.Float(string='Fee amount',help="Comisión")
    meli_currency_id = fields.Char(string='Currency ML')
#        'buyer': fields.many2one( "mercadolibre.buyers","Buyer"),
#       'meli_seller': fields.text( string='Seller' ),
    meli_shipping_id =  fields.Char('Meli Shipping Id')
    meli_shipment = fields.Many2one('mercadolibre.shipment',string='Meli Shipment Obj')
    meli_shipment_logistic_type = fields.Char(string="Logistic Type",index=True)

    def action_confirm(self):
        #_logger.info("meli order action_confirm: " + str(self.mapped("name")) )
        res = super(sale_order,self).action_confirm()
        try:
            for order in self:
                if(order.meli_order_id):
                    for line in order.order_line:
                        #_logger.info(line)
                        #_logger.info(line.is_delivery)
                        #_logger.info(line.price_unit)
                        if line.is_delivery and line.price_unit<=0.0:
                            #_logger.info(line)
                            line.write({ "qty_to_invoice": 0.0 })
                            #_logger.info(line.qty_to_invoice)
                            pass;
        except:
            pass;

        try:
            company = self.env.user.company_id
            _logger.info("Company: "+str(company))
            _logger.info("Order done: company.mercadolibre_cron_post_update_stock: "+str(company.mercadolibre_cron_post_update_stock))
            for order in self:
                for line in order.order_line:
                    if (company.mercadolibre_cron_post_update_stock):
                        if line.product_id and line.product_id.meli_id and line.product_id.meli_pub:
                            _logger.info("Order done: product_post_stock: "+str(line.product_id.meli_id))
                            line.product_id.product_post_stock()
        except:
            pass;
        return res

    def action_done(self):
        _logger.info("meli order action done: " + str(self.mapped("name")) )
        res = super(sale_order,self).action_done()
        try:
            for order in self:
                if(order.meli_order_id):
                    for line in order.order_line:
                        #_logger.info(line)
                        #_logger.info(line.is_delivery)
                        #_logger.info(line.price_unit)
                        if line.is_delivery and line.price_unit<=0.0:
                            #_logger.info(line)
                            line.write({ "qty_to_invoice": 0.0 })
                            #_logger.info(line.qty_to_invoice)
                            pass;
        except:
            pass;

        try:
            company = self.env.user.company_id
            _logger.info("Company: "+str(company))
            _logger.info("Order done: company.mercadolibre_cron_post_update_stock: "+str(company.mercadolibre_cron_post_update_stock))
            for order in self:
                for line in order.order_line:
                    if (company.mercadolibre_cron_post_update_stock):
                        if line.product_id and line.product_id.meli_id and line.product_id.meli_pub:
                            _logger.info("Order done: product_post_stock: "+str(line.product_id.meli_id))
                            line.product_id.product_post_stock()
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

        if total_config in ['manual']:
            #resolve always as conflict
            return 0

        if total_config in ['manual_conflict']:

            if abs(self.meli_total_amount - self.meli_paid_amount)<1.0:
                if ( meli_shipment and meli_shipment.shipping_cost>0 and meli_shipment.shipping_list_cost>0 ):
                    return 0
                return self.meli_paid_amount
            else:
                #conflict if do not match
                if ( meli_shipment and meli_shipment.shipping_cost>0 and meli_shipment.shipping_list_cost>0 ):
                    if ( self.meli_total_amount + self.shipping_cost - self.meli_paid_amount )<1.0:
                        return self.meli_paid_amount
                return 0

        if total_config in ['paid_amount']:
            return self.meli_paid_amount

        if total_config in ['total_amount']:
            return self.meli_total_amount

        return 0

    def meli_confirm_order( self, meli=None, config=None ):
        res = {}
        if ( (self.state=="draft" or self.state=="sent") and self.meli_status=="paid"):
            _logger.info("paid_confirm ok! confirming sale")
            self.action_confirm()
        return res

    def meli_create_invoice( self, meli=None, config=None):
        res = {}
        if so.state in ['sale','done']:
            _logger.info("paid_confirm with invoice ok! create invoice")
            self.action_invoice_create()
        return res

    def meli_deliver( self, meli=None, config=None, data=None ):
        res = {}
        if (self.state=="sale" or self.state=="done"):
            #spick = stock_picking.search([('order_id','=',self.id)])
            _logger.info("paid_delivered ok! delivering")
            if self.picking_ids:
                for spick in self.picking_ids:
                    #_logger.info(str(spick)+":"+str(spick.state))

                    try:
                        if (spick.state in ['confirmed','waiting','draft']):
                            #_logger.info("action_assign")
                            res = spick.action_assign()
                            #_logger.info("action_assign res:"+str(res)+" state:"+str(spick.state))

                        if (spick.move_line_ids):
                            _logger.info(spick.move_line_ids)
                            if (len(spick.move_line_ids)>=1):
                                for pop in spick.move_line_ids:
                                    _logger.info(pop)
                                    if (pop.qty_done==0.0 and pop.product_qty>=0.0):
                                        pop.qty_done = pop.product_qty
                                #_logger.info("do_new_transfer")

                                if (spick.state in ['assigned']):
                                    spick.button_validate()
                    except Exception as e:
                        _logger.error("stock pick button_validate error"+str(e))
                        res = { 'error': str(e) }
                        pass;
        return res

    def confirm_ml( self, meli=None, config=None ):
        try:
            #_logger.info("meli_oerp confirm_ml")
            company = (config and 'company_id' in config._fields and config.company_id) or self.env.user.company_id
            config = config or company
            res = {}

            stock_picking = self.env["stock.picking"]

            #cancelling with no conditions, here because paid_amount is 0, dont use confirm_cond
            if (self.meli_status=="cancelled"):
                if (self.state in ["draft","sale","sent"]):
                    self.action_cancel()
                    _logger.info("Confirm Order Cancelled")
                return res

            amount_to_invoice = self.meli_amount_to_invoice( meli=meli, config=config )
            confirm_cond = (amount_to_invoice > 0) and abs( float(amount_to_invoice) - self.amount_total ) < 1.1
            if not confirm_cond:
                return {'error': "Condition not met: meli_paid_amount and amount_total doesn't match"}

                
            if (self.meli_shipment_logistic_type and "fulfillment" in self.meli_shipment_logistic_type):
                
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
            _logger.info("Confirm Order Exception")
            _logger.error(e, exc_info=True)
            return { 'error': str(e) }
            pass
        #_logger.info("meli_oerp confirm_ml ended.")
        return res

    def meli_fix_team( self, meli=None, config=None ):
        company = (config and "company_id" in config._fields and config.company_id) or self.env.user.company_id

        seller_team = (config and config.mercadolibre_seller_team) or None
        seller_user = (config and config.mercadolibre_seller_user) or None

        #_logger.info("meli_fix_team: company: "+str(company.name)+" seller_team:"+str(seller_team and seller_team.name))

        so = self
        if not so:
            return None

        team_id = so.sudo().team_id
        user_id = so.sudo().user_id

        #_logger.info("meli_fix_team: so.team_id: "+str(team_id and team_id.name))

        if (team_id and team_id.company_id.id != company.id) or not team_id:
            if (seller_team and seller_team.company_id.id == company.id):
                if team_id.id!=seller_team.id:
                    so.sudo().write( { 'team_id': seller_team.id } )
            else:
                #unassign, wrong company team
                so.sudo().write( { 'team_id': None } )

        if (user_id and seller_user and user_id.id!=seller_user.id) or not user_id:
            if seller_user:
                so.sudo().write( { 'user_id': seller_user.id } )
            else:
                so.sudo().write( { 'user_id': None } )

    def meli_oerp_update( self ):
        res = {}
        for order in self:
            if order.meli_orders:
                res = order.meli_orders[0].orders_update_order()
        return res

    _sql_constraints = [
        ('unique_meli_order_id', 'unique(meli_order_id)', 'Meli Order id already exists!')
    ]
sale_order()

class mercadolibre_orders(models.Model):
    _name = "mercadolibre.orders"
    _description = "Pedidos en MercadoLibre"

    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']

    def fix_locals(self,  Receiver={}, Buyer={} ):
        updated = {}

        country_id = self.country( Receiver=Receiver, Buyer=Buyer )
        state_id = self.state( country_id, Receiver=Receiver, Buyer=Buyer )
        city_name = self.city( Receiver=Receiver, Buyer=Buyer )

        if "l10n_co_cities.city" in self.env:
            city = self.env["l10n_co_cities.city"].search([('city_name','ilike',city_name)])

            if not city and state_id:
                _logger.warning("City not found for: "+str(city_name) + " state_id: "+str(state_id))
                _logger.info("Search FIRST city for state: " + str(state_id))
                city = self.env["l10n_co_cities.city"].search([('state_id','=',state_id)])

            if city:
                _logger.info(city)
                city = city[0]

                _logger.info("Founded cities for state: " + str(state_id)+ " city_name: "+str(city.city_name))

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
            full_street = (('STREET_NAME' in binfo and binfo['STREET_NAME']) or '')
            full_street+= (('STREET_NUMBER' in binfo and binfo['STREET_NUMBER']) or '')
        return full_street

    def city(self,  Receiver={}, Buyer={} ):
        full_city = ''
        if (Receiver and 'city' in Receiver):
            full_city = Receiver['city']['name']
        if ( Buyer and 'billing_info' in Buyer and 'CITY_NAME' in Buyer['billing_info'] ):
            binfo = Buyer['billing_info']
            full_city = (('CITY_NAME' in binfo and binfo['CITY_NAME']) or '')
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
            full_state = (('CITY_NAME' in binfo and binfo['CITY_NAME']) or '')
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

        return ret

    def buyer_full_name( self, Buyer={}):

        full_name = ("name" in Buyer and Buyer['name']) or ""

        first_name = str( ('first_name' in Buyer and Buyer['first_name'] ) or '' )
        last_name = str( ('last_name' in Buyer and Buyer['last_name']) or '' )

        if first_name and last_name:
            last_name = ' '+last_name

        full_name = first_name + last_name

        business_name = ('business_name' in Buyer and Buyer['business_name'])
        full_name = business_name or full_name or ''

        return full_name

    def get_billing_info( self, order_id=None, meli=None, data=None ):
        order_id = order_id or (data and 'id' in data and data['id']) or (self and self.order_id)
        Buyer = (data and 'buyer' in data and data['buyer']) or {}
        _billing_info = ('billing_info' in Buyer and Buyer['billing_info']) or {}
        if meli and order_id:
            response = meli.get("/orders/"+str(order_id)+"/billing_info", {'access_token':meli.access_token})
            if response:
                biljson = response.json()
                #_logger.info("get_billing_info: "+str(biljson))
                _billing_info = (biljson and 'billing_info' in biljson and biljson['billing_info']) or {}
                if "additional_info" in _billing_info:
                    adds = _billing_info["additional_info"]
                    for add in adds:
                        _billing_info[add["type"]] = add["value"]
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
        if "alternative_phone" in buyer_json:
            phone_json = buyer_json["alternative_phone"]
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

    def _set_product_unit_price( self, product_related_obj, Item, config=None ):

        upd_line = {
            "price_unit": ml_product_price_conversion( self, product_related_obj=product_related_obj, price=Item['unit_price'], config=config )
        }
        #else:
        #    if ( float(Item['unit_price']) == product_template.lst_price and not self.env.user.has_group('sale.group_show_price_subtotal')):
        #        upd_line["tax_id"] = None
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

        order_fields = {
            'name': "MO [%s]" % ( str(order_json["id"]) ),
            'company_id': company.id,
            'seller_id': seller_id,
            'order_id': '%s' % (str(order_json["id"])),
            'status': order_json["status"],
            'status_detail': order_json["status_detail"] or '' ,
            'fee_amount': 0.0,
            'total_amount': order_json["total_amount"],
            'paid_amount': order_json["paid_amount"],
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

        if meli.access_token=="PASIVA":
            if (self):
                order_fields["fee_amount"] = self.payments and self.payments[0].fee_amount
                if (self.sale_order):
                    self.sale_order.meli_fee_amount = order_fields["fee_amount"]
        return order_fields

    def prepare_sale_order_vals( self, meli=None, order_json=None, config=None, sale_order=None, shipment=None ):
        if not order_json:
            return {}
        meli_order_fields = {
            #TODO: "add parameter for":
            'name': "ML %s" % ( str(order_json["id"]) ),
            #'partner_id': partner_id.id,
            #'pricelist_id': plistid.id,
            'meli_order_id': '%s' % (str(order_json["id"])),
            'meli_status': ("status" in order_json and order_json["status"]) or '',
            'meli_status_detail': ("status_detail" in order_json and order_json["status_detail"]) or '' ,
            'meli_total_amount': ("total_amount" in order_json and order_json["total_amount"]),
            'meli_paid_amount': ("paid_amount" in order_json and order_json["paid_amount"]),
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
        product_related = False
        product_obj = self.env['product.product']
        if not meli_item:
            return None
        meli_id = meli_item['id']
        meli_id_variation = ("variation_id" in meli_item and meli_item['variation_id'])
        meli_seller_sku = "seller_sku" in meli_item and meli_item["seller_sku"]
        if meli_seller_sku:
            product_related = product_obj.search([ ('default_code','=ilike',meli_seller_sku)])
            #search by barcode
            if ((not product_related) or len(product_related)>1):
                product_related = product_obj.search([ ('barcode','=ilike',meli_seller_sku)])

        if ((not product_related) or len(product_related)>1):
            if (meli_id_variation):
                product_related = product_obj.search([ ('meli_id','=',meli_id), ('meli_id_variation','=',meli_id_variation) ])
            else:
                product_related = product_obj.search([('meli_id','=', meli_id)])

        return product_related

    def update_partner_billing_info( self, partner_id, meli_buyer_fields, Receiver):

        partner_update = {}

        if not partner_id or not meli_buyer_fields:
            return partner_update

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

    def orders_update_order_json( self, data, context=None, config=None, meli=None ):

        oid = data["id"]
        order_json = data["order_json"]
        #_logger.info( "data:" + str(data) )
        context = context or self.env.context
        #_logger.info( "context:" + str(context) )
        company = (config and "company_id" in config._fields and config.company_id) or self.env.user.company_id
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
        if config.mercadolibre_pricelist:
            plistid = config.mercadolibre_pricelist
        else:
            plistids = pricelist_obj.search([])[0]
            if plistids:
                plistid = plistids

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
            _logger.info("order_json: "+str(order_json))

        order_fields = self.prepare_ml_order_vals( order_json=order_json, meli=meli, config=config )

        if (    "mercadolibre_filter_order_datetime_start" in config._fields
                and "date_closed" in order_fields
                and config.mercadolibre_filter_order_datetime_start
                and config.mercadolibre_filter_order_datetime_start>parse(order_fields["date_closed"]) ):
            error = { "error": "orden filtrada por fecha START > " + str(order_fields["date_closed"]) + " inferior a "+str(ml_datetime(config.mercadolibre_filter_order_datetime_start)) }
            _logger.info( "orders_update_order_json > filter:" + str(error) )
            return error


        if (    "mercadolibre_filter_order_datetime" in config._fields
                and "date_closed" in order_fields
                and config.mercadolibre_filter_order_datetime
                and config.mercadolibre_filter_order_datetime>parse(order_fields["date_closed"]) ):
            error = { "error": "orden filtrada por FROM > " + str(order_fields["date_closed"]) + " inferior a "+str(ml_datetime(config.mercadolibre_filter_order_datetime)) }
            _logger.info( "orders_update_order_json > filter:" + str(error) )
            return error

        if (    "mercadolibre_filter_order_datetime_to" in config._fields
                and "date_closed" in order_fields
                and config.mercadolibre_filter_order_datetime_to
                and config.mercadolibre_filter_order_datetime_to<parse(order_fields["date_closed"]) ):
            error = { "error": "orden filtrada por fecha TO > " + str(order_fields["date_closed"]) + " superior a "+str(ml_datetime(config.mercadolibre_filter_order_datetime_to)) }
            _logger.info( "orders_update_order_json > filter:" + str(error) )
            return error

        _logger.info("orders_update_order_json > data "+str(data['id']) + " json:" + str(data['order_json']['id']) )

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
            Buyer['billing_info'] = self.get_billing_info(order_id=order_json['id'],meli=meli,data=order_json)
            Buyer['first_name'] = ('first_name' in Buyer and Buyer['first_name']) or ('FIRST_NAME' in Buyer['billing_info'] and Buyer['billing_info']['FIRST_NAME']) or ''
            Buyer['last_name'] = ('last_name' in Buyer and Buyer['last_name']) or ('LAST_NAME' in Buyer['billing_info'] and Buyer['billing_info']['LAST_NAME']) or ''
            Buyer['business_name'] = ('business_name' in Buyer and Buyer['business_name']) or ('BUSINESS_NAME' in Buyer['billing_info'] and Buyer['billing_info']['BUSINESS_NAME']) or ''
            Receiver = False
            if ('shipping' in order_json and order_json['shipping']):
                if ('receiver_address' in order_json['shipping']):
                    Receiver = order_json['shipping']['receiver_address']
                elif ('id' in order_json['shipping']):
                    Shipment = self.env["mercadolibre.shipment"].search([('shipping_id','=',order_json['shipping']["id"])],limit=1)
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
            meli_buyer_fields = {
                'name': self.buyer_full_name(Buyer),
                'street': self.street(Receiver,Buyer),
                'city': self.city(Receiver,Buyer),
                'country_id': self.country(Receiver,Buyer),
                'state_id': self.state(self.country(Receiver,Buyer),Receiver,Buyer),
                'phone': self.full_phone( Buyer ),
                #'email': Buyer['email'],
                'meli_buyer_id': Buyer['id'],
            }
            meli_buyer_fields.update(self.fix_locals(Receiver=Receiver,Buyer=Buyer))
            if company:
                meli_buyer_fields["lang"] =  company.partner_id.lang

            buyer_fields = {
                'buyer_id': Buyer['id'],
                'nickname': Buyer['nickname'],
                'email': ('email' in Buyer and Buyer['email']) or "",
                'phone': self.full_phone( Buyer ),
                'alternative_phone': self.full_alt_phone( Buyer ),
                'first_name': ('first_name' in Buyer and Buyer['first_name']) or "",
                'last_name': ('last_name' in Buyer and Buyer['last_name']) or "",
                'billing_info': self.billing_info(Buyer['billing_info']),
            }
            buyer_fields.update(self.buyer_additional_info(Buyer['billing_info']))
            buyer_fields.update({'name': self.buyer_full_name(Buyer) })

            buyer_ids = buyers_obj.search([  ('buyer_id','=',buyer_fields['buyer_id'] ) ] )
            buyer_id = 0
            if (buyer_ids==False or len(buyer_ids)==0):
                _logger.info( "creating buyer")
                _logger.info(buyer_fields)
                buyer_id = buyers_obj.create(( buyer_fields ))
            else:
                buyer_id = buyer_ids
                buyer_id.write( ( buyer_fields ) )
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


                #Chile/Arg/Latam
                if ( ('doc_type' in Buyer['billing_info']) and ('l10n_latam_identification_type_id' in self.env['res.partner']._fields) ):
                    doc_type_id = self.env["l10n_latam.identification.type"].search([('country_id','=',company.country_id.id),('name','ilike',Buyer['billing_info']['doc_type'])],limit=1)
                    if (Buyer['billing_info']['doc_type']=="RUT"):
                        meli_buyer_fields['l10n_latam_identification_type_id'] = (doc_type_id and doc_type_id.id) or 4
                    if (Buyer['billing_info']['doc_type']=="RUN"):
                        meli_buyer_fields['l10n_latam_identification_type_id'] = (doc_type_id and doc_type_id.id) or 5
                    if (doc_type_id):
                        meli_buyer_fields['l10n_latam_identification_type_id'] = (doc_type_id and doc_type_id.id)

                    if (company.country_id.code == "AR" and 'l10n_ar.afip.responsibility.type' in self.env):
                        afipid = self.env['l10n_ar.afip.responsibility.type'].search([('code','=',5)]).id
                        meli_buyer_fields["l10n_ar_afip_responsibility_type_id"] = afipid
                        if ('TAXPAYER_TYPE_ID' in Buyer['billing_info'] and Buyer['billing_info']['TAXPAYER_TYPE_ID'] and Buyer['billing_info']['TAXPAYER_TYPE_ID']=="IVA Responsable Inscripto"):
                            afipid = self.env['l10n_ar.afip.responsibility.type'].search([('code','=',1)]).id
                            meli_buyer_fields["l10n_ar_afip_responsibility_type_id"] = afipid
                        if ('TAXPAYER_TYPE_ID' in Buyer['billing_info'] and Buyer['billing_info']['TAXPAYER_TYPE_ID'] and Buyer['billing_info']['TAXPAYER_TYPE_ID']=="IVA Sujeto Exento"):
                            afipid = self.env['l10n_ar.afip.responsibility.type'].search([('code','=',4)]).id
                            meli_buyer_fields["l10n_ar_afip_responsibility_type_id"] = afipid
                        if ('TAXPAYER_TYPE_ID' in Buyer['billing_info'] and Buyer['billing_info']['TAXPAYER_TYPE_ID'] and Buyer['billing_info']['TAXPAYER_TYPE_ID']=="Responsable Monotributo"):
                            afipid = self.env['l10n_ar.afip.responsibility.type'].search([('code','=',6)]).id
                            meli_buyer_fields["l10n_ar_afip_responsibility_type_id"] = afipid

                    meli_buyer_fields['vat'] = Buyer['billing_info']['doc_number']

                #Chile YNext
                if ( ('doc_type' in Buyer['billing_info']) and ('dte_email' in self.env['res.partner']._fields)):

                    meli_buyer_fields['dte_email'] = 'nomail@fake.com'
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
                    sep_millon = "."
                    #sep_millon = ""
                    if (len(vatn)==9):
                        vatn = vatn[:2]+str(sep_millon)+vatn[2:5]+""+vatn[5:8]+"-"+vatn[8:9]
                        isb = float(vatn[:2])
                        _logger.info("Chile VAT: is business:"+str(isb))
                        is_business = (isb >= 50)
                        _logger.info("Chile VAT: is business? "+str(is_business))
                    if (len(vatn)==8):
                        vatn = vatn[:1]+str(sep_millon)+vatn[1:4]+""+vatn[4:7]+"-"+vatn[7:8]
                    meli_buyer_fields['vat'] = vatn

                    if "l10n_cl_sii_taxpayer_type" in self.env['res.partner']._fields:
                        if is_business:
                            meli_buyer_fields['l10n_cl_sii_taxpayer_type'] = "1"
                            meli_buyer_fields['company_type'] = "company"
                        else:
                            meli_buyer_fields['l10n_cl_sii_taxpayer_type'] = "3"
                            meli_buyer_fields['company_type'] = "person"



                if ( ('doc_type' in Buyer['billing_info']) and ('document_type_id' in self.env['res.partner']._fields) and ('document_number' in self.env['res.partner']._fields) ):

                    if (Buyer['billing_info']['doc_type']=="RUT"):
                        meli_buyer_fields['document_type_id'] = self.env['sii.document_type'].search([('code','=','RUT')],limit=1).id
                    elif (Buyer['billing_info']['doc_type']):
                        meli_buyer_fields['document_type_id'] = self.env['sii.document_type'].search([('code','=',Buyer['billing_info']['doc_type'])],limit=1).id

                    meli_buyer_fields['document_number'] = Buyer['billing_info']['doc_number']

                    meli_buyer_fields['vat'] = 'CL'+str(Buyer['billing_info']['doc_number'])
                    #meli_buyer_fields['email'] = str(Buyer['email'])

                    ('activity_description' in self.env['res.partner']._fields) and meli_buyer_fields.update({"activity_description": self.env["sii.activity.description"].search([('name','=','NCP')],limit=1).id })

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
                            _logger.info("tribute_id: tributeIVA01:"+str(tributeIVA01 and tributeIVA01.name))

                    fisc_noresp = False
                    fisc_simple = False
                    if ("fiscal_responsability_ids" in self.env['res.partner']._fields ):
                        fisc_noresp = self.env['dian.fiscal.responsability'].search([("name","like","No responsable")],limit=1)
                        fisc_simple = self.env['dian.fiscal.responsability'].search([("name","like","Simple")],limit=1)
                        _logger.info("fiscal_responsability_ids: fisc_noresp:"+str(fisc_noresp and fisc_noresp.name)+" fisc_simple:"+str(fisc_simple and fisc_simple.name))



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

                    if ("property_payment_term_id" in self.env['res.partner']._fields):
                        meli_buyer_fields['property_payment_term_id'] = config.mercadolibre_payment_term and config.mercadolibre_payment_term.id

            partner_invoice_id = None
            partner_invoice_meli_order_id = str(order_json['pack_id'] or order_json['id'])
            partner_id = respartner_obj.search([  ('meli_buyer_id','=',buyer_fields['buyer_id'] ) ], limit=1 )
            partner_invoice_id = partner_id

            partner_ids = respartner_obj.search([  ('meli_buyer_id','=',buyer_fields['buyer_id'] ) ] )
            if (len(partner_ids)>0):
                partner_id = partner_ids[0]
            if ("fe_regimen_fiscal" in self.env['res.partner']._fields):
                if (partner_id and not partner_id.fe_regimen_fiscal):
                    meli_buyer_fields['fe_regimen_fiscal'] = '49';
                else:
                    meli_buyer_fields['fe_regimen_fiscal'] = '49';

            if (partner_id and "vat" in meli_buyer_fields and meli_buyer_fields["vat"]!=str(partner_id.vat)):
                #CREAR INVOICE CONTACT
                #_logger.info("Partner Invoice is NEW: "+str(partner_invoice_meli_order_id)+" VAT:"+str(meli_buyer_fields["vat"])+ " vs "+str(partner_id.vat))
                partner_invoice_id = respartner_obj.search([  ('meli_order_id','=',partner_invoice_meli_order_id ) ], limit=1 )
                partner_update = {}
                partner_update.update( meli_buyer_fields )
                partner_update.update({
                    'meli_order_id': partner_invoice_meli_order_id,
                    'type': 'invoice',
                    "parent_id": partner_id.id,
                    "meli_buyer_id": None,
                })

                if partner_invoice_id:
                    partner_update = self.update_partner_billing_info( partner_id=partner_invoice_id, meli_buyer_fields=partner_update, Receiver=Receiver )
                    if partner_update:
                        try:
                            _logger.info("Partner Invoice Updating: "+str(partner_update))
                            partner_invoice_id.write(partner_update)
                        except Exception as e:
                            _logger.info("orders_update_order > Error actualizando Partner Invoice Id:"+str(e))
                            _logger.error(e, exc_info=True)
                            pass;
                else:
                    try:
                        partner_invoice_id = respartner_obj.create(( partner_update ))
                        if partner_invoice_id:
                            #partner_update = self.update_partner_billing_info( partner_id=partner_invoice_id, meli_buyer_fields=partner_update )
                            #partner_invoice_id.write(partner_update)
                            _logger.info("Partner Invoice created: "+str(partner_update))

                    except Exception as e:
                        _logger.info("orders_update_order > Error creando Partner Invoice Id:"+str(e))
                        _logger.error(e, exc_info=True)
                        pass;


            if not partner_id:
                #_logger.info( "creating partner:" + str(meli_buyer_fields) )
                try:
                    partner_id = respartner_obj.create(( meli_buyer_fields ))
                    partner_invoice_id = partner_id
                except Exception as e:
                    _logger.info("orders_update_order > Error creando Partner:"+str(e))
                    _logger.error(e, exc_info=True)
                    pass;
            elif (partner_id and "meli_update_forbidden" in partner_id._fields and not partner_id.meli_update_forbidden):
                #_logger.info("Updating partner")
                #TODO: _logger.info("Updating partner (do not update principal, always create new one)")
                #_logger.info(meli_buyer_fields)
                #complete country at most:
                partner_update = {}

                partner_update = self.update_partner_billing_info( partner_id=partner_id, meli_buyer_fields=meli_buyer_fields, Receiver=Receiver )

                if partner_update:
                    _logger.info("Updating partner: "+str(partner_update))
                    try:
                        partner_id.write(partner_update)
                    except Exception as e:
                        _logger.info("orders_update_order > Error actualizando Partner:"+str(e))
                        _logger.error(e, exc_info=True)
                        pass;


                if (partner_id.email and (partner_id.email==buyer_fields["email"] or "mercadolibre.com" in partner_id.email)):
                    #eliminar email de ML que no es valido
                    meli_buyer_fields["email"] = ''
                #crear nueva direccion de entrega
                #partner_id.write( meli_buyer_fields )

            if (partner_id):
                partner_shipping_id = self.env["mercadolibre.shipment"].partner_delivery_id( partner_id=partner_id, Receiver=Receiver)

            if (partner_id):
                if ("fe_habilitada" in self.env['res.partner']._fields):
                    try:
                        partner_id.write( { "fe_habilitada": True } )
                    except:
                        _logger.error("No se pudo habilitar la Facturacion Electronica para este usuario")

            if order and buyer_id:
                return_id = order.write({'buyer':buyer_id.id})
        else:
            _logger.error("Buyer not fetched!")

        if (not partner_id):
            _logger.error("No partner founded or created for ML Order" )
            return {'error': 'No partner founded or created for ML Order' }
        #process base order fields
        meli_order_fields = self.prepare_sale_order_vals( order_json=order_json, meli=meli, config=config, sale_order=sorder )
        meli_order_fields.update({
            'partner_id': partner_id.id,
            'partner_invoice_id': (partner_invoice_id and partner_invoice_id.id),
            'pricelist_id': plistid.id,
        })
        if partner_shipping_id:
            meli_order_fields['partner_shipping_id'] = partner_shipping_id.id

        if ("pack_id" in order_json and order_json["pack_id"]):
            meli_order_fields['name'] = "ML %s" % ( str(order_json["pack_id"]) )
            #meli_order_fields['pack_id'] = order_json["pack_id"]

        if ('account.payment.term' in self.env):
            inmediate_or_not = ('mercadolibre_payment_term' in config._fields and config.mercadolibre_payment_term) or ('mercadolibre_payment_term' in company._fields and company.mercadolibre_payment_term) or None
            meli_order_fields["payment_term_id"] = (inmediate_or_not and inmediate_or_not.id)

        if ("shipping" in order_json and order_json["shipping"]):
            order_fields['shipping'] = self.pretty_json( id, order_json["shipping"] )
            meli_order_fields['meli_shipping'] = self.pretty_json( id, order_json["shipping"] )

            if ("logistic_type" in order_json["shipping"]):
                order_fields['shipment_logistic_type'] = order_json["shipping"]["logistic_type"]
                meli_order_fields["meli_shipment_logistic_type"] = order_json["shipping"]["logistic_type"]

            if ("cost" in order_json["shipping"]):
                order_fields["shipping_cost"] = float(order_json["shipping"]["cost"])
                meli_order_fields["meli_shipping_cost"] = float(order_json["shipping"]["cost"])

            if ("id" in order_json["shipping"]):
                order_fields['shipping_id'] = order_json["shipping"]["id"]
                meli_order_fields['meli_shipping_id'] = order_json["shipping"]["id"]

        #create or update order
        if (order and order.id):
            #_logger.info("Updating order: %s" % (order.id))
            order.write( order_fields )
        else:
            _logger.info("Adding new order: " )
            #_logger.info(order_fields)
            order = order_obj.create( (order_fields))

        if (sorder and sorder.id):
            #_logger.info("Updating sale.order: %s" % (sorder.id))
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

            if 'pack_order' in order_json["tags"]:
                #_logger.info("Pack Order, dont create sale.order, leave it to mercadolibre.shipment")
                if order and not order.sale_order:
                    order.message_post(body=str("Pack Order, dont create sale.order, leave it to mercadolibre.shipment"),message_type=order_message_type)
            else:
                #_logger.info("Adding new sale.order: " )
                sorder = saleorder_obj.create((meli_order_fields))
                sorder.meli_fix_team( meli=meli, config=config )

        #check error
        if not order:
            _logger.error("Error adding mercadolibre.order. " )
            return {'error': 'Error adding mercadolibre.order' }

        #check error
        if not sorder:
            _logger.warning("Warning adding sale.order. Normally a pack order." )
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

                #prepare for catalogs:


                post_related = posting_obj.search([('meli_id','=',Item['item']['id'])])
                if (post_related):
                    pass;
                    #_logger.info("order post related by meli_id:",post_related)
                else:
                    #create post!
                    posting_fields = {
                        'posting_date': str(datetime.now()),
                        'meli_id':Item['item']['id'],
                        'name': 'Order: ' + Item['item']['title'] }

                    post_related = self.env['mercadolibre.posting'].create((posting_fields))

                if len(post_related):
                    post_related_obj = post_related
                else:
                    _logger.info( "No post related, exiting" )
                    return { 'error': 'No post related, exiting'}

                product_related = order.search_meli_product( meli=meli, meli_item=Item['item'], config=config )
                if ( product_related and len(product_related)==0 and ('seller_custom_field' in Item['item'] or 'seller_sku' in Item['item'])):

                    #1ST attempt "seller_sku" or "seller_custom_field"
                    seller_sku = ('seller_sku' in Item['item'] and Item['item']['seller_sku']) or ('seller_custom_field' in Item['item'] and Item['item']['seller_custom_field'])
                    if (seller_sku):
                        product_related = product_obj.search([('default_code','=ilike',seller_sku)])

                    #2ND attempt only old "seller_custom_field"
                    if (not product_related and 'seller_custom_field' in Item['item']):
                        seller_sku = ('seller_custom_field' in Item['item'] and Item['item']['seller_custom_field'])
                    if (seller_sku):
                        product_related = product_obj.search([('default_code','=ilike',seller_sku)])

                    #TODO: 3RD attempt using barcode
                    #if (not product_related):
                    #   search using item attributes GTIN and SELLER_SKU

                    if (len(product_related)):
                        _logger.info("order product related by seller_custom_field and default_code:"+str(seller_sku) )

                        if (len(product_related)>1):
                            product_related = product_related[0]

                        if (not product_related.meli_id and config.mercadolibre_create_product_from_order):
                            prod_fields = {
                                'meli_id': Item['item']['id'],
                                'meli_pub': True,
                            }
                            product_related.write((prod_fields))
                            if (product_related.product_tmpl_id):
                                product_related.product_tmpl_id.meli_pub = True
                            product_related.product_meli_get_product()
                            #if (seller_sku):
                            #    prod_fields['default_code'] = seller_sku
                    else:
                        combination = []
                        if ('variation_id' in Item['item'] and Item['item']['variation_id'] ):
                            combination = [( 'meli_id_variation','=',Item['item']['variation_id'])]
                        product_related = product_obj.search([('meli_id','=',Item['item']['id'])] + combination)
                        if (product_related and len(product_related)):
                            _logger.info("Product founded:"+str(Item['item']['id']))
                        else:
                            #optional, get product
                            productcreated = None
                            product_related = None

                            try:
                                response3 = meli.get("/items/"+str(Item['item']['id']), {'access_token':meli.access_token, 'include_attributes': 'all'})
                                rjson3 = response3.json()

                                if rjson3 and 'variations' in rjson3['variations'] and len(rjson3['variations'])>0:
                                    if len(rjson3['variations'])==1:
                                        #only 1, usually added variation by ML
                                        product_related = product_obj.search([('meli_id','=', Item['item']['id'])], order='id asc',limit=1)
                                        if (product_related):
                                            productcreated = product_related

                                    if len(rjson3['variations'])>1:
                                        #check missings
                                        product_related = product_obj.search([('meli_id','=', Item['item']['id'])], order='id asc')
                                        if product_related and len(product_related)>=1:
                                            return {'error': 'variations id missing for :'+str(Item['item']['id'])}

                                prod_fields = {
                                    'name': rjson3['title'].encode("utf-8"),
                                    'description': rjson3['title'].encode("utf-8"),
                                    'meli_id': rjson3['id'],
                                    'meli_pub': True,
                                }
                                if (seller_sku):
                                    prod_fields['default_code'] = seller_sku
                                #prod_fields['default_code'] = rjson3['id']
                                #productcreated = False
                                if config.mercadolibre_create_product_from_order and not productcreated:
                                    productcreated = self.env['product.product'].create((prod_fields))
                                if (productcreated):
                                    if (productcreated.product_tmpl_id):
                                        productcreated.product_tmpl_id.meli_pub = True
                                    _logger.info( "product created: " + str(productcreated) + " >> meli_id:" + str(rjson3['id']) + "-" + str( rjson3['title'].encode("utf-8")) )
                                    #pdb.set_trace()
                                    _logger.info(productcreated)
                                    productcreated.product_meli_get_product()
                                else:
                                    _logger.info( "product couldnt be created or updated")
                                product_related = productcreated
                            except Exception as e:
                                _logger.info("Error creando producto.")
                                _logger.error(e, exc_info=True)
                                pass;

                        if ('variation_attributes' in Item['item']):
                            _logger.info("TODO: search by attributes")

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
                    if (post_related.product_id==False):
                        post_related.product_id = product_related

                order_item_fields = {
                    'order_id': order.id,
                    'posting_id': post_related_obj.id,
                    'order_item_id': Item['item']['id'],
                    'order_item_variation_id': Item['item']['variation_id'],
                    'order_item_title': Item['item']['title'],
                    'order_item_category_id': Item['item']['category_id'],
                    'unit_price': Item['unit_price'],
                    'quantity': Item['quantity'],
                    'currency_id': Item['currency_id']
                }

                if (product_related):
                    if (len(product_related)>1):
                        error = { 'error': "Error products duplicated for item:"+str(Item and 'item' in Item and Item['item']) }
                        _logger.error(error)
                        order and order.message_post(body=str(error["error"]),message_type=order_message_type)
                        return error
                    order_item_fields['product_id'] = product_related.id

                order_item_ids = order_items_obj.search( [('order_item_id','=',order_item_fields['order_item_id']),
                                                            ('order_id','=',order.id)] )
                #_logger.info( order_item_fields )
                if not order_item_ids:
                    #_logger.info( "order_item_fields: " + str(order_item_fields) )
                    order_item_ids = order_items_obj.create( ( order_item_fields ))
                else:
                    order_item_ids.write( ( order_item_fields ) )

                if (product_related_obj == False or len(product_related_obj)==0):
                    error = { 'error': 'No product related to meli_id '+str(Item['item']['id']), 'item': str(Item['item']) }
                    _logger.error(error)
                    order and order.message_post(body=str(error["error"])+"\n"+str(error["item"]),message_type=order_message_type)
                    return error

                order.name = "MO [%s] %s" % ( str(order.order_id), product_related_obj.display_name )

                if (sorder):
                    saleorderline_item_fields = {
                        'company_id': company.id,
                        'order_id': sorder.id,
                        'meli_order_item_id': Item['item']['id'],
                        'meli_order_item_variation_id': Item['item']['variation_id'],
                        'price_unit': float(Item['unit_price']),
                        'product_id': product_related_obj.id,
                        'product_uom_qty': Item['quantity'],
                        'product_uom': product_related_obj.uom_id.id,
                        'name': product_related_obj.display_name or Item['item']['title'],
                    }
                    saleorderline_item_fields.update( self._set_product_unit_price( product_related_obj=product_related_obj, Item=Item, config=config ) )

                    saleorderline_item_ids = saleorderline_obj.search( [('meli_order_item_id','=',saleorderline_item_fields['meli_order_item_id']),
                                                                        ('meli_order_item_variation_id','=',saleorderline_item_fields['meli_order_item_variation_id']),
                                                                        ('order_id','=',sorder.id)] )

                    if not saleorderline_item_ids:
                        if sorder.amount_total<sorder.meli_paid_amount:
                            saleorderline_item_ids = saleorderline_obj.create( ( saleorderline_item_fields ))
                    else:
                        saleorderline_item_ids.write( ( saleorderline_item_fields ) )

        if 'payments' in order_json:
            payments = order_json['payments']
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
                    'taxes_amount': 0
                }

                headers = {'Accept': 'application/json', 'User-Agent': 'Odoo', 'Content-type':'application/json'}
                params = { 'access_token': meli.access_token }
                mp_response = requests.get( mp_payment_url, params=urlencode(params), headers=headers )
                if (mp_response):
                    payment_fields["full_payment"] = mp_response.json()
                    payment_fields["shipping_amount"] = payment_fields["full_payment"]["shipping_amount"]
                    payment_fields["total_paid_amount"] = payment_fields["full_payment"]["transaction_details"]["total_paid_amount"]
                    if ("fee_details" in payment_fields["full_payment"] and len(payment_fields["full_payment"]["fee_details"])>0):
                        fee_details = payment_fields["full_payment"]["fee_details"]
                        for fee_detail in fee_details:
                            #fee_detail = fee_details[index]
                            if fee_detail and "amount" in fee_detail:
                                fee_type = fee_detail["type"]
                                fee_payer = fee_detail["fee_payer"]
                                if (fee_payer and fee_payer == "collector"):
                                    payment_fields["fee_amount"] = fee_detail["amount"]
                        if (order):
                            order.fee_amount = payment_fields["fee_amount"]
                            if (sorder):
                                sorder.meli_fee_amount = order.fee_amount
                    payment_fields["taxes_amount"] = payment_fields["full_payment"]["taxes_amount"]

                payment_ids = payments_obj.search( [  ('payment_id','=',payment_fields['payment_id']),
                                                            ('order_id','=',order.id ) ] )

                if not payment_ids:
	                payment_ids = payments_obj.create( ( payment_fields ))
                else:
                    payment_ids.write( ( payment_fields ) )

        #if order:
        #    return_id = self.env['mercadolibre.orders'].update

        if config.mercadolibre_cron_get_orders_shipment:
            #_logger.info("Updating order: Shipment")
            if (order and order.shipping_id):
                shipment = shipment_obj.fetch( order, meli=meli, config=config )
                if (shipment):
                    order.shipment = shipment
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
                #_logger.info(line)
                #_logger.info(line.is_delivery)
                #_logger.info(line.price_unit)
                if sorder.meli_order_id and line.is_delivery and line.price_unit<=0.0:
                    #_logger.info(line)
                    line.write({ "qty_to_invoice": 0.0 })
                    #_logger.info(line.qty_to_invoice)
                    pass;

            #if (config.mercadolibre_order_confirmation!="manual"):
            sorder.confirm_ml( meli=meli, config=config )

            if (sorder.meli_status=="cancelled" and sorder.state in ["draft","sale","sent"]):
                sorder.action_cancel()

            #if "confirm_ml_financial" in self.env["mercadolibre.orders"]:
            #sorder.confirm_ml_financial( meli=meli, config=config )

            if meli.access_token=="PASIVA":
                if (sorder):
                    sorder.meli_fee_amount = order_fields["fee_amount"]
        try:
            self.orders_get_invoice()
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
                    _logger.info(ret)
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
        _logger.info(log_msg)

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
                self._cr.commit()
                if ret and "error" in ret:
                    rets.append(ret)
            except Exception as e:
                _logger.info("orders_update_order > Error actualizando ORDEN")
                _logger.error(e, exc_info=True)
                self._cr.rollback()
                pass;
                #raise e

        if rets and len(rets)==1:
            return warningobj.info( title='MELI WARNING', message = "update order errors: "+str(len(rets)), message_html = str(rets))



        return rets

    def orders_query_iterate( self, offset=0, context=None, config=None, meli=None, fetch_id_only=False, fetch_ids=[] ):

        _logger.info("mercadolibre.orders >> orders_query_iterate: meli: "+str(meli)+" config:"+str(config)+' fetch_id_only:'+str(fetch_id_only))
        offset_next = 0
        __fetch_ids = fetch_ids

        company = self.env.user.company_id
        if not config:
            config = company

        orders_obj = self.env['mercadolibre.orders']

        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)

        orders_query = "/orders/search?seller="+str(meli.seller_id)+"&sort=date_desc"
        #TODO: "create parameter for": orders_query+= "&limit=10"

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
                        if not order_date_filter:
                            offset_next = 0
                        else:
                            offset_next = offset + orders_json["paging"]["limit"]
                        _logger.info("offset_next:"+str(offset_next))

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
                                and config.mercadolibre_filter_order_datetime_start
                                and config.mercadolibre_filter_order_datetime_start>parse(order_fields["date_closed"]) ):
                            #error = { "error": "orden filtrada por fecha START > " + str(order_fields["date_closed"]) + " inferior a "+str(ml_datetime(config.mercadolibre_filter_order_datetime_start)) }
                            #_logger.info( "orders_update_order_json > filter:" + str(error) )
                            #return error
                            in_range = False
                
                
                        if (    "mercadolibre_filter_order_datetime" in config._fields
                                and "date_closed" in order_fields
                                and config.mercadolibre_filter_order_datetime
                                and config.mercadolibre_filter_order_datetime>parse(order_fields["date_closed"]) ):
                            #error = { "error": "orden filtrada por FROM > " + str(order_fields["date_closed"]) + " inferior a "+str(ml_datetime(config.mercadolibre_filter_order_datetime)) }
                            #_logger.info( "orders_update_order_json > filter:" + str(error) )
                            in_range = False
                
                        if (    "mercadolibre_filter_order_datetime_to" in config._fields
                                and "date_closed" in order_fields
                                and config.mercadolibre_filter_order_datetime_to
                                and config.mercadolibre_filter_order_datetime_to<parse(order_fields["date_closed"]) ):
                            #error = { "error": "orden filtrada por fecha TO > " + str(order_fields["date_closed"]) + " superior a "+str(ml_datetime(config.mercadolibre_filter_order_datetime_to)) }
                            #_logger.info( "orders_update_order_json > filter:" + str(error) )
                            in_range = False
                            
                        if in_range:
                            __fetch_ids.append(str(order_json["id"]))
                    else:
                        try:
                            ret = self.orders_update_order_json( data=pdata, config=config, meli=meli )
                            self._cr.commit()
                        except Exception as e:
                            _logger.info("orders_query_iterate > Error actualizando ORDEN")
                            _logger.error(e, exc_info=True)
                            self._cr.rollback()
                            pass;

        if (offset_next>0):
            __fetch_ids = self.orders_query_iterate( offset=offset_next, meli=meli, config=config, fetch_id_only=fetch_id_only, fetch_ids=__fetch_ids )

        return __fetch_ids

    def orders_query_recent( self, meli=None, config=None, fetch_id_only=False ):

        company = self.env.user.company_id
        if not config:
            config = company
        
        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)

        _logger.info("mercadolibre.orders >> orders_query_recent: meli: "+str(meli)+" config:"+str(config)+' fetch_id_only:'+str(fetch_id_only))
        self._cr.autocommit(False)
        __fetch_ids = None
        try:
            __fetch_ids = self.orders_query_iterate( offset=0, meli=meli, config=config, fetch_id_only=fetch_id_only )
        except Exception as e:
            _logger.info("orders_query_recent > Error iterando ordenes")
            _logger.error(e, exc_info=True)
            self._cr.rollback()

        if __fetch_ids:
            _logger.info( "__fetch_ids:"+str(__fetch_ids) )
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
                order.status_detail = order_json["status_detail"] or ''
                if order.sale_order:
                    order.sale_order.confirm_ml(meli=meli,config=config)

    def _get_config( self, config=None ):
        config = config or (self and self.company_id)
        return config

    def orders_get_invoice(self, context=None, meli=None, config=None):
        _logger.info("orders_get_invoice")

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
                                    ("invalid","Invalido: malicious")], string='Order Status')

    status_detail = fields.Text(string='Status detail, in case the order was cancelled.')
    date_created = fields.Datetime('Creation date')
    date_closed = fields.Datetime('Closing date')


    def search_order_order_product(self, operator, value):
        _logger.info("search_order_item_product_id")
        _logger.info(operator)
        _logger.info(value)
        if operator == '=':
            #name = self.env.context.get('name', False)
            #if name is not False:
            id_list = []
            _logger.info(self.env.context)
            #name = self.env.context.get('name', False)
            order_items = []
            if value == True:
                order_items = self.env['mercadolibre.order_items'].search([('product_id','!=',False)], limit=10000)
            else:
                order_items = self.env['mercadolibre.order_items'].search([('product_id','=',False)], limit=10000)
            
            #if (value):
            for item in order_items:
                #if (value in p.meli_publications):
                id_list.append(item.order_id.id)

            return [('id', 'in', id_list)]
        else:
            _logger.error(
                'The field name is not searchable'
                ' with the operator: {}',format(operator)
            )
            
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
                ord.order_product_sku = ord.order_items[0].seller_sku
    
    order_product_sku = fields.Char(string='Order Product Sku', compute=_order_product_sku )


    payments = fields.One2many('mercadolibre.payments','order_id',string='Payments' )

    def _payments_shipment_amount(self):
        for mor in self:
            sum = 0
            for pay in mor.payments:
                if pay.status == 'approved':
                    sum+= pay.shipping_amount
            mor.payments_shipment_amount = sum

    payments_shipment_amount = fields.Float(string="Payments Shipment Amount", compute="_payments_shipment_amount" )
    shipping = fields.Text(string="Shipping")
    shipping_id = fields.Char(string="Shipping id")
    shipment = fields.Many2one('mercadolibre.shipment',string='Shipment')
    shipment_logistic_type = fields.Char(string="Logistic Type",index=True)

    fee_amount = fields.Float(string='Fee total amount')
    total_amount = fields.Float(string='Total amount')
    shipping_cost = fields.Float(string='Shipping Cost',help='Gastos de envío')
    shipping_list_cost = fields.Float(string='Shipping List Cost',help='Gastos de envío, costo de lista/interno')
    paid_amount = fields.Float(string='Paid amount',help='Includes shipping cost')
    currency_id = fields.Char(string='Currency')
    buyer =  fields.Many2one( "mercadolibre.buyers","Buyer")
    buyer_billing_info = fields.Text(string="Billing Info")
    seller = fields.Text( string='Seller Name' )
    tags = fields.Text(string="Tags")
    pack_order = fields.Boolean(string="Order Pack (Carrito)")
    catalog_order = fields.Boolean(string="Order From Catalog")
    company_id = fields.Many2one("res.company",string="Company")
    seller_id = fields.Many2one("res.users",string="Seller")

    shipment_status = fields.Char(string="Shipment Status",related="shipment.status",index=True)
    shipment_substatus = fields.Char(string="Shipment SubStatus",related="shipment.substatus",index=True)

    _sql_constraints = [
        ('unique_order_id', 'unique(order_id)', 'Meli Order id already exists!')
    ]

mercadolibre_orders()


class mercadolibre_order_items(models.Model):
    _name = "mercadolibre.order_items"
    _description = "Producto pedido en MercadoLibre"

    posting_id = fields.Many2one("mercadolibre.posting","Posting")
    product_id = fields.Many2one("product.product",string="Product",help="Product Variant")
    order_id = fields.Many2one("mercadolibre.orders","Order")
    order_item_id = fields.Char('Item Id')
    order_item_variation_id = fields.Char('Item Variation Id')
    order_item_title = fields.Char('Item Title')
    order_item_category_id = fields.Char('Item Category Id')
    unit_price = fields.Char(string='Unit price')
    quantity = fields.Integer(string='Quantity')
    currency_id = fields.Char(string='Currency')
    seller_sku = fields.Char(string='SKU')
    seller_custom_field = fields.Char(string='seller_custom_field')

mercadolibre_order_items()


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
    taxes_amount = fields.Float('Taxes Amount')

    def _get_config( self, config=None ):
        config = config or (self and self.order_id and self.order_id._get_config(config=config))
        return config

mercadolibre_payments()

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

    _sql_constraints = [
        ('unique_buyer_id', 'unique(buyer_id)', 'Mei Buyer id already exists!')
    ]

mercadolibre_buyers()

class res_partner(models.Model):
    _inherit = "res.partner"

    meli_buyer_id = fields.Char('Meli Buyer Id',index=True)
    meli_buyer = fields.Many2one('mercadolibre.buyers',string='Buyer')
    meli_update_forbidden = fields.Boolean(string='Meli Update Forbiden')
    meli_order_id = fields.Char('Meli Order Id',index=True)

    _sql_constraints = [
        ('unique_partner_meli_buyer_id', 'unique(meli_buyer_id)', 'Mei Partner Buyer id already exists!')
    ]

res_partner()


class mercadolibre_orders_update(models.TransientModel):
    _name = "mercadolibre.orders.update"
    _description = "Update Order"

    def order_update(self, context=None):
        context = context or self.env.context
        orders_ids = ('active_ids' in context and context['active_ids']) or []
        orders_obj = self.env['mercadolibre.orders']
        warningobj = self.env['meli.warning']

        self._cr.autocommit(False)
        rets = []
        try:

            for order_id in orders_ids:

                _logger.info("order_update: %s " % (order_id) )

                order = orders_obj.browse(order_id)
                ret = order.orders_update_order()
                _logger.info("order_update ret:"+str(ret))
                if ret and type(ret)==dict and 'name' in ret:
                    rets.append(ret)
                if ret and len(ret) and type(ret)==list and ret[0] and "error" in ret[0]:
                    rets.append(ret[0])
        except Exception as e:
            _logger.info("order_update > Error actualizando ordenes")
            _logger.error(e, exc_info=True)
            self._cr.rollback()

        #Add warning with all filters errors:
        if rets and len(rets)>0:
            #return warning.
            return warningobj.info( title='MELI WARNING', message = "update order errors: "+str(len(rets)), message_html = str(rets))

        return {}

mercadolibre_orders_update()

class mercadolibre_orders_update_invoice(models.TransientModel):
    _name = "mercadolibre.orders.update.invoice"
    _description = "Update Order Invoice"

    def order_update_invoice(self, context=None):
        context = context or self.env.context
        orders_ids = ('active_ids' in context and context['active_ids']) or []
        orders_obj = self.env['mercadolibre.orders']

        self._cr.autocommit(False)
        try:

            for order_id in orders_ids:

                _logger.info("order_update: %s " % (order_id) )

                order = orders_obj.browse(order_id)
                #order.orders_update_order()
                if order:
                    order.orders_get_invoice()

        except Exception as e:
            _logger.info("order_update > Error actualizando factura ordenes")
            _logger.error(e, exc_info=True)
            self._cr.rollback()

        return {}

mercadolibre_orders_update()

class sale_order_cancel_wiz_meli(models.TransientModel):
    _name = "sale.order.cancel.wiz.meli"
    _description = "Cancel Order"

    def cancel_order(self, context=None):
        context = context or self.env.context
        orders_ids = ('active_ids' in context and context['active_ids']) or []
        orders_obj = self.env['sale.order']

        self._cr.autocommit(False)
        try:

            for order_id in orders_ids:

                _logger.info("cancel_order: %s " % (order_id) )

                order = orders_obj.browse(order_id)
                if (order and order.state in ["draft","sale","sent"]):
                    order.action_cancel()

        except Exception as e:
            _logger.info("order_update > Error cancelando ordenes")
            _logger.error(e, exc_info=True)
            self._cr.rollback()

        return {}

sale_order_cancel_wiz_meli()
