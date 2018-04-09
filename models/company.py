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
from ..melisdk.meli import Meli

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
        message = "Login to ML needed in Odoo."
        #pdb.set_trace()

        try:
            if not (company.mercadolibre_seller_id==False):
                response = meli.get("/users/"+str(company.mercadolibre_seller_id), {'access_token':meli.access_token} )
                _logger.info("response.content:"+str(response.content))
                rjson = response.json()
                #response = meli.get("/users/")
                if "error" in rjson:
                    ML_state = True

                    if rjson["error"]=="not_found":
                        ML_state = True

                    if "message" in rjson:
                        message = rjson["message"]
                        if (rjson["message"]=="expired_token" or rjson["message"]=="invalid_token"):
                            ML_state = True
                            try:
                                refresh = meli.get_refresh_token()
                                _logger.info("need to refresh:"+str(refresh))
                                if (refresh):
                                    ACCESS_TOKEN = meli.access_token
                                    REFRESH_TOKEN = meli.refresh_token
                                    company.write({'mercadolibre_access_token': ACCESS_TOKEN, 'mercadolibre_refresh_token': REFRESH_TOKEN, 'mercadolibre_code': '' } )
                                    ML_state = False
                            except Exception as e:
                                _logger.error(e)
            else:
                ML_state = True

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

            if (company.mercadolibre_refresh_token and company.mercadolibre_cron_mail):
                # we put the job_exception in context to be able to print it inside
                # the email template
                context = {
                    'job_exception': message,
                    'dbname': self._cr.dbname,
                }

                _logger.debug(
                    "Sending scheduler error email with context=%s", context)

                self.env['mail.template'].browse(
                    company.mercadolibre_cron_mail.id
                ).with_context(context).sudo().send_mail( (company.id), force_send=True)

        #res = {}
        #for company in self.browse(cr,uid,ids):
        #for company in self:
        #    res[company.id] = ML_state
        company.mercadolibre_state = ML_state

        if (company.mercadolibre_cron_get_orders):
            _logger.info("company.mercadolibre_cron_get_orders")
            self.meli_query_orders()

        if (company.mercadolibre_cron_get_update_products):
            _logger.info("company.mercadolibre_cron_get_update_products")
            self.meli_update_products()


        #_logger.info("ML_state:"+str(ML_state))
        #return res

    mercadolibre_client_id = fields.Char(string='Client ID para ingresar a MercadoLibre',size=128)
    mercadolibre_secret_key = fields.Char(string='Secret Key para ingresar a MercadoLibre',size=128)
    mercadolibre_redirect_uri = fields.Char( string='Redirect uri (https://myserver/meli_login)',size=1024)
    mercadolibre_access_token = fields.Char( string='Access Token',size=256)
    mercadolibre_refresh_token = fields.Char( string='Refresh Token', size=256)
    mercadolibre_code = fields.Char( string='Code', size=256)
    mercadolibre_seller_id = fields.Char( string='Vendedor Id', size=256)
    mercadolibre_state = fields.Boolean( compute=get_meli_state, string="Se requiere Iniciar Sesión con MLA", store=False )
    mercadolibre_category_import = fields.Char( string='Category Code to Import', size=256)
    mercadolibre_recursive_import = fields.Boolean( string='Import all categories (recursiveness)', size=256)

    mercadolibre_cron_refresh = fields.Boolean(string='Cron Refresh')
    mercadolibre_cron_mail = fields.Many2one(
        comodel_name="mail.template",
        string="Cron Error E-mail Template",
        help="Select the email template that will be sent when "
        "cron refresh fails.")
    mercadolibre_cron_get_orders = fields.Boolean(string='Cron Get Orders')
    mercadolibre_cron_get_questions = fields.Boolean(string='Cron Get Questions')
    mercadolibre_cron_get_update_products = fields.Boolean(string='Cron Update Products')
    mercadolibre_create_website_categories = fields.Boolean(string='Create Website Categories')
    mercadolibre_pricelist = fields.Many2one( "product.pricelist", "Product Pricelist default", help="Select price list for ML product"
        "when published from Odoo to ML")

    mercadolibre_buying_mode = fields.Selection( [("buy_it_now","Compre ahora"),
                                                  ("classified","Clasificado")],
                                                  string='Método de compra predeterminado')
    mercadolibre_currency = fields.Selection([("ARS","Peso Argentino (ARS)")],
                                                string='Moneda predeterminada')
    mercadolibre_condition = fields.Selection([ ("new", "Nuevo"),
                                                ("used", "Usado"),
                                                ("not_specified","No especificado")],
                                                'Condición del producto predeterminado')
    mercadolibre_warranty = fields.Char(string='Garantía', size=256)
    mercadolibre_listing_type = fields.Selection([("free","Libre"),
                                                ("bronze","Bronce"),
                                                ("silver","Plata"),
                                                ("gold","Oro"),
                                                ("gold_premium","Gold Premium"),
                                                ("gold_special","Gold Special"),
                                                ("gold_pro","Oro Pro")],
                                                string='Tipo de lista  predeterminada')
    mercadolibre_attributes = fields.Boolean(string='Apply product attributes')

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

        orders_obj = self.env['mercadolibre.orders']

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
                        prod_fields = {
                            'name': rjson3['id'],
                            'description': rjson3['title'].encode("utf-8"),
                            'meli_id': rjson3['id']
                        }
                        prod_fields['default_code'] = rjson3['id']
                        productcreated = self.env['product.product'].create((prod_fields))
                        if (productcreated):
                            _logger.info( "product created: " + str(productcreated) + " >> meli_id:" + str(rjson3['id']) + "-" + str( rjson3['title'].encode("utf-8")) )
                            #pdb.set_trace()
                            _logger.info(productcreated)
                            productcreated.product_meli_get_product()
                        else:
                            _logger.info( "product couldnt be created")
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
        product_obj = self.env['product.product']
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
                _logger.info( "Product to update: " + str(obj.id)  )
                #_logger.info( "Product to update name: " + str(obj.name)  )
                #obj.product_meli_get_product()
                #import pdb; pdb.set_trace()
                #print "Product " + obj.name
                obj.product_meli_get_product()

        return {}

    def meli_import_categories(self, context=None ):
        company = self.env.user.company_id

        category_obj = self.env['mercadolibre.category']

        CATEGORY_ROOT = company.mercadolibre_category_import

        result = category_obj.import_all_categories(category_root=CATEGORY_ROOT )

        return {}

res_company()
