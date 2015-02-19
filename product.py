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

import requests
import melisdk
import base64
import mimetypes

from meli_oerp_config import *

from melisdk.meli import Meli

class product_product(osv.osv):
    
    _inherit = "product.product"


    def product_meli_get_product( self, cr, uid, ids, context=None ):
        user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        company = user_obj.company_id
        product_obj = self.pool.get('product.product')
        product = product_obj.browse(cr, uid, ids[0])

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)

        response = meli.get("/items/"+product.meli_id, {'access_token':meli.access_token})

        print "product_meli_get_product: " + response.content

        return {}

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

    def product_get_meli_loginstate( self, cr, uid, ids, field_name, attributes, context=None ):
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
        else:
            response = meli.get("/users/me/", {'access_token':meli.access_token} )
            rjson = response.json()
            if 'error' in rjson:
                if rjson['message']=='invalid_token' or rjson['message']=='expired_token':
                    ACCESS_TOKEN = ''
                    REFRESH_TOKEN = ''
                    company.write({'mercadolibre_access_token': ACCESS_TOKEN, 'mercadolibre_refresh_token': REFRESH_TOKEN, 'mercadolibre_code': '' } )
                    ML_state = True
                    #raise osv.except_osv( _('MELI WARNING'), _('INVALID TOKEN (must login, go to Edit Company and login):  error: %s, message: %s, status: %s') % ( rjson["error"], rjson["message"],rjson["status"],))

        res = {}		
        for product in self.browse(cr,uid,ids):
            res[product.id] = ML_state
        return res

    def product_meli_status_close( self, cr, uid, ids, context=None ):
        user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        company = user_obj.company_id
        product_obj = self.pool.get('product.product')
        product = product_obj.browse(cr, uid, ids[0])

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)

        response = meli.put("/items/"+product.meli_id, { 'status': 'closed' }, {'access_token':meli.access_token})

        print "product_meli_status_close: " + response.content

        return {}

    def product_meli_status_pause( self, cr, uid, ids, context=None ):
        user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        company = user_obj.company_id
        product_obj = self.pool.get('product.product')
        product = product_obj.browse(cr, uid, ids[0])

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)

        response = meli.put("/items/"+product.meli_id, { 'status': 'paused' }, {'access_token':meli.access_token})

        print "product_meli_status_pause: " + response.content

        return {}

    def product_meli_status_active( self, cr, uid, ids, context=None ):
        user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        company = user_obj.company_id
        product_obj = self.pool.get('product.product')
        product = product_obj.browse(cr, uid, ids[0])

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)

        response = meli.put("/items/"+product.meli_id, { 'status': 'active' }, {'access_token':meli.access_token})

        print "product_meli_status_active: " + response.content

        return {}

    def product_meli_delete( self, cr, uid, ids, context=None ):

        user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        company = user_obj.company_id
        product_obj = self.pool.get('product.product')
        product = product_obj.browse(cr, uid, ids[0])

        if product.meli_status!='closed':
            self.product_meli_status_close( cr, uid, ids, context )

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)

        response = meli.put("/items/"+product.meli_id, { 'deleted': 'true' }, {'access_token':meli.access_token})

        print "product_meli_delete: " + response.content
        rjson = response.json()
        ML_status = rjson["status"]
        if "error" in rjson:
            ML_status = rjson["error"]
        if "sub_status" in rjson:
            if len(rjson["sub_status"]) and rjson["sub_status"][0]=='deleted':
                product.write({ 'meli_id': '' })

        return {}

    def product_meli_upload_image( self, cr, uid, ids, context=None ):

        user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        company = user_obj.company_id

        product_obj = self.pool.get('product.product')
        product = product_obj.browse(cr, uid, ids[0])

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        #
        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)

        if product.image==None:
            return { 'status': 'error', 'message': 'no image to upload' }

        print "product_meli_upload_image"
        #print "product_meli_upload_image: " + response.content
        imagebin = base64.b64decode(product.image)
        imageb64 = product.image
