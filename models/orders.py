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
                                    ("invalid","Invalido: malicious")
                                    ], string='Order Status')

    meli_status_brief = fields.Char(string="Meli Status Brief", compute="_meli_status_brief", store=False, index=True)

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
        _logger.info("meli order action_confirm: " + str(self.mapped("name")) )
        res = super(sale_order,self).action_confirm()
        try:
            for order in self:
                for line in order.order_line:
                    #_logger.info(line)
                    #_logger.info(line.is_delivery)
                    #_logger.info(line.price_unit)
                    if line.is_delivery and line.price_unit<=0.0:
                        #_logger.info(line)
                        line.write({ "qty_to_invoice": 0.0 })
                        #_logger.info(line.qty_to_invoice)
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
                for line in order.order_line:
                    #_logger.info(line)
                    #_logger.info(line.is_delivery)
                    #_logger.info(line.price_unit)
                    if line.is_delivery and line.price_unit<=0.0:
                        #_logger.info(line)
                        line.write({ "qty_to_invoice": 0.0 })
                        #_logger.info(line.qty_to_invoice)
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

    def confirm_ml( self, meli=None, config=None ):
        try:
            _logger.info("meli_oerp confirm_ml")
            company = (config and 'company_id' in config._fields and config.company_id) or self.env.user.company_id
            config = config or company
            res = {}

            stock_picking = self.env["stock.picking"]

            confirm_cond = abs(self.meli_paid_amount - self.amount_total)<0.1
            if not confirm_cond:
                return {'error': "Condition not met: meli_paid_amount and amount_total doesn't match"}

            if (self.meli_status=="cancelled"):
                self.action_cancel()

            if (config.mercadolibre_order_confirmation=="paid_confirm"):

                if ( (self.state=="draft" or self.state=="sent") and self.meli_status=="paid"):
                    _logger.info("paid_confirm ok! confirming sale")
                    self.action_confirm()

            if (config.mercadolibre_order_confirmation=="paid_delivered"):

                if ( (self.state=="draft" or self.state=="sent") and self.meli_status=="paid"):
                    _logger.info("paid_delivered ok! confirming sale")
                    self.action_confirm()

                if (self.state=="sale" or self.state=="done"):
                    #spick = stock_picking.search([('order_id','=',self.id)])
                    _logger.info("paid_delivered ok! delivering")
                    if self.picking_ids:
                        for spick in self.picking_ids:
                            _logger.info(str(spick)+":"+str(spick.state))

                            try:
                                if (spick.state in ['confirmed','waiting','draft']):
                                    _logger.info("action_assign")
                                    res = spick.action_assign()
                                    _logger.info("action_assign res:"+str(res)+" state:"+str(spick.state))

                                if (spick.move_line_ids):
                                    _logger.info(spick.move_line_ids)
                                    if (len(spick.move_line_ids)>=1):
                                        for pop in spick.move_line_ids:
                                            _logger.info(pop)
                                            if (pop.qty_done==0.0 and pop.product_qty>=0.0):
                                                pop.qty_done = pop.product_qty
                                        _logger.info("do_new_transfer")

                                        if (spick.state in ['assigned']):
                                            spick.button_validate()
                            except Exception as e:
                                _logger.error("stock pick button_validate error"+str(e))
                                res = { 'error': str(e) }
                                pass;


            if (config.mercadolibre_order_confirmation=="paid_confirm_with_invoice"):
                if ( (self.state=="draft" or self.state=="sent") and self.meli_status=="paid"):
                    _logger.info("paid_confirm with invoice ok! confirming sale and create invoice")
                    self.action_confirm()
                    self.action_invoice_create()
        except Exception as e:
            _logger.info("Confirm Order Exception")
            _logger.error(e, exc_info=True)
            return { 'error': str(e) }
            pass
        _logger.info("meli_oerp confirm_ml ended.")
        return res

    _sql_constraints = [
        ('unique_meli_order_id', 'unique(meli_order_id)', 'Mei Order id already exists!')
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
        if (Receiver and 'state' in Receiver):
            if ('id' in Receiver['state']):
                state = self.env['res.country.state'].search([('code','like',Receiver['state']['id']),('country_id','=',country_id)])
                if (len(state)):
                    state_id = state[0].id
                    return state_id
            id_ml = 'id' in Receiver['state'] and str(Receiver['state']['id']).split("-")
            #_logger.info(Receiver)
            #_logger.info(id_ml)
            if (id_ml and len(id_ml)==2):
                id = id_ml[1]
                state = self.env['res.country.state'].search([('code','like',id),('country_id','=',country_id)])
                if (len(state)):
                    state_id = state[0].id
                    return state_id
            if ('name' in Receiver['state']):
                full_state = Receiver['state']['name']
                state = self.env['res.country.state'].search(['&',('name','like',full_state),('country_id','=',country_id)])
                if (len(state)):
                    state_id = state[0].id

        if ( Buyer and 'billing_info' in Buyer and 'STATE_NAME' in Buyer['billing_info'] ):
            binfo = Buyer['billing_info']
            full_state = (('CITY_NAME' in binfo and binfo['CITY_NAME']) or '')
            state = self.env['res.country.state'].search(['&',('name','like',full_state),('country_id','=',country_id)])
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
                _logger.info("get_billing_info: "+str(biljson))
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
        product_obj = self.env['product.product']
        if not meli_item:
            return None
        meli_id = meli_item['id']
        meli_id_variation = ("variation_id" in meli_item and meli_item['variation_id'])
        if (meli_id_variation):
            product_related = product_obj.search([ ('meli_id','=',meli_id), ('meli_id_variation','=',meli_id_variation) ])
        else:
            product_related = product_obj.search([('meli_id','=', meli_id)])
        return product_related


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

        order_fields = self.prepare_ml_order_vals( order_json=order_json, meli=meli, config=config )

        if (    "mercadolibre_filter_order_datetime" in config._fields
                and "date_closed" in order_fields
                and config.mercadolibre_filter_order_datetime
                and config.mercadolibre_filter_order_datetime>parse(order_fields["date_closed"]) ):
            return { "error": "orden filtrada por fecha > " + str(order_fields["date_closed"]) + " inferior a "+str(ml_datetime(config.mercadolibre_filter_order_datetime)) }

        if (    "mercadolibre_filter_order_datetime_to" in config._fields
                and "date_closed" in order_fields
                and config.mercadolibre_filter_order_datetime_to
                and config.mercadolibre_filter_order_datetime_to<parse(order_fields["date_closed"]) ):
            return { "error": "orden filtrada por fecha TO > " + str(order_fields["date_closed"]) + " superior a "+str(ml_datetime(config.mercadolibre_filter_order_datetime_to)) }

        _logger.info("orders_update_order_json > data "+str(data['id']) + " json:" + str(data['order_json']['id']) )

        # if id is defined, we are updating existing one
        if (oid):
            order = order_obj.browse(oid )
            if (order):
                _logger.info(order)
                sorder_s = saleorder_obj.search([ ('meli_order_id','=',order.order_id) ] )
                if (sorder_s):
                    _logger.info(sorder_s)
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
            _logger.info("Buyer not present, fetch order")
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
            if ('shipping' in order_json):
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
            _logger.info("Buyer:"+str(Buyer) )
            #_logger.info(order_json)
            meli_buyer_fields = {
                'name': self.buyer_full_name(Buyer),
                'street': self.street(Receiver,Buyer),
                'city': self.city(Receiver,Buyer),
                'country_id': self.country(Receiver,Buyer),
                'state_id': self.state(self.country(Receiver,Buyer),Receiver,Buyer),
                'phone': self.full_phone( Buyer ),
                #'email': Buyer['email'],
                'meli_buyer_id': Buyer['id']
            }
            meli_buyer_fields.update(self.fix_locals(Receiver=Receiver,Buyer=Buyer))

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


                #Chile
                if ( ('doc_type' in Buyer['billing_info']) and ('l10n_latam_identification_type_id' in self.env['res.partner']._fields) ):
                    if (Buyer['billing_info']['doc_type']=="RUT"):
                        meli_buyer_fields['l10n_latam_identification_type_id'] = 4
                    if (Buyer['billing_info']['doc_type']=="RUN"):
                        meli_buyer_fields['l10n_latam_identification_type_id'] = 5

                    meli_buyer_fields['vat'] = Buyer['billing_info']['doc_number']

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
                            meli_buyer_fields['responsabilidad_fiscal_fe'] = [ ( 6, 0, [29] ) ]

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
                            meli_buyer_fields['responsabilidad_fiscal_fe'] = [ ( 6, 0, [29] ) ]

                    meli_buyer_fields['vat'] = Buyer['billing_info']['doc_number']
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


            partner_ids = respartner_obj.search([  ('meli_buyer_id','=',buyer_fields['buyer_id'] ) ] )
            if (len(partner_ids)>0):
                partner_id = partner_ids[0]
            if ("fe_regimen_fiscal" in self.env['res.partner']._fields):
                if (partner_id and not partner_id.fe_regimen_fiscal):
                    meli_buyer_fields['fe_regimen_fiscal'] = '49';
                else:
                    meli_buyer_fields['fe_regimen_fiscal'] = '49';
            if not partner_id:
                #_logger.info( "creating partner:" + str(meli_buyer_fields) )
                partner_id = respartner_obj.create(( meli_buyer_fields ))
            elif (partner_id and "meli_update_forbidden" in partner_id._fields and not partner_id.meli_update_forbidden):
                _logger.info("Updating partner")
                #TODO: _logger.info("Updating partner (do not update principal, always create new one)")
                _logger.info(meli_buyer_fields)
                #complete country at most:
                partner_update = {}

                #TODO: re DO with, self.update_billing_data( partner_id, meli_buyer_fields )
                if "document_type_id" in meli_buyer_fields and str(meli_buyer_fields['document_type_id'])!=str(partner_id.document_type_id and partner_id.document_type_id.id):
                    partner_update.update(meli_buyer_fields)

                if "document_number" in meli_buyer_fields and str(meli_buyer_fields['document_number'])!=str(partner_id.document_number):
                    partner_update.update(meli_buyer_fields)

                if ("vat" in meli_buyer_fields and meli_buyer_fields["vat"]!=str(partner_id.vat) ):
                    partner_update.update(meli_buyer_fields)

                if "l10n_co_document_type" in meli_buyer_fields and str(meli_buyer_fields['l10n_co_document_type'])!=str(partner_id.l10n_co_document_type):
                    partner_update.update(meli_buyer_fields)

                if "l10n_latam_identification_type_id" in meli_buyer_fields and str(meli_buyer_fields['l10n_latam_identification_type_id'])!=str(partner_id.l10n_latam_identification_type_id and partner_id.l10n_latam_identification_type_id.id):
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

                if partner_update:
                    _logger.info("Updating partner: "+str(partner_update))
                    partner_id.write(partner_update)

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
            'pricelist_id': plistid.id,
        })
        if partner_shipping_id:
            meli_order_fields['partner_shipping_id'] = partner_shipping_id.id

        if ("pack_id" in order_json and order_json["pack_id"]):
            meli_order_fields['name'] = "ML %s" % ( str(order_json["pack_id"]) )
            #meli_order_fields['pack_id'] = order_json["pack_id"]

        if ('account.payment.term' in self.env):
            inmediate_or_not = ('mercadolibre_payment_term' in config._fields and config.mercadolibre_payment_term) or None
            meli_order_fields["payment_term_id"] = (inmediate_or_not and inmediate_or_not.id)

        if (order_json["shipping"]):
            order_fields['shipping'] = self.pretty_json( id, order_json["shipping"] )
            meli_order_fields['meli_shipping'] = self.pretty_json( id, order_json["shipping"] )
            if ("cost" in order_json["shipping"]):
                order_json["shipping_cost"] = float(order_json["shipping"]["cost"])
                meli_order_fields["meli_shipping_cost"] = float(order_json["shipping"]["cost"])
            if ("id" in order_json["shipping"]):
                order_fields['shipping_id'] = order_json["shipping"]["id"]
                meli_order_fields['meli_shipping_id'] = order_json["shipping"]["id"]

        #create or update order
        if (order and order.id):
            _logger.info("Updating order: %s" % (order.id))
            order.write( order_fields )
        else:
            _logger.info("Adding new order: " )
            #_logger.info(order_fields)
            order = order_obj.create( (order_fields))

        if (sorder and sorder.id):
            _logger.info("Updating sale.order: %s" % (sorder.id))
            #_logger.info(meli_order_fields)
            sorder.write( meli_order_fields )
        else:
            #_logger.info(meli_order_fields)
            #user
            if (config.mercadolibre_seller_user):
                meli_order_fields["user_id"] = config.mercadolibre_seller_user.id
            if (config.mercadolibre_seller_team):
                meli_order_fields["team_id"] = config.mercadolibre_seller_team.id

            if 'pack_order' in order_json["tags"]:
                _logger.info("Pack Order, dont create sale.order, leave it to mercadolibre.shipment")
                if order and not order.sale_order:
                    order.message_post(body=str("Pack Order, dont create sale.order, leave it to mercadolibre.shipment"))
            else:
                _logger.info("Adding new sale.order: " )
                sorder = saleorder_obj.create((meli_order_fields))

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
                if ( len(product_related)==0 and ('seller_custom_field' in Item['item'] or 'seller_sku' in Item['item'])):

                    #1ST attempt "seller_sku" or "seller_custom_field"
                    seller_sku = ('seller_sku' in Item['item'] and Item['item']['seller_sku']) or ('seller_custom_field' in Item['item'] and Item['item']['seller_custom_field'])
                    if (seller_sku):
                        product_related = product_obj.search([('default_code','=',seller_sku)])

                    #2ND attempt only old "seller_custom_field"
                    if (not product_related and 'seller_custom_field' in Item['item']):
                        seller_sku = ('seller_custom_field' in Item['item'] and Item['item']['seller_custom_field'])
                    if (seller_sku):
                        product_related = product_obj.search([('default_code','=',seller_sku)])

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
                        order and order.message_post(body=str(error["error"]))
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
                    order and order.message_post(body=str(error["error"])+"\n"+str(error["item"]))
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
                        payment_fields["fee_amount"] = payment_fields["full_payment"]["fee_details"][0]["amount"]
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
            _logger.info("Updating order: Shipment")
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
                            _logger.info("fixing meli_date_created")
                            sorder.meli_date_created = order.date_created
                            sorder.meli_date_closed = order.date_closed

        #could be packed sorder or standard one product item order
        if sorder:
            for line in sorder.order_line:
                #_logger.info(line)
                #_logger.info(line.is_delivery)
                #_logger.info(line.price_unit)
                if line.is_delivery and line.price_unit<=0.0:
                    #_logger.info(line)
                    line.write({ "qty_to_invoice": 0.0 })
                    #_logger.info(line.qty_to_invoice)

            if (config.mercadolibre_order_confirmation!="manual"):
                sorder.confirm_ml( meli=meli, config=config )

            if (sorder.meli_status=="cancelled"):
                sorder.action_cancel()

        return {}

    def orders_update_order( self, context=None, meli=None, config=None ):

        #get with an item id
        context = context or self.env.context
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

        if "error" in order_json:
            _logger.error( order_json["error"] )
            _logger.error( order_json["message"] )
        else:
            try:
                self.orders_update_order_json( {"id": order.id, "order_json": order_json }, meli=meli, config=config )
                self._cr.commit()
            except Exception as e:
                _logger.info("orders_update_order > Error actualizando ORDEN")
                _logger.error(e, exc_info=True)
                self._cr.rollback()
                pass;
                #raise e

        return {}

    def orders_query_iterate( self, offset=0, context=None, config=None, meli=None ):

        _logger.info("mercadolibre.orders >> orders_query_iterate: meli: "+str(meli)+" config:"+str(config))
        offset_next = 0

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

        if "results" in orders_json:
            for order_json in orders_json["results"]:
                if order_json:
                    #_logger.info( order_json )
                    pdata = {"id": False, "order_json": order_json}
                    try:
                        self.orders_update_order_json( data=pdata, config=config, meli=meli )
                        self._cr.commit()
                    except Exception as e:
                        _logger.info("orders_query_iterate > Error actualizando ORDEN")
                        _logger.error(e, exc_info=True)
                        self._cr.rollback()
                        pass;

        if (offset_next>0):
            self.orders_query_iterate( offset=offset_next, meli=meli, config=config )

        return {}

    def orders_query_recent( self, meli=None, config=None ):

        _logger.info("mercadolibre.orders >> orders_query_recent: meli: "+str(meli)+" config:"+str(config))
        self._cr.autocommit(False)

        try:
            self.orders_query_iterate( offset=0, meli=meli, config=config )
        except Exception as e:
            _logger.info("orders_query_recent > Error iterando ordenes")
            _logger.error(e, exc_info=True)
            self._cr.rollback()

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

    order_items = fields.One2many('mercadolibre.order_items','order_id',string='Order Items' )
    payments = fields.One2many('mercadolibre.payments','order_id',string='Payments' )
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
    seller = fields.Text( string='Seller' )
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

    meli_buyer_id = fields.Char('Meli Buyer Id')
    meli_buyer = fields.Many2one('mercadolibre.buyers',string='Buyer')
    meli_update_forbidden = fields.Boolean(string='Meli Update Forbiden')

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

        self._cr.autocommit(False)
        try:

            for order_id in orders_ids:

                _logger.info("order_update: %s " % (order_id) )

                order = orders_obj.browse(order_id)
                order.orders_update_order()

        except Exception as e:
            _logger.info("order_update > Error actualizando ordenes")
            _logger.error(e, exc_info=True)
            self._cr.rollback()

        return {}

mercadolibre_orders_update()

class sale_order_cancel(models.TransientModel):
    _name = "sale.order.cancel"
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
                if order:
                    order.action_cancel()

        except Exception as e:
            _logger.info("order_update > Error cancelando ordenes")
            _logger.error(e, exc_info=True)
            self._cr.rollback()

        return {}

sale_order_cancel()
