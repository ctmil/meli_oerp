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
import requests
import melisdk

from meli_oerp_config import *

from melisdk.meli import Meli

class product_product(osv.osv):
    
    _inherit = "product.template"

    def product_meli_login(self, cr, uid, ids, context=None ):

        user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        company = user_obj.company_id

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET)

        url_login_meli = meli.auth_url(redirect_URI=REDIRECT_URI)
        #url_login_oerp = "/meli_login"

        print "OK company.meli_login() called: url is ", url_login_meli

        return {
	        "type": "ir.actions.act_url",
	        "url": url_login_meli,
	        "target": "new",
        }

    def product_meli_state( self, cr, uid, ids, field_name, attributes, context=None ):
        # recoger el estado y devolver True o False (meli)
        #False if logged ok
        #True if need login
        user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        company = user_obj.company_id

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)

        ML_state = False
        if ACCESS_TOKEN=='':
            ML_state = True

        res = {}		
        for product in self.browse(cr,uid,ids):
            res[product.id] = ML_state
        return res

    _columns = {
	'meli_id': fields.char(string='Id del item asignado por Meli', size=256),
	'meli_title': fields.char(string='Nombre del producto en Mercado Libre',size=256), 
	'meli_description': fields.html(string='Description'),
	'meli_category': fields.many2one("mercadolibre.category","Categoría de MercadoLibre"),
	'meli_listing_type': fields.selection([("free","Libre"),("bronze","Bronce"),("silver","Plata"),("gold","Oro"),("premium","Premium")], string='Tipo de lista'),
	'meli_buying_mode': fields.selection( [("buy_it_now","Compre ahora"),("classified","Clasificado")], string='Método de compra'),
	'meli_price': fields.char(string='Precio de venta', size=128),
	'meli_currency': fields.selection([("ARS","Peso Argentino (ARS)")],string='Moneda (ARS)'),
	'meli_condition': fields.selection([ ("new", "Nuevo"), ("used", "Usado"), ("not_specified","No especificado")],'Condición del producto'),
	'meli_available_quantity': fields.integer(string='Cantidad disponible', size=128),
	'meli_warranty': fields.char(string='Garantía', size=256),
	'meli_imagen': fields.char(string='Imagen', size=256),
	'meli_video': fields.char(string='Video (id de youtube)', size=256),
	'meli_state': fields.function( product_meli_state, method=True, type='boolean', string="Estado de la sesión con MLA", store=False ),
	### Agregar imagen/archivo uno o mas, y la descripcion en HTML...
	# TODO Agregar el banner
    }

product_product()
