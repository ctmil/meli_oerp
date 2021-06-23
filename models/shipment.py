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

from urllib.request import urlopen
import requests
import base64
import mimetypes
from . import orders
from . import product
from . import product_post
from . import posting
from . import res_partner
from pdf2image import convert_from_path, convert_from_bytes

from dateutil.parser import *
from datetime import *

from . import versions
from .versions import *

#
#     https://www.odoo.com/fr_FR/forum/aide-1/question/solved-call-report-and-save-result-to-attachment-133244
#


#
# https://api.mercadolibre.com/shipment_labels?shipment_ids=20178600648,20182100995&response_type=pdf&access_token=
class mercadolibre_shipment_print(models.TransientModel):
    _name = "mercadolibre.shipment.print"
    _description = "Impresión de etiquetas"

    def shipment_print(self, context=None, meli=None, config=None):
        context = context or self.env.context
        company = self.env.user.company_id
        if not config:
            config = company
        shipment_ids = ('active_ids' in context and context['active_ids']) or []
        shipment_obj = self.env['mercadolibre.shipment']
        warningobj = self.env['warning']

        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)
            if meli.need_login():
                return meli.redirect_login()

        _logger.info("shipment_print")
        _logger.info(shipment_ids)

        return self.shipment_print_report(shipment_ids=shipment_ids,meli=meli,config=config,include_ready_to_print=self.include_ready_to_print)

    def shipment_stock_picking_print(self, context=None, meli=None, config=None):
        _logger.info("shipment_stock_picking_print")
        context = context or self.env.context
        company = self.env.user.company_id
        if not config:
            config = company
        picking_ids = ('active_ids' in context and context['active_ids']) or []
        #product_obj = self.env['product.template']
        picking_obj = self.env['stock.picking']
        shipment_obj = self.env['mercadolibre.shipment']
        warningobj = self.env['warning']

        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)
            if meli.need_login():
                return meli.redirect_login()

        sep = ""
        shipment_ids= []

        for pick_id in picking_ids:
            #sacar la orden relacionada
            #de la orden sacar el shipping id
            pick = picking_obj.browse(pick_id)
            shipid = None
            shipment = None
            if (pick and pick.sale_id):
                if (pick.sale_id.meli_shipment):
                    shipid = pick.sale_id.meli_shipment.id
                if ( (not shipid) and len(pick.sale_id.meli_orders) ):
                    shipment = shipment_obj.search([('shipping_id','=',pick.sale_id.meli_orders[0].shipping_id)])
                    if (shipment):
                        shipid = shipment.id
            else:
                continue;

            if (shipid):
                #shipment = shipment_obj.browse(shipid)
                #shipment.update()
                shipment_ids.append(shipid)

        return self.shipment_print_report(shipment_ids=shipment_ids,meli=meli,config=config,include_ready_to_print=self.include_ready_to_print)

    def shipment_print_report(self, shipment_ids=[], meli=None, config=None, include_ready_to_print=None):
        full_ids = ""
        reporte = ""
        sep = ""
        full_url_link_pdf = {}
        shipment_obj = self.env['mercadolibre.shipment']
        warningobj = self.env['warning']

        for shipid in shipment_ids:
            shipment = shipment_obj.browse(shipid)
            ship_report = shipment.shipment_print( meli=meli, config=config, include_ready_to_print=include_ready_to_print )
            reporte = reporte + sep + str( ship_report['message'] )

            if (shipment and shipment.status=="ready_to_ship"):
                atoken = ship_report['access_token']
                if atoken and not (atoken in full_url_link_pdf):
                    full_url_link_pdf[atoken] = { 'full_ids': '', 'comma': '', 'full_link': '' }

                if atoken and atoken in full_url_link_pdf:
                    full_url_link_pdf[atoken]['full_ids'] += full_url_link_pdf[atoken]['comma'] + shipment.shipping_id
                    full_url_link_pdf[atoken]['comma']  = ","

                    full_url_link_pdf[atoken]['full_link'] = "https://api.mercadolibre.com/shipment_labels?shipment_ids="+full_url_link_pdf[atoken]['full_ids']+"&response_type=pdf&access_token="+atoken

            sep = "<br>"+"\n"

        full_links = ''
        for atoken in full_url_link_pdf:
            _logger.info('atoken:'+str(atoken))
            full_ids+= full_url_link_pdf[atoken]['full_ids']
            full_link = full_url_link_pdf[atoken]['full_link']
            #_logger.info(full_link)
            if full_link:
                full_links+= '<a href="'+full_link+'" target="_blank"><strong><u>Descargar PDF</u></strong></a>'

        if (full_links):
            return warningobj.info( title='Impresión de etiquetas', message="Abrir links para descargar PDF", message_html=""+full_ids+'<br><br>'+full_links+"<br><br>Reporte de no impresas:<br>"+reporte )
        else:
            return warningobj.info( title='Impresión de etiquetas: Estas etiquetas ya fueron todas impresas.', message=reporte )


    include_ready_to_print = fields.Boolean(string="Include Ready To Print",default=False)

mercadolibre_shipment_print()


