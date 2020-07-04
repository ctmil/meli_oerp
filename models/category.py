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

from .meli_oerp_config import *
from .warning import warning

import requests
from ..melisdk.meli import Meli
import json

from .versions import *

class product_public_category(models.Model):

    _inherit="product.public.category"

    mercadolibre_category = fields.Many2one( "mercadolibre.category", string="Mercado Libre Category")

product_public_category()


class mercadolibre_category_attribute(models.Model):
    _name = "mercadolibre.category.attribute"
    _description = "MercadoLibre Attribute"

    att_id = fields.Char(string="Attribute Id (ML)",index=True)
    name = fields.Char(string="Attribute Name (ML)",index=True)

    value_type = fields.Char(string="Value Type",index=True)

    hidden = fields.Boolean(string="Hidden")
    variation_attribute = fields.Boolean(string="Variation Attribute")
    multivalued = fields.Boolean(string="Multivalued")

    tooltip = fields.Text(string="Tooltip")
    values = fields.Text(string="Values")
    type = fields.Char(string="Type")

    required = fields.Boolean(string="Required by ML")

mercadolibre_category_attribute()

class product_attribute(models.Model):

    _inherit="product.attribute"

    mercadolibre_attribute_id = fields.Many2one( "mercadolibre.category.attribute", string="MercadoLibre Attribute")

product_attribute()

