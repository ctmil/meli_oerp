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
from odoo.tools.translate import _
import logging
_logger = logging.getLogger(__name__)
import urllib2
import pdb

from meli_oerp_config import *
from warning import warning

import requests
import melisdk
from melisdk.meli import Meli

#REDIRECT_URI = 'http://127.0.0.1:8069/meli_login'

class res_company(models.Model):
    _name = "res.company"
    _inherit = "res.company"

    def meli_get_object( self, cr, uid, ids, field_name, attributes, context=None ):
        return True

    @api.multi
    def get_meli_state( self ):
        # recoger el estado y devolver True o False (meli)
        #False if logged ok
        #True if need login
        _logger.info('company get_meli_state() ')
        #user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        #company = user_obj.company_id
        company = self.env.user.company_id
        warningobj = self.pool.get('warning')

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)
        ML_state = False

        #pdb.set_trace()

        try:
            _logger.info("access_token:"+str(ACCESS_TOKEN))
            response = meli.get("/items/MLA1", {'access_token':meli.access_token} )
            _logger.info("response.content:"+str(response.content))
            rjson = response.json()
            #response = meli.get("/users/")
            if "error" in rjson:
                ML_state = True
                if "message" in rjson and rjson["message"]=="expired_token":
                    ML_state = True
                if rjson["error"]=="not_found":
                    ML_state = False

            if ACCESS_TOKEN=='' or ACCESS_TOKEN==False:
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

        #res = {}
        #for company in self.browse(cr,uid,ids):
        #for company in self:
        #    res[company.id] = ML_state
        company.mercadolibre_state = ML_state
        #_logger.info("ML_state:"+str(ML_state))
        #return res

    mercadolibre_client_id = fields.Char(string='Client ID para ingresar a MercadoLibre',size=128);
    mercadolibre_secret_key = fields.Char(string='Secret Key para ingresar a MercadoLibre',size=128);
    mercadolibre_redirect_uri = fields.Char( string='Redirect uri (https://myserver/meli_login)',size=1024);
    mercadolibre_access_token = fields.Char( string='Access Token',size=256);
    mercadolibre_refresh_token = fields.Char( string='Refresh Token', size=256);
    mercadolibre_code = fields.Char( string='Code', size=256);
    mercadolibre_seller_id = fields.Char( string='Vendedor Id', size=256);
    mercadolibre_state = fields.Boolean( compute=get_meli_state, string="Se requiere Iniciar Sesión con MLA", store=False );
    #'mercadolibre_login': fields.selection( [ ("unknown", "Desconocida"), ("logged","Abierta"), ("not logged","Cerrada")],string='Estado de la sesión'), )

    @api.multi
    def	meli_logout(self):
        _logger.info('company.meli_logout() ')
        self.ensure_one()
        company = self.env.user.company_id
        #user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        #company = user_obj.company_id

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

    @api.multi
    def meli_login(self):
        _logger.info('company.meli_login() ')
        self.ensure_one()
        company = self.env.user.company_id
        #user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        #company = user_obj.company_id

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

    @api.multi
    def meli_query_orders(self):

        _logger.info('company.meli_query_orders() ')
        #user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        #company = user_obj.company_id
        company = self.env.user.company_id

        orders_obj = self.pool.get('mercadolibre.orders')

        result = orders_obj.orders_query_recent()
