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

from openerp.osv import fields, osv
import logging
import meli_oerp_config

import melisdk
from melisdk.meli import Meli

import json

import logging
_logger = logging.getLogger(__name__)

import posting
import product
#https://api.mercadolibre.com/questions/search?item_id=MLA508223205

class sale_order_line(osv.osv):
    _inherit = "sale.order.line"

    _columns = {
        'meli_order_item_id': fields.char('Meli Order Item Id'),
    }
sale_order_line()

class sale_order(osv.osv):
    _inherit = "sale.order"

    _columns = {
        'meli_order_id': fields.char('Meli Order Id'),
        'meli_status': fields.selection( [
        #Initial state of an order, and it has no payment yet.
                                        ("confirmed","Confirmado"),
        #The order needs a payment to become confirmed and show users information.
                                      ("payment_required","Pago requerido"),
        #There is a payment related with the order, but it has not accredited yet
                                    ("payment_in_process","Pago en proceso"),
        #The order has a related payment and it has been accredited.
                                    ("paid","Pagado"),
        #The order has not completed by some reason.
                                    ("cancelled","Cancelado")], string='Order Status'),

        'meli_status_detail': fields.text(string='Status detail, in case the order was cancelled.'),
        'meli_date_created': fields.date('Creation date'),
        'meli_date_closed': fields.date('Closing date'),

#        'meli_order_items': fields.one2many('mercadolibre.order_items','order_id','Order Items' ),
#        'meli_payments': fields.one2many('mercadolibre.payments','order_id','Payments' ),
        'meli_shipping': fields.text(string="Shipping"),

        'meli_total_amount': fields.char(string='Total amount'),
        'meli_currency_id': fields.char(string='Currency'),
#        'buyer': fields.many2one( "mercadolibre.buyers","Buyer"),
#       'meli_seller': fields.text( string='Seller' ),
    }

sale_order()

class res_partner(osv.osv):
    _inherit = "res.partner"

    _columns = {
        'meli_buyer_id': fields.char('Meli Buyer Id'),
    }

res_partner()