class mercadolibre_category(models.Model):
    _name = "mercadolibre.category"
    _description = "Categories of MercadoLibre"


    def _get_category_url( self ):
        company = self.env.user.company_id

        warningobj = self.env['warning']
        category_obj = self.env['mercadolibre.category']
        att_obj = self.env['mercadolibre.category.attribute']
        prod_att_obj = self.env['product.attribute']

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)

        for category in self:
            if (category and category.meli_category_id):
                _logger.info("_get_category_url:"+str(category.meli_category_id))
                response_cat = meli.get("/categories/"+str(category.meli_category_id), {'access_token':meli.access_token})
                rjson_cat = response_cat.json()
                category.is_branch = ( "children_categories" in rjson_cat and len(rjson_cat["children_categories"])>0 )
                category.meli_category_url = "https://api.mercadolibre.com/categories/"+str(category.meli_category_id)
                category.meli_category_attributes = "https://api.mercadolibre.com/categories/"+str(category.meli_category_id)+"/attributes"
                #_logger.info(rjson_cat["path_from_root"])
                if (len(rjson_cat["path_from_root"])>=2):
                    fid = int(len(rjson_cat["path_from_root"])-2)
                    #_logger.info(fid)
                    _logger.info(rjson_cat["path_from_root"][fid]["id"])
                    category.meli_father_category_id = rjson_cat["path_from_root"][fid]["id"]


    def _get_attributes( self ):

        company = self.env.user.company_id

        warningobj = self.env['warning']
        category_obj = self.env['mercadolibre.category']
        att_obj = self.env['mercadolibre.category.attribute']
        prod_att_obj = self.env['product.attribute']

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)
        for category in self:
            if (category.meli_category_id
                and category.is_branch==False
                and ( category.meli_category_attribute_ids==None or len(category.meli_category_attribute_ids)==0 )):
                _logger.info("_get_attributes:"+str(category.meli_category_id))
                category.meli_category_attributes = "https://api.mercadolibre.com/categories/"+str(category.meli_category_id)+"/attributes"
                resp = meli.get("/categories/"+str(category.meli_category_id)+"/attributes", {'access_token':meli.access_token})
                rjs = resp.json()
                att_ids = []
                for att in rjs:
                    try:
                        _logger.info("att:")
                        _logger.info(att)
                        _logger.info(att['id'])
                        attrs = att_obj.search( [ ('att_id','like',str(att['id'])) ] )
                        attrs_field = {
                            'name': att['name'],
                            'value_type': att['value_type'],
                            'hidden': ('hidden' in att['tags']),
                            'multivalued': ( 'multivalued' in att['tags']),
                            'variation_attribute': ('variation_attribute' in att['tags']) | ('allow_variations' in att['tags']),
                            'required': ('catalog_required' in att['tags'])
                        }

                        if ('tooltip' in att):
                            attrs_field['tooltip'] = att['tooltip']

                        if ('values' in att):
                            attrs_field['values'] = json.dumps(att['values'])

                        if ('type' in att):
                            attrs_field['type'] = att['type']

                        if (len(attrs)):
                            attrs[0].write(attrs_field)
                            attrs = attrs[0]
                            att_ids.append(attrs.id)
                        else:
                            _logger.info("Add attribute")
                            attrs_field['att_id'] = att['id']
                            _logger.info(attrs_field)
                            attrs = att_obj.create(attrs_field)
                            att_ids.append(attrs[0].id)

                        if (attrs.id):
                            if (company.mercadolibre_product_attribute_creation!='manual'):
                                #primero que coincida todo
                                prod_attrs = prod_att_obj.search( [ ('name','like',att['name']),
                                                                    ('meli_default_id_attribute','=',attrs[0].id) ] )
                                if (len(prod_attrs)==0):
                                    #que solo coincida el id
                                    prod_attrs = prod_att_obj.search( [ ('meli_default_id_attribute','=',attrs[0].id) ] )

                                if (len(prod_attrs)==0):
                                    #que coincida el nombre al menos
                                    prod_att_obj.search( [ ('name','like',att['name']) ] )

                                #if (len(prod_attrs)==0):
                                    #que coincida el meli_id!!
                                    #prod_att_obj.search( [ ('meli_id','like',att['id']) ] )

                                prod_att = {
                                    'name': att['name'],
                                    'create_variant': default_create_variant,
                                    'meli_default_id_attribute': attrs[0].id,
                                    #'meli_id': attrs[0].att_id
                                }
                                if (len(prod_attrs)>=1):
                                    #tomamos el primero
                                    _logger.error("Atención multiples atributos asignados!")
                                    #prod_attrs = prod_attrs[0]
                                    for prod_attr in prod_attrs:
                                        prod_att['create_variant'] = prod_attr.create_variant
                                        prod_attr.write(prod_att)
                                    #if (len(prod_attrs)==1):
                                    #    if (prod_attrs.id):
                                    #        prod_att['create_variant'] = prod_attrs.create_variant
                                    #        prod_att_obj.write(prod_att)
                                else:
                                    prod_attrs = prod_att_obj.create(prod_att)

                    except Exception as e:
                        _logger.info("att:")
                        _logger.info(att)
                        _logger.info("Exception")
                        _logger.info(e, exc_info=True)

                #_logger.info("Add att_ids")
                #_logger.info(att_ids)
                category.write({'meli_category_attribute_ids': [(6, 0, att_ids)] })

                response_cat = meli.get("/categories/"+str(category.meli_category_id), {'access_token':meli.access_token})
                rjson_cat = response_cat.json()
                category.is_branch = ( "children_categories" in rjson_cat and len(rjson_cat["children_categories"])>0 )

        return {}

    def action_import_father_category( self ):
        for obj in self:
            if (obj.meli_father_category_id):
                try:
                    obj.meli_father_category = obj.import_category(obj.meli_father_category_id)
                except:
                    _logger.error("No se pudo importar: "+ str(obj.meli_father_category_id))

    def import_category(self, category_id ):
        company = self.env.user.company_id

        warningobj = self.env['warning']
        category_obj = self.env['mercadolibre.category']

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)
        ml_cat_id = None
        if (category_id):
            is_branch = False
            father = None
            response_cat = meli.get("/categories/"+str(category_id), {'access_token':meli.access_token})
            rjson_cat = response_cat.json()
            is_branch = ("children_categories" in rjson_cat and len(rjson_cat["children_categories"])>0)

            ml_cat_id = category_obj.search([('meli_category_id','=',category_id)])
            if (len(ml_cat_id) and ml_cat_id[0].id and is_branch==False):
                #_logger.info("category exists!" + str(ml_cat_id))
                ml_cat_id._get_attributes()
            else:
                _logger.info("Creating category: " + str(category_id))
                #https://api.mercadolibre.com/categories/MLA1743
                #_logger.info("category:" + str(rjson_cat))
                fullname = ""
                if ("path_from_root" in rjson_cat):
                  path_from_root = rjson_cat["path_from_root"]
                  for path in path_from_root:
                    fullname = fullname + "/" + path["name"]
                  if (len(rjson_cat["path_from_root"])>1):
                      father_ml_id = rjson_cat["path_from_root"][len(rjson_cat["path_from_root"])-2]["id"]
                      father_id = category_obj.search([('meli_category_id','=',father_ml_id)])
                      if (father_id and len(father_id)):
                          father = father_id[0]


                #fullname = fullname + "/" + rjson_cat['name']
                #_logger.info( "category fullname:" + str(fullname) )
                _logger.info(fullname)
                cat_fields = {
                    'name': fullname,
                    'meli_category_id': ''+str(category_id),
                    'is_branch': is_branch,
                    'meli_father_category': father
                }
                ml_cat_id = category_obj.create((cat_fields))
                if (ml_cat_id.id and is_branch==False):
                  ml_cat_id._get_attributes()

        return ml_cat_id


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

            _logger.info( "response.content:", response.content )

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


    name = fields.Char('Name',index=True)
    is_branch = fields.Boolean('Rama (no hoja)',index=True)
    meli_category_id = fields.Char('Category Id',index=True)
    meli_father_category = fields.Many2one('mercadolibre.category',string="Padre",index=True)
    meli_father_category_id = fields.Char(string='Father ML Id',compute=_get_category_url,index=True)
    public_category_id = fields.Integer(string='Public Category Id',index=True)

    #public_category = fields.Many2one( "product.category.public", string="Product Website category default", help="Select Public Website category for this ML category ")
    meli_category_attributes = fields.Char(compute=_get_attributes,  string="Mercado Libre Category Attributes")
    meli_category_url = fields.Char(compute=_get_category_url, string="Mercado Libre Category Url")
    meli_category_attribute_ids = fields.Many2many("mercadolibre.category.attribute",string="Attributes")

    meli_category_settings = fields.Char(string="Settings")
    meli_setting_minimum_price = fields.Float(string="Minimum price")
    meli_setting_maximum_price = fields.Float(string="Maximum price")


mercadolibre_category()