#"type": "ir.actions.act_window",
#"id": "action_meli_orders_tree",
        return {}

    @api.multi
    def meli_query_products(self):
        _logger.info('company.meli_query_products() ')
        #user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        #company = user_obj.company_id
        company = self.env.user.company_id

        #products_obj = self.pool.get('product.product')

        #result = products_obj.product_meli_get_products(products_obj)
        #"type": "ir.actions.act_window",
        #"id": "action_meli_orders_tree",
        self.product_meli_get_products()

        return {}

    def product_meli_get_products( self ):
        _logger.info('company.product_meli_get_products() ')
        #user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        #company = user_obj.company_id
        company = self.env.user.company_id
        product_obj = self.pool.get('product.product')
        #product = product_obj.browse(cr, uid, ids[0])

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)

        url_login_meli = meli.auth_url(redirect_URI=REDIRECT_URI)
        #url_login_oerp = "/meli_login"

        results = []
        response = meli.get("/users/"+company.mercadolibre_seller_id+"/items/search", {'access_token':meli.access_token,'offset': 0 })
        #response = meli.get("/sites/MLA/search?seller_id="+company.mercadolibre_seller_id+"&limit=0", {'access_token':meli.access_token})
        rjson = response.json()
        _logger.info( rjson )

        if 'error' in rjson:
            if rjson['message']=='invalid_token' or rjson['message']=='expired_token':
                ACCESS_TOKEN = ''
                REFRESH_TOKEN = ''
                company.write({'mercadolibre_access_token': ACCESS_TOKEN, 'mercadolibre_refresh_token': REFRESH_TOKEN, 'mercadolibre_code': '' } )
            return {
            "type": "ir.actions.act_url",
            "url": url_login_meli,
            "target": "new",}


        if 'results' in rjson:
            results = rjson['results']

        #download?
        if (rjson['paging']['total']>rjson['paging']['limit']):
            pages = rjson['paging']['total']/rjson['paging']['limit']
            ioff = rjson['paging']['limit']
            condition_last_off = False
            while (condition_last_off!=True):
                response = meli.get("/users/"+company.mercadolibre_seller_id+"/items/search", {'access_token':meli.access_token,'offset': ioff })
                rjson2 = response.json()
                if 'error' in rjson2:
                    if rjson2['message']=='invalid_token' or rjson2['message']=='expired_token':
                        ACCESS_TOKEN = ''
                        REFRESH_TOKEN = ''
                        company.write({'mercadolibre_access_token': ACCESS_TOKEN, 'mercadolibre_refresh_token': REFRESH_TOKEN, 'mercadolibre_code': '' } )
                    condition = True
                    return {
                    "type": "ir.actions.act_url",
                    "url": url_login_meli,
                    "target": "new",}
                else:
                    results += rjson2['results']
                    ioff+= rjson['paging']['limit']
                    condition_last_off = ( ioff>=rjson['paging']['total'])


        _logger.info( rjson )
        _logger.info( "("+str(rjson['paging']['total'])+") products to check...")
        iitem = 0
        if (results):
            for item_id in results:
                print item_id
                iitem+= 1
                _logger.info( item_id + "("+str(iitem)+"/"+str(rjson['paging']['total'])+")" )
                posting_id = self.env['product.product'].search([('meli_id','=',item_id)])
                response = meli.get("/items/"+item_id, {'access_token':meli.access_token})
                rjson3 = response.json()
                if (posting_id):
                    _logger.info( "Item already in database: " + str(posting_id[0]) )
                    #print "Item already in database: " + str(posting_id[0])
                else:
                    #idcreated = self.pool.get('product.product').create(cr,uid,{ 'name': rjson3['title'], 'meli_id': rjson3['id'] })
                    if 'id' in rjson3:
                        productcreated = self.env['product.product'].create({ 'name': rjson3['id'], 'description': rjson3['title'].encode("utf-8"), 'meli_id': rjson3['id'] })
                        if (productcreated):
                            _logger.info( "product created: " + str(productcreated) + " >> meli_id:" + str(rjson3['id']) + "-" + str( rjson3['title'].encode("utf-8")) )
                            #pdb.set_trace()
                            product_obj.product_meli_get_product( productcreated )
                    else:
                        _logger.info( "product error: " + str(rjson3) )

        return {}

    @api.multi
    def meli_update_products(self):
        _logger.info('company.meli_update_products() ')
        #user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        #company = user_obj.company_id
        company = self.env.user.company_id

        #products_obj = self.pool.get('product.product')

        #result = products_obj.product_meli_get_products(products_obj)
        #"type": "ir.actions.act_window",
        #"id": "action_meli_orders_tree",
        self.product_meli_update_products()

        return {}

    def product_meli_update_products( self ):
        _logger.info('company.product_meli_update_products() ')
        #user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        #company = user_obj.company_id
        company = self.env.user.company_id
        product_obj = self.pool.get('product.product')
        #product = product_obj.browse(cr, uid, ids[0])

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)

        url_login_meli = meli.auth_url(redirect_URI=REDIRECT_URI)
        #url_login_oerp = "/meli_login"

        product_ids = self.env['product.product'].search([])
        if product_ids:
            for obj in product_ids:
                product = product_obj.browse(obj.id)
                _logger.info( "Product to update: " + str(obj.id) + " name:" + str(product.name) )

        return {}

res_company()
