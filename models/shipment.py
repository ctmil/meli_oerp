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
	shipment_id = fields.Char('Envío Id')
	order_id =  fields.Char('Order Id')
	order = field.Many2one("mercadolibre.orders","Order");

	mode = fields.Char('Mode')
	shipping_mode = fields.Char('Shipping mode')

	date_created = fields.Datetime('Creation date')
	last_updated = fields.Datetime('Last updated')

	order_cost = fields.Char('Order Cost')
	base_cost = fields.Char('Base Cost')

	status = fields.Char("Status")
	status_history = fields.Text("status_history")
	tracking_number = fields.Char("Tracking number")
	tracking_method = fields.Char("Tracking method")


	date_first_printed = fields.Datetime('First Printed date')

	receiver_id = fields.Char('Receiver Id')
	receiver_address_id = fields.Char('Receiver address id')
	receiver_address_phone = fields.Char('Teléfono')
	receiver_address_name = fields.Char('Nombre')
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
