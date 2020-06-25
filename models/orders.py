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

    meli_order_item_id = fields.Char('Meli Order Item Id');
sale_order_line()

class sale_order(models.Model):
    _inherit = "sale.order"

    meli_order_id =  fields.Char(string='Meli Order Id',index=True)
    meli_orders = fields.Many2many('mercadolibre.orders',string="ML Orders")
    meli_status = fields.Selection( [
        #Initial state of an order, and it has no payment yet.
                                        ("confirmed","Confirmado"),
        #The order needs a payment to become confirmed and show users information.
                                      ("payment_required","Pago requerido"),
        #There is a payment related with the order, but it has not accredited yet
                                    ("payment_in_process","Pago en proceso"),
        #The order has a related payment and it has been accredited.
                                    ("paid","Pagado"),
        #The order has not completed by some reason.
                                    ("cancelled","Cancelado")], string='Order Status');

    meli_status_detail = fields.Text(string='Status detail, in case the order was cancelled.')
    meli_date_created = fields.Datetime('Creation date')
    meli_date_closed = fields.Datetime('Closing date')

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

    def confirm_ml(self):

        company = self.env.user.company_id
        stock_picking = self.env["stock.picking"]

        if (company.mercadolibre_order_confirmation=="paid_confirm"):

            if ( (self.state=="draft" or self.state=="sent") and self.meli_status=="paid"):
                _logger.info("paid_confirm ok! confirming sale")
                self.action_confirm()

        if (company.mercadolibre_order_confirmation=="paid_delivered"):

            if ( (self.state=="draft" or self.state=="sent") and self.meli_status=="paid"):
                _logger.info("paid_delivered ok! confirming sale")
                self.action_confirm()

            if (self.state=="sale" or self.state=="done"):
                #spick = stock_picking.search([('order_id','=',self.id)])
                _logger.info("paid_delivered ok! delivering")
                for spick in self.picking_ids:
                    _logger.info(spick)
                    if (spick.move_line_ids):
                        _logger.info(spick.move_line_ids)
                        if (len(spick.move_line_ids)>=1):
                            for pop in spick.move_line_ids:
                                _logger.info(pop)
                                if (pop.qty_done==0.0 and pop.product_qty>=0.0):
                                    pop.qty_done = pop.product_qty
                            _logger.info("do_new_transfer")
                            spick.action_done()

sale_order()

