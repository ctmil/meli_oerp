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
from openerp.tools.translate import _
import logging
_logger = logging.getLogger(__name__)
import urllib2

from meli_oerp_config import *
from warning import warning

import requests
import melisdk
from melisdk.meli import Meli

#REDIRECT_URI = 'http://127.0.0.1:8069/meli_login'

class res_company(osv.osv):
    _name = "res.company"
    _inherit = "res.company"

    def meli_get_object( self, cr, uid, ids, field_name, attributes, context=None ):
        return True

    def get_meli_state( self, cr, uid, ids, field_name, attributes, context=None ):
        # recoger el estado y devolver True o False (meli)
        #False if logged ok
        #True if need login
        print 'company get_meli_state() '
        user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        company = user_obj.company_id
        warningobj = self.pool.get('warning')

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)
        ML_state = False

        try:
            response = meli.get("/items/MLA1", {'access_token':meli.access_token} )
            print "response.content:", response.content
            rjson = response.json()
            #response = meli.get("/users/")
            if "error" in rjson:
                if "message" in rjson and rjson["message"]=="expired_token":
                    ML_state = True

            if ACCESS_TOKEN=='':
                ML_state = True
        except requests.exceptions.ConnectionError as e:
            #raise osv.except_osv( _('MELI WARNING'), _('NO INTERNET CONNECTION TO API.MERCADOLIBRE.COM: complete the Cliend Id, and Secret Key and try again'))
            ML_state = True
            error_msg = 'MELI WARNING: NO INTERNET CONNECTION TO API.MERCADOLIBRE.COM: complete the Cliend Id, and Secret Key and try again '
            _logger.error(error_msg)

#        except requests.exceptions.HTTPError as e:
#            print "And you get an HTTPError:", e.message

        if ML_state:
            ACCESS_TOKEN = ''
            REFRESH_TOKEN = ''

            company.write({'mercadolibre_access_token': ACCESS_TOKEN, 'mercadolibre_refresh_token': REFRESH_TOKEN, 'mercadolibre_code': '' } )

        res = {}
        for company in self.browse(cr,uid,ids):
            res[company.id] = ML_state
        return res

    _columns = {
        'mercadolibre_client_id': fields.char(string='Client ID para ingresar a MercadoLibre',size=128),
        'mercadolibre_secret_key': fields.char(string='Secret Key para ingresar a MercadoLibre',size=128),
        'mercadolibre_redirect_uri': fields.char( string='Redirect uri (https://myserver/meli_login)',size=1024),
        'mercadolibre_access_token': fields.char( string='Access Token',size=256),
        'mercadolibre_refresh_token': fields.char( string='Refresh Token', size=256),
        'mercadolibre_code': fields.char( string='Code', size=256),
        'mercadolibre_seller_id': fields.char( string='Vendedor Id', size=256),
        'mercadolibre_state': fields.function( get_meli_state, method=True, type='boolean', string="Se requiere Iniciar Sesión con MLA", store=False ),
        #'mercadolibre_login': fields.selection( [ ("unknown", "Desconocida"), ("logged","Abierta"), ("not logged","Cerrada")],string='Estado de la sesión'), )
    }

    def	meli_logout(self, cr, uid, ids, context=None ):

        user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        company = user_obj.company_id

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = ''
        REFRESH_TOKEN = ''

        company.write({'mercadolibre_access_token': ACCESS_TOKEN, 'mercadolibre_refresh_token': REFRESH_TOKEN, 'mercadolibre_code': '' } )
        url_logout_meli = '/web?debug=#view_type=kanban&model=product.template&action=150'
        print url_logout_meli
        return {
            "type": "ir.actions.act_url",
            "url": url_logout_meli,
            "target": "new",
        }

    def meli_login(self, cr, uid, ids, context=None ):

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
            "target": "self",
        }

    def meli_query_orders(self, cr, uid, ids, context=None ):

        user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        company = user_obj.company_id

        orders_obj = self.pool.get('mercadolibre.orders')

        result = orders_obj.orders_query_recent(cr,uid)
#"type": "ir.actions.act_window",
#"id": "action_meli_orders_tree",
        return {}

    def meli_query_products(self, cr, uid, ids, context=None ):
        user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        company = user_obj.company_id

        products_obj = self.pool.get('product.product')

        result = products_obj.product_meli_get_products(cr,uid)
        #"type": "ir.actions.act_window",
        #"id": "action_meli_orders_tree",
        return {}

res_company()