#       print "data:image/png;base64,"+imageb64
#       files = [ ('images', ('image_medium', imagebin, "image/png")) ]
        files = { 'file': ('image.png', imagebin, "image/png"), }
        print  files
        response = meli.upload("/pictures", files, { 'access_token': meli.access_token } )
        print response.content

        rjson = response.json()
        if ("error" in rjson):
            print "Error!"
            raise osv.except_osv( _('MELI WARNING'), _('No se pudo cargar la imagen en MELI! Error: %s , Mensaje: %s, Status: %s') % ( rjson["error"], rjson["message"],rjson["status"],))
            return { 'status': 'error', 'message': 'not uploaded'}

        if ("id" in rjson):
            #guardar id
            product.write( { "meli_imagen_id": rjson["id"] } )
            #asociar imagen a producto
            if product.meli_id:
                response = meli.post("/items/"+product.meli_id+"/pictures", { 'id': rjson["id"] }, { 'access_token': meli.access_token } )
                print response.content
            else:
                return { 'status': 'warning', 'message': 'uploaded but not assigned' }
        
        return { 'status': 'success', 'message': 'uploaded and assigned' } 

    def product_meli_upload_multi_images( self, cr, uid, ids, context=None ):

        user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        company = user_obj.company_id

        product_obj = self.pool.get('product.product')
        product = product_obj.browse(cr, uid, ids[0])

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        #
        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)

        if product.images==None:
            return { 'status': 'error', 'message': 'no images to upload' }

        image_ids = []
        c = 0

        #loop over images
        for product_image in product.images:
            print "product_image: ", product_image
            imagebin = base64.b64decode( product_image.image )
            files = { 'file': ('image.png', imagebin, "image/png"), }
            print  files
            response = meli.upload("/pictures", files, { 'access_token': meli.access_token } )
            print response.content

            rjson = response.json()
            if ("error" in rjson):
                print "Error!"
                raise osv.except_osv( _('MELI WARNING'), _('No se pudo cargar la imagen en MELI! Error: %s , Mensaje: %s, Status: %s') % ( rjson["error"], rjson["message"],rjson["status"],))
                #return { 'status': 'error', 'message': 'not uploaded'}
            else:
                print "image id:", rjson['id']
                image_ids+= [ { 'id': rjson['id'] }]
                c = c + 1 
        
        product.write( { "meli_multi_imagen_id": "%s" % (image_ids) } )
                
        return image_ids
        

    def product_on_change_meli_banner(self, cr, uid, ids, banner_id ):
        print 'product_on_change_meli_banner > ', banner_id
        print 'ids:', ids

        banner_obj = self.pool.get('mercadolibre.banner')

        #solo para saber si ya habia una descripcion completada
        product_obj = self.pool.get('product.product')
        if len(ids):
            product = product_obj.browse(cr, uid, ids[0])
        else:
            product = product_obj.browse(cr, uid, ids)

        banner = banner_obj.browse( cr, uid, banner_id )


        return { 'value': { 'meli_description' : banner.description } }

    def product_get_meli_status( self, cr, uid, ids, field_name, attributes, context=None ):
        
        print "product_get_meli_status (product status)"
        user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        company = user_obj.company_id
        warningobj = self.pool.get('warning')

        product_obj = self.pool.get('product.product')
        product = product_obj.browse(cr, uid, ids[0])

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        ML_status = "unknown"
        if ACCESS_TOKEN=='':
            ML_status = "unknown"
        else:
            meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)
            if product.meli_id:
                response = meli.get("/items/"+product.meli_id, {'access_token':meli.access_token} )
                print response.content
                rjson = response.json()
                ML_status = rjson["status"]
                if "error" in rjson:
                    ML_status = rjson["error"]
                if "sub_status" in rjson:
                    if len(rjson["sub_status"]) and rjson["sub_status"][0]=='deleted':
                        product.write({ 'meli_id': '' })

        res = {}		
        for product in self.browse(cr,uid,ids):
            res[product.id] = ML_status
        return res

    def product_get_permalink( self, cr, uid, ids, field_name, attributes, context=None ):
        ML_permalink = ''

        user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        company = user_obj.company_id

        product_obj = self.pool.get('product.product')
        product = product_obj.browse(cr, uid, ids[0])        

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token


        ML_permalink = ""
        if ACCESS_TOKEN=='':
            ML_permalink = ""
        else:
            meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)
            if product.meli_id:
                response = meli.get("/items/"+product.meli_id, {'access_token':meli.access_token} )
                print response.content
                rjson = response.json()
                if "permalink" in rjson:
                    ML_permalink = rjson["permalink"]
                if "error" in rjson:
                    ML_permalink = ""                    
                #if "sub_status" in rjson:
                    #if len(rjson["sub_status"]) and rjson["sub_status"][0]=='deleted':
                    #    product.write({ 'meli_id': '' })


        res = {}		
        for product in self.browse(cr,uid,ids):
            res[product.id] = ML_permalink
        return res      


    _columns = {
    'meli_post_required': fields.boolean(string='Este producto es publicable en Mercado Libre'),
	'meli_id': fields.char( string='Id del item asignado por Meli', size=256),
    'meli_permalink': fields.function( product_get_permalink, method=True, type='char',  size=256, string='PermaLink in MercadoLibre' ),
	'meli_title': fields.char(string='Nombre del producto en Mercado Libre',size=256), 
	'meli_description': fields.html(string='Descripción'),
    'meli_description_banner_id': fields.many2one("mercadolibre.banner","Banner"),
	'meli_category': fields.many2one("mercadolibre.category","Categoría de MercadoLibre"),
	'meli_listing_type': fields.selection([("free","Libre"),("bronze","Bronce"),("silver","Plata"),("gold","Oro"),("gold_premium","Gold Premium"),("gold_special","Gold Special")], string='Tipo de lista'),
	'meli_buying_mode': fields.selection( [("buy_it_now","Compre ahora"),("classified","Clasificado")], string='Método de compra'),
	'meli_price': fields.char(string='Precio de venta', size=128),
	'meli_currency': fields.selection([("ARS","Peso Argentino (ARS)")],string='Moneda (ARS)'),
	'meli_condition': fields.selection([ ("new", "Nuevo"), ("used", "Usado"), ("not_specified","No especificado")],'Condición del producto'),
	'meli_available_quantity': fields.integer(string='Cantidad disponible'),
	'meli_warranty': fields.char(string='Garantía', size=256),
	'meli_imagen_logo': fields.char(string='Imagen Logo', size=256),
    'meli_imagen_id': fields.char(string='Imagen Id', size=256),
    'meli_multi_imagen_id': fields.char(string='Multi Imagen Ids', size=512),
	'meli_video': fields.char( string='Video (id de youtube)', size=256),
	'meli_state': fields.function( product_get_meli_loginstate, method=True, type='boolean', string="Inicio de sesión requerida", store=False ),
    'meli_status': fields.function( product_get_meli_status, method=True, type='char', size=128, string="Estado del producto en MLA", store=False ),
	### Agregar imagen/archivo uno o mas, y la descripcion en HTML...
	# TODO Agregar el banner
    }

    _defaults = {
        'meli_imagen_logo': 'http://www.nuevohorizonte-sa.com.ar/images/logo1.png',
        'meli_video': '6JhmxwtTjoA'
    }


product_product()
