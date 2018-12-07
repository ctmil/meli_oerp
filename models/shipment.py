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
#
# https://api.mercadolibre.com/shipment_labels?shipment_ids=20178600648,20182100995&response_type=pdf&access_token=

class mercadolibre_shipment(models.Model):
	_name = "mercadolibre.shipment"
	_description = "Envío de MercadoLibre"

	site_id = fields.Char('Site id')
	posting_id = fields.Many2one("mercadolibre.posting","Posting")
	shipping_id = fields.Char('Envío Id')
	order_id =  fields.Char('Order Id')
	order = fields.Many2one("mercadolibre.orders","Order");

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
	receiver_address_phone = fields.Char('Teléfono')
	receiver_address_name = fields.Char('Nombre')
	receiver_address_comment = fields.Char('Comment')
	receiver_street_name = fields.Char('Calle')
	receiver_street_number = fields.Char('Nro')
	receiver_city = fields.Char('Ciudad')
	receiver_state = fields.Char('Estado')
	receiver_pais = fields.Char('Pais')
	receiver_latitude = fields.Char('Latitud')
	receiver_longitude = fields.Char('Longitud')

	sender_id = fields.Char('Sender Id')

	logistic_type = fields.Char('Logistic type')

	def create_shipment( self ):
		return {}

	def fetch( self, order ):

		company = self.env.user.company_id

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

		ships = shipment_obj.search([('shipping_id','=', ship_id)])
		_logger.info(ships)
		if (len(ships)==0):
			_logger.info("Importing shipment: " + str(ship_id))
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
						"shipping_id": ship_json["id"],
						"site_id": ship_json["site_id"],
						"order_id": ship_json["order_id"],
						"order": order,
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
						"receiver_address_comment": ship_json["receiver_address"]["comment"],
						"receiver_street_name": ship_json["receiver_address"]["street_name"],
						"receiver_street_number": ship_json["receiver_address"]["street_number"],
						"receiver_city": ship_json["receiver_address"]["city"]["name"],
						"receiver_state": ship_json["receiver_address"]["state"]["name"],
						"receiver_pais": ship_json["receiver_pais"],
						"receiver_latitude": ship_json["receiver_latitude"],
						"receiver_longitude": ship_json["receiver_longitude"],
						"sender_id": ship_json["sender_id"],
						"logistic_type": ship_json["logistic_type"]
					}
					ship = shipment_obj.create((ship_fields))
					if (ship):
						_logger.info("Created shipment ok!")
		else:
			_logger.info("Updating shipment: " + str(ship_id))

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