class mercadolibre_orders(models.Model):
    _name = "mercadolibre.orders"
    _description = "Pedidos en MercadoLibre"

    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']

    def street(self, Receiver ):
        full_street = 'no street'
        if (Receiver and 'address_line' in Receiver):
            full_street = Receiver['address_line']
        return full_street

    def city(self, Receiver ):
        full_city = ''
        if (Receiver and 'city' in Receiver):
            full_city = Receiver['city']['name']
        return full_city

    def state(self, country_id, Receiver ):
        full_state = ''
        state_id = False
        if (Receiver and 'state' in Receiver):
            if ('id' in Receiver['state']):
                state = self.env['res.country.state'].search([('code','like',Receiver['state']['id'])])
                if (len(state)):
                    state_id = state[0].id
                    return state_id
            if ('name' in Receiver['state']):
                full_state = Receiver['state']['name']
                state = self.env['res.country.state'].search(['&',('name','like',full_state),('country_id','=',country_id)])
                if (len(state)):
                    state_id = state[0].id
        return state_id

    def country(self, Receiver ):
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

    def billing_info( self, billing_json, context=None ):
        billinginfo = ''

        if 'doc_type' in billing_json:
            if billing_json['doc_type']:
                billinginfo+= billing_json['doc_type']

        if 'doc_number' in billing_json:
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

    def _set_product_unit_price( self, product_related_obj, Item ):
        product_template = product_related_obj.product_tmpl_id
        ml_price_converted = float(Item['unit_price'])
        #11.0
        #tax_excluded = self.env.user.has_group('sale.group_show_price_subtotal')
        #12.0 and 13.0
        tax_excluded = ml_tax_excluded(self)
        if ( tax_excluded and product_template.taxes_id ):
            txfixed = 0
            txpercent = 0
            #_logger.info("Adjust taxes")
            for txid in product_template.taxes_id:
                if (txid.type_tax_use=="sale" and not txid.price_include):
                    if (txid.amount_type=="percent"):
                        txpercent = txpercent + txid.amount
                    if (txid.amount_type=="fixed"):
                        txfixed = txfixed + txid.amount
                    #_logger.info(txid.amount)
            if (txfixed>0 or txpercent>0):
                #_logger.info("Tx Total:"+str(txtotal)+" to Price:"+str(ml_price_converted))
                ml_price_converted = txfixed + ml_price_converted / (1.0 + txpercent*0.01)
                _logger.info("Price adjusted with taxes:"+str(ml_price_converted))

        ml_price_converted = round(ml_price_converted,2)

        upd_line = {
            "price_unit": ml_price_converted,
        }
        #else:
        #    if ( float(Item['unit_price']) == product_template.lst_price and not self.env.user.has_group('sale.group_show_price_subtotal')):
        #        upd_line["tax_id"] = None
        return upd_line

    def pretty_json( self, ids, data, indent=0, context=None ):
        return json.dumps( data, sort_keys=False, indent=4 )

    def orders_update_order_json( self, data, context=None ):

        _logger.info("orders_update_order_json > data "+str(data['id']) + " json:" + str(data['order_json']['id']) )

        oid = data["id"]
        order_json = data["order_json"]
        #_logger.info( "data:" + str(data) )
        company = self.env.user.company_id

        saleorder_obj = self.env['sale.order']
        saleorderline_obj = self.env['sale.order.line']
        product_obj = self.env['product.product']

        pricelist_obj = self.env['product.pricelist']
        respartner_obj = self.env['res.partner']

        plistid = None
        if company.mercadolibre_pricelist:
            plistid = company.mercadolibre_pricelist
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
            order_s = order_obj.search([ ('order_id','=','%i' % (order_json["id"])) ] )
            if (order_s):
                if (len(order_s)>1):
                    order = order_s[0]
                else:
                    order = order_s
            #    order = order_obj.browse(order_s[0] )

            sorder_s = saleorder_obj.search([ ('meli_order_id','=','%i' % (order_json["id"])) ] )
            if (sorder_s):
                if (len(sorder_s)>1):
                    sorder = sorder_s[0]
                else:
                    sorder = sorder_s
            #if (sorder_s and len(sorder_s)>0):
            #    sorder = saleorder_obj.browse(sorder_s[0] )

        order_fields = {
            'name': "MO [%i]" % ( order_json["id"] ),
            'order_id': '%i' % (order_json["id"]),
            'status': order_json["status"],
            'status_detail': order_json["status_detail"] or '' ,
            'fee_amount': 0.0,
            'total_amount': order_json["total_amount"],
            'paid_amount': order_json["paid_amount"],
            'currency_id': order_json["currency_id"],
            'date_created': ml_datetime(order_json["date_created"]),
            'date_closed': ml_datetime(order_json["date_closed"]),
            'pack_order': False
        }
        if 'tags' in order_json:
            order_fields["tags"] = order_json["tags"]
            if 'pack_order' in order_json["tags"]:
                order_fields["pack_order"] = True

        partner_id = False

        if 'buyer' in order_json:
            Buyer = order_json['buyer']
            Receiver = False
            if ('shipping' in order_json):
                if ('receiver_address' in order_json['shipping']):
                    Receiver = order_json['shipping']['receiver_address']
                elif ('id' in order_json['shipping']):
                    Shipment = self.env["mercadolibre.shipment"].search([('shipping_id','=',order_json['shipping']["id"])])
                    if (len(Shipment)==1):
                        Receiver = {
                            'receiver_address': Shipment.receiver_address_line,
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


            meli_buyer_fields = {
                'name': Buyer['first_name']+' '+Buyer['last_name'],
                'street': self.street(Receiver),
                'city': self.city(Receiver),
                'country_id': self.country(Receiver),
                'state_id': self.state(self.country(Receiver),Receiver),
                'phone': self.full_phone( Buyer ),
                #'email': Buyer['email'],
                'meli_buyer_id': Buyer['id']
            }

            buyer_fields = {
                'name': Buyer['first_name']+' '+Buyer['last_name'],
                'buyer_id': Buyer['id'],
                'nickname': Buyer['nickname'],
                'email': Buyer['email'],
                'phone': self.full_phone( Buyer ),
                'alternative_phone': self.full_alt_phone( Buyer ),
                'first_name': Buyer['first_name'],
                'last_name': Buyer['last_name'],
                'billing_info': self.billing_info(Buyer['billing_info']),
            }
            if ('doc_type' in Buyer['billing_info']):
                buyer_fields['billing_info_doc_type'] = Buyer['billing_info']['doc_type']
                if ('doc_number' in Buyer['billing_info']):
                    buyer_fields['billing_info_doc_number'] = Buyer['billing_info']['doc_number']
            else:
                buyer_fields['billing_info_doc_type'] = ''
                buyer_fields['billing_info_doc_number'] = ''


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
                            afipid = self.env['afip.responsability.type'].search([('code','=',1)]).id
                            meli_buyer_fields["afip_responsability_type_id"] = afipid
                        else:
                            #if (Buyer['billing_info']['doc_type']=="DNI"):
                            #Consumidor Final
                            afipid = self.env['afip.responsability.type'].search([('code','=',5)]).id
                            meli_buyer_fields["afip_responsability_type_id"] = afipid
                    else:
                        _logger.error("res.partner.id_category:" + str(Buyer['billing_info']['doc_type']))

                #Colombia
                if ( ('doc_type' in Buyer['billing_info']) and ('l10n_co_document_type' in self.env['res.partner']._fields) ):
                    if (Buyer['billing_info']['doc_type']=="CC"):
                        meli_buyer_fields['l10n_co_document_type'] = 'national_citizen_id'
                    if (Buyer['billing_info']['doc_type']=="NIT"):
                        meli_buyer_fields['l10n_co_document_type'] = 'rut'
                    if (Buyer['billing_info']['doc_type']=="CE"):
                        meli_buyer_fields['l10n_co_document_type'] = 'foreign_id_card'

                    meli_buyer_fields['vat'] = Buyer['billing_info']['doc_number']


            partner_ids = respartner_obj.search([  ('meli_buyer_id','=',buyer_fields['buyer_id'] ) ] )
            if (len(partner_ids)>0):
                partner_id = partner_ids[0]
            if not partner_id:
                #_logger.info( "creating partner:" + str(meli_buyer_fields) )
                partner_id = respartner_obj.create(( meli_buyer_fields ))
            else:
                partner_id = partner_ids
                _logger.info("Updating partner")
                _logger.info(meli_buyer_fields)

                if (partner_id.email==buyer_fields["email"]):
                    #eliminar email de ML que no es valido
                    meli_buyer_fields["email"] = ''

                partner_id.write(meli_buyer_fields)

            if order and buyer_id:
                return_id = order.write({'buyer':buyer_id.id})

        if (not partner_id):
            _logger.error("No partner founded or created for ML Order" )
            return {'error': 'No partner founded or created for ML Order' }
        #process base order fields
        meli_order_fields = {
            'partner_id': partner_id.id,
            'pricelist_id': plistid.id,
            'meli_order_id': '%i' % (order_json["id"]),
            'meli_status': order_json["status"],
            'meli_status_detail': order_json["status_detail"] or '' ,
            'meli_total_amount': order_json["total_amount"],
            'meli_paid_amount': order_json["paid_amount"],
            'meli_currency_id': order_json["currency_id"],
            'meli_date_created': ml_datetime(order_json["date_created"]),
            'meli_date_closed': ml_datetime(order_json["date_closed"]),
        }

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
            sorder.write( meli_order_fields )
        else:
            _logger.info("Adding new sale.order: " )
            #_logger.info(meli_order_fields)
            if 'pack_order' in order_json["tags"]:
                _logger.info("Pack Order, dont create sale.order, leave it to mercadolibre.shipment")
            else:
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

                product_related = product_obj.search([('meli_id','=',Item['item']['id'])])
                if ("variation_id" in Item["item"]):
                    product_related = product_obj.search([('meli_id','=',Item['item']['id']),('meli_id_variation','=',str(Item['item']['variation_id']))])
                if ( ('seller_custom_field' in Item['item'] or 'seller_sku' in Item['item'])  and len(product_related)==0):

                    seller_sku = Item['item']['seller_custom_field']

                    if (not seller_sku and 'seller_sku' in Item['item']):
                        seller_sku = Item['item']['seller_sku']

                    if (seller_sku):
                        product_related = product_obj.search([('default_code','=',seller_sku)])

                    if (len(product_related)):
                        _logger.info("order product related by seller_custom_field and default_code:"+str(seller_sku) )
                    else:
                        combination = []
                        if ('variation_id' in Item['item'] and Item['item']['variation_id'] ):
                            combination = [( 'meli_id_variation','=',Item['item']['variation_id'])]
                        product_related = product_obj.search([('meli_id','=',Item['item']['id'])] + combination)
                        if product_related and len(product_related):
                            _logger.info("Product founded:"+str(Item['item']['id']))
                        else:
                            #optional, get product
                            if not company.mercadolibre_create_product_from_order:
                                product_related = None

                            try:
                                CLIENT_ID = company.mercadolibre_client_id
                                CLIENT_SECRET = company.mercadolibre_secret_key
                                ACCESS_TOKEN = company.mercadolibre_access_token
                                REFRESH_TOKEN = company.mercadolibre_refresh_token

                                #
                                meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN )

                                response3 = meli.get("/items/"+str(Item['item']['id']), {'access_token':meli.access_token})
                                rjson3 = response3.json()
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
                                productcreated = self.env['product.product'].create((prod_fields))
                                if (productcreated):
                                    if (productcreated.product_tmpl_id):
                                        productcreated.product_tmpl_id.meli_pub = True
                                    _logger.info( "product created: " + str(productcreated) + " >> meli_id:" + str(rjson3['id']) + "-" + str( rjson3['title'].encode("utf-8")) )
                                    #pdb.set_trace()
                                    _logger.info(productcreated)
                                    productcreated.product_meli_get_product()
                                else:
                                    _logger.info( "product couldnt be created")
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
                    'order_item_title': Item['item']['title'],
                    'order_item_category_id': Item['item']['category_id'],
                    'unit_price': Item['unit_price'],
                    'quantity': Item['quantity'],
                    'currency_id': Item['currency_id']
                }

                if (product_related):
                    order_item_fields['product_id'] = product_related.id

                order_item_ids = order_items_obj.search( [('order_item_id','=',order_item_fields['order_item_id']),('order_id','=',order.id)] )
                #_logger.info( order_item_fields )
                if not order_item_ids:
                    #_logger.info( "order_item_fields: " + str(order_item_fields) )
                    order_item_ids = order_items_obj.create( ( order_item_fields ))
                else:
                    order_item_ids.write( ( order_item_fields ) )

                if (product_related_obj == False or len(product_related_obj)==0):
                    _logger.error("No product related to meli_id:"+str(Item['item']['id']))
                    return { 'error': 'No product related to meli_id' }

                order.name = "MO [%s] %s" % ( str(order.order_id), product_related_obj.display_name )

                if (sorder):
                    saleorderline_item_fields = {
                        'company_id': company.id,
                        'order_id': sorder.id,
                        'meli_order_item_id': Item['item']['id'],
                        'price_unit': float(Item['unit_price']),
                        'product_id': product_related_obj.id,
                        'product_uom_qty': Item['quantity'],
                        'product_uom': 1,
                        'name': Item['item']['title'],
                    }
                    saleorderline_item_fields.update( self._set_product_unit_price( product_related_obj, Item ) )

                    saleorderline_item_ids = saleorderline_obj.search( [('meli_order_item_id','=',saleorderline_item_fields['meli_order_item_id']),('order_id','=',sorder.id)] )

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
                    'mercadopago_url': mp_payment_url+'?access_token='+str(company.mercadolibre_access_token),
                    'full_payment': '',
                    'fee_amount': 0,
                    'shipping_amount': 0,
                    'taxes_amount': 0
                }

                headers = {'Accept': 'application/json', 'User-Agent': 'Odoo', 'Content-type':'application/json'}
                params = { 'access_token': company.mercadolibre_access_token }
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

        if company.mercadolibre_cron_get_orders_shipment:
            _logger.info("Updating order: Shipment")
            if (order and order.shipping_id):
                shipment = shipment_obj.fetch( order )
                if (shipment):
                    order.shipment = shipment
                    #TODO: enhance with _order_update_pack()...
                    #Updated sorder because shipment could create sorder pack...
                    if (sorder):
                        shipment.sale_order = sorder
                    else:
                        sorder = shipment.sale_order

        #could be packed sorder or standard one product item order
        if sorder:
            if (company.mercadolibre_order_confirmation!="manual"):
                sorder.confirm_ml()

        return {}

    def orders_update_order( self, context=None ):

        #get with an item id
        company = self.env.user.company_id

        order_obj = self.env['mercadolibre.orders']
        order = self

        log_msg = 'orders_update_order: %s' % (order.order_id)
        _logger.info(log_msg)

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        #
        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN )

        response = meli.get("/orders/"+order.order_id, {'access_token':meli.access_token})
        order_json = response.json()
        #_logger.info( order_json )

        if "error" in order_json:
            _logger.error( order_json["error"] )
            _logger.error( order_json["message"] )
        else:
            try:
                self.orders_update_order_json( {"id": order.id, "order_json": order_json } )
                self._cr.commit()
            except Exception as e:
                _logger.info("orders_update_order > Error actualizando ORDEN")
                _logger.error(e, exc_info=True)
                pass

        return {}


    def orders_query_iterate( self, offset=0, context=None ):

        offset_next = 0

        company = self.env.user.company_id

        orders_obj = self.env['mercadolibre.orders']

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        #
        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN )

        orders_query = "/orders/search?seller="+company.mercadolibre_seller_id+"&sort=date_desc"

        if (offset):
            orders_query = orders_query + "&offset="+str(offset).strip()

        response = meli.get( orders_query, {'access_token':meli.access_token})
        orders_json = response.json()

        if "error" in orders_json:
            _logger.error( orders_query )
            _logger.error( orders_json["error"] )
            if (orders_json["message"]=="invalid_token"):
                _logger.error( orders_json["message"] )
            return {}

        if "paging" in orders_json:
            if "total" in orders_json["paging"]:
                if (orders_json["paging"]["total"]==0):
                    return {}
                else:
                    if (orders_json["paging"]["total"]==orders_json["paging"]["limit"]):
                        offset_next = offset + orders_json["paging"]["limit"]

        if "results" in orders_json:
            for order_json in orders_json["results"]:
                if order_json:
                    #_logger.info( order_json )
                    pdata = {"id": False, "order_json": order_json}
                    try:
                        self.orders_update_order_json( pdata )
                        self._cr.commit()
                    except Exception as e:
                        _logger.info("orders_query_iterate > Error actualizando ORDEN")
                        _logger.error(e, exc_info=True)
                        pass

        if (offset_next>0):
            self.orders_query_iterate(offset_next)

        return {}

    def orders_query_recent( self ):

        self._cr.autocommit(False)

        try:
            self.orders_query_iterate( 0 )
        except Exception as e:
            _logger.info("orders_query_recent > Error iterando ordenes")
            _logger.error(e, exc_info=True)
            self._cr.rollback()

        return {}

    name = fields.Char(string='Order Name',index=True)
    order_id = fields.Char(string='Order Id',index=True)
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
        #The order has not completed by some reason.
                                    ("cancelled","Cancelado")], string='Order Status')

    status_detail = fields.Text(string='Status detail, in case the order was cancelled.')
    date_created = fields.Datetime('Creation date')
    date_closed = fields.Datetime('Closing date')

    order_items = fields.One2many('mercadolibre.order_items','order_id',string='Order Items' )
    payments = fields.One2many('mercadolibre.payments','order_id',string='Payments' )
    shipping = fields.Text(string="Shipping")
    shipping_id = fields.Char(string="Shipping id")
    shipment = fields.Many2one('mercadolibre.shipment',string='Shipment')

    fee_amount = fields.Float(string='Fee total amount')
    total_amount = fields.Float(string='Total amount')
    shipping_cost = fields.Float(string='Shipping Cost',help='Gastos de envío')
    shipping_list_cost = fields.Float(string='Shipping List Cost',help='Gastos de envío, costo de lista/interno')
    paid_amount = fields.Float(string='Paid amount',help='Includes shipping cost')
    currency_id = fields.Char(string='Currency')
    buyer =  fields.Many2one( "mercadolibre.buyers","Buyer")
    seller = fields.Text( string='Seller' )
    tags = fields.Text(string="Tags")
    pack_order = fields.Boolean(string="Order Pack (Carrito)")

