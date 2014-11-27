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

from bottle import Bottle, run, template, route, request
import json

import melisdk
from melisdk.meli import Meli

class product_post(osv.osv_memory):
	_name = "mercadolibre.product.post"
	_description = "Wizard de Product Posting en MercadoLibre"
    
	_columns = {
		'posting_date': fields.date('Fecha del posting'), 
	}

	def product_post(self, cr, uid, ids, context=None):
		product_ids = context['active_ids']
		product_obj = self.pool.get('product.product')
		company = self.pool.get('res.company').browse(cr,uid,1)
		mercadolibre_client_id = company.mercadolibre_client_id
		mercadolibre_secret_key = company.mercadolibre_secret_key
		print mercadolibre_client_id
		print mercadolibre_secret_key

		meli = Meli(client_id=mercadolibre_client_id,client_secret=mercadolibre_secret_key, access_token=ACCESS_TOKEN,refresh_token=REFRESH_TOKEN)
		
		for product_id in product_ids:
			product = product_obj.browse(cr,uid,product_id)
			print product.name
			# invocar posting
			body = {"condition":"new", "warranty":"60 dias", "currency_id":"BRL", "accepts_mercadopago":True, "description":"Lindo Ray_Ban_Original_Wayfarer", "listing_type_id":"bronze", "title":"oculos Ray Ban Aviador  Que Troca As Lentes  Lancamento!", "available_quantity":64, "price":289, "subtitle":"Acompanha 3 Pares De Lentes!! Compra 100% Segura", "buying_mode":"buy_it_now", "category_id":"MLB5125", "pictures":[{"source":"http://upload.wikimedia.org/wikipedia/commons/f/fd/Ray_Ban_Original_Wayfarer.jpg"}, {"source":"http://en.wikipedia.org/wiki/File:Teashades.gif"}] }
			response = meli.post("/items", body, {'access_token':meli.access_token})
			print response.content
		import pdb;pdb.set_trace()

		return {}
	
product_post()