class mercadolibre_orders(osv.osv):
    _name = "mercadolibre.orders"
    _description = "Pedidos en MercadoLibre"


    def billing_info( self, cr, uid, billing_json, context=None ):
        billinginfo = ''

        if 'doc_type' in billing_json:
            if billing_json['doc_type']:
                billinginfo+= billing_json['doc_type']

        if 'doc_number' in billing_json:
            if billing_json['doc_number']:
                billinginfo+= billing_json['doc_number']

        return billinginfo

    def full_phone( self, cr, uid, phone_json, context=None ):
        full_phone = ''

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

    def pretty_json( self, cr, uid, ids, data, indent=0, context=None ):
        return json.dumps( data, sort_keys=False, indent=4 )

    def orders_update_order_json( self, cr, uid, data, context=None ):

        oid = data["id"]
        order_json = data["order_json"]
        print "data:" + str(data)
        #_logger.info("orders_update_order_json > data[id]: " + oid + " order_json:" + order_json )

        user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        company = user_obj.company_id

        saleorder_obj = self.pool.get('sale.order')
        saleorderline_obj = self.pool.get('sale.order.line')
        product_obj = self.pool.get('product.product')
        pricelist_obj = self.pool.get('product.pricelist')
        respartner_obj = self.pool.get('res.partner')

        plistids = pricelist_obj.search(cr,uid, [('currency_id','=','ARS')] )
        plistid = None
        if plistids:
            plistid = plistids[0]

        order_obj = self.pool.get('mercadolibre.orders')
        buyers_obj = self.pool.get('mercadolibre.buyers')
        posting_obj = self.pool.get('mercadolibre.posting')
        order_items_obj = self.pool.get('mercadolibre.order_items')
        payments_obj = self.pool.get('mercadolibre.payments')


        order = None
        sorder = None

        # if id is defined, we are updating existing one
        if (oid):
            order = order_obj.browse(cr, uid, oid )
            ##sorder = order_obj.browse(
            sorder = saleorder_obj.browse(cr, uid, oid )
        else:
        #we search for existing order with same order_id => "id"
            order_s = order_obj.search(cr,uid, [ ('order_id','=',order_json['id']) ] )
            if (order_s):
                order = order_obj.browse(cr, uid, order_s[0] )

            sorder_s = saleorder_obj.search(cr,uid, [ ('meli_order_id','=',order_json['id']) ] )
            if (sorder_s and len(sorder_s)>0):
                sorder = saleorder_obj.browse(cr, uid, sorder_s[0] )

        order_fields = {
            'order_id': '%i' % (order_json["id"]),
            'status': order_json["status"],
            'status_detail': order_json["status_detail"] or '' ,
            'total_amount': order_json["total_amount"],
            'currency_id': order_json["currency_id"],
            'date_created': order_json["date_created"] or '',
            'date_closed': order_json["date_closed"] or '',
        }

        print "order:" + str(order)

        if 'buyer' in order_json:
            Buyer = order_json['buyer']
            meli_buyer_fields = {
                'name': Buyer['first_name']+' '+Buyer['last_name'],
                'street': 'no street',
                'phone': self.full_phone( cr, uid, Buyer['phone']),
                'email': Buyer['email'],
                'meli_buyer_id': Buyer['id'],
            }

            buyer_fields = {
                'buyer_id': Buyer['id'],
                'nickname': Buyer['nickname'],
                'email': Buyer['email'],
                'phone': self.full_phone( cr, uid, Buyer['phone']),
                'alternative_phone': self.full_phone( cr, uid, Buyer['alternative_phone']),
                'first_name': Buyer['first_name'],
                'last_name': Buyer['last_name'],
                'billing_info': self.billing_info( cr, uid, Buyer['billing_info']),
            }

            buyer_ids = buyers_obj.search(cr,uid,[  ('buyer_id','=',buyer_fields['buyer_id'] ) ] )
            buyer_id = 0
            if not buyer_ids:
                print "creating buyer:" + str(buyer_fields)
                buyer_id = buyers_obj.create(cr,uid,( buyer_fields ))
            else:
                if (len(buyer_ids)>0):
                      buyer_id = buyer_ids[0]

            partner_ids = respartner_obj.search(cr,uid,[  ('meli_buyer_id','=',buyer_fields['buyer_id'] ) ] )
            partner_id = 0
            if not partner_ids:
                print "creating partner:" + str(meli_buyer_fields)
                partner_id = respartner_obj.create(cr,uid,( meli_buyer_fields ))
            else:
                if (len(partner_ids)>0):
                    partner_id = partner_ids[0]

            if order:
                return_id = self.pool.get('mercadolibre.orders').write(cr,uid,order.id,{'buyer':buyer_id})
            else:
                buyers_obj.write(cr,uid, buyer_id, ( buyer_fields ) )

        if (len(partner_ids)>0):
            partner_id = partner_ids[0]
        #process base order fields
        meli_order_fields = {
            'partner_id': partner_id,
            'pricelist_id': plistid,
            'meli_order_id': '%i' % (order_json["id"]),
            'meli_status': order_json["status"],
            'meli_status_detail': order_json["status_detail"] or '' ,
            'meli_total_amount': order_json["total_amount"],
            'meli_currency_id': order_json["currency_id"],
            'meli_date_created': order_json["date_created"] or '',
            'meli_date_closed': order_json["date_closed"] or '',
        }

        if (order_json["shipping"]):
            order_fields['shipping'] = self.pretty_json( cr, uid, id, order_json["shipping"] )
            meli_order_fields['meli_shipping'] = self.pretty_json( cr, uid, id, order_json["shipping"] )


        #create or update order
        if (order and order.id):
            _logger.info("Updating order: %s" % (order.id))
            order.write( order_fields )
        else:
            _logger.info("Adding new order: " )
            _logger.info(order_fields)
            print "creating order:" + str(order_fields)
            return_id = order_obj.create(cr,uid,(order_fields))
            order = order_obj.browse(cr,uid,return_id)

        if (sorder and sorder.id):
            _logger.info("Updating sale.order: %s" % (sorder.id))
            sorder.write( meli_order_fields )
        else:
            _logger.info("Adding new sale.order: " )
            _logger.info(meli_order_fields)
            print "creating sale order:" + str(order_fields)
            sreturn_id = saleorder_obj.create(cr,uid,(meli_order_fields))
            sorder = saleorder_obj.browse(cr,uid,sreturn_id)

        #check error
        if not order:
            _logger.error("Error adding order. " )
            print "Error adding order"
            return {}

        #check error
        if not sorder:
            _logger.error("Error adding sale.order. " )
            print "Error adding sale.order"
            return {}

        #update internal fields (items, payments, buyers)
        if 'order_items' in order_json:
            items = order_json['order_items']
            _logger.info( items )
            print "order items" + str(items)
            cn = 0
            for Item in items:
                cn = cn + 1
                _logger.info(cn)
                _logger.info(Item )

                product_related = product_obj.search( cr, uid, [('meli_id','=',Item['item']['id'])])
                post_related = posting_obj.search( cr, uid, [('meli_id','=',Item['item']['id'])])
                post_related_obj = ''
                product_related_obj = ''
                product_related_obj_id = False
                if (post_related):
                    if (post_related[0]):
                        post_related_obj = post_related[0]

                if (product_related):
                    if (product_related[0]):
                        product_related_obj_id = product_related[0]
                        product_related_obj = product_obj.browse(cr, uid, product_related_obj_id)
                        _logger.info("product_related:")
                        _logger.info( product_related_obj )

                order_item_fields = {
                    'order_id': order.id,
                    'posting_id': post_related_obj,
                    'order_item_id': Item['item']['id'],
                    'order_item_title': Item['item']['title'],
                    'order_item_category_id': Item['item']['category_id'],
                    'unit_price': Item['unit_price'],
                    'quantity': Item['quantity'],
                    'currency_id': Item['currency_id']
                }
                order_item_ids = order_items_obj.search(cr,uid,[('order_item_id','=',order_item_fields['order_item_id']),('order_id','=',order.id)] )

                if not order_item_ids:
                    print "order_item_fields: " + str(order_item_fields)
                    order_item_ids = order_items_obj.create(cr,uid,( order_item_fields ))
                else:
                    order_items_obj.write(cr,uid, order_item_ids[0], ( order_item_fields ) )

                saleorderline_item_fields = {
                    'company_id': company.id,
                    'order_id': sorder.id,
                    'meli_order_item_id': Item['item']['id'],
                    'price_unit': float(Item['unit_price']),
                    'price_total': float(Item['unit_price']) * float(Item['quantity']),
                    'product_id': product_related_obj.id,
                    'product_uom_qty': Item['quantity'],
                    'product_uom': 1,
                    'name': Item['item']['title'],
                    'customer_lead': float(0)                    
                }
                saleorderline_item_ids = saleorderline_obj.search(cr,uid,[('meli_order_item_id','=',saleorderline_item_fields['meli_order_item_id']),('order_id','=',sorder.id)] )

                if not saleorderline_item_ids:
                    print "saleorderline_item_fields: " + str(saleorderline_item_fields)
                    saleorderline_item_ids = saleorderline_obj.create(cr,uid,( saleorderline_item_fields ))
                else:
                    saleorderline_obj.write(cr,uid, saleorderline_item_ids[0], ( saleorderline_item_fields ) )


        if 'payments' in order_json:
            payments = order_json['payments']
            _logger.info( payments )
            cn = 0
            for Payment in payments:
                cn = cn + 1
                _logger.info(cn)
                _logger.info(Payment )

                payment_fields = {
                    'order_id': order.id,
                    'payment_id': Payment['id'],
                    'transaction_amount': Payment['transaction_amount'] or '',
                    'currency_id': Payment['currency_id'] or '',
                    'status': Payment['status'] or '',
                    'date_created': Payment['date_created'] or '',
                    'date_last_modified': Payment['date_last_modified'] or '',
                }

                payment_ids = payments_obj.search(cr,uid,[  ('payment_id','=',payment_fields['payment_id']),
                                                            ('order_id','=',order.id ) ] )

                if not payment_ids:
	                payment_ids = payments_obj.create(cr,uid,( payment_fields ))
                else:
                    payments_obj.write(cr,uid, payment_ids[0], ( payment_fields ) )


        if order:
            return_id = self.pool.get('mercadolibre.orders').update

        return {}

    def orders_update_order( self, cr, uid, id, context=None ):

        #get with an item id
        user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        company = user_obj.company_id

        order_obj = self.pool.get('mercadolibre.orders')
        order_items_obj = self.pool.get('mercadolibre.order_items')
        order = order_obj.browse(cr, uid, id )

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
        #_logger.info( product_json )

        if "error" in order_json:
            _logger.error( order_json["error"] )
            _logger.error( order_json["message"] )
        else:
            self.orders_update_order_json( cr, uid, {"id": id, "order_json": order_json } )


        return {}


    def orders_query_iterate( self, cr, uid, offset=0, context=None ):


        offset_next = 0

        user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        company = user_obj.company_id

        orders_obj = self.pool.get('mercadolibre.orders')

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



        _logger.info( orders_json )

        #testing with json:
        if (True==False):
            with open('/home/fabricio/envOdoo8/sources/meli_oerp/orders.json') as json_data:
                _logger.info( json_data )
                orders_json = json.load(json_data)
                _logger.info( orders_json )


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
                    self.orders_update_order_json( cr, uid, {"id": False, "order_json": order_json} )


        if (offset_next>0):
            self.orders_query_iterate(cr,uid,offset_next)

        return {}

    def orders_query_recent( self, cr, uid, context=None ):

        self.orders_query_iterate( cr, uid, 0 )

        return {}

    _columns = {
        'order_id': fields.char('Order Id'),

        'status': fields.selection( [
        #Initial state of an order, and it has no payment yet.
                                        ("confirmed","Confirmado"),
        #The order needs a payment to become confirmed and show users information.
                                      ("payment_required","Pago requerido"),
        #There is a payment related with the order, but it has not accredited yet
                                    ("payment_in_process","Pago en proceso"),
        #The order has a related payment and it has been accredited.
                                    ("paid","Pagado"),
        #The order has not completed by some reason.
                                    ("cancelled","Cancelado")], string='Order Status'),

        'status_detail': fields.text(string='Status detail, in case the order was cancelled.'),
        'date_created': fields.date('Creation date'),
        'date_closed': fields.date('Closing date'),

        'order_items': fields.one2many('mercadolibre.order_items','order_id','Order Items' ),
        'payments': fields.one2many('mercadolibre.payments','order_id','Payments' ),
        'shipping': fields.text(string="Shipping"),

        'total_amount': fields.char(string='Total amount'),
        'currency_id': fields.char(string='Currency'),
        'buyer': fields.many2one( "mercadolibre.buyers","Buyer"),
        'seller': fields.text( string='Seller' ),
    }

