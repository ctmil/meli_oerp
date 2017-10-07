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

class mercadolibre_category(osv.osv):
    _name = "mercadolibre.category"
    _description = "Categories of MercadoLibre"

    _columns = {
	'name': fields.char('Name'),
	'meli_category_id': fields.char('Category Id'),
    }

    def import_category(self, cr, uid, category_id ):
        user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        company = user_obj.company_id

        warningobj = self.pool.get('warning')

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)

        if (category_id):
            ml_cat_id = self.pool.get('mercadolibre.category').search(cr,uid,[('meli_category_id','=',category_id)])
            if (ml_cat_id):
              print "category exists!" + str(ml_cat_id)
            else:
              print "Creating category: " + str(category_id)
              #https://api.mercadolibre.com/categories/MLA1743
              response_cat = meli.get("/categories/"+str(category_id), {'access_token':meli.access_token})
              rjson_cat = response_cat.json()
              print "category:" + str(rjson_cat)
              fullname = ""
              if ("path_from_root" in rjson_cat):
                  path_from_root = rjson_cat["path_from_root"]
                  for path in path_from_root:
                    fullname = fullname + "/" + path["name"]

              #fullname = fullname + "/" + rjson_cat['name']
              print "category fullname:" + fullname
              cat_fields = {
                'name': fullname,
                'meli_category_id': ''+str(category_id),
              }
              ml_cat_id = self.pool.get('mercadolibre.category').create(cr,uid,(cat_fields))


    def import_all_categories(self, cr, uid, category_root ):
        user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        company = user_obj.company_id

        warningobj = self.pool.get('warning')

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)

        RECURSIVE_IMPORT = company.mercadolibre_recursive_import

        if (category_root):
            response = meli.get("/categories/"+str(category_root), {'access_token':meli.access_token} )

            print "response.content:", response.content

            rjson = response.json()
            if ("name" in rjson):
                # en el html deberia ir el link  para chequear on line esa categoría corresponde a sus productos.
                warningobj.info(cr, uid, title='MELI WARNING', message="Preparando importación de todas las categorías en "+str(category_root), message_html=response )
                if ("children_categories" in rjson):
                    #empezamos a iterar categorias
                    for child in children_categories:
                        ml_cat_id = child["id"]
                        if (ml_cat_id):
                            category.import_category(category_id=ml_cat_id)
                            if (RECURSIVE_IMPORT):
                                category.import_all_categories(category_root=category_id)





mercadolibre_category()
