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

from odoo import fields, osv, models, api, Command, _
import logging
_logger = logging.getLogger(__name__)

from .meli_oerp_config import *
from .warning import warning

import requests
#from ..melisdk.meli import Meli
import json
import math

from .versions import *

#     "channels": [
#  "marketplace", --- No aparece sin token propietario
#   "mshops" --- No aparece sin token propietario
#],
class meli_channel_mkt(models.Model):

    _name = "meli.channel.mkt"
    _description = "MercadoLibre Channel Marketplace"


    name = fields.Char(string="Name",index=True)
    code = fields.Char(string="Code",index=True)



class mercadolibre_category_import(models.TransientModel):
    _name = "mercadolibre.category.import"
    _description = "Wizard de Importacion de Categoria desde MercadoLibre"

    meli_charts = fields.Boolean(string="Importar Guias",help="Importar las guias de esta categoria, complete el genero y la marca",default=False)
    meli_gender = fields.Char(string="Genero (GENDER)",help="Completar para importar las guias",default="")
    meli_brand = fields.Char(string="Marca (BRAND) Category ID",help="Completar para importar las guias",default="")

    def _get_default_meli_category_id(self, context=None):
        context = context or self.env.context
        company = self.env.user.company_id
        #_logger.info("_get_default_meli_category_id")
        #_logger.info(context)

    def _get_default_meli_recursive_import(self, context=None):
        context = context or self.env.context
        company = self.env.user.company_id
        #_logger.info("_get_default_meli_recursive_import")
        #_logger.info(context)
        return False

    meli_category_id = fields.Char(string="MercadoLibre Category ID",help="MercadoLibre Category ID (ML????????)",default=_get_default_meli_category_id)
    meli_category_id_sel = fields.Many2one("mercadolibre.category", string="MercadoLibre Category",help="MercadoLibre Category")
    meli_recursive_import = fields.Boolean(string="Recursive Import",help="Importar todas las subramas",default=_get_default_meli_recursive_import)

    def meli_category_import(self, context=None):

        context = context or self.env.context
        company = self.env.user.company_id
        mlcat_ids = ('active_ids' in context and context['active_ids']) or []
        mlcat_obj = self.env['mercadolibre.category']

        warningobj = self.env['meli.warning']

        meli = self.env["mercadolibre.category"].get_meli()
        if meli and meli.need_login():
            return meli.redirect_login()

        #_logger.info("Meli Category Import Wizard")
        #_logger.info(context)
        if ( self.meli_category_id_sel and self.meli_charts):
            #buscar una guia de talles ok
            rjson_charts = self.meli_category_id_sel.get_search_chart( meli=meli, brand=self.meli_brand, gender=self.meli_gender)
            _logger.info("rjson_charts: " +str(rjson_charts))
            if rjson_charts:
                rjson_charts_a = "charts" in rjson_charts and rjson_charts["charts"]
                for charts in rjson_charts_a:
                    _logger.info("charts: " +str(charts))
                    self.env["mercadolibre.grid.chart"].create_chart(charts)
        else:
            if ( self.meli_category_id):
                #_logger.info("Import single category: "+str(self.meli_category_id))
                catid = self.env["mercadolibre.category"].import_all_categories( self.meli_category_id, self.meli_recursive_import )
            else:
                #_logger.info("Importing active categories: "+str(mlcat_ids))
                for ml_cat_id in mlcat_ids:
                    #_logger.info("Importing single: "+str(ml_cat_id))
                    ml_cat = mlcat_obj.browse([ml_cat_id])
                    if ml_cat:
                        meli_category_id = ml_cat.meli_category_id
                        catid = self.env["mercadolibre.category"].import_all_categories( meli_category_id, self.meli_recursive_import )


class product_public_category(models.Model):

    _inherit="product.public.category"

    mercadolibre_category = fields.Many2one( "mercadolibre.category", string="Mercado Libre Category")