class mercadolibre_shipment_update(models.TransientModel):
    _name = "mercadolibre.shipment.update"
    _description = "Actualizar datos de envio"

    def shipment_update(self, context=None, config=None, meli=None):
        context = context or self.env.context
        company = self.env.user.company_id
        if not config:
            config = company
        shipment_ids = ('active_ids' in context and context['active_ids']) or []
        #product_obj = self.env['product.template']
        shipment_obj = self.env['mercadolibre.shipment']
        warningobj = self.env['warning']

        _logger.info("shipment_update")
        _logger.info(shipment_ids)
        #_logger.info( "shipment_update: context: "+str(context)+" meli: "+str(meli)+ " config: " +str(config) )


        for shipid in shipment_ids:
            shipment = shipment_obj.browse(shipid)
            if (shipment):
                shipment.update(meli=meli,config=config)


mercadolibre_shipment_update()

class mercadolibre_shipment_item(models.Model):
    _name = "mercadolibre.shipment.item"
    _description = "Item de Envio de MercadoLibre"

    shipment_id = fields.Many2one("mercadolibre.shipment",string="Shipment")
    name = fields.Char(string='Name', index=True)
    description = fields.Char(string="Description", index=True)
    item_id = fields.Char(string="Item Id (meli id)", index=True)
    variation_id = fields.Char(string="Variation Id", index=True)
    order_id = fields.Char(string="Order Id", index=True)
    data = fields.Text(string="Full Item Data")

mercadolibre_shipment_item()

