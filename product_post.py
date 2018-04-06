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

import json
from datetime import datetime

#from bottle import Bottle, run, template, route, request
#import json
from meli_oerp_config import *

from warning import warning

import melisdk
from melisdk.meli import Meli

class product_post(osv.osv_memory):
    _name = "mercadolibre.product.post"
    _description = "Wizard de Product Posting en MercadoLibre"

    _columns = {
	    'type': fields.selection([('post','Alta'),('put','Editado'),('delete','Borrado')], string='Tipo de operación' ),
	    'posting_date': fields.date('Fecha del posting'),
	    #'company_id': fields.many2one('res.company',string='Company'),
	    #'mercadolibre_state': fields.related( 'res.company', 'mercadolibre_state', string="State" )
    }

    def pretty_json( self, cr, uid, ids, data, indent=0, context=None ):
        return json.dumps( data, sort_keys=False, indent=4 )

    def product_post(self, cr, uid, ids, context=None):

        product_ids = context['active_ids']
        product_obj = self.pool.get('product.product')

        user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        #user_obj.company_id.meli_login()
        company = user_obj.company_id
        warningobj = self.pool.get('warning')

        #company = self.pool.get('res.company').browse(cr,uid,1)

        REDIRECT_URI = company.mercadolibre_redirect_uri
        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token


        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)

        if ACCESS_TOKEN=='':
            meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET)
            url_login_meli = meli.auth_url(redirect_URI=REDIRECT_URI)
            return {
	            "type": "ir.actions.act_url",
	            "url": url_login_meli,
	            "target": "new",
            }

        for product_id in product_ids:
            product = product_obj.browse(cr,uid,product_id)

            if (product.meli_id):
                response = meli.get("/items/%s" % product.meli_id, {'access_token':meli.access_token})

            # print product.meli_category.meli_category_id

            if product.meli_title==False:
                # print 'Assigning title: product.meli_title: %s name: %s' % (product.meli_title, product.name)
                product.meli_title = product.name

            if product.meli_price==False:
                # print 'Assigning price: product.meli_price: %s standard_price: %s' % (product.meli_price, product.standard_price)
                product.meli_price = product.standard_price

            body = {
                "title": product.meli_title or '',
                "description": product.meli_description or '',
                "category_id": product.meli_category.meli_category_id or '0',
                "listing_type_id": product.meli_listing_type or '0',
                "buying_mode": product.meli_buying_mode or '',
                "price": product.meli_price  or '0',
                "currency_id": product.meli_currency  or '0',
                #"condition": product.meli_condition  or '',
                "available_quantity": product.meli_available_quantity  or '0',
                "warranty": product.meli_warranty or '',
                #"pictures": [ { 'source': product.meli_imagen_logo} ] ,
                "video_id": product.meli_video  or '',
            }
            #print "product.meli_id before setting condigions ]"+product.meli_id+"["
            if (len(product.meli_id)==0):
                body["condition"] = product.meli_condition;

            # print body

            assign_img = False and product.meli_id

            #publicando imagen cargada en OpenERP
            if product.image==None:
                return warningobj.info(cr, uid, title='MELI WARNING', message="Debe cargar una imagen de base en el producto.", message_html="" )
            elif product.meli_imagen_id==False:
                # print "try uploading image..."
                resim = product.product_meli_upload_image()
                if "status" in resim:
                    if (resim["status"]=="error" or resim["status"]=="warning"):
                        error_msg = 'MELI: mensaje de error:   ', resim
                        _logger.error(error_msg)
                    else:
                        assign_img = True and product.meli_imagen_id

            #modificando datos si ya existe el producto en MLA
            if (product.meli_id):
                body = {
                    "title": product.meli_title or '',
                    #"description": product.meli_description or '',
                    #"category_id": product.meli_category.meli_category_id,
                    #"listing_type_id": product.meli_listing_type,
                    #"buying_mode": product.meli_buying_mode or '',
                    "price": product.meli_price or '0',
                    #"currency_id": product.meli_currency,
                    #"condition": product.meli_condition or '',
                    "available_quantity": product.meli_available_quantity or '0',
                    "warranty": product.meli_warranty or '',
                    "pictures": [],
                    #"pictures": [ { 'source': product.meli_imagen_logo} ] ,
                    "video_id": product.meli_video or '',
                }

            #publicando multiples imagenes
            multi_images_ids = {}
            if (product.images):
                # print 'website_multi_images presente:   ', product.images
                #recorrer las imagenes y publicarlas
                multi_images_ids = product.product_meli_upload_multi_images()

            #asignando imagen de logo (por source)
            if product.meli_imagen_logo:
                if product.meli_imagen_id:
                    if 'pictures' in body.keys():
                        body["pictures"]+= [ { 'id': product.meli_imagen_id } ]
                    else:
                        body["pictures"] = [ { 'id': product.meli_imagen_id } ]

                        if (multi_images_ids):
                            if 'pictures' in body.keys():
                                body["pictures"]+= multi_images_ids
                            else:
                                body["pictures"] = multi_images_ids

                    if 'pictures' in body.keys():
                        body["pictures"]+= [ { 'source': product.meli_imagen_logo} ]
                    else:
                        body["pictures"]+= [ { 'source': product.meli_imagen_logo} ]
                else:
                    imagen_producto = ""
                    if (product.meli_description!="" and product.meli_description!=False and product.meli_imagen_link!=""):
                        imgtag = "<img style='width: 420px; height: auto;' src='%s'/>" % ( product.meli_imagen_link )
                        result = product.meli_description.replace( "[IMAGEN_PRODUCTO]", imgtag )
                        if (result):
                            _logger.info( "result: %s" % (result) )
                            product.meli_description = result
                        else:
                            result = product.meli_description



            else:
                return warningobj.info(cr, uid, title='MELI WARNING', message="Debe completar el campo 'Imagen_Logo' con el url: http://www.nuevohorizonte-sa.com.ar/images/logo1.png", message_html="")

            #check fields
            if product.meli_description==False:
                return warningobj.info(cr, uid, title='MELI WARNING', message="Debe completar el campo 'description' (en html)", message_html="")

            #put for editing, post for creating
            if product.meli_id:
                response = meli.put("/items/"+product.meli_id, body, {'access_token':meli.access_token})
            else:
                assign_img = True and product.meli_imagen_id
                response = meli.post("/items", body, {'access_token':meli.access_token})

            #check response
            # print response.content
            rjson = response.json()

            #check error
            if "error" in rjson:
                #print "Error received: %s " % rjson["error"]
                error_msg = 'MELI: mensaje de error:  %s , mensaje: %s, status: %s, cause: %s ' % (rjson["error"], rjson["message"], rjson["status"], rjson["cause"])
                _logger.error(error_msg)

                missing_fields = error_msg

                #expired token
                if "message" in rjson and (rjson["message"]=='invalid_token' or rjson["message"]=="expired_token"):
                    meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET)
                    url_login_meli = meli.auth_url(redirect_URI=REDIRECT_URI)
                    #print "url_login_meli:", url_login_meli
                    #raise osv.except_osv( _('MELI WARNING'), _('INVALID TOKEN or EXPIRED TOKEN (must login, go to Edit Company and login):  error: %s, message: %s, status: %s') % ( rjson["error"], rjson["message"],rjson["status"],))
                    return warningobj.info(cr, uid, title='MELI WARNING', message="Debe iniciar sesión en MELI.  ", message_html="")
                else:
                     #Any other errors
                    return warningobj.info(cr, uid, title='MELI WARNING', message="Completar todos los campos!  ", message_html="<br><br>"+missing_fields )

            #last modifications if response is OK
            if "id" in rjson:
                product.write( { 'meli_id': rjson["id"]} )

            posting_fields = {'posting_date': str(datetime.now()),'meli_id':rjson['id'],'product_id':product.id,'name': 'Post: ' + product.meli_title }

            posting_id = self.pool.get('mercadolibre.posting').search(cr,uid,[('meli_id','=',rjson['id'])])

            if not posting_id:
	            posting_id = self.pool.get('mercadolibre.posting').create(cr,uid,(posting_fields))


        return {}

product_post()
