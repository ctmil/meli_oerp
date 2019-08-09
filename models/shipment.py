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
#
#     https://www.odoo.com/fr_FR/forum/aide-1/question/solved-call-report-and-save-result-to-attachment-133244
#


#
# https://api.mercadolibre.com/shipment_labels?shipment_ids=20178600648,20182100995&response_type=pdf&access_token=
class mercadolibre_shipment_print(models.TransientModel):
	_name = "mercadolibre.shipment.print"
	_description = "Impresión de etiquetas"

	def shipment_print(self, context):
		#pdb.set_trace()
		company = self.env.user.company_id
		shipment_ids = context['active_ids']
		#product_obj = self.env['product.template']
		shipment_obj = self.env['mercadolibre.shipment']
		warningobj = self.env['warning']

		CLIENT_ID = company.mercadolibre_client_id
		CLIENT_SECRET = company.mercadolibre_secret_key
		ACCESS_TOKEN = company.mercadolibre_access_token
		REFRESH_TOKEN = company.mercadolibre_refresh_token

		#
		meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN )

		#user_obj = self.pool.get('res.users').browse(cr, uid, uid)
		#user_obj.company_id.meli_login()
		#company = user_obj.company_id
		#warningobj = self.env['warning']
		_logger.info("shipment_print")
		_logger.info(shipment_ids)


		#https://api.mercadolibre.com/shipment_labels?shipment_ids=20178600648,20182100995&response_type=pdf&
		full_ids = ""
		comma = ""
		reporte = ""
		sep = ""
		for shipid in shipment_ids:
			shipment = shipment_obj.browse(shipid)
			shipment.update()
			if (shipment and shipment.status=="ready_to_ship"):
				full_ids = full_ids + comma + shipment.shipping_id
				#full_str_ids = full_str_ids + comma + shipment
				comma = ","
				download_url = "https://api.mercadolibre.com/shipment_labels?shipment_ids="+shipment.shipping_id+"&response_type=pdf&access_token="+meli.access_token
				shipment.pdf_link = download_url

				if (shipment.substatus=="printed"):
					try:
						data = urlopen(shipment.pdf_link).read()
						_logger.info(data)
						shipment.pdf_filename = "Shipment_"+shipment.shipping_id+".pdf"
						shipment.pdf_file = base64.encodestring(data)
						images = convert_from_bytes(data, dpi=300,fmt='jpg')
						if (1==1 and len(images)>1):
							for image in images:
								image.save("/tmp/%s-page%d.jpg" % ("Shipment_"+shipment.shipping_id,images.index(image)), "JPEG")
								if (images.index(image)==1):
									imgdata = urlopen("file:///tmp/Shipment_"+shipment.shipping_id+"-page1.jpg").read()
									shipment.pdfimage_file = base64.encodestring(imgdata)
									shipment.pdfimage_filename = "Shipment_"+shipment.shipping_id+".jpg"
					except Exception as e:
						_logger.info("Exception!")
						_logger.info(e, exc_info=True)
						#return warningobj.info( title='Impresión de etiquetas: Error descargando guias', message=download_url )
						reporte = reporte + sep + "Error descargando pdf:" + str(shipment.shipping_id) + " - Status: " + str(shipment.status) + " - SubStatus: " + str(shipment.substatus)+'<a href="'+download_url+'" target="_blank"><strong><u>Descargar PDF</u></strong></a>'
						sep = "<br>"+"\n"

			else:
				reporte = reporte + sep + str(shipment.shipping_id) + " - Status: " + str(shipment.status) + " - SubStatus: " + str(shipment.substatus)
				sep = "<br>"+"\n"

		_logger.info(full_ids)
		full_url_link_pdf = "https://api.mercadolibre.com/shipment_labels?shipment_ids="+full_ids+"&response_type=pdf&access_token="+meli.access_token
		_logger.info(full_url_link_pdf)
		if (full_ids):
			return warningobj.info( title='Impresión de etiquetas', message="Abrir este link para descargar el PDF", message_html=""+full_ids+'<br><br><a href="'+full_url_link_pdf+'" target="_blank"><strong><u>Descargar PDF</u></strong></a>'+"<br><br>Reporte de no impresas:<br>"+reporte )
		else:
			return warningobj.info( title='Impresión de etiquetas: Estas etiquetas ya fueron todas impresas.', message=reporte )


mercadolibre_shipment_print()