class mercadolibre_shipment(models.Model):
    _name = "mercadolibre.shipment"
    _description = "Envio de MercadoLibre"

    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Name',index=True)
    site_id = fields.Char(string='Site id')
    posting_id = fields.Many2one("mercadolibre.posting",string="Posting")
    shipping_id = fields.Char(string='Envio Id',index=True)
    order_id = fields.Char(string='Order Id',index=True)
    order = fields.Many2one("mercadolibre.orders",string="Order")
    orders = fields.Many2many("mercadolibre.orders",string="Orders (carrito)")
    shipment_items = fields.One2many("mercadolibre.shipment.item","shipment_id",string="Items")
    sale_order = fields.Many2one('sale.order',string="Sale Order",help="Pedido de venta relacionado en Odoo")

    mode = fields.Char('Mode')
    shipping_mode = fields.Char(string='Shipping mode')

    date_created = fields.Datetime(string='Creation date')
    last_updated = fields.Datetime(string='Last updated')

    order_cost = fields.Float(string='Order Cost')
    base_cost = fields.Float(string='Base Cost')
    shipping_cost = fields.Float(string='Shipping Cost')
    shipping_list_cost = fields.Float(string='Shipping List Cost')
    promoted_amount = fields.Float(string='Promoted amount')

    #state = fields.Selection(string="State",)
    status = fields.Char(string="Status",index=True)
    substatus = fields.Char(string="Sub Status",index=True)
    status_history = fields.Text(string="status_history",index=True)
    tracking_number = fields.Char(string="Tracking number",index=True)
    tracking_method = fields.Char(string="Tracking method",index=True)
    comments = fields.Char(string="Tracking Custom Comments")


    date_first_printed = fields.Datetime(string='First Printed date',index=True)

    receiver_id = fields.Char('Receiver Id')
    receiver_address_id = fields.Char('Receiver address id')
    receiver_address_phone = fields.Char('Phone')
    receiver_address_name = fields.Char('Nombre')
    receiver_address_comment = fields.Char('Comment')

    receiver_address_line = fields.Char('Receiver Address Line')
    receiver_street_name = fields.Char('Calle')
    receiver_street_number = fields.Char('Nro')
    receiver_city = fields.Char('Ciudad')
    receiver_city_code = fields.Char(string='Codigo Ciudad')
    receiver_state = fields.Char('Estado')
    receiver_state_code = fields.Char('Estado ID')
    receiver_state_id = fields.Many2one('res.country.state',string='State')

    receiver_country = fields.Char('Pais')
    receiver_country_code = fields.Char('Código Pais')
    receiver_country_id = fields.Many2one('res.country',string='Country')
    receiver_latitude = fields.Char('Latitud')
    receiver_longitude = fields.Char('Longitud')

    sender_id = fields.Char('Sender Id')
    sender_address_id = fields.Char('Sender Address Id')
    sender_address_line = fields.Char('Sender Address Line')
    sender_address_comment = fields.Text('Sender Address Comment')

    sender_street_name = fields.Char('Sender Address Street Name')
    sender_street_number = fields.Char('Sender Address Street Number')
    sender_city = fields.Char('Sender Address City')
    sender_state = fields.Char('Sender Address State')
    sender_country = fields.Char('Sender Address Country')
    sender_latitude = fields.Char('Sender Address Latitude')
    sender_longitude = fields.Char('Sender Address Longitude')

    logistic_type = fields.Char('Logistic type',index=True)

    pdf_link = fields.Char('Pdf link')
    pdf_file = fields.Binary(string='Pdf File',attachment=True)
    pdf_filename = fields.Char(string='Pdf Filename')
    pdfimage_file = fields.Binary(string='Pdf Image File',attachment=True)
    pdfimage_filename = fields.Char(string='Pdf Image Filename')

    company_id = fields.Many2one("res.company",string="Company")
    seller_id = fields.Many2one("res.users",string="Seller")

    pack_order = fields.Boolean(string="Carrito de compra")

    _sql_constraints = [
        ('unique_shipping_id','unique(shipping_id)','Meli Shipping id already exists!'),
    ]

    def create_shipment( self ):
        return {}

    def _update_sale_order_shipping_info( self, order, meli=None, config=None ):

        company = self.env.user.company_id
        product_tpl = self.env['product.template']
        product_obj = self.env['product.product']
        saleorderline_obj = self.env['sale.order.line']

        for shipment in self:
            _logger.info("_update_sale_order_shipping_info")
            sorder = shipment.sale_order
            if (not sorder or not order):
                continue;

            sorder.meli_shipping_cost = shipment.shipping_cost
            sorder.meli_shipping_list_cost = shipment.shipping_list_cost
            sorder.meli_shipment_logistic_type = shipment.logistic_type

            order.shipping_cost = shipment.shipping_cost
            order.shipping_list_cost = shipment.shipping_list_cost
            order.shipment_logistic_type = shipment.logistic_type

            if (sorder.partner_id):
                partner_id = sorder.partner_id
                if (partner_id and "meli_update_forbidden" in partner_id._fields and not partner_id.meli_update_forbidden):
                    partner_id.street = shipment.receiver_address_line
                    partner_id.street2 = shipment.receiver_address_comment
                    partner_id.city = shipment.receiver_city
                    if shipment.receiver_address_phone and not ("XXXX" in shipment.receiver_address_phone):
                        partner_id.phone = shipment.receiver_address_phone
                #sorder.partner_id.state = ships.receiver_state

            ship_name = shipment.tracking_method or (shipment.mode=="custom" and "Personalizado")

            if not ship_name or len(ship_name)==0:
                continue;

            product_shipping_id = product_obj.search([('default_code','=','ENVIO')])
            if (len(product_shipping_id)==0):
                product_shipping_id = product_obj.search(['|','|',('default_code','=','ENVIO'),
                        ('default_code','=',ship_name),
                        ('name','=',ship_name)] )

            if len(product_shipping_id):
                product_shipping_id = product_shipping_id[0]
            else:
                product_shipping_id = None
                ship_prod = {
                    "name": ship_name,
                    "default_code": ship_name,
                    "type": "service",
                    #"taxes_id": None
                    #"categ_id": 279,
                    #"company_id": company.id
                }
                _logger.info(ship_prod)
                product_shipping_tpl = product_tpl.create((ship_prod))
                if (product_shipping_tpl):
                    product_shipping_id = product_shipping_tpl.product_variant_ids[0]
            _logger.info(product_shipping_id)

            if (not product_shipping_id):
                _logger.info('Failed to create shipping product service')
                continue

            #CO
            if "enable_charges" in product_shipping_id._fields:
                product_shipping_id.enable_charges = True

            ship_carrier = {
                "name": ship_name,
            }
            ship_carrier["product_id"] = product_shipping_id.id
            ship_carrier_id = self.env["delivery.carrier"].search([ ('name','=',ship_carrier['name']) ])
            if not ship_carrier_id:
                ship_carrier_id = self.env["delivery.carrier"].create(ship_carrier)
            if (len(ship_carrier_id)>1):
                ship_carrier_id = ship_carrier_id[0]
                ship_carrier_id.write(ship_carrier)

            stock_pickings = self.env["stock.picking"].search([('sale_id','=',sorder.id),('name','like','OUT')])
            #carrier_id = self.env["delivery.carrier"].search([('name','=',)])
            for st_pick in stock_pickings:
                #if ( 1==2 and ship_carrier_id ):
                #    st_pick.carrier_id = ship_carrier_id
                st_pick.carrier_tracking_ref = shipment.tracking_number

            if (shipment.tracking_method == "MEL Distribution"):
                _logger.info('MEL Distribution, not adding to order')
                #continue

            del_price = shipment.shipping_cost
            delivery_price = ml_product_price_conversion( self, product_related_obj=product_shipping_id, price=del_price, config=config ),
            if type(delivery_price)==tuple and len(delivery_price):
                delivery_price = delivery_price[0]

            _logger.info("delivery_price:"+str(delivery_price)+" meli_paid_amount: "+str(sorder.meli_paid_amount) +" amount_total:"+str(sorder.amount_total) )

            shipment_amount_cond = abs(sorder.meli_paid_amount - sorder.amount_total)>1.0 and (delivery_price>0.0)
            _logger.info("shipment_amount_cond:"+str(shipment_amount_cond))
            shipment_amount_cond_fix = (sorder.amount_total-sorder.meli_paid_amount)>1.0 and (delivery_price>0.0)
            _logger.info("shipment_amount_cond_fix:"+str(shipment_amount_cond_fix))

            shipment_amount_cond_fix2 = (sorder.amount_total-sorder.meli_paid_amount)<-1.0 and (delivery_price>0.0)

            if (not shipment_amount_cond) or shipment_amount_cond_fix:
                _logger.info("shipment_cond: "+str(shipment_amount_cond)+" paid: "+str(sorder.meli_paid_amount)+" vs total: "+str(sorder.amount_total))
                if ( ship_carrier_id and sorder.carrier_id):
                #if ( ship_carrier_id and sorder.carrier_id and abs( sorder.amount_total - sorder.meli_paid_amount - delivery_price ) < 1.0 ):
                    delivery_price = 0.0
                    set_delivery_line( sorder, delivery_price, "Defined by MELI" )
                delivery_price = 0.0
            if shipment_amount_cond_fix2 and ship_carrier_id and sorder.carrier_id:
                set_delivery_line( sorder, delivery_price, "Defined by MELI" )


            if (ship_carrier_id and not sorder.carrier_id):
                sorder.carrier_id = ship_carrier_id
                #vals = sorder.carrier_id.rate_shipment(sorder)
                #if vals.get('success'):
                #delivery_message = vals.get('warning_message', False)
                delivery_message = "Defined by MELI"
                #delivery_price = vals['price']
                #display_price = vals['carrier_price']
                set_delivery_line(sorder, delivery_price, delivery_message )

            #REMOVE OLD SALE ORDER ITEM SHIPPING ITEM
            saleorderline_item_fields = {
                'company_id': company.id,
                'order_id': sorder.id,
                'meli_order_item_id': 'ENVIO',
                'price_unit': delivery_price,
                'product_id': product_shipping_id.id,
                'product_uom_qty': 1.0,
                #'tax_id': None,
                'product_uom': product_shipping_id.uom_id.id,
                'name': "Shipping " + str(shipment.shipping_mode),
            }
            saleorderline_item_ids = saleorderline_obj.search( [('meli_order_item_id','=',saleorderline_item_fields['meli_order_item_id']),
                                                                ('order_id','=',sorder.id)] )

            if not saleorderline_item_ids and (del_price>0):
                #saleorderline_item_ids = saleorderline_obj.create( ( saleorderline_item_fields ))
                pass;
            else:
                if (1==2 and del_price>0):
                    saleorderline_item_ids.write( ( saleorderline_item_fields ) )
                    #saleorderline_item_ids.tax_id = None
                else:
                    try:
                        saleorderline_item_ids.unlink()
                    except:
                        _logger.info("Could not unlink.")

    def partner_delivery_id( self, partner_id=None, Receiver=None ):
        if not Receiver:
            return None
        orders_obj = self.env['mercadolibre.orders']

        partner_shipping_id = None

        deliv_id = self.env["res.partner"].search([("parent_id","=",partner_id.id),
                                                ("type","=","delivery"),
                                                #('street','=',partner_id.street)
                                                ],
                                            limit=1)

        _logger.info("partner_delivery_id > Receiver: "+str(Receiver) )

        pdelivery_fields = {
            "type": "delivery",
            "parent_id": partner_id.id,
            'name': Receiver["receiver_name"],
            'street': Receiver['address_line'],
            #'street2': meli_buyer_fields['name'],
            'city': orders_obj.city(Receiver),
            'country_id': orders_obj.country(Receiver),
            'state_id': orders_obj.state(orders_obj.country(Receiver),Receiver),
            #'zip': meli_buyer_fields['name'],
            #'phone': orders_obj.full_phone( Receiver ),
            #'email':contactfields['billingInfo_email'],
        }
        full_phone = orders_obj.full_phone( Receiver )
        if full_phone and not ("XXXX" in full_phone):
            pdelivery_fields['phone'] = full_phone

        pdelivery_fields.update(orders_obj.fix_locals(Receiver))
        #TODO: agregar un campo para diferencia cada delivery res partner al shipment y orden asociado, crear un binding usando values diferentes... y listo
        deliv_id = self.env["res.partner"].search([("parent_id","=",pdelivery_fields['parent_id']),
                                                    ("type","=","delivery"),
                                                    ('street','=',pdelivery_fields['street'])],
                                                    limit=1)
        if not deliv_id or len(deliv_id)==0:
            _logger.info("Create partner delivery")
            respartner_obj = self.env['res.partner']
            try:
                deliv_id = respartner_obj.create(pdelivery_fields)
                if deliv_id:
                    _logger.info("Created Res Partner Delivery "+str(deliv_id))
                    partner_shipping_id = deliv_id
            except Exception as e:
                _logger.error("Created res.partner delivery issue.")
                _logger.info(e, exc_info=True)
                pass;
        else:
            try:
                deliv_id.write(pdelivery_fields)
                partner_shipping_id = deliv_id
            except:
                _logger.error("Updating res.partner delivery issue.")
                pass;
        return partner_shipping_id

    #Return shipment object based on mercadolibre.orders "order"
    def fetch( self, order, meli=None, config=None ):

        company = self.env.user.company_id
        if not config:
            config = company
        sale_order_pack = None
        saleorder_obj = self.env['sale.order']
        saleorderline_obj = self.env['sale.order.line']
        product_obj = self.env['product.product']
        pricelist_obj = self.env['product.pricelist']
        respartner_obj = self.env['res.partner']

        orders_obj = self.env['mercadolibre.orders']
        shipment_obj = self.env['mercadolibre.shipment']
        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)
            if meli.need_login():
                return meli.redirect_login()

        ship_id = False
        shipment = None

        if (order and order.shipping_id):
            ship_id = order.shipping_id
        else:
            return None

        response = meli.get("/shipments/"+ str(ship_id),  {'access_token':meli.access_token})
        if (response):
            ship_json = response.json()
            #_logger.info( ship_json )

            if "error" in ship_json:
                _logger.error( ship_json["error"] )
                _logger.error( ship_json["message"] )
            else:
                _logger.info("Saving shipment fields")
                rescosts = meli.get("/shipments/"+ str(ship_id)+str('/costs'),  {'access_token':meli.access_token})
                if rescosts:
                    rcosts = rescosts.json()
                    ship_json['costs'] = rcosts
                    recdiscounts = 'receiver' in rcosts and 'discounts' in rcosts['receiver'] and rcosts['receiver']['discounts']
                    for discount in recdiscounts:
                        if 'promoted_amount' in discount:
                            ship_json['promoted_amount'] =  discount['promoted_amount'] or 0.0

                seller_id = None
                if config.mercadolibre_seller_user:
                    seller_id = config.mercadolibre_seller_user.id
                ship_fields = {
                    "name": "MSO ["+str(ship_id)+"] "+str("")+str(ship_json["status"])+"/"+str(ship_json["substatus"])+str(""),
                    'company_id': company.id,
                    'seller_id': seller_id,
                    "order": order.id,
                    "shipping_id": ship_json["id"],
                    "site_id": ship_json["site_id"],
                    "order_id": ship_json["order_id"],
                    "mode": ship_json["mode"],
                    "shipping_mode": ship_json["shipping_option"]["name"],
                    "date_created": ml_datetime(ship_json["date_created"]),
                    "last_updated": ml_datetime(ship_json["last_updated"]),
                    "order_cost": ship_json["order_cost"],
                    "shipping_cost": ("cost" in ship_json["shipping_option"] and ship_json["shipping_option"]["cost"]) or 0.0,
                    "shipping_list_cost": ("list_cost" in ship_json["shipping_option"] and ship_json["shipping_option"]["list_cost"]) or 0.0,
                    "base_cost": ship_json["base_cost"],
                    'promoted_amount': ('promoted_amount' in ship_json and ship_json['promoted_amount']) or 0.0,
                    "status": ship_json["status"],
                    "substatus": ship_json["substatus"],
                    #"status_history": ship_json["status_history"],
                    "tracking_number": ship_json["tracking_number"],
                    "tracking_method": ship_json["tracking_method"],
                    "comments": ship_json["comments"] or '',
                    "date_first_printed": ml_datetime(ship_json["date_first_printed"]),
                    "receiver_id": ship_json["receiver_id"],
                    "sender_id": ship_json["sender_id"],
                    "logistic_type": ("logistic_type" in ship_json and ship_json["logistic_type"]) or ""
                }
                if "receiver_address" in ship_json and ship_json["receiver_address"]:
                    ship_fields.update({
                        "receiver_address_id": ship_json["receiver_address"]["id"],
                        "receiver_address_name": ship_json["receiver_address"]["receiver_name"],
                        "receiver_address_line": ship_json["receiver_address"]["address_line"],
                        "receiver_address_comment": ship_json["receiver_address"]["comment"],
                        "receiver_street_name": ship_json["receiver_address"]["street_name"],
                        "receiver_street_number": ship_json["receiver_address"]["street_number"],
                        "receiver_city": ship_json["receiver_address"]["city"]["name"],
                        "receiver_city_code": ship_json["receiver_address"]["city"]["id"],
                        "receiver_state": ship_json["receiver_address"]["state"]["name"],
                        "receiver_state_code": ship_json["receiver_address"]["state"]["id"],
                        "receiver_country": ship_json["receiver_address"]["country"]["name"],
                        "receiver_country_code": ship_json["receiver_address"]["country"]["id"],
                        "receiver_latitude": ship_json["receiver_address"]["latitude"],
                        "receiver_longitude": ship_json["receiver_address"]["longitude"]
                    })
                    receiver_phone = ("receiver_phone" in ship_json["receiver_address"] and ship_json["receiver_address"]["receiver_phone"] and not "XXXX" in ship_json["receiver_address"]["receiver_phone"] and ship_json["receiver_address"]["receiver_phone"])
                    if receiver_phone:
                        ship_fields.update({"receiver_address_phone": receiver_phone })

                if "sender_address" in ship_json and ship_json["sender_address"]:
                    ship_fields.update({
                        "sender_address_id": ship_json["sender_address"]["id"],
                        "sender_address_line": ship_json["sender_address"]["address_line"],
                        "sender_address_comment": ship_json["sender_address"]["comment"],
                        "sender_street_name": ship_json["sender_address"]["street_name"],
                        "sender_street_number": ship_json["sender_address"]["street_number"],
                        "sender_city": ship_json["sender_address"]["city"]["name"],
                        "sender_state": ship_json["sender_address"]["state"]["name"],
                        "sender_country": ship_json["sender_address"]["country"]["name"],
                        "sender_latitude": ship_json["sender_address"]["latitude"],
                        "sender_longitude": ship_json["sender_address"]["longitude"],
                    });

                response2 = meli.get("/shipments/"+ str(ship_id)+"/items",  {'access_token':meli.access_token})
                items_json = []
                if (response2):
                    items_json = response2.json()
                    if "error" in items_json:
                        _logger.error( items_json["error"] )
                        _logger.error( items_json["message"] )
                    else:
                        if (len(items_json)>1 or ( len(items_json)==1 and order.pack_order==True ) ):
                            _logger.info("Es carrito")
                            ship_fields["pack_order"] = True
                        else:
                            ship_fields["pack_order"] = False

                        full_orders = False
                        all_orders = []
                        all_orders_ids = []
                        coma = ""
                        packed_order_ids =""
                        for item in items_json:
                            #check mercadolibre_orders for full pack
                            if "order_id" in item:
                                #search order, if not present search orders...
                                #search by meli_order_id in mercadolibre.orders
                                #_logger.info(item)
                                item_order = orders_obj.search( [("order_id",'=',item["order_id"])], limit=1 )
                                if len(item_order):
                                    all_orders.append(item_order)
                                    all_orders_ids.append(item_order.id)
                                    packed_order_ids+= coma + item["order_id"]
                                    coma = ","
                        full_orders = ( len(items_json) == len(all_orders) )
                        #_logger.info(items_json)
                        #_logger.info("full_orders:"+str(full_orders))
                        if (full_orders):
                            #We can create order with all items now
                            ship_fields["orders"] = [(6, 0, all_orders_ids)]

                shipment = shipment_obj.search([('shipping_id','=', ship_id)])
                #_logger.info(ships)
                if (len(shipment)==0):
                    _logger.info("Importing shipment: " + str(ship_id))
                    #_logger.info(str(ship_fields))
                    shipment = shipment_obj.create((ship_fields))
                    if (shipment):
                        _logger.info("Created shipment ok!")
                else:
                    _logger.info("Updating shipment: " + str(ship_id))
                    shipment.write((ship_fields))

                if shipment and items_json:
                    #mercadolibre.shipment.item
                    for item in items_json:
                        shipment.update_item(item)

                try:
                    _logger.info("ships.pdf_filename:")
                    _logger.info(shipment.pdf_filename)
                    if (1==1 and shipment.pdf_filename):
                        _logger.info("We have a pdf file")
                        if (shipment.pdfimage_filename==False):
                            _logger.info("Try create a pdf image file")
                            data = base64.b64decode( shipment.pdf_file )
                            images = convert_from_bytes(data, dpi=300,fmt='jpg')
                            for image in images:
                                image_filename = "/tmp/%s-page%d.jpg" % ("Shipment_"+shipment.shipping_id, images.index(image))
                                image.save(image_filename, "JPEG")
                                if (images.index(image)==0):
                                    imgdata = urlopen("file://"+image_filename).read()
                                    shipment.pdfimage_file = base64.encodestring(imgdata)
                                    shipment.pdfimage_filename = "Shipment_"+shipment.shipping_id+".jpg"
                            #if (len(images)):
                            #    _logger.info(images)
                                #for image in images:
                                #base64.b64decode( pimage.image )
                            #    image = images[1]
                            #    ships.pdfimage_file = base64.encodestring(image.tobytes())
                            #    ships.pdfimage_filename = "Shipment_"+ships.shipping_id+".jpg"
                except Exception as e:
                    _logger.info("Error converting pdf to jpg: try installing pdf2image and poppler-utils, like this:")
                    _logger.info("sudo apt install poppler-utils && sudo pip install pdf2image")
                    _logger.info(e, exc_info=True)
                    pass;

                #associate order if it was non pack order created bir orders.py
                if (ship_fields["pack_order"]==False):
                    sorder = self.env["sale.order"].search( [ ('meli_order_id','=',ship_fields["order_id"]) ] )
                    if len(sorder):
                        shipment.sale_order = sorder[0]
                        sorder.meli_shipment = shipment

                #if its a pack order, create it, oif full_orders were fetched (we can force this now)
                if (full_orders and ship_fields["pack_order"]):
                    plistid = None
                    if config.mercadolibre_pricelist:
                        plistid = config.mercadolibre_pricelist
                    else:
                        plistids = pricelist_obj.search([])[0]
                        if plistids:
                            plistid = plistids

                    #buyer_ids = buyers_obj.search([  ('buyer_id','=',buyer_fields['buyer_id'] ) ] )
                    partner_id = respartner_obj.search([  ('meli_buyer_id','=',ship_fields['receiver_id'] ) ] )
                    if (partner_id.id):

                        sorder_pack = self.env["sale.order"].search( [ ('meli_order_id','=',packed_order_ids) ] )

                        order_json = {
                            "id": all_orders[0]["order_id"],
                            'status': all_orders[0]["status"],
                            'status_detail': all_orders[0]["status_detail"] or '' ,
                            'total_amount': shipment.order_cost,
                            'paid_amount': shipment.order_cost,
                            'currency_id': all_orders[0]["currency_id"],
                            "date_created": all_orders[0]["date_created"],
                            "date_closed": all_orders[0]["date_closed"],
                        }

                        meli_order_fields = self.env['mercadolibre.orders'].prepare_sale_order_vals( order_json=order_json, meli=meli, config=config, sale_order=sorder_pack, shipment=shipment )
                        #meli_order_fields.update({
                        #    'partner_id': partner_id.id,
                        #    'pricelist_id': plistid.id,
                        #})
                        meli_order_fields.update({
                            #TODO: "add parameter for pack_id":
                            #'name': "ML %i" % ( all_orders[0]["pack_id"] ),
                            #'name': "ML %s" % ( str(all_orders[0]["order_id"]) ),
                            'partner_id': partner_id.id,
                            'pricelist_id': plistid.id,
                            #'meli_order_id': '%i' % (order_json["id"]),
                            'meli_order_id': packed_order_ids,
                            'meli_orders': [(6, 0, all_orders_ids)],
                            'meli_shipping_id': shipment.shipping_id,
                            'meli_shipping': shipment,
                            'meli_shipment': shipment.id,
                            #'meli_status': all_orders[0]["status"],
                            #'meli_status_detail': all_orders[0]["status_detail"] or '' ,
                            #'meli_total_amount': shipment.order_cost,
                            'meli_shipping_cost': shipment.shipping_cost,
                            'meli_shipping_list_cost': shipment.shipping_list_cost,
                            #'meli_paid_amount': shipment.order_cost,
                            'meli_fee_amount': 0.0,
                            #'meli_currency_id': all_orders[0]["currency_id"],
                            'meli_date_created': ml_datetime(all_orders[0]["date_created"]) or all_orders[0]["date_created"],
                            'meli_date_closed': ml_datetime(all_orders[0]["date_closed"]) or all_orders[0]["date_created"],
                        })
                        #TODO: agregar un campo para diferencia cada delivery res partner al shipment y orden asociado, crear un binding usando values diferentes... y listo
                        _logger.info("ship_json[receiver_address]:"+str(ship_json["receiver_address"]) )
                        partner_shipping_id = self.partner_delivery_id( partner_id=partner_id, Receiver=ship_json["receiver_address"])

                        if partner_shipping_id:
                            meli_order_fields['partner_shipping_id'] = partner_shipping_id.id

                        if ("pack_id" in all_orders[0] and all_orders[0]["pack_id"]):
                            meli_order_fields['name'] = "ML %s" % ( str(all_orders[0]["pack_id"]) )
                            #meli_order_fields['pack_id'] = all_orders[0]["pack_id"]

                        if (config.mercadolibre_seller_user):
                            meli_order_fields["user_id"] = config.mercadolibre_seller_user.id
                        if (config.mercadolibre_seller_team):
                            meli_order_fields["team_id"] = config.mercadolibre_seller_team.id

                        if (len(sorder_pack)):
                            sorder_pack = sorder_pack[0]
                            _logger.info("Update sale.order pack")
                            #_logger.info(all_orders[0])
                            #_logger.info(meli_order_fields)
                            sorder_pack.write(meli_order_fields)
                        else:
                            sorder_pack = self.env["sale.order"].create(meli_order_fields)

                        if (sorder_pack.id):
                            shipment.sale_order = sorder_pack

                            order.sale_order = sorder_pack
                            order.shipping_cost = shipment.shipping_cost
                            order.shipping_list_cost = shipment.shipping_list_cost

                            #creating and updating all items related to ml.orders
                            sorder_pack.meli_fee_amount = 0.0
                            for mOrder in all_orders:
                                #Each Order one product with one price and one quantity
                                product_related_obj = mOrder.order_items[0].product_id or mOrder.order_items[0].posting_id.product_id
                                if not (product_related_obj):
                                    _logger.error("Error adding order line: product not found in database: " + str(mOrder.order_items[0]["order_item_title"]) )
                                    continue;
                                unit_price = mOrder.order_items[0]["unit_price"]
                                saleorderline_item_fields = {
                                    'company_id': company.id,
                                    'order_id': shipment.sale_order.id,
                                    'meli_order_item_id': mOrder.order_items[0]["order_item_id"],
                                    'meli_order_item_variation_id': mOrder.order_items[0]["order_item_variation_id"],
                                    'price_unit': float(unit_price),
                                    'product_id': product_related_obj.id,
                                    'product_uom_qty': mOrder.order_items[0]["quantity"],
                                    'product_uom': product_related_obj.uom_id.id,
                                    'name': product_related_obj.display_name or mOrder.order_items[0]["order_item_title"],
                                }
                                if (mOrder.fee_amount):
                                    sorder_pack.meli_fee_amount = sorder_pack.meli_fee_amount + mOrder.fee_amount

                                saleorderline_item_fields.update( order._set_product_unit_price( product_related_obj, mOrder.order_items[0] ) )

                                saleorderline_item_ids = saleorderline_obj.search( [('meli_order_item_id','=',saleorderline_item_fields['meli_order_item_id']),
                                                                                    ('meli_order_item_variation_id','=',saleorderline_item_fields['meli_order_item_variation_id']),
                                                                                    ('order_id','=',shipment.sale_order.id)] )

                                if not saleorderline_item_ids:
                                    saleorderline_item_ids = saleorderline_obj.create( ( saleorderline_item_fields ))
                                else:
                                    saleorderline_item_ids.write( ( saleorderline_item_fields ) )


        if (shipment):
            shipment._update_sale_order_shipping_info( order, meli=meli, config=config )

        return shipment

    def update_item( self, item=None ):
        shipment = self
        sitem = None
        if "variation_id" in item and item["variation_id"]:
            sitem = self.env["mercadolibre.shipment.item"].search([ ("shipment_id","=",shipment.id),("order_id","=",item["order_id"]), ("item_id","=",item["item_id"]), ("variation_id","=",item["variation_id"]) ],limit=1)
        else:
            sitem = self.env["mercadolibre.shipment.item"].search([ ("shipment_id","=",shipment.id),("order_id","=",item["order_id"]), ("item_id","=",item["item_id"])],limit=1)

        ifields = {
            "name": str(item["description"])+"-"+str(item["item_id"])+"-"+str(item["variation_id"])+"-"+str(item["order_id"]),
            "item_id": str(item["item_id"]),
            "variation_id": str(item["variation_id"]),
            "order_id": str(item["order_id"]),
            "shipment_id": shipment.id,
            "data": str(item)
        }

        if sitem:
            sitem.write(ifields)
        else:
            sitem = self.env["mercadolibre.shipment.item"].create(ifields)
        return sitem

    def update( self, context=None, meli=None, config=None ):

        _logger.info( "update: context: "+str(context)+ " meli: "+str(meli)+ " config: " +str(config) )

        self.fetch( self.order, meli=meli, config=config )

        return {}

    def shipment_query( self, meli=None, config=None ):

        company = self.env.user.company_id
        if not config:
            config = company
        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)
            if meli.need_login():
                return meli.redirect_login()

        orders_obj = self.env['mercadolibre.orders']
        shipment_obj = self.env['mercadolibre.shipment']


        #orders_query = "/orders/search?seller="+config.mercadolibre_seller_id+"&sort=date_desc"

        # https://api.mercadolibre.com/shipment_labels?shipment_ids=20178600648,20182100995&response_type=pdf&access_token=
        # https://api.mercadolibre.com/shipments/27693158904?access_token=APP_USR-3069131366650174-120509-8746c1a831468e99f84105cd631ff206-246057399


        return {}

    def shipment_print( self, meli=None, config=None, include_ready_to_print=None ):
        shipment= self
        shipment.update()

        ship_report = { 'message': '', 'access_token': meli.access_token }

        if (shipment and shipment.status=="ready_to_ship"):

            #full_str_ids = full_str_ids + comma + shipment
            download_url = "https://api.mercadolibre.com/shipment_labels?shipment_ids="+shipment.shipping_id+"&response_type=pdf&access_token="+meli.access_token
            shipment.pdf_link = download_url

            if (shipment.substatus=="printed" or include_ready_to_print):
                try:
                    data = urlopen(shipment.pdf_link).read()
                    _logger.info(data)
                    shipment.pdf_filename = "Shipment_"+shipment.shipping_id+".pdf"
                    shipment.pdf_file = base64.encodestring(data)
                    images = convert_from_bytes(data, dpi=300,fmt='jpg')
                    if (1==1 and len(images)>1):
                        for image in images:
                            image_filename = "/tmp/%s-page%d.jpg" % ("Shipment_"+shipment.shipping_id, images.index(image))
                            image.save(image_filename, "JPEG")
                            if (images.index(image)==0):
                                imgdata = urlopen("file://"+image_filename).read()
                                shipment.pdfimage_file = base64.encodestring(imgdata)
                                shipment.pdfimage_filename = "Shipment_"+shipment.shipping_id+".jpg"

                except Exception as e:
                    _logger.info("Exception!")
                    _logger.info(e, exc_info=True)
                    #return warningobj.info( title='Impresión de etiquetas: Error descargando guias', message=download_url )
                    ship_report['message'] = "Error descargando pdf:" + str(shipment.shipping_id) + " - Status: " + str(shipment.status) + " - SubStatus: " + str(shipment.substatus)+'<a href="'+download_url+'" target="_blank"><strong><u>Descargar PDF</u></strong></a>'
                    #sep = "<br>"+"\n"

        else:
            ship_report['message'] = str(shipment.shipping_id) + " - Status: " + str(shipment.status) + " - SubStatus: " + str(shipment.substatus)
            #sep = "<br>"+"\n"

        return ship_report