mercadolibre_orders()


class mercadolibre_order_items(models.Model):
    _name = "mercadolibre.order_items"
    _description = "Producto pedido en MercadoLibre"

    posting_id = fields.Many2one("mercadolibre.posting","Posting")
    product_id = fields.Many2one("product.product",string="Product",help="Product Variant")
    order_id = fields.Many2one("mercadolibre.orders","Order")
    order_item_id = fields.Char('Item Id')
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

    name = fields.Char(string='Name')
    buyer_id = fields.Char(string='Buyer ID')
    nickname = fields.Char(string='Nickname')
    email = fields.Char(string='Email')
    phone = fields.Char( string='Phone')
    alternative_phone = fields.Char( string='Alternative Phone')
    first_name = fields.Char( string='First Name')
    last_name = fields.Char( string='Last Name')
    billing_info = fields.Char( string='Billing Info')
    billing_info_doc_type = fields.Char( string='Billing Info Doc Type')
    billing_info_doc_number = fields.Char( string='Billing Info Doc Number')

mercadolibre_buyers()

class res_partner(models.Model):
    _inherit = "res.partner"


    meli_buyer_id = fields.Char('Meli Buyer Id')
    meli_buyer = fields.Many2one('mercadolibre.buyers',string='Buyer')


res_partner()


class mercadolibre_orders_update(models.TransientModel):
    _name = "mercadolibre.orders.update"
    _description = "Update Order"

    def order_update(self, context=None):
        context = context or self.env.context
        orders_ids = context['active_ids']
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