class mercadolibre_category_attribute(models.Model):
    _name = "mercadolibre.category.attribute"
    _description = "MercadoLibre Attribute"

    cat_id = fields.Char(string="Category Id (ML)",index=True)
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
    product_attributes = fields.One2many("product.attribute","meli_default_id_attribute",string="Atributos de odoo asociados")
    products_to_fix = fields.Many2many("product.template",string="Products need fixing or reimport")

    def fix_attribute_create_variant( self ):
        #_logger.info("fix_attribute_create_variant, convierte de no crear variant a instantaneo")
        #Solo borra las lineas de valores de atributos de todos los productos si el atributo esta en modo create_variant
        meli_att_creates_variant = not self.hidden and self.variation_attribute
        #_logger.info("fix_attribute_create_variant, CONVERTIR SE DEBE")

        if meli_att_creates_variant:
            #_logger.info("fix_attribute_create_variant, convirtiendo")
            for att in self.product_attributes:
                if (att.create_variant=="no_variant"):
                    #eliminar el atributo de todos los productos
                    for product_tmpl in att.product_tmpl_ids:
                        for att_line in product_tmpl.attribute_line_ids:
                            if att_line.attribute_id.id==att.id:

                                try:
                                    att_line.unlink()
                                    self.products_to_fix = [(4,product_tmpl.id)]
                                    self._cr.commit();
                                except:
                                    pass;

                                break;
                    if "number_related_products" in  att._fields and att.number_related_products==0:
                        #_logger.info("fix_attribute_create_variant, convirtiendo a always")
                        try:
                            att.create_variant = "always"
                        except Exception as E:
                            _logger.error("Error intentando convertir: "+str(E))
                            pass;


    def fix_products_reimport( self ):
        #_logger.info("fix_products_reimport, reimportar")

        product_ids = self.products_to_fix.mapped('id')
        product_obj = self.env["product.template"]
        Autocommit(self, False)

        for product_tmpl_id in product_ids:

            product_tmpl = product_obj.browse(product_tmpl_id)

            if product_tmpl.meli_pub:

                for att_line in product_tmpl.attribute_line_ids:
                    if (att_line.attribute_id.create_variant=='always' and
                        att_line.attribute_id.id in self.product_attributes.mapped('id')):
                        #_logger.info("Ok product fixed removing from list: "+str(product_tmpl.name))
                        self.products_to_fix = [(3,product_tmpl.id)]
                        continue;

                #actualizar variantes:
                try:
                    #_logger.info("Ok re-importando: "+str(product_tmpl.name))
                    product_tmpl.product_template_update()
                except:
                    _logger.error("Error importando")

                    #archivar variantes:
                    #if E.
                    #for var in product_tmpl.product_variant_ids:
                    #    var.active = False

                    break;

                for att_line in product_tmpl.attribute_line_ids:

                    if (att_line.attribute_id.create_variant=='always' and
                        att_line.attribute_id.id in self.product_attributes.mapped('id')):
                        #_logger.info("Ok product fixed removing from list: "+str(product_tmpl.name))
                        self.products_to_fix = [(3,product_tmpl.id)]
                        continue;

                self._cr.commit()


class product_attribute(models.Model):

    _inherit="product.attribute"

    mercadolibre_attribute_id = fields.Many2one( "mercadolibre.category.attribute", string="MercadoLibre Attribute")


