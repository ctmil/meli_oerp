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

import pdb
import threading

from .meli_oerp_config import *
from .warning import warning

import requests

class res_company(models.Model):
    _name = "res.company"
    _inherit = "res.company"

    def meli_get_object( self ):
        return True

    def get_ML_AUTH_URL(self,meli=False):

        AUTH_URL = "https://auth.mercadolibre.com.ar"

        ML_AUTH_URL = {
            "MLA": { "name": "Argentina", "AUTH_URL": "https://auth.mercadolibre.com.ar" },
            "MLM": { "name": "México", "AUTH_URL": "https://auth.mercadolibre.com.mx" },
            "MCO": { "name": "Colombia", "AUTH_URL": "https://auth.mercadolibre.com.co" },
            "MPE": { "name": "Perú", "AUTH_URL": "https://auth.mercadolibre.com.pe" },
            "MBO": { "name": "Bolivia", "AUTH_URL": "https://auth.mercadolibre.com.bo" },
            "MLB": { "name": "Brasil", "AUTH_URL": "https://auth.mercadolibre.com.br" },
            "MLC": { "name": "Chile", "AUTH_URL": "https://auth.mercadolibre.cl" },
            "MCR": {"name": "Costa Rica", "AUTH_URL": "https://auth.mercadolibre.com.cr" },
            "MLV": { "name": "Venezuela", "AUTH_URL": "https://auth.mercadolibre.com.ve" },
            "MRD": { "name": "Dominicana", "AUTH_URL": "https://auth.mercadolibre.com.do" },
            "MPA": { "name": "Panamá", "AUTH_URL": "https://auth.mercadolibre.com.pa" },
            "MPY": { "name": "Paraguay", "AUTH_URL": "https://auth.mercadolibre.com.py" },
            "MEC": { "name": "Ecuador", "AUTH_URL": "https://auth.mercadolibre.com.ec" },
        }
        MLsite = self._get_ML_sites(meli=meli)
        if MLsite in ML_AUTH_URL:
            AUTH_URL =  ML_AUTH_URL[MLsite]["AUTH_URL"] or AUTH_URL

        return AUTH_URL+"/authorization"

    def _get_ML_currencies(self):
        #https://api.mercadolibre.com/currencies
        company = self.env.user.company_id
        meli = self.env['meli.util'].get_new_instance(company)
        ML_currencies = [ ("ARS","Peso Argentino (ARS)"),
                            ("MXN","Peso Mexicano (MXN)"),
                            ("COP","Peso Colombiano (COP)"),
                            ("PEN","Sol Peruano (PEN)"),
                            ("BOB","Boliviano (BOB)"),
                            ("BRL","Real (BRL)"),
                            ("CLP","Peso Chileno (CLP)"),
                            ("CRC","Colon Costarricense (CRC)"),
                            ("UYU","Peso Uruguayo (UYU)"),
                            ("USD","Dolar Estadounidense (USD)")]
        if (meli):
            response = meli.get("/currencies")
            if (response):
                ML_currencies = []
                currencies = response.json()
                for k in currencies:
                    ML.append(( k["id"], k["description"] ))

        return ML_currencies


    def _get_ML_sites(self,meli=False):
        # to check api.mercadolibre.com/sites  > MLA
        company = self.env.user.company_id
        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)
        ML_sites = {
            "ARS": { "name": "Argentina", "id": "MLA", "default_currency_id": "ARS" },
            "MXN": { "name": "México", "id": "MLM", "default_currency_id": "MXN" },
            "COP": { "name": "Colombia", "id": "MCO", "default_currency_id": "COP" },
            "PEN": { "name": "Perú", "id": "MPE", "default_currency_id": "PEN" },
            "BOB": { "name": "Bolivia", "id": "MBO", "default_currency_id": "BOB" },
            "BRL": { "name": "Brasil", "id": "MLB", "default_currency_id": "BRL" },
            "CLP": { "name": "Chile", "id": "MLC", "default_currency_id": "CLP" },
            "CRC": {"name": "Costa Rica", "id": "MCR", "default_currency_id": "CRC"},
            "UYU": { "name": "Uruguay", "id": "MLU", "default_currency_id": "UYU" },
            "USD": { "name": "Uruguay", "id": "MLU", "default_currency_id": "UYU" },
        }
        response = meli.get("/sites")
        if (response):
            sites = response.json()
            #_logger.info(sites)
            for site in sites:
                #_logger.info("site:")
                #_logger.info(site)
                _key_ = site["default_currency_id"]
                if (_key_!="USD"):
                    ML_sites[_key_] = site

        currency = self.mercadolibre_currency

        #_logger.info(ML_sites)

        if (currency and currency in ML_sites):
            return ML_sites[currency]["id"]
        return "MLA"

    def get_meli_state( self ):
        # recoger el estado y devolver True o False (meli)
        #False if logged ok
        #True if need login
        #_logger.info('company get_meli_state() ')
        for company in self:
            #company = self or self.env.user.company_id
            _logger.info('company get_meli_state() '+str(company and company.name))
            #warningobj = self.pool.get('warning')
            meli = self.env['meli.util'].get_new_instance(company)
            if meli:
                company.mercadolibre_state = meli.needlogin_state


    def cron_meli_process( self ):

        _logger.info('company cron_meli_process() '+str(self))

        company = self.env.user.company_id
        warningobj = self.pool.get('warning')

        apistate = self.env['meli.util'].get_new_instance(company)
        if apistate.needlogin_state:
            return True

        _logger.info(str(company.name))

        if (company.mercadolibre_cron_get_update_products):
            _logger.info("company.mercadolibre_cron_get_update_products")
            self.meli_update_local_products()

        if (company.mercadolibre_cron_get_new_products):
            _logger.info("company.mercadolibre_cron_get_new_products")
            self.product_meli_get_products()

        if (company.mercadolibre_cron_post_update_products or company.mercadolibre_cron_post_new_products):
            _logger.info("company.mercadolibre_cron_post_update_products")
            self.meli_update_remote_products(post_new=company.mercadolibre_cron_post_new_products)

        if (company.mercadolibre_cron_post_update_stock):
            _logger.info("company.mercadolibre_cron_post_update_stock")
            self.meli_update_remote_stock(meli=apistate)

        if (company.mercadolibre_cron_post_update_price):
            _logger.info("company.mercadolibre_cron_post_update_price")
            self.meli_update_remote_price(meli=apistate)

    def cron_meli_orders(self):
        _logger.info('company cron_meli_orders() ')

        company = self.env.user.company_id
        warningobj = self.pool.get('warning')

        apistate = self.env['meli.util'].get_new_instance(company)
        if apistate.needlogin_state:
            return True

        if (company.mercadolibre_cron_get_orders):
            _logger.info("company.mercadolibre_cron_get_orders")
            self.meli_query_orders()

        if (company.mercadolibre_cron_get_questions):
            _logger.info("company.mercadolibre_cron_get_questions")
            self.meli_query_get_questions()

    mercadolibre_client_id = fields.Char(string='App Id', help='Client ID para ingresar a MercadoLibre',size=128)
    mercadolibre_secret_key = fields.Char(string='Secret Key', help='Secret Key para ingresar a MercadoLibre',size=128)
    mercadolibre_redirect_uri = fields.Char( string='Redirect Uri', help='Redirect uri (https://yourserver.yourdomain.com/meli_login)',size=1024)
    mercadolibre_access_token = fields.Char( string='Access Token', help='Access Token', size=256)
    mercadolibre_refresh_token = fields.Char( string='Refresh Token', help='Refresh Token', size=256)
    mercadolibre_code = fields.Char( string='Code', help='Code', size=256)
    mercadolibre_seller_id = fields.Char( string='Vendedor Id', size=256)
    mercadolibre_state = fields.Boolean( compute=get_meli_state, string='Desconectado', help="Se requiere Iniciar Sesión con MLA", store=False )
    mercadolibre_category_import = fields.Char( string='Category to import', help='Category Code to Import, check Recursive Import to import the full tree', size=256)
    mercadolibre_recursive_import = fields.Boolean( string='Recursive import', help='Import all the category tree from Category Code', size=256)

    mercadolibre_cron_refresh = fields.Boolean(string='Keep alive',help='Cron Automatic Token Refresh for keeping ML connection alive.')
    mercadolibre_cron_mail = fields.Many2one(
        comodel_name="mail.template",
        string="Error E-mail Template",
        help="Select the email template that will be sent when "
        "cron refresh fails.")
    mercadolibre_cron_get_orders = fields.Boolean(string="Importar pedidos",help='Cron Get Orders / Pedidos de venta')
    mercadolibre_cron_get_orders_shipment = fields.Boolean(string='Importar envíos',help='Cron Get Orders Shipment')
    mercadolibre_cron_get_orders_shipment_client = fields.Boolean(string='Importar clientes',help='Cron Get Orders Shipment Client')
    mercadolibre_cron_get_questions = fields.Boolean(string='Importar preguntas',help='Cron Get Questions')
    mercadolibre_cron_get_update_products = fields.Boolean(string='Actualizar productos',help='Cron Update Products already imported')
    mercadolibre_cron_post_update_products = fields.Boolean(string='Actualizar productos',help='Cron Update Posted Products, Product Templates or Variants with Meli Publication field checked')
    mercadolibre_cron_post_update_stock = fields.Boolean(string='Publicar Stock',help='Cron Post Updated Stock')
    mercadolibre_cron_post_update_price = fields.Boolean(string='Publicar Precio',help='Cron Post Updated Price')
    mercadolibre_create_website_categories = fields.Boolean(string='Crear categorías',help='Create Website eCommerce Categories from imported products ML categories')
    mercadolibre_pricelist = fields.Many2one( "product.pricelist", "Product Pricelist default", help="Select price list for ML product"
        "when published from Odoo to ML")

    mercadolibre_buying_mode = fields.Selection( [("buy_it_now","Compre ahora"),
                                                  ("classified","Clasificado")],
                                                  string='Método de compra predeterminado')
    mercadolibre_currency = fields.Selection([  ("ARS","Peso Argentino (ARS)"),
                                                ("MXN","Peso Mexicano (MXN)"),
                                                ("COP","Peso Colombiano (COP)"),
                                                ("PEN","Sol Peruano (PEN)"),
                                                ("BOB","Boliviano (BOB)"),
                                                ("BRL","Real (BRL)"),
                                                ("CLP","Peso Chileno (CLP)"),
                                                ("CRC","Colon Costarricense (CRC)"),
                                                ("UYU","Peso Uruguayo (UYU)"),
                                                ("USD","Dolar Estadounidense (USD)")],
                                                string='Moneda predeterminada')
    mercadolibre_condition = fields.Selection([ ("new", "Nuevo"),
                                                ("used", "Usado"),
                                                ("not_specified","No especificado")],
                                                string='Condición',
                                                help='Condición del producto predeterminado')
    mercadolibre_warranty = fields.Char(string='Garantía', size=256, help='Garantía del producto predeterminado. Es obligatorio y debe ser un número seguido por una unidad temporal. Ej. 2 meses, 3 años.')
    mercadolibre_listing_type = fields.Selection([("free","Libre"),
                                                ("bronze","Bronce"),
                                                ("silver","Plata"),
                                                ("gold","Oro"),
                                                ("gold_premium","Gold Premium"),
                                                ("gold_special","Gold Special/Clásica"),
                                                ("gold_pro","Oro Pro")],
                                                string='Tipo de lista',
                                                help='Tipo de lista  predeterminada para todos los productos')
    mercadolibre_attributes = fields.Boolean(string='Apply product attributes')
    mercadolibre_exclude_attributes = fields.Many2many('product.attribute.value',
        string='Valores excluidos', help='Seleccionar valores que serán excluidos para las publicaciones de variantes')
    mercadolibre_update_local_stock = fields.Boolean(string='Cron Get Products and take Stock from ML')
    mercadolibre_product_template_override_variant = fields.Boolean(string='Product template override Variant')
    mercadolibre_product_template_override_method = fields.Selection(string='Método para Sobreescribir',
                                                                    help='Método para Sobreescribir Titulo y Descripcion desde la información del Producto a la solapa de ML y sus variantes de ML',
                                                                    selection=[
                                                                        ('default','Predeterminado, sobreescribe descripcion solamente'),
                                                                        ('description','Sobreescribir descripcion solamente'),
                                                                        ('title','Sobreescribir título solamente'),
                                                                        ('title_and_description','Sobreescribir titulo y descripcion')
                                                                    ],
                                                                    default='default')
    mercadolibre_order_confirmation = fields.Selection([ ("manual", "Manual"),
                                                ("paid_confirm", "Pagado>Confirmado"),
                                                ("paid_delivered", "Pagado>Entregado")],
                                                string='Acción al recibir un pedido',
                                                help='Acción al confirmar una orden o pedido de venta')
    mercadolibre_product_attribute_creation = fields.Selection([ ("manual", "Manual"),
                                                ("full", "Sincronizado completo (uno a uno, sin importar si se usa o no)"),
                                                ("dynamic", "Dinámico (cuando se asocia un producto a una categoría (ML) con atributos (ML))") ],
                                                string='Create Product Attributes')
    #'mercadolibre_login': fields.selection( [ ("unknown", "Desconocida"), ("logged","Abierta"), ("not logged","Cerrada")],string='Estado de la sesión'), )
    mercadolibre_overwrite_template = fields.Boolean(string='Overwrite product template',help='Sobreescribir siempre Nombre y Descripción de la plantilla.')
    mercadolibre_overwrite_variant = fields.Boolean(string='Overwrite product variant',help='Sobreescribir siempre Nombre y Descripción de la variante.')
    mercadolibre_process_notifications = fields.Boolean(string='Process all notifications',help='Procesar las notificaciones recibidas (/meli_notify)')

    mercadolibre_create_product_from_order = fields.Boolean(string='Importar productos inexistentes',help='Importar productos desde la orden si no se encuentran en la base.')
    mercadolibre_update_existings_variants = fields.Boolean(string='Actualiza/agrega variantes',help='Permite agregar y actualizar variantes de un producto existente (No recomendable cuando se está ya en modo Odoo a ML, solo usar cuando se importa por primera vez de ML a Odoo, para no romper el stock)')
    mercadolibre_tax_included = fields.Selection( string='Tax Included',
                                                  help='Esto se aplica al importar ordenes, productos y tambien al publicar, sobre la lista de precio seleccionada o sobre el precio de lista.',
                                                  selection=[ ('auto','Configuración del sistema'),
                                                              ('tax_included','Impuestos ya incluídos del precio de lista'),
                                                              ('tax_excluded','Impuestos excluídos del precio de lista') ] )

    mercadolibre_do_not_use_first_image = fields.Boolean(string="Do not use first image")
    mercadolibre_cron_post_new_products = fields.Boolean(string='Incluir nuevos productos',help='Cron Post New Products, Product Templates or Variants with Meli Publication field checked')
    mercadolibre_cron_get_new_products = fields.Boolean(string='Importar nuevos productos',help='Cron Import New Products, Product Templates or Variants')

    mercadolibre_process_offset = fields.Char('Offset for pause all')
    mercadolibre_post_default_code = fields.Boolean(string='Post SKU',help='Post Odoo default_code field for templates or variants to seller_custom_field in ML')
    mercadolibre_import_search_sku = fields.Boolean(string='Search SKU',help='Search product by default_code')

    mercadolibre_seller_user = fields.Many2one("res.users", string="Vendedor", help="Usuario con el que se registrarán las órdenes automáticamente")
    mercadolibre_seller_team = fields.Many2one("crm.team", string="Equipo de ventas", help="Equipo de ventas asociado a las ventas de ML")
    mercadolibre_remove_unsync_images = fields.Boolean(string='Removing unsync images (ml id defined for image but no longer in ML publication)')

    mercadolibre_official_store_id = fields.Char(string="Official Store Id")

    mercadolibre_filter_order_datetime = fields.Datetime("Order Closed Date")
    mercadolibre_filter_order_datetime_to = fields.Datetime("Order Closed Date To")

    mercadolibre_payment_term = fields.Many2one("account.payment.term",string="Payment Term")

    #mercadolibre_use_buyer_name = fields.Boolean(string="Use buyer name",default=True)

    def	meli_logout(self):
        _logger.info('company.meli_logout() ')
        self.ensure_one()
        company = self.env.user.company_id
        company.write({'mercadolibre_access_token': '', 'mercadolibre_refresh_token': '', 'mercadolibre_code': '' } )
        url_logout_meli = '/web?debug=#'
        _logger.info( url_logout_meli )
        return {
            "type": "ir.actions.act_url",
            "url": url_logout_meli,
            "target": "new",
        }


    def meli_login(self):
        _logger.info('company.meli_login() ')
        self.ensure_one()
        company = self.env.user.company_id

        meli = self.env['meli.util'].get_new_instance(company)

        return meli.redirect_login()

    def meli_query_get_questions(self):

        _logger.info("meli_query_get_questions")
        posting_obj = self.env['mercadolibre.posting']
        posting_ids = posting_obj.search(['|',('meli_status','=','active'),('meli_status','=','under_review')])
        _logger.info(posting_ids)
        if (posting_ids):
            for posting in posting_ids:
                posting.posting_query_questions()

        posting_ids = posting_obj.search(['&',('meli_status','!=','active'),('meli_status','!=','under_review')])
        _logger.info(posting_ids)
        if (posting_ids):
            for posting in posting_ids:
                posting.posting_query_questions()
        return {}


    def meli_query_orders(self):
        _logger.info('company.meli_query_orders() ')
        company = self.env.user.company_id
        orders_obj = self.env['mercadolibre.orders']
        result = orders_obj.orders_query_recent()
        return {}


    def meli_query_products(self):
        _logger.info('company.meli_query_products() ')
        company = self.env.user.company_id
        self.product_meli_get_products()
        return {}

    def product_meli_get_products( self ):
        _logger.info('company.product_meli_get_products() ')
        company = self.env.user.company_id
        product_obj = self.pool.get('product.product')

        meli = self.env['meli.util'].get_new_instance(company)
        if meli.need_login():
            return meli.redirect_login()

        results = []
        response = meli.get("/users/"+company.mercadolibre_seller_id+"/items/search", {'access_token':meli.access_token,'offset': 0 })
        rjson = response.json()
        _logger.info( rjson )

        if 'error' in rjson:
            _logger.error(rjson)


        if 'results' in rjson:
            results = rjson['results']

        #download?
        totalmax = 0
        if 'paging' in rjson:
            totalmax = rjson['paging']['total']

        _logger.info( "totalmax: "+str(totalmax) )

        scroll_id = False
        if (totalmax>1000):
            #USE SCAN METHOD....
            _logger.info( "use scan method: "+str(totalmax) )
            response = meli.get("/users/"+company.mercadolibre_seller_id+"/items/search",
                                {'access_token':meli.access_token,
                                'search_type': 'scan',
                                'limit': '100' })
            rjson = response.json()
            _logger.info( rjson )

            condition_last_off = True
            ioff = 0

            if ('scroll_id' in rjson):
                scroll_id = rjson['scroll_id']
                ioff = rjson['paging']['limit']
                results = rjson['results']
                condition_last_off = False

            while (condition_last_off!=True):
                _logger.info( "Prefetch products ("+str(ioff)+"/"+str(rjson['paging']['total'])+")" )
                response = meli.get("/users/"+company.mercadolibre_seller_id+"/items/search",
                    {
                    'access_token':meli.access_token,
                    'search_type': 'scan',
                    'scroll_id': scroll_id,
                    'limit': '100'
                    })
                rjson2 = response.json()
                if 'error' in rjson2:
                    _logger.error(rjson2)
                    if rjson2['message']=='invalid_token' or rjson2['message']=='expired_token':
                        ACCESS_TOKEN = ''
                        REFRESH_TOKEN = ''
                        company.write({'mercadolibre_access_token': ACCESS_TOKEN, 'mercadolibre_refresh_token': REFRESH_TOKEN, 'mercadolibre_code': '' } )
                        condition = True
                        return {
                        "type": "ir.actions.act_url",
                        "url": url_login_meli,
                        "target": "new",}
                    condition_last_off = True
                else:
                    #_logger.info(rjson2)
                    results += rjson2['results']
                    ioff+= rjson2['paging']['limit']
                    if ('scroll_id' in rjson2):
                        scroll_id = rjson2['scroll_id']
                        condition_last_off = False
                    else:
                        condition_last_off = True

        if (totalmax<=1000 and totalmax>rjson['paging']['limit']):
            pages = rjson['paging']['total']/rjson['paging']['limit']
            ioff = rjson['paging']['limit']
            condition_last_off = False
            while (condition_last_off!=True):
                _logger.info( "Prefetch products ("+str(ioff)+"/"+str(rjson['paging']['total'])+")" )
                response = meli.get("/users/"+company.mercadolibre_seller_id+"/items/search", {'access_token':meli.access_token,'offset': ioff })
                rjson2 = response.json()
                if 'error' in rjson2:
                    if rjson2['message']=='invalid_token' or rjson2['message']=='expired_token':
                        ACCESS_TOKEN = ''
                        REFRESH_TOKEN = ''
                        company.write({'mercadolibre_access_token': ACCESS_TOKEN, 'mercadolibre_refresh_token': REFRESH_TOKEN, 'mercadolibre_code': '' } )
                        return {
                        "type": "ir.actions.act_url",
                        "url": url_login_meli,
                        "target": "new",}
                    condition_last_off = True
                else:
                    results += rjson2['results']
                    ioff+= rjson['paging']['limit']
                    condition_last_off = ( ioff>=totalmax)

        _logger.info( results )
        _logger.info( "FULL RESULTS: " + str(len(results)) )
        _logger.info( "("+str(rjson['paging']['total'])+") products to check...")
        iitem = 0
        icommit = 0
        micom = 5
        if (results):
            self._cr.autocommit(False)
            try:
                for item_id in results:
                    _logger.info(item_id)
                    iitem+= 1
                    icommit+= 1
                    if (icommit>=micom):
                        self._cr.commit()
                        icommit = 0
                    _logger.info( item_id + "("+str(iitem)+"/"+str(rjson['paging']['total'])+")" )
                    posting_id = self.env['product.product'].search([('meli_id','=',item_id)])

                    response = meli.get("/items/"+item_id, {'access_token':meli.access_token})
                    rjson3 = response.json()
                    if ( ( not posting_id or len(posting_id)==0 ) and company.mercadolibre_import_search_sku ):
                        seller_sku = None
                        if ('seller_custom_field' in rjson3 and rjson3['seller_custom_field'] and len(rjson3['seller_custom_field'])):
                            seller_sku = rjson3['seller_custom_field']
                        if not seller_sku and "attributes" in rjson3:
                            for att in rjson3['attributes']:
                                if att["id"] == "SELLER_SKU":
                                    seller_sku = att["values"][0]["name"]
                                    break;
                        if (seller_sku):
                            posting_id = self.env['product.product'].search([('default_code','=',seller_sku)])
                            if (not posting_id or len(posting_id)==0):
                                posting_id = self.env['product.template'].search([('default_code','=',seller_sku)])
                                _logger.info("Founded template with default code, dont know how to handle it.")
                            else:
                                posting_id.meli_id = item_id
                        if ('variations' in rjson3):
                            for var in rjson3['variations']:
                                if ('seller_custom_field' in var and var['seller_custom_field'] and len(var['seller_custom_field'])):
                                    posting_id = self.env['product.product'].search([('default_code','=',var['seller_custom_field'])])
                                    if (posting_id):
                                        posting_id.meli_id = item_id
                                        if (len(posting_id.product_tmpl_id.product_variant_ids)>1):
                                            posting_id.meli_id_variation = var['id']

                    if (posting_id):
                        _logger.info( "Item already in database: " + str(posting_id[0]) )
                    #elif (not company.mercadolibre_import_search_sku):
                    else:
                        #idcreated = self.pool.get('product.product').create(cr,uid,{ 'name': rjson3['title'], 'meli_id': rjson3['id'] })
                        if 'id' in rjson3:
                            prod_fields = {
                                'name': rjson3['title'].encode("utf-8"),
                                'description': rjson3['title'].encode("utf-8"),
                                'meli_id': rjson3['id'],
                                'meli_pub': True,
                            }
                            #prod_fields['default_code'] = rjson3['id']
                            productcreated = self.env['product.product'].create((prod_fields))
                            if (productcreated):
                                if (productcreated.product_tmpl_id):
                                    productcreated.product_tmpl_id.meli_pub = True
                                _logger.info( "product created: " + str(productcreated) + " >> meli_id:" + str(rjson3['id']) + "-" + str( rjson3['title'].encode("utf-8")) )
                                #pdb.set_trace()
                                _logger.info(productcreated)
                                productcreated.product_meli_get_product()
                            else:
                                _logger.info( "product couldnt be created")
                        else:
                            _logger.info( "product error: " + str(rjson3) )
            except Exception as e:
                _logger.info("product_meli_get_products Exception!")
                _logger.info(e, exc_info=True)
                self._cr.rollback()
        return {}


    def meli_update_local_products(self):
        _logger.info('company.meli_update_local_products() ')
        self.product_meli_update_local_products()
        return {}


    def meli_post_new_remote_products(self):
        _logger.info('company.meli_post_new_remote_products() ')
        self.product_meli_update_remote_products(post_new=True)
        return {}

    def meli_update_remote_products(self,post_new=False):
        _logger.info('company.meli_update_remote_products() ')
        self.product_meli_update_remote_products(post_new=post_new)
        return {}

    def product_meli_update_local_products( self ):
        _logger.info('company.product_meli_update_local_products() ')
        company = self.env.user.company_id
        product_obj = self.env['product.product']

        meli = self.env['meli.util'].get_new_instance(company)
        url_login_meli = meli.auth_url()

        product_ids = self.env['product.product'].search([('meli_id','!=',False),
                                                          '|',('company_id','=',False),('company_id','=',company.id)])
        if product_ids:
            cn = 0
            ct = len(product_ids)
            self._cr.autocommit(False)
            try:
                for obj in product_ids:
                    cn = cn + 1
                    _logger.info( "Product to update: [" + str(obj.id) + "] " + str(cn)+"/"+str(ct))
                    try:
                        obj.product_meli_get_product()
                        self._cr.commit()
                    except Exception as e:
                        _logger.info("updating product > Exception error.")
                        _logger.error(e, exc_info=True)
                        pass

            except Exception as e:
                _logger.info("product_meli_update_products > Exception error.")
                _logger.error(e, exc_info=True)
                self._cr.rollback()

        return {}

    def product_meli_update_remote_products( self, post_new = False ):
        _logger.info('company.product_meli_update_remote_products() ')
        company = self.env.user.company_id
        product_obj = self.env['product.product']

        meli = self.env['meli.util'].get_new_instance(company)
        url_login_meli = meli.auth_url()

        #product_ids = self.env['product.product'].search([('meli_pub','=',True),('meli_id','!=',False)])
        product_ids = self.env['product.template'].search([('meli_pub','=',True),
                                                          '|',('company_id','=',False),('company_id','=',company.id)])
        _logger.info("product_ids to update or create:" + str(product_ids))

        ret_messages = []
        if product_ids:
            for obj in product_ids:
                try:
                    post_update = company.mercadolibre_cron_post_update_products
                    updating = post_update and obj.meli_publications and len(obj.meli_publications)
                    #(obj.meli_variants_status=='active')
                    creating = post_new and ( not obj.meli_publications or ( obj.meli_publications and obj.meli_publications == '') )
                    _logger.info(obj.name)
                    _logger.info(obj.meli_publications)
                    _logger.info(obj.meli_variants_status)
                    if ( updating or creating):
                        res = {}
                        if (updating):
                            _logger.info( "Product remote update: " + str(obj.id)  )
                            res = obj.product_template_post()
                        if (creating):
                            _logger.info( "Product remote to create: " + str(obj.id)  )
                            res = obj.with_context({'force_meli_pub': True }).product_template_post()

                        #we have a message
                        if 'res_id' in res:
                            warning = self.env["warning"].browse(res["res_id"])
                            if (warning):
                                ret_messages.append( { 'obj': obj, 'message': str(warning.message)  } )

                except Exception as e:
                    _logger.info("product_meli_update_remote_products > Exception founded!")
                    _logger.info(e, exc_info=True)

        self.meli_send_report( ret_messages )

    def meli_send_report(self, report_messages ):
        company = self.env.user.company_id
        thread_obj = self.env['mail.thread']

        if (len(report_messages)):

            report_body = ""

            for msg in report_messages:
                report_body+= msg["obj"].name+": "+str(msg["obj"].meli_publications)+"\n"
                report_body+= "Mensaje: " + str(msg["message"]) + "\n"
                report_body+= "\n"

            post_vars = {
             'subject': "Meli Notification - Update Remote Products",
             'body': report_body,
             'partner_ids': [(3, 1)],
             'type': "notification",
             'subtype': "mt_comment"
             }

            thread_obj.message_post( **post_vars )


    def meli_import_categories(self, context=None ):
        company = self.env.user.company_id
        category_obj = self.env['mercadolibre.category']
        CATEGORY_ROOT = company.mercadolibre_category_import
        result = category_obj.import_all_categories(category_root=CATEGORY_ROOT )
        return {}


    def meli_update_remote_stock(self, meli=False):
        company = self.env.user.company_id
        if (company.mercadolibre_cron_post_update_stock):
            auto_commit = not getattr(threading.currentThread(), 'testing', False)
            product_ids_null = self.env['product.product'].search([
                ('meli_pub','=',True),
                ('meli_id','!=',False),
                ('meli_stock_update','=',False),
                '|',('company_id','=',False),('company_id','=',company.id)
                ], order='id asc')
            product_ids_not_null = self.env['product.product'].search([
                ('meli_pub','=',True),
                ('meli_id','!=',False),
                ('meli_stock_update','!=',False),
                '|',('company_id','=',False),('company_id','=',company.id)
                ], order='meli_stock_update asc')
            product_ids = product_ids_null + product_ids_not_null
            topcommits = 80
            _logger.info("product_ids stock to update:" + str(product_ids))
            _logger.info("updating stock #" + str(len(product_ids)) + " on " + str(company.name)+ " cron top:"+str(topcommits))
            icommit = 0
            icount = 0
            maxcommits = len(product_ids)
            internals = {
                "application_id": company.mercadolibre_client_id,
                "user_id": company.mercadolibre_seller_id,
                "topic": "internal",
                "resource": "meli_update_remote_stock #"+str(maxcommits),
                "state": "PROCESSING"
            }
            noti = self.env["mercadolibre.notification"].start_internal_notification( internals )
            logs = ""
            errors = ""

            try:
                if auto_commit:
                    self.env.cr.commit()
                for obj in product_ids:
                    #_logger.info( "Product check if active: " + str(obj.id)+ ' meli_id:'+str(obj.meli_id)  )
                    if (obj.meli_id and icount<=topcommits):
                        icommit+= 1
                        icount+= 1
                        try:
                            _logger.info( "Update Stock: #" + str(icount) +'/'+str(maxcommits)+ ' meli_id:'+str(obj.meli_id)  )
                            resjson = obj.product_post_stock(meli=meli)
                            logs+= str(obj.default_code)+" "+str(obj.meli_id)+": "+str(obj.meli_available_quantity)+"\n"

                            if "error" in resjson:

                                obj.stock_error = str(resjson)
                                errors+= str(obj.default_code)+" "+str(obj.meli_id)+" >> "+str(resjson)+"\n"

                                is_fulfillment = obj.meli_shipping_logistic_type and "fulfillment" in obj.meli_shipping_logistic_type
                                if is_fulfillment:
                                    obj.stock_error = "fulfillment"

                            else:
                                obj.stock_error = str({})

                            if ( icommit==40 or icount==maxcommits or icount==topcommits ):
                                noti.processing_errors = errors
                                noti.processing_logs = logs
                                noti.resource = "meli_update_remote_stock #"+str(icount) +'/'+str(maxcommits)
                                _logger.info("meli_update_remote_stock commiting")
                                icommit=0
                                if auto_commit:
                                    self.env.cr.commit()

                        except Exception as e:
                            _logger.info("meli_update_remote_stock > Exception founded!")
                            _logger.info(e, exc_info=True)
                            logs+= str(obj.default_code)+" "+str(obj.meli_id)+": "+str(obj.meli_available_quantity)+", "
                            #errors+= str(obj.default_code)+" "+str(obj.meli_id)+" >> "+str(e.args[0])+str(", ")
                            errors+= str(obj.default_code)+" "+str(obj.meli_id)+" >> "+str(e)+"\n"
                            if auto_commit:
                                self.env.cr.rollback()

                noti.resource = "meli_update_remote_stock #"+str(icount) +'/'+str(maxcommits)
                noti.stop_internal_notification(errors=errors,logs=logs)

            except Exception as e:
                _logger.info("meli_update_remote_stock > Exception founded!")
                _logger.info(e, exc_info=True)
                if auto_commit:
                    self.env.cr.rollback()
                noti.stop_internal_notification( errors=errors , logs=logs )
                if auto_commit:
                    self.env.cr.commit()

        return {}


    def meli_update_remote_price(self, meli=False):
        company = self.env.user.company_id
        if (company.mercadolibre_cron_post_update_price):
            auto_commit = not getattr(threading.currentThread(), 'testing', False)
            product_ids = self.env['product.product'].search([('meli_pub','=',True),('meli_id','!=',False),
                                                              '|',('company_id','=',False),('company_id','=',company.id)])
            _logger.info("product_ids price to update:" + str(product_ids))
            _logger.info("updating price #" + str(len(product_ids)) + " on " + str(company.name))

            icommit = 0
            icount = 0
            maxcommits = len(product_ids)

            #meli = self.env['meli.util'].get_new_instance(company)

            if product_ids and meli:

                internals = {
                    "application_id": company.mercadolibre_client_id,
                    "user_id": company.mercadolibre_seller_id,
                    "topic": "internal",
                    "resource": "meli_update_remote_price #"+str(maxcommits),
                    "state": "PROCESSING"
                }
                noti = self.env["mercadolibre.notification"].start_internal_notification( internals )
                logs = ""
                errors = ""
                try:
                    if auto_commit:
                        self.env.cr.commit()
                    for obj in product_ids:

                        icommit+= 1
                        icount+= 1
                        #_logger.info( "Product remote to update: " + str(obj.id)  )
                        if (obj.meli_id):
                            try:
                                _logger.info( "Update Price: #" + str(icount) +'/'+str(maxcommits)+ ' meli_id:'+str(obj.meli_id)  )
                                resjson = obj.product_post_price(meli=meli)
                                logs+= str(obj.default_code)+" "+str(obj.meli_id)+": "+str(obj.meli_price)+"\n"
                                if "error" in resjson:
                                    errors+= str(obj.default_code)+" "+str(obj.meli_id)+" >> "+str(resjson)+"\n"

                                if ((icommit==40 or (icount==maxcommits)) and 1==1):
                                    noti.processing_errors = errors
                                    noti.processing_logs = logs
                                    noti.resource = "meli_update_remote_price #"+str(icount) +'/'+str(maxcommits)
                                    _logger.info("meli_update_remote_price commiting")
                                    icommit=0
                                    if auto_commit:
                                        self.env.cr.commit()

                            except Exception as e:
                                _logger.info("meli_update_remote_price > Exception founded!")
                                _logger.info(e, exc_info=True)
                                logs+= str(obj.default_code)+" "+str(obj.meli_id)+": "+str(obj.meli_price)+", "
                                #errors+= str(obj.default_code)+" "+str(obj.meli_id)+" >> "+str(e.args[0])+str(", ")
                                errors+= str(obj.default_code)+" "+str(obj.meli_id)+" >> "+str(e)+"\n"
                                if auto_commit:
                                    self.env.cr.rollback()

                    noti.resource = "meli_update_remote_price #"+str(icount) +'/'+str(maxcommits)
                    noti.stop_internal_notification(errors=errors,logs=logs)

                except Exception as e:
                    _logger.info("meli_update_remote_price > Exception founded!")
                    _logger.info(e, exc_info=True)
                    if auto_commit:
                        self.env.cr.rollback()
                    noti.stop_internal_notification( errors=errors , logs=logs )
                    if auto_commit:
                        self.env.cr.commit()

        return {}

    def meli_notifications(self, data=False):
        company = self
        _logger.info("meli_notifications")
        notifications = self.env['mercadolibre.notification']
        if (self.mercadolibre_process_notifications):
            return notifications.fetch_lasts( data, company )
        return {}

    def meli_set_automatic_tax_included(self):
        #create a product with a price of 100, check if tax are created
        #create an order with this product and check final amount in line.
        return False

    def meli_pause_all( self ):
        _logger.info('company.meli_pause_all() ')
        company = self.env.user.company_id
        product_obj = self.pool.get('product.product')

        meli = self.env['meli.util'].get_new_instance(company)
        url_login_meli = meli.auth_url()

        results = []
        offset = 0
        status = 'active'
        if (company.mercadolibre_process_offset):
            offset = company.mercadolibre_process_offset
        response = meli.get("/users/"+company.mercadolibre_seller_id+"/items/search", {'status': status,'access_token':meli.access_token,'offset': offset })
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
        totalmax = rjson['paging']['total']
        scroll_id = False
        if (totalmax>1000):
            #USE SCAN METHOD....
            response = meli.get("/users/"+company.mercadolibre_seller_id+"/items/search",
                                {'access_token':meli.access_token,
                                'search_type': 'scan',
                                'status': status,
                                'offset': offset,
                                'limit': '100' })
            rjson = response.json()
            _logger.info( rjson )
            condition_last_off = True
            if ('scroll_id' in rjson):
                scroll_id = rjson['scroll_id']
                ioff = rjson['paging']['limit']
                results = rjson['results']
                condition_last_off = False
            while (condition_last_off!=True):
                _logger.info( "Prefetch products ("+str(ioff)+"/"+str(rjson['paging']['total'])+")" )
                response = meli.get("/users/"+company.mercadolibre_seller_id+"/items/search",
                    {
                    'access_token':meli.access_token,
                    'search_type': 'scan',
                    'scroll_id': scroll_id,
                    'limit': '100'
                    })
                rjson2 = response.json()
                if 'error' in rjson2:
                    _logger.error( rjson2 )
                    if rjson2['message']=='invalid_token' or rjson2['message']=='expired_token':
                        ACCESS_TOKEN = ''
                        REFRESH_TOKEN = ''
                        company.write({'mercadolibre_access_token': ACCESS_TOKEN, 'mercadolibre_refresh_token': REFRESH_TOKEN, 'mercadolibre_code': '' } )
                        condition = True
                        return {
                        "type": "ir.actions.act_url",
                        "url": url_login_meli,
                        "target": "new",}
                    condition_last_off = True
                else:
                    results += rjson2['results']
                    ioff+= rjson2['paging']['limit']
                    if ('scroll_id' in rjson2):
                        scroll_id = rjson2['scroll_id']
                        condition_last_off = False
                    else:
                        condition_last_off = True

        if (totalmax<=1000 and totalmax>rjson['paging']['limit']):
            pages = rjson['paging']['total']/rjson['paging']['limit']
            ioff = rjson['paging']['limit']
            condition_last_off = False
            while (condition_last_off!=True):
                _logger.info( "Prefetch products ("+str(ioff)+"/"+str(rjson['paging']['total'])+")" )
                response = meli.get("/users/"+company.mercadolibre_seller_id+"/items/search", {'access_token':meli.access_token,'offset': ioff })
                rjson2 = response.json()
                if 'error' in rjson2:
                    if rjson2['message']=='invalid_token' or rjson2['message']=='expired_token':
                        ACCESS_TOKEN = ''
                        REFRESH_TOKEN = ''
                        company.write({'mercadolibre_access_token': ACCESS_TOKEN, 'mercadolibre_refresh_token': REFRESH_TOKEN, 'mercadolibre_code': '' } )
                        return {
                        "type": "ir.actions.act_url",
                        "url": url_login_meli,
                        "target": "new",}
                    condition_last_off = True
                else:
                    results += rjson2['results']
                    ioff+= rjson['paging']['limit']
                    condition_last_off = ( ioff>=totalmax)

        _logger.info( results )
        _logger.info( "FULL RESULTS: " + str(len(results)) )
        _logger.info( "("+str(rjson['paging']['total'])+") products to check...")
        iitem = 0
        icommit = 0
        micom = 5
        if (results):
            #self._cr.autocommit(False)
            try:
                for item_id in results:
                    _logger.info(item_id)
                    iitem+= 1
                    icommit+= 1
                    if (icommit>=micom):
                        #self._cr.commit()
                        icommit = 0
                    _logger.info( item_id + "("+str(iitem)+"/"+str(rjson['paging']['total'])+")" )
                    posting_id = self.env['product.product'].search([('meli_id','=',item_id),
                                                                      '|',('company_id','=',False),('company_id','=',company.id)])
                    if (posting_id):
                        _logger.info( "meli_pause_all Item already in database: " + str(posting_id[0]) )
                        #response = meli.get("/items/"+item_id, {'access_token':meli.access_token})
                        #rjson3 = response.json()
                    else:
                        #idcreated = self.pool.get('product.product').create(cr,uid,{ 'name': rjson3['title'], 'meli_id': rjson3['id'] })
                        #prod_fields['default_code'] = rjson3['id']
                        response = meli.put("/items/"+item_id, { 'status': 'paused' }, {'access_token':meli.access_token})
            except Exception as e:
                _logger.info("meli_pause_all Exception!")
                _logger.info(e, exc_info=True)
                #self._cr.rollback()
        return {}

res_company()
