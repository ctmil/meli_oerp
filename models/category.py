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
_logger = logging.getLogger(__name__)
import urllib2

from meli_oerp_config import *
from warning import warning

import requests
from ..melisdk.meli import Meli

class product_public_category(models.Model):

    _inherit="product.public.category"

    mercadolibre_category = fields.Many2one( "mercadolibre.category", string="Mercado Libre Category")

product_public_category()


class mercadolibre_category(models.Model):
    _name = "mercadolibre.category"
    _description = "Categories of MercadoLibre"

    @api.one
    def get_attributes( self ):

        company = self.env.user.company_id

        warningobj = self.env['warning']
        category_obj = self.env['mercadolibre.category']

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)

        if (self.meli_category_id):
            self.meli_category_attributes = "https://api.mercadolibre.com/categories/"+str(self.meli_category_id)+"/attributes"

        return {}


    def import_category(self, category_id ):
        company = self.env.user.company_id

        warningobj = self.env['warning']
        category_obj = self.env['mercadolibre.category']

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)

        if (category_id):
            ml_cat_id = category_obj.search([('meli_category_id','=',category_id)])
            if (ml_cat_id):
              _logger.info("category exists!" + str(ml_cat_id))
            else:
              _logger.info("Creating category: " + str(category_id))
              #https://api.mercadolibre.com/categories/MLA1743
              response_cat = meli.get("/categories/"+str(category_id), {'access_token':meli.access_token})
              rjson_cat = response_cat.json()
              _logger.info("category:" + str(rjson_cat))
              fullname = ""
              if ("path_from_root" in rjson_cat):
                  path_from_root = rjson_cat["path_from_root"]
                  for path in path_from_root:
                    fullname = fullname + "/" + path["name"]

              #fullname = fullname + "/" + rjson_cat['name']
              #print "category fullname:" + str(fullname)
              _logger.info(fullname)
              cat_fields = {
                'name': fullname,
                'meli_category_id': ''+str(category_id),
              }
              ml_cat_id = category_obj.create((cat_fields))


    def import_all_categories(self, category_root ):
        company = self.env.user.company_id

        warningobj = self.env['warning']
        category_obj = self.env['mercadolibre.category']

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
                warningobj.info( title='MELI WARNING', message="Preparando importación de todas las categorías en "+str(category_root), message_html=response )
                if ("children_categories" in rjson):
                    #empezamos a iterar categorias
                    for child in rjson["children_categories"]:
                        ml_cat_id = child["id"]
                        if (ml_cat_id):
                            category_obj.import_category(category_id=ml_cat_id)
                            if (RECURSIVE_IMPORT):
                                category_obj.import_all_categories(category_root=ml_cat_id)


    name = fields.Char('Name')
    meli_category_id = fields.Char('Category Id')
    public_category_id = fields.Integer('Public Category Id')
    #public_category = fields.Many2one( "product.category.public", string="Product Website category default", help="Select Public Website category for this ML category ")
    meli_category_attributes = fields.Char(compute=get_attributes,  string="Mercado Libre Category Attributes")


mercadolibre_category()