class mercadolibre_category(models.Model):
    _name = "mercadolibre.category"
    _description = "Categories of MercadoLibre"

    def get_meli( self, meli=None ):

        #_logger.info("get_meli")
        #_logger.info(self)
        #_logger.info(meli)
        #_logger.info(str(meli and meli.seller_id))
        #_logger.info(str(meli and meli.client_id))
        #_logger.info(str(meli and meli.meli_login_id))

        if meli:
            return meli

        company = self.env.user.company_id

        if "mercadolibre_connections" in company:
            connacc = company.mercadolibre_connections and company.mercadolibre_connections[0]
            config = (connacc and connacc.configuration) or company
            meli = self.env['meli.util'].get_new_instance( config, connacc)
        else:
            meli = self.env['meli.util'].get_new_instance( company )

        return meli


    def create_ecommerce_category(self, category_id, meli=None, create_missing_website=True ):

        #_logger.info("Creating Ecommerce Category "+str(category_id))
        if not ('product.public.category' in self.env):
            return False

        www_cats = self.env['product.public.category']

        if not meli or not www_cats or not category_id:
            return False

        response_cat = meli.get("/categories/"+str(category_id), {'access_token':meli.access_token})
        rjson_cat = response_cat and response_cat.json()

        #_logger.info( "category:" + str(rjson_cat) )
        fullname = ""

        if (rjson_cat and "path_from_root" in rjson_cat):

            path_from_root = rjson_cat["path_from_root"]
            p_id = False

            #pdb.set_trace()
            for path in path_from_root:

                fullname = fullname + "/" + path["name"]

                if (create_missing_website and www_cats ):
                    if www_cats!=False:
                        www_cat_id = www_cats.search([('name','=',path["name"])]).id
                        if www_cat_id==False:
                            www_cat_fields = {
                              'name': path["name"],
                              #'parent_id': p_id,
                              #'sequence': 1
                            }
                            if p_id:
                                www_cat_fields['parent_id'] = p_id
                            www_cat_id = www_cats.create((www_cat_fields)).id
                            if www_cat_id:
                               #_logger.info("Website Category created:"+fullname)
                                pass;

                        p_id = www_cat_id
            return p_id
        return False

    def meli_get_category( self, category_id, meli=None, create_missing_website=False, config=None ):

        company = self.env.user.company_id
        www_cats = False
        if 'product.public.category' in self.env:
            www_cats = self.env['product.public.category']


        mlcatid = False
        www_cat_id = False

        if not meli:
            meli = self.get_meli(meli=meli)
            if meli.need_login():
                return mlcatid, www_cat_id


        ml_cat = self.env['mercadolibre.category'].search([('meli_category_id','=',category_id)],limit=1)
        if not ml_cat:
            ml_cat = self.import_category(category_id=category_id, meli=meli, create_missing_website=create_missing_website)

        ml_cat_id = ml_cat and ml_cat.id
        if (ml_cat_id):
            #_logger.info( "category exists!" + str(ml_cat_id) )
            mlcatid = ml_cat_id
            if www_cats:
                www_cat_id = ml_cat.public_category_id

        if not www_cat_id and ml_cat_id:
            #_logger.info( "Creating category: " + str(category_id) )
            #https://api.mercadolibre.com/categories/MLA1743
            www_cat_id = self.create_ecommerce_category( category_id=category_id, meli=meli, create_missing_website=create_missing_website )

            if www_cat_id:
                p_cat_id = www_cats.search([('id','=',www_cat_id)],limit=1)
                if (len(p_cat_id)):
                    cat_fields['public_category_id'] = www_cat_id
                    cat_fields['public_category'] = p_cat_id.id
                #cat_fields['public_category'] = p_cat_id

        return mlcatid, www_cat_id

    def _get_category_url( self, meli=None ):
        company = self.env.user.company_id

        warningobj = self.env['meli.warning']
        category_obj = self.env['mercadolibre.category']
        att_obj = self.env['mercadolibre.category.attribute']
        prod_att_obj = self.env['product.attribute']

        meli = self.get_meli(meli=meli)

        for category in self:
            if (category and category.meli_category_id):
                #_logger.info("_get_category_url:"+str(category.meli_category_id))
                response_cat = meli.get("/categories/"+str(category.meli_category_id), {'access_token':meli.access_token})
                rjson_cat = response_cat.json()
                category.is_branch = ( "children_categories" in rjson_cat and len(rjson_cat["children_categories"])>0 )
                category.meli_category_url = "https://api.mercadolibre.com/categories/"+str(category.meli_category_id)
                category.meli_category_attributes = "https://api.mercadolibre.com/categories/"+str(category.meli_category_id)+"/attributes"
                #_logger.info(rjson_cat["path_from_root"])
                if (len(rjson_cat["path_from_root"])>=2):
                    fid = int(len(rjson_cat["path_from_root"])-2)
                    #_logger.info(fid)
                    #_logger.info(rjson_cat["path_from_root"][fid]["id"])
                    category.meli_father_category_id = rjson_cat["path_from_root"][fid]["id"]


    def get_attributes( self, meli=None ):
        for cat in self:
            cat._get_attributes(meli=meli)

    def _get_attributes( self, meli=None ):

        company = self.env.user.company_id

        warningobj = self.env['meli.warning']
        category_obj = self.env['mercadolibre.category']
        att_obj = self.env['mercadolibre.category.attribute']
        prod_att_obj = self.env['product.attribute']

        meli = self.get_meli(meli=meli)

        for category in self:
            if (category.meli_category_id
                and category.is_branch==False
                and ( 1==1 or category.meli_category_attribute_ids==None or len(category.meli_category_attribute_ids)==0 )):
                #_logger.info("_get_attributes:"+str(category.meli_category_id))
                category.meli_category_attributes = "https://api.mercadolibre.com/categories/"+str(category.meli_category_id)+"/attributes"
                resp = meli.get("/categories/"+str(category.meli_category_id)+"/attributes", {'access_token':meli.access_token})
                rjs = resp.json()
                att_ids = []
                for att in rjs:
                    try:
                        #_logger.info("att:")
                        #_logger.info(att)
                        #_logger.info(att['id'])
                        attrs = att_obj.search( [ ('att_id','=',str(att['id'])),('name','=ilike',str(att['name'])) ] )
                        #attrs = att_obj.search( [ ('cat_id','=',False),('att_id','=',str(att['id'])),('name','=',str(att['name'])) ] )
                        attrs_field = {
                            'name': att['name'],
                            #'cat_id': str(category.meli_category_id),
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
                            #_logger.info("Add attribute")
                            attrs_field['att_id'] = att['id']
                            #_logger.info(attrs_field)
                            attrs = att_obj.create(attrs_field)
                            att_ids.append(attrs[0].id)

                        if (attrs.id):
                            if (company.mercadolibre_product_attribute_creation!='manual'):
                                #primero que coincida todo
                                prod_attrs = prod_att_obj.search( [ ('name','=ilike',att['name']),
                                                                    ('meli_default_id_attribute','=',attrs[0].id) ] )
                                if (len(prod_attrs)==0):
                                    #que solo coincida el id
                                    prod_attrs = prod_att_obj.search( [ ('meli_default_id_attribute','=',attrs[0].id) ] )

                                if (len(prod_attrs)==0):
                                    #que coincida el nombre al menos
                                    prod_attrs = prod_att_obj.search( [ ('name','=ilike',att['name']) ] )

                                #if (len(prod_attrs)==0):
                                    #que coincida el meli_id!!
                                    #prod_att_obj.search( [ ('meli_id','like',att['id']) ] )

                                prod_att = {
                                    'name': att['name'],
                                    'create_variant': self.env["product.attribute"].meli_default_create_variant(meli_attribute=attrs_field),
                                    'meli_default_id_attribute': attrs[0].id,
                                    #'meli_id': attrs[0].att_id
                                }
                                #_logger.info("prod_att:"+str(prod_att))
                                if (len(prod_attrs)>=1):
                                    #tomamos el primero
                                    #_logger.error("Atención multiples atributos asignados! Para el atributo: "+str(prod_attrs[0] and prod_attrs[0].name))

                                    #prod_attrs = prod_attrs[0]
                                    for prod_attr in prod_attrs:
                                        #prod_attr['create_variant'] = prod_att.create_variant
                                        try:
                                            prod_attr.write(prod_att)
                                        except Exception as E:
                                            _logger.error("Error cambiando atributo: "+str(prod_attr))
                                            _logger.info(E, exc_info=True)
                                    #if (len(prod_attrs)==1):
                                    #    if (prod_attrs.id):
                                    #        prod_att['create_variant'] = prod_attrs.create_variant
                                    #        prod_att_obj.write(prod_att)
                                else:
                                    prod_attrs = prod_att_obj.create(prod_att)

                    except Exception as e:
                        #_logger.info("att:")
                        #_logger.info(att)
                        _logger.info("Exception")
                        _logger.info(e, exc_info=True)
                        pass;

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

    def import_category(self, category_id, meli=None, create_missing_website=False ):

       #_logger.info("Import Category "+str(category_id))
        company = self.env.user.company_id

        warningobj = self.env['meli.warning']
        category_obj = self.env['mercadolibre.category']
        www_cats = None
        if 'product.public.category' in self.env:
            www_cats = self.env['product.public.category']

        meli = self.get_meli(meli=meli)

        config = company
        create_missing_website = create_missing_website or config.mercadolibre_create_website_categories
        ml_cat_id = None
        www_cat_id = None
        if (category_id):
            is_branch = False
            father = None
            response_cat = meli.get("/categories/"+str(category_id), {'access_token':meli.access_token})
            rjson_cat = response_cat.json()
            is_branch = ("children_categories" in rjson_cat and len(rjson_cat["children_categories"])>0)

            ml_cat_id = category_obj.search([('meli_category_id','=',category_id)],limit=1)
            if (len(ml_cat_id) and ml_cat_id[0].id and is_branch==False):
                #_logger.info("category exists!" + str(ml_cat_id))
                ml_cat_id._get_attributes(meli=meli)

            if not ml_cat_id:
               #_logger.info("Creating category: " + str(category_id))
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
                #_logger.info(fullname)
                cat_fields = {
                    'name': fullname,
                    'meli_category_id': ''+str(category_id),
                    'is_branch': is_branch,
                    #'meli_father_category': father
                }
                cat_fields["catalog_domain"] = "settings" in rjson_cat and "catalog_domain" in rjson_cat["settings"] and rjson_cat["settings"]["catalog_domain"]
                cat_fields["data_json"] = json.dumps(rjson_cat)
                cat_fields["catalog_domain_json"] = self.get_catalog_domain_json(catalog_domain=cat_fields["catalog_domain"],meli=meli)
                if (father and father.id):
                    cat_fields['meli_father_category'] = father.id
                #_logger.info(cat_fields)
                ml_cat_id = ml_cat_id.create((cat_fields))
                if (ml_cat_id.id and is_branch==False):
                  ml_cat_id._get_attributes(meli=meli)
                  ml_cat_id.get_search_chart_filters(meli=meli)

            if (ml_cat_id):
               #_logger.info("MercadoLibre Category Ok: "+str(ml_cat_id)+" www_cats:"+str(www_cats))

                if 'product.public.category' in self.env:
                    www_cat_id = ml_cat_id.public_category_id

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
                cat_fields = {
                    'name': fullname,
                    'meli_category_id': ''+str(category_id),
                    'is_branch': is_branch,
                    #'meli_father_category': father
                }
                cat_fields["catalog_domain"] = "settings" in rjson_cat and "catalog_domain" in rjson_cat["settings"] and rjson_cat["settings"]["catalog_domain"]
                cat_fields["data_json"] = json.dumps(rjson_cat)
                cat_fields["catalog_domain_json"] = self.get_catalog_domain_json(catalog_domain=cat_fields["catalog_domain"],meli=meli)

                if (father and father.id):
                    cat_fields['meli_father_category'] = father.id
                #_logger.info(cat_fields)
                ml_cat_id.write((cat_fields))

                if (ml_cat_id.id and is_branch==False):
                  ml_cat_id._get_attributes()
                  ml_cat_id.get_search_chart_filters(meli=meli)

            if not www_cat_id and create_missing_website and 'product.public.category' in self.env:
                #_logger.info("Ecommerce category missing")
                #_logger.info( "Creating category: " + str(category_id) )
                #https://api.mercadolibre.com/categories/MLA1743
                www_cat_id = self.create_ecommerce_category( category_id=category_id, meli=meli, create_missing_website=create_missing_website )

            if www_cat_id:
                wcat = www_cats.browse([www_cat_id])
                #_logger.info("Ecommerce category found: "+str(www_cat_id)+" "+str(wcat))
                if wcat and not wcat.mercadolibre_category:
                    #_logger.info("Assigning mercadolibre_category "+str(wcat)+" to "+str(ml_cat_id))
                    wcat.mercadolibre_category = ml_cat_id
                if wcat and not ml_cat_id.public_category:
                    ml_cat_id.public_category = wcat

        return ml_cat_id


    def import_all_categories(self, category_root, recursive_import=False, meli=None ):

        #_logger.info("Importing all categories from root: "+str(category_root))

        company = self.env.user.company_id

        warningobj = self.env['meli.warning']
        category_obj = self.env['mercadolibre.category']

        meli = self.get_meli(meli=meli)

        RECURSIVE_IMPORT = recursive_import or company.mercadolibre_recursive_import

        if (category_root):
            response = meli.get("/categories/"+str(category_root), {'access_token':meli.access_token} )

            rjson = response and response.json()
            #_logger.info( "response:" + str(rjson) )
            if (rjson and "name" in rjson):

                category_obj.import_category(category_id=category_root,meli=meli)

                # en el html deberia ir el link  para chequear on line esa categoría corresponde a sus productos.
                warningobj.info( title='MELI WARNING', message="Preparando importación de todas las categorías en "+str(category_root), message_html=response )
                if ("children_categories" in rjson):
                    #empezamos a iterar categorias
                    for child in rjson["children_categories"]:
                        ml_cat_id = child["id"]
                        if (ml_cat_id):
                            category_obj.import_category(category_id=ml_cat_id,meli=meli)
                            if (RECURSIVE_IMPORT):
                                category_obj.import_all_categories(category_root=ml_cat_id)


    name = fields.Char('Name',index=True)
    is_branch = fields.Boolean('Rama (no hoja)',index=True)
    meli_category_id = fields.Char('Category Id',index=True)
    meli_father_category = fields.Many2one('mercadolibre.category',string="Padre",index=True)
    meli_father_category_id = fields.Char(string='Father ML Id',compute=_get_category_url,index=True)
    public_category_id = fields.Integer(string='Public Category Id',index=True)
    public_category = fields.Many2one('product.public.category',string='Public Category')
    public_categories = fields.One2many('product.public.category','mercadolibre_category',string='Public Categories')


    #public_category = fields.Many2one( "product.category.public", string="Product Website category default", help="Select Public Website category for this ML category ")
    meli_category_attributes = fields.Char(compute=_get_attributes,  string="Mercado Libre Category Attributes")
    meli_category_url = fields.Char(compute=_get_category_url, string="Mercado Libre Category Url")
    meli_category_attribute_ids = fields.Many2many("mercadolibre.category.attribute",string="Attributes")


    meli_category_settings = fields.Char(string="Settings")
    meli_setting_minimum_price = fields.Float(string="Minimum price")
    meli_setting_maximum_price = fields.Float(string="Maximum price")
    meli_setting_minimum_qty = fields.Float(string="Minimum qty")
    meli_setting_maximum_qty = fields.Float(string="Maximum qty")

    #description_template = fields.Many2one( string="Plantilla para descripcion del producto", "")

    #TODO: fee for each listing type
    # https://api.mercadolibre.com/sites/MLM/listing_prices?price=1#options
    #
    # check: https://www.mercadolibre.com.mx/ayuda/Costos-de-vender-un-producto_870
    #ver tambien: https://www.mercadolibre.com.mx/ayuda/Tarifas-y-facturacion_1044
    # https://api.mercadolibre.com/sites/MLM/listing_types#json
    def get_catalog_domain_json( self, catalog_domain=None, meli=None ):
        company = self.env.user.company_id
        meli = self.get_meli(meli=meli)
        catalog_domain_json = ""
        if catalog_domain:
            response_dom = meli.get("/catalog_domains/"+str(catalog_domain), {'access_token':meli.access_token})
            #_logger.info("response_dom para "+str(catalog_domain)+": "+str(response_dom))
            rjson_dom = response_dom and response_dom.json()
            if rjson_dom:
                catalog_domain_json = json.dumps(rjson_dom)

        return catalog_domain_json


    catalog_domain = fields.Char(string="Domain Id", index=True)
    def _catalog_domain_link(self):
        for cat in self:
            cat.catalog_domain_link = (cat.catalog_domain and "https://api.mercadolibre.com/catalog_domains/"+str(cat.catalog_domain)) or ""

    def get_search_chart( self, brand=None, gender=None, model=None, meli=None ):
        ##https://api.mercadolibre.com/catalog/charts/search
        company = self.env.user.company_id
        meli = self.get_meli(meli=meli)
        cat = self
        #https://api.mercadolibre.com/catalog/charts/search
        params = {
            'access_token': meli.access_token
        }
        site_id = company._get_ML_sites(meli=meli)
        body = {
            'site_id': site_id,
            'domain_id': str(cat.catalog_domain).replace(site_id+str("-"),""),
            'seller_id': int(meli and meli.seller_id),
            'attributes': []
            }

        if brand:
            body["attributes"].append({
                "id": "BRAND",
               "values": [
                   {
                       "name": str(brand)
                   }
               ]

            })

        if gender:
            body["attributes"].append({
                "id": "GENDER",
               "values": [
                   {
                       "name": str(gender)
                   }
               ]
            })

        if model:
            body["attributes"].append({
                "id": "MODEL",
               "values": [
                   {
                       "name": str(model)
                   }
               ]
            })


        #_logger.info("params:"+str(params))
        response_chart = meli.post( path="/catalog/charts/search", body=body, params=params )
        #_logger.info("response_chart para "+str(cat.catalog_domain)+": "+str(response_chart))
        rjson_chart = response_chart and response_chart.json()
        #_logger.info("rjson_chart para "+str(cat.catalog_domain)+": "+str(rjson_chart))

        return rjson_chart


    def get_search_chart_filters( self, meli=None ):
        cat = self
        rjson_chart = cat.get_search_chart(meli=meli)
        if rjson_chart:
            cat.catalog_domain_chart_result = rjson_chart and json.dumps(rjson_chart)
            cat.catalog_domain_chart_active = (( not ("domain_not_active" in cat.catalog_domain_chart_result)) and
                                                "filters_validation_error" in cat.catalog_domain_chart_result)

    catalog_domain_link = fields.Char(string="Domain Id Link",compute=_catalog_domain_link)
    catalog_domain_json = fields.Text(string="Domain id json")
    catalog_domain_chart_active = fields.Boolean(string="Domain Charts active", index=True,readonly=True)
    catalog_domain_chart_result = fields.Text(string="Domain Charts result")


    @api.depends('catalog_domain_link', 'catalog_domain_json', 'catalog_domain_chart_active', 'catalog_domain_chart_result')
    def _compute_catalog_domain_chart_ids(self):
        meli = self.get_meli(meli=None)
        for meli_cat in self:
            if meli_cat.catalog_domain:
                company = self.env.user.company_id
                site_id = company._get_ML_sites(meli=meli)
                cat_domain = str( meli_cat.catalog_domain ).replace( str(site_id) + str("-") , "" )
                domain_charts = self.env['mercadolibre.grid.chart'].search([('domain_id','ilike',cat_domain)])
                domain_charts_ids_command = [Command.clear()]
                if domain_charts:
                    domain_charts_ids_command += [Command.link(grid_chart.id) for grid_chart in domain_charts]
                meli_cat.catalog_domain_chart_ids = domain_charts_ids_command
            else:
                meli_cat.catalog_domain_chart_ids = False
            # Uses move._origin.id to handle records in edition/existing records and 0 for new records


    catalog_domain_chart_ids = fields.Many2many(comodel_name='mercadolibre.grid.chart', compute='_compute_catalog_domain_chart_ids')

    data_json = fields.Text(string="Data json")

    _sql_constraints = [
    	('unique_meli_category_id','unique(meli_category_id)','Meli Category id already exists!'),
    ]


class mercadolibre_grid_value(models.Model):
    _name = "mercadolibre.grid.value"
    _description = "Valor de Guia de talles de MercadoLibre"

    meli_id = fields.Char(string="Id",required=True,index=True)
    name = fields.Char(string="Nombre",index=True)
    value = fields.Char(string="Value",index=True)
    att_id = fields.Many2one("mercadolibre.grid.attribute", string="Attribute")


    def prepare_vals( self, djson ):
        fields = {
            "meli_id": djson["id"],
            "name": json.dumps(djson["name"]),
        }

class mercadolibre_grid_attribute(models.Model):
    _name = "mercadolibre.grid.attribute"
    _description = "Atributo de Guia de talles de MercadoLibre"

    meli_id = fields.Char(string="Id",required=True,index=True)
    name = fields.Char(string="Nombre",index=True)
    values = fields.One2many("mercadolibre.grid.value", "att_id", string="Values")

    def prepare_vals( self, djson ):
        fields = {
            "meli_id": djson["id"],
            "name": json.dumps(djson["name"]),
        }

class mercadolibre_grid_attribute_line(models.Model):
    _name = "mercadolibre.grid.attribute.line"
    _description = "Linea de atributo de Guia de talles de MercadoLibre"

    grid_chart_id = fields.Many2one("mercadolibre.grid.chart", string="row id")
    att_id = fields.Many2one("mercadolibre.grid.attribute", string="Attribute")
    val_id = fields.Many2one("mercadolibre.grid.value", string="Values")

    def prepare_vals( self, djson ):
        fields = {
            #"grid_chart_id": djson["id"],
            #"att_id":
            #"val_id":
        }
        return fields

class mercadolibre_grid_row_col(models.Model):
    _name = "mercadolibre.grid.row.col"
    _description = "Col de atributo de Guia de talles de MercadoLibre"

    grid_row_id = fields.Many2one("mercadolibre.grid.row", string="Row id")
    #att_id = fields.Many2one("mercadolibre.grid.attribute", string="Attribute")
    #val_id = fields.Many2one("mercadolibre.grid.value", string="Values")
    att_id = fields.Char(string="Id",required=True,index=True)
    name = fields.Char(string="Name",required=True,index=True)
    value = fields.Char(string="Value",required=True,index=True)
    number = fields.Char(string="Number",required=False,index=True)
    unit = fields.Char(string="Unit",required=False,index=True)

    def name_get(self):
        """Override because in general the name of the value is confusing if it
        is displayed without the name of the corresponding attribute.
        Eg. on product list & kanban views, on BOM form view

        However during variant set up (on the product template form) the name of
        the attribute is already on each line so there is no need to repeat it
        on every value.
        """
        #if not self._context.get('show_attribute', True):
        #    return super(mercadolibre_grid_row_col, self).name_get()
        return [(col.att_id, "%s: %s" % (col.name, col.value)) for col in self]

    def prepare_vals( self, djson ):

        number_val = "values" in djson and djson["values"] and djson["values"] and djson["values"][0]
        number_struc = number_val and "struct" in number_val and number_val["struct"]

        val_number = number_struc and "number" in number_struc and number_struc["number"]
        val_unit = number_struc and "unit" in number_struc and number_struc["unit"]
        val_name = number_val and "name" in number_val and number_val["name"]
        if not val_unit or not val_number:
            #_logger.info("prepare_vals grid_row_col > miss "+str(djson))
            pass;

        fields = {
            "att_id": djson["id"],
            "name": djson["name"],
            "value": val_name,
            "number": val_number,
            "unit": val_unit
        }
        return fields

class mercadolibre_grid_row(models.Model):
    _name = "mercadolibre.grid.row"
    _description = "Fila de guia de talles de MercadoLibre"

    row_id = fields.Char(string="Id",required=True,index=True)
    grid_chart_id = fields.Many2one("mercadolibre.grid.chart", string="Chart id")
    attribute_values = fields.One2many("mercadolibre.grid.row.col", "grid_row_id", string="Attributes Values")

    def prepare_vals( self, djson ):
        fields = {
            "row_id": djson["id"],
            #"grid_chart_id": self.get_grid_chart_id(),
            "attribute_values": []
        }
        row_att_arrs = []
        row_att_arrs.append((5,0,0))
        for row_att in djson["attributes"]:
            att_field = self.env["mercadolibre.grid.row.col"].prepare_vals(row_att)
            row_att_arrs.append( (0, 0, att_field) )

        fields["attribute_values"] = row_att_arrs
        return fields

class mercadolibre_grid_chart(models.Model):
    _name = "mercadolibre.grid.chart"
    _description = "Guia de talles de MercadoLibre"

    meli_id = fields.Char(string="Id de guia de talle",required=True,index=True)
    site_id = fields.Char(string="ML Site Id",index=True)
    domain_id = fields.Char(string="Dominio", index=True)

    @api.depends('site_id','domain_id')
    def _meli_domain_id( self ):
        for gchart in self:
            if not gchart.site_id:
                gchart.site_id = "MLA"
            gchart.meli_domain_id = str(gchart.site_id)+str("-")+str(gchart.domain_id)

    meli_domain_id = fields.Char(string="ML Dominio", compute=_meli_domain_id, index=True, store=True)
    name = fields.Char(string="Nombre de la guia de talles", index=True)
    type = fields.Char(string="Tipo de la guia de talles", index=True)
    main_attribute_id = fields.Char( string="Atributo principal de la guia de talles" )
    data_json = fields.Text( string="Data json" )
    attributes = fields.One2many( "mercadolibre.grid.attribute.line", "grid_chart_id", string="Attributes" )
    rows = fields.One2many( "mercadolibre.grid.row", "grid_chart_id", string="Rows" )

    def prepare_vals( self, djson ):
        #_logger.info("prepare_vals djson:"+str(djson))
        fields = {
            "meli_id": djson["id"],
            "name": json.dumps(djson["names"]),
            "type": djson["type"],
            "domain_id": djson["domain_id"],
            "site_id": djson["site_id"],
            "main_attribute_id": djson["main_attribute_id"],
            "data_json": json.dumps(djson),
        }
        for att in djson["attributes"]:
            #create attribute
            att_field = self.env["mercadolibre.grid.attribute.line"].prepare_vals(att)

        row_arrs = []
        row_arrs.append((5,0,0))
        for row in djson["rows"]:
            row_field = self.env["mercadolibre.grid.row"].prepare_vals(row)
            row_arrs.append( (0, 0, row_field) )

        fields["rows"] = row_arrs

        return fields

    def search_charts(self, category, brand, gender ):
        #get the category with the catalog_domain
        return True

    def create_chart(self, djson ):
        vals = self.prepare_vals(djson)
        #_logger.info("create_chart vals: " +str(vals)+" from:"+str(djson))
        chart = self.search([('meli_id','=',vals["meli_id"])],limit=1)
        if not chart:
            chart = self.create(vals)
        else:
            chart.write(vals)
        return chart

    def update_attributes(self, product=None):
        #
        #_logger.info("update_attributes")
        #search for an attribute SIZE also related to this chart id.
        # if not, create it
        ml_size_att = self.env["mercadolibre.category.attribute"].search([('att_id','=','SIZE')], limit=1)
        all_odoo_sizes = self.env["product.attribute"].search([
                    ('meli_default_id_attribute','=',ml_size_att.id),
                    ('meli_chart_id','=',self.id)
                    ])
        if (all_odoo_sizes):
            #solo recargar los valores o chequearlos
            #_logger.info("update_attributes: reload")
            for osi in all_odoo_sizes:
                self.update_attribute_values( osi )
        else:
            odoo_att_fields = {
                "name": "Talle",
                "meli_default_id_attribute": ml_size_att.id,
                "meli_chart_id": self.id,
                "create_variant": "always"
            }
            #_logger.info("update_attributes: create "+str(odoo_att_fields))
            osi = self.env["product.attribute"].create(odoo_att_fields)
            if (osi):
                self.update_attribute_values( osi )

    def update_attribute_values(self, osi ):
        if osi:
            #_logger.info("update_attributes: reload att values in odoo")
            pass;

    def search_row_id( self, value ):

        #_logger.info("search_row_id: for value: " + str(value) + "value.isnumeric() : " + str(value and value.replace(".","").isnumeric()) )

        row_id = None
        ret_row_id = None
        ret_size_val = ""
        ret_col_size_val = ""

        for row in self.rows:

            #_logger.info( "search_row_id: in row: " + str(row) )
            row_id = row.row_id
            ret_col_size_val = ""

            for attval in row.attribute_values:

                ret_col_id = attval.id
                ret_col_name = attval.name
                ret_col_value = attval.value
                if attval.att_id == 'SIZE':
                    ret_col_size_val = attval.value

                #_logger.info( "search_row_id: in attribute_values: " + str(attval) )

                #if ( attval.number and not math.isnan(attval.number) and not math.isnan(value) and ( value == attval.value or float(value)==float(attval.number) ) ):
                #    ret_row_id = row_id
                #    ret_col_name = attval.name
                #    ret_col_id = attval.id
                #    #_logger.info( "search_row_id: ret_row_id found: " + str(ret_row_id) )
                #    _logger.info( "search_row_id: ret_row_id FINAL for Value: "+str(value)+" is Col Name: "+str(ret_col_name)+" ROW ID >>> " + str(ret_row_id) )
                #

                #_logger.info("search_row_id: in attribute_values: name: " + str(attval.name)+ " value: " + str(attval.value) )
                if ( attval.name and ( really_compare(value,attval.value) or really_compare(value,attval.name) ) ):

                    ret_row_id = row_id
                    ret_size_val = ret_col_size_val
                    _logger.info("search_row_id: ret_row_id FINAL for Value: "+str(value)+" GRID Row Val: "+str(ret_size_val)+" from Col Name: "+str(ret_col_name)+" Col Value: "+str(ret_col_value)+" ROW ID >>> " + str(ret_row_id) )

                else:
                    if ( attval.number and value.replace(".","").isnumeric()):
                        #_logger.info("search_row_id: isnumeric value:" + str(float(value))+" vs attval.number:" +str(float(attval.number)) )
                        if ( value == attval.value or float(value)==float(attval.number) ):

                            ret_row_id = row_id
                            ret_size_val = ret_col_size_val

                        #    #_logger.info( "search_row_id: ret_row_id found: " + str(ret_row_id) )
                            #_logger.info( "search_row_id: ret_row_id FINAL for Value: "+str(value)+" is Col Name: "+str(ret_col_name)+" ROW ID >>> " + str(ret_row_id) )
                            #_logger.info("search_row_id: isnumeric ret_row_id FINAL for Value: "+str(value)+" is Col Name: "+str(ret_col_name)+" ROW ID >>> " + str(ret_row_id) )

        return [ret_row_id, ret_size_val]