class mercadolibre_shipment_update(models.TransientModel):
	_name = "mercadolibre.shipment.update"
	_description = "Actualizar datos de envio"

	def shipment_update(self, context):
		#pdb.set_trace()
		company = self.env.user.company_id
		shipment_ids = context['active_ids']
		#product_obj = self.env['product.template']
		shipment_obj = self.env['mercadolibre.shipment']
		warningobj = self.env['warning']

		_logger.info("shipment_update")
		_logger.info(shipment_ids)

		for shipid in shipment_ids:
			shipment = shipment_obj.browse(shipid)
			if (shipment):
				shipment.update()


mercadolibre_shipment_update()

class mercadolibre_shipment(models.Model):
	_name = "mercadolibre.shipment"
	_description = "Envio de MercadoLibre"

	site_id = fields.Char('Site id')
	posting_id = fields.Many2one("mercadolibre.posting",string="Posting")
	shipping_id = fields.Char('Envio Id')
	order_id =  fields.Char('Order Id')
	order = fields.Many2one("mercadolibre.orders",string="Order")
	orders = fields.Many2many("mercadolibre.orders",string="Orders (carrito)")

	mode = fields.Char('Mode')
	shipping_mode = fields.Char('Shipping mode')

	date_created = fields.Datetime('Creation date')
	last_updated = fields.Datetime('Last updated')

	order_cost = fields.Char('Order Cost')
	base_cost = fields.Char('Base Cost')

	status = fields.Char("Status")
	substatus = fields.Char("Sub Status")
	status_history = fields.Text("status_history")
	tracking_number = fields.Char("Tracking number")
	tracking_method = fields.Char("Tracking method")


	date_first_printed = fields.Datetime('First Printed date')

	receiver_id = fields.Char('Receiver Id')
	receiver_address_id = fields.Char('Receiver address id')
	receiver_address_phone = fields.Char('Phone')
	receiver_address_name = fields.Char('Nombre')
	receiver_address_comment = fields.Char('Comment')

	receiver_address_line = fields.Char('Receiver Address Line')
	receiver_street_name = fields.Char('Calle')
	receiver_street_number = fields.Char('Nro')
	receiver_city = fields.Char('Ciudad')
	receiver_state = fields.Char('Estado')
	receiver_country = fields.Char('Pais')
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

	logistic_type = fields.Char('Logistic type')

	pdf_link = fields.Char('Pdf link')
	pdf_file = fields.Binary(string='Pdf File',attachment=True)
	pdf_filename = fields.Char(string='Pdf Filename')
	pdfimage_file = fields.Binary(string='Pdf Image File',attachment=True)
	pdfimage_filename = fields.Char(string='Pdf Image Filename')

	pack_order = fields.Boolean(string="Carrito de compra")

	def create_shipment( self ):
		return {}

	def fetch( self, order ):

		company = self.env.user.company_id

		saleorder_obj = self.env['sale.order']
		saleorderline_obj = self.env['sale.order.line']
		product_obj = self.env['product.product']
		pricelist_obj = self.env['product.pricelist']
		respartner_obj = self.env['res.partner']

		orders_obj = self.env['mercadolibre.orders']
		shipment_obj = self.env['mercadolibre.shipment']

		CLIENT_ID = company.mercadolibre_client_id
		CLIENT_SECRET = company.mercadolibre_secret_key
		ACCESS_TOKEN = company.mercadolibre_access_token
		REFRESH_TOKEN = company.mercadolibre_refresh_token

		#
		meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN )

		ship_id = False
		if (order and order.shipping_id):
			ship_id = order.shipping_id
		else:
			return {}

		response = meli.get("/shipments/"+ str(ship_id),  {'access_token':meli.access_token})
		if (response):
			ship_json = response.json()
			_logger.info( ship_json )

			if "error" in ship_json:
				_logger.error( ship_json["error"] )
				_logger.error( ship_json["message"] )
			else:
				_logger.info("Saving shipment fields")
				ship_fields = {
					"order": order.id,
					"shipping_id": ship_json["id"],
					"site_id": ship_json["site_id"],
					"order_id": ship_json["order_id"],
					"order": order.id,
					"mode": ship_json["mode"],
					"shipping_mode": ship_json["shipping_option"]["name"],
					"date_created": ship_json["date_created"],
					"last_updated": ship_json["last_updated"],
					"order_cost": ship_json["order_cost"],
					"base_cost": ship_json["base_cost"],
					"status": ship_json["status"],
					"substatus": ship_json["substatus"],
					#"status_history": ship_json["status_history"],
					"tracking_number": ship_json["tracking_number"],
					"tracking_method": ship_json["tracking_method"],
					"date_first_printed": ship_json["date_first_printed"],
					"receiver_id": ship_json["receiver_id"],
					"receiver_address_id": ship_json["receiver_address"]["id"],
					"receiver_address_phone": ship_json["receiver_address"]["receiver_phone"],
					"receiver_address_name": ship_json["receiver_address"]["receiver_name"],
					"receiver_address_line": ship_json["receiver_address"]["address_line"],
					"receiver_address_comment": ship_json["receiver_address"]["comment"],
					"receiver_street_name": ship_json["receiver_address"]["street_name"],
					"receiver_street_number": ship_json["receiver_address"]["street_number"],
					"receiver_city": ship_json["receiver_address"]["city"]["name"],
					"receiver_state": ship_json["receiver_address"]["state"]["name"],
					"receiver_country": ship_json["receiver_address"]["country"]["name"],
					"receiver_latitude": ship_json["receiver_address"]["latitude"],
					"receiver_longitude": ship_json["receiver_address"]["longitude"],

					"sender_id": ship_json["sender_id"],
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


					"logistic_type": ship_json["logistic_type"]
				}

				response2 = meli.get("/shipments/"+ str(ship_id)+"/items",  {'access_token':meli.access_token})
				if (response2):
					items_json = response2.json()
					if "error" in items_json:
						_logger.error( items_json["error"] )
						_logger.error( items_json["message"] )
					else:
						if (len(items_json)>1):
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
							if item["order_id"]:
								#search order, if not present search orders...
								#search by meli_order_id in mercadolibre.orders
								_logger.info(item)
								item_order = orders_obj.search( [("order_id",'=',item["order_id"])] )
								if (len(item_order)==1):
									all_orders.append(item_order)
									all_orders_ids.append(item_order.id)
									packed_order_ids+= coma+item["order_id"]
									coma = ","
						full_orders = ( len(items_json) == len(all_orders) )
						_logger.info(items_json)
						_logger.info(full_orders)
						if (full_orders):
							#We can create order with all items now
							ship_fields["orders"] = [(6, 0, all_orders_ids)]



				ships = shipment_obj.search([('shipping_id','=', ship_id)])
				_logger.info(ships)
				if (len(ships)==0):
					_logger.info("Importing shipment: " + str(ship_id))
					ship = shipment_obj.create((ship_fields))
					if (ship):
						_logger.info("Created shipment ok!")
				else:
					_logger.info("Updating shipment: " + str(ship_id))
					ships.write((ship_fields))

					try:
						_logger.info("ships.pdf_filename:")
						_logger.info(ships.pdf_filename)
						if (1==1 and ships.pdf_filename):
							_logger.info("We have a pdf file")
							if (ships.pdfimage_filename==False):
								_logger.info("Try create a pdf image file")
								data = base64.b64decode( ships.pdf_file )
								images = convert_from_bytes(data, dpi=300,fmt='jpg')
								for image in images:
									image.save("/tmp/%s-page%d.jpg" % ("Shipment_"+ships.shipping_id,images.index(image)), "JPEG")
									if (images.index(image)==1):
										imgdata = urlopen("file:///tmp/Shipment_"+ships.shipping_id+"-page1.jpg").read()
										ships.pdfimage_file = base64.encodestring(imgdata)
										ships.pdfimage_filename = "Shipment_"+ships.shipping_id+".jpg"
								#if (len(images)):
								#	_logger.info(images)
									#for image in images:
									#base64.b64decode( pimage.image )
								#	image = images[1]
								#	ships.pdfimage_file = base64.encodestring(image.tobytes())
								#	ships.pdfimage_filename = "Shipment_"+ships.shipping_id+".jpg"
					except Exception as e:
						_logger.info("Error converting pdf to jpg: try installing pdf2image and poppler-utils, like this:")
						_logger.info("sudo apt install poppler-utils && sudo pip install pdf2image")
						_logger.info(e, exc_info=True)
						pass;

					if (full_orders and ship_fields["pack_order"]):
						plistid = None
						if company.mercadolibre_pricelist:
							plistid = company.mercadolibre_pricelist
						else:
							plistids = pricelist_obj.search([])[0]
							if plistids:
								plistid = plistids

						#buyer_ids = buyers_obj.search([  ('buyer_id','=',buyer_fields['buyer_id'] ) ] )
						partner_id = respartner_obj.search([  ('meli_buyer_id','=',ship_fields['receiver_id'] ) ] )
						if (partner_id.id):
							meli_order_fields = {
								'partner_id': partner_id.id,
								'pricelist_id': plistid.id,
								#'meli_order_id': '%i' % (order_json["id"]),
								'meli_order_id': packed_order_ids,
								'meli_shipping_id': ships.id,
								'meli_shipping': ships,
								'meli_status': all_orders[0]["status"],
								'meli_status_detail': all_orders[0]["status_detail"] or '' ,
								'meli_total_amount': ship_fields["order_cost"],
								'meli_currency_id': all_orders[0]["currency_id"],
								'meli_date_created': all_orders[0]["date_created"] or '',
								'meli_date_closed': all_orders[0]["date_closed"] or '',
							}
							sorder = self.env["sale.order"].search( [ ('meli_order_id','=',meli_order_fields["meli_order_id"]) ] )
							if (len(sorder)):
								sorder = sorder[0]
								sorder.write(meli_order_fields)
							else:
								sorder = self.env["sale.order"].create(meli_order_fields)

							if (sorder.id):
								for mOrder in all_orders:
									#Each Order one product with one price and one quantity

									product_related_obj = mOrder.order_items[0].posting_id.product_id
									unit_price = mOrder.order_items[0]["unit_price"]
									saleorderline_item_fields = {
										'company_id': company.id,
										'order_id': sorder.id,
										'meli_order_item_id': mOrder.order_items[0]["order_item_id"],
										'price_unit': float(unit_price),
										'product_id': product_related_obj.id,
										'product_uom_qty': mOrder.order_items[0]["quantity"],
										'product_uom': 1,
										'name': mOrder.order_items[0]["order_item_title"],
									}
									if (float(unit_price)==product_related_obj.product_tmpl_id.lst_price):
										saleorderline_item_fields['price_unit'] = float(unit_price)
										saleorderline_item_fields['tax_id'] = None
									else:
										saleorderline_item_fields['price_unit'] = product_related_obj.product_tmpl_id.lst_price

									saleorderline_item_ids = saleorderline_obj.search( [('meli_order_item_id','=',saleorderline_item_fields['meli_order_item_id']),('order_id','=',sorder.id)] )

									if not saleorderline_item_ids:
										saleorderline_item_ids = saleorderline_obj.create( ( saleorderline_item_fields ))
									else:
										saleorderline_item_ids.write( ( saleorderline_item_fields ) )

	def update( self ):

		self.fetch( self.order )

		return {}

	def shipment_query( self ):

		company = self.env.user.company_id

		orders_obj = self.env['mercadolibre.orders']
		shipment_obj = self.env['mercadolibre.shipment']

		CLIENT_ID = company.mercadolibre_client_id
		CLIENT_SECRET = company.mercadolibre_secret_key
		ACCESS_TOKEN = company.mercadolibre_access_token
		REFRESH_TOKEN = company.mercadolibre_refresh_token

		#
		meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN )

		#orders_query = "/orders/search?seller="+company.mercadolibre_seller_id+"&sort=date_desc"

		# https://api.mercadolibre.com/shipment_labels?shipment_ids=20178600648,20182100995&response_type=pdf&access_token=
		# https://api.mercadolibre.com/shipments/27693158904?access_token=APP_USR-3069131366650174-120509-8746c1a831468e99f84105cd631ff206-246057399


		return {}

mercadolibre_shipment()


class AccountInvoice(models.Model):
	_inherit = "account.invoice"

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
				_logger.info("Order found:"+str(order.name))
				#if (order.meli_order_id)
				if (order.meli_shipping_id):
					shipment = self.env["mercadolibre.shipment"].search([('shipping_id','=',order.meli_shipping_id)])
					ret["shipping_id"] = order.meli_shipping_id
					ret["pdfimage_filename"] = shipment.pdfimage_filename
					ret["pdfimage_file"] = shipment.pdfimage_file
					ret["receiver_address_name"] = shipment.receiver_address_name
					ret["receiver_address_line"] = shipment.receiver_address_line
					ret["receiver_address_phone"] = shipment.receiver_address_phone
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

AccountInvoice()