mercadolibre_shipment()


class AccountInvoice(models.Model):
    _inherit = acc_inv_model

    @api.model
    def _get_shipment(self):
        ret = {}
        ret["shipping_id"] = ''
        ret["pdfimage_filename"] = ''
        ret["pdfimage_file"] = ''
        ret["receiver_address_name"] = ''
        ret["receiver_address_line"] = ''
        ret["receiver_address_phone"] = ''
        ret["receiver_city"] = ''
        ret["receiver_state"] = ''
        ret["tracking_method"] = ''
        if (self.origin):
            order = self.env["sale.order"].search([('name','=',self.origin)])
            if (order.id):
                _logger.info("Order found in _get_shipment:"+str(order.name))
                #if (order.meli_order_id)
                if (order.meli_shipment):
                    shipment = order.meli_shipment
                    ret["shipping_id"] = order.meli_shipment.shipping_id
                    ret["pdfimage_filename"] = shipment.pdfimage_filename
                    ret["pdfimage_file"] = shipment.pdfimage_file
                    ret["receiver_address_name"] = shipment.receiver_address_name
                    ret["receiver_address_line"] = shipment.receiver_address_line
                    ret["receiver_address_phone"] = (shipment.receiver_address_phone and not "XXXX" in shipment.receiver_address_phone and shipment.receiver_address_phone)
                    ret["receiver_city"] = shipment.receiver_city
                    ret["receiver_state"] = shipment.receiver_state
                    ret["tracking_method"] = shipment.tracking_method

                    ret["items"] = []
                    for order_item in shipment.order.order_items:
                        ret["items"].append({'quantity':order_item.quantity, 'name': order_item.posting_id.product_id.name})

                else:
                    _logger.info("No meli_shipping_id found for:"+str(order.meli_shipping_id))
            else:
                _logger.info("No order found for:"+str(self.origin))
        return ret

    @api.model
    def _get_meli_shipment(self):
        ret = False
        if (self.origin):
            order = self.env["sale.order"].search([('name','=',self.origin)])
            if (order.id):
                _logger.info("Order found in _get_shipment:"+str(order.name))
                #if (order.meli_order_id)
                if (order.meli_shipment):
                    return order.meli_shipment

        return ret

AccountInvoice()