mercadolibre_orders()


class mercadolibre_order_items(osv.osv):
	_name = "mercadolibre.order_items"
	_description = "Producto pedido en MercadoLibre"

	_columns = {
        'posting_id': fields.many2one("mercadolibre.posting","Posting"),
        'order_id': fields.many2one("mercadolibre.orders","Order"),
        'order_item_id': fields.char('Item Id'),
        'order_item_title': fields.char('Item Title'),
        'order_item_category_id': fields.char('Item Category Id'),
        'unit_price': fields.char(string='Unit price'),
        'quantity': fields.integer(string='Quantity'),
#        'total_price': fields.char(string='Total price'),
        'currency_id': fields.char(string='Currency')
	}
mercadolibre_order_items()


class mercadolibre_payments(osv.osv):
	_name = "mercadolibre.payments"
	_description = "Pagos en MercadoLibre"

	_columns = {
        'order_id': fields.many2one("mercadolibre.orders","Order"),
        'payment_id': fields.char('Payment Id'),
        'transaction_amount': fields.char('Transaction Amount'),
        "currency_id": fields.char(string='Currency'),
        "status": fields.char(string='Payment Status'),
        "date_created": fields.date('Creation date'),
        "date_last_modified": fields.date('Modification date'),
	}
mercadolibre_payments()

class mercadolibre_buyers(osv.osv):
	_name = "mercadolibre.buyers"
	_description = "Compradores en MercadoLibre"

	_columns = {
        'buyer_id': fields.char(string='Buyer ID'),
        'nickname': fields.char(string='Nickname'),
        'email': fields.char(string='Email'),
        'phone': fields.char( string='Phone'),
        'alternative_phone': fields.char( string='Alternative Phone'),
        'first_name': fields.char( string='First Name'),
        'last_name': fields.char( string='Last Name'),
        'billing_info': fields.char( string='Billing Info'),
	}
mercadolibre_buyers()


class mercadolibre_orders_update(osv.osv_memory):
    _name = "mercadolibre.orders.update"
    _description = "Update Order"

    def order_update(self, cr, uid, ids, context=None):

        orders_ids = context['active_ids']
        orders_obj = self.pool.get('mercadolibre.orders')

        for order_id in orders_ids:

            _logger.info("order_update: %s " % (order_id) )

            order = orders_obj.browse(cr,uid, order_id)
            orders_obj.orders_update_order( cr, uid, order_id )

        return {}

mercadolibre_orders_update()

