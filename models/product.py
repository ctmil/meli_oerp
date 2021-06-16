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

from odoo import models, fields, api, osv
from odoo.tools.translate import _

import pdb
import logging
_logger = logging.getLogger(__name__)

import hashlib
import math
import requests
import base64
import mimetypes
from urllib.request import urlopen

from datetime import datetime

from .meli_oerp_config import *

from ..melisdk.meli import Meli
import string
if (not ('replace' in string.__dict__)):
    string = str

from . import versions
from .versions import *

class product_template(models.Model):
    _inherit = "product.template"

    def product_template_post(self):
        product_obj = self.env['product.template']
        company = self.env.user.company_id
        warningobj = self.env['warning']

        meli = self.env['meli.util'].get_new_instance(company)
        if meli.need_login():
            return meli.redirect_login()

        _logger.info("Product Template Post")
        _logger.info(self.env.context)

        custom_context = {}
        force_meli_pub = False
        force_meli_active = False
        if ("force_meli_pub" in self.env.context):
            force_meli_pub = self.env.context.get("force_meli_pub")
            custom_context = { "force_meli_pub": force_meli_pub, "force_meli_active": force_meli_active }
        if ("force_meli_active" in self.env.context):
            force_meli_active = self.env.context.get("force_meli_active")
            custom_context = { "force_meli_pub": force_meli_pub, "force_meli_active": force_meli_active }
        _logger.info(custom_context)

        ret = {}
        posted_products = 0
        for product in self:
            if (product.meli_pub_as_variant):
                _logger.info("Posting as variants")
                #filtrar las variantes que tengan esos atributos que definimos
                #la primera variante que cumple las condiciones es la que publicamos.
                variant_principal = False
                #las condiciones es que los atributos de la variante
                conditions_ok = True
                for variant in product.product_variant_ids:
                    if (variant._conditions_ok() ):
                        variant.meli_pub = True
                        if (variant_principal==False):
                            _logger.info("Posting variant principal:")
                            _logger.info(variant)
                            variant_principal = variant
                            product.meli_pub_principal_variant = variant
                            ret = variant.with_context(custom_context).product_post()
                            if ('name' in ret[0]):
                                return ret[0]
                            posted_products+= 1

                        else:
                            if (variant_principal):
                                ret = variant.with_context(custom_context).product_post_variant(variant_principal)
                                #if ('name' in ret[0]):
                                #    return ret[0]
                                #posted_products+= 1
                    else:
                        _logger.info("No condition met for:"+variant.display_name)
                _logger.info(product.meli_pub_variant_attributes)


            else:
                for variant in product.product_variant_ids:
                    _logger.info("Variant:", variant, variant.meli_pub)
                    if (force_meli_pub==True):
                        variant.meli_pub = True
                    if (variant.meli_pub):
                        _logger.info("Posting variant")
                        ret = variant.with_context(custom_context).product_post()
                        if ('name' in ret[0]):
                            return ret[0]
                        posted_products+= 1
                    else:
                        _logger.info("No meli_pub for:"+variant.display_name)

        if (posted_products==0):
            ret = warningobj.info( title='MELI WARNING', message="Se intentaron publicar 0 productos. Debe forzar las publicaciones o marcar el producto con el campo Meli Publication, debajo del titulo.", message_html="" )

        return ret

    def product_template_update(self, meli_id=None):
        product_obj = self.env['product.template']
        company = self.env.user.company_id
        warningobj = self.env['warning']
        ret = {}

        meli = self.env['meli.util'].get_new_instance(company)
        if meli.need_login():
            return meli.redirect_login()

        _logger.info("Product Template Update")

        for product in self:
            if (product.meli_pub_as_variant and product.meli_pub_principal_variant.id):
                _logger.info("Updating principal variant")
                ret = product.meli_pub_principal_variant.product_meli_get_product(meli_id=meli_id)
            else:
                for variant in product.product_variant_ids:
                    _logger.info("Variant:", variant)
                    if (variant.meli_pub):
                        _logger.info("Updating variant")
                        ret = variant.product_meli_get_product(meli_id=meli_id)
                        if ('name' in ret):
                            return ret

        return ret

    def _variations(self, config=None):
        variations = False
        for product_tmpl in self:
            for variant in product_tmpl.product_variant_ids:
                if ( variant._conditions_ok() ):
                    variant.meli_pub = True
                    var = variant._combination()
                    if (var):
                        if (variations==False):
                            variations = []
                        var_attributes = variant._update_sku_attribute( attributes=("attributes" in var and var["attributes"]), set_sku=config.mercadolibre_post_default_code )
                        var_attributes and var.update({"attributes": var_attributes })
                        variations.append(var)

        return variations


    def product_template_stats(self):

        for product in self:
            _pubs = ""
            _stats = ""
            for variant in product.product_variant_ids:
                if (variant.meli_pub):
                    if ( (variant.meli_status=="active" or variant.meli_status=="paused") and variant.meli_id):
                        ml_full_status = variant.meli_status
                        if (variant.meli_sub_status):
                            ml_full_status+= ' ('+str(variant.meli_sub_status)+')'
                        if (len(_pubs)):
                            _pubs = _pubs + "|" + variant.meli_id + ":" + ml_full_status
                        else:
                            _pubs = variant.meli_id + ":" + ml_full_status

                        if (variant.meli_status=="active"):
                            _stats = "active"

                        if (_stats == "" and variant.meli_status=="paused"):
                            _stats = "paused"

            product.meli_publications = _pubs
            product.meli_variants_status = _stats

        return {}

    def search_template_stats(self, operator, value):
        _logger.info("search_template_stats")
        _logger.info(operator)
        _logger.info(value)
        if operator == 'ilike':
            #name = self.env.context.get('name', False)
            #if name is not False:
            id_list = []
            _logger.info(self.env.context)
            #name = self.env.context.get('name', False)
            products = self.env['product.template'].search([], limit=10000)
            if (value):
                for p in products:
                    if (value in p.meli_publications):
                        id_list.append(p.id)

            return [('id', 'in', id_list)]
        else:
            _logger.error(
                'The field name is not searchable'
                ' with the operator: {}',format(operator)
            )


    def action_meli_pause(self):
        for product in self:
            for variant in product.product_variant_ids:
                if (variant.meli_pub):
                    variant.product_meli_status_pause()
        return {}


    def action_meli_activate(self):
        for product in self:
            for variant in product.product_variant_ids:
                if (variant.meli_pub):
                    variant.product_meli_status_active()
        return {}


    def action_meli_close(self):
        for product in self:
            for variant in product.product_variant_ids:
                if (variant.meli_pub):
                    variant.product_meli_status_close()
        return {}


    def action_meli_delete(self):
        for product in self:
            for variant in product.product_variant_ids:
                if (variant.meli_pub):
                    variant.product_meli_delete()
        return {}

    @api.onchange('meli_pub')
    def _onchange_meli_pub( self ):
        product = self
        _logger.info("_onchange_meli_pub meli_pub:"+str(product))
        for product in self:
            _logger.info("onchange meli_pub:"+str(product))
            #product = self._origin
            #product = self
            for variant in product.product_variant_ids:
                _logger.info("onchange meli_pub variant before::"+str(variant.meli_pub))
                variant.write({'meli_pub':product.meli_pub})

    def get_title_for_meli(self):
        return self.name

    def get_title_for_category_predictor(self):
        return self.name

    def get_price_for_category_predictor(self):
        pricelist = self._get_pricelist_for_meli()
        return int(self.with_context(pricelist=pricelist.id).price)

    def action_category_predictor(self):
        self.ensure_one()
        warning_model = self.env['warning']

        meli_categ, rjson = self._get_meli_category_from_predictor()
        if meli_categ:
            self.meli_category = meli_categ.id
            return warning_model.info( title='MELI WARNING', message="CATEGORY PREDICTOR", message_html="Categoria sugerida: %s" % meli_categ.name)

        message_html = ''
        if rjson and len(rjson):
            for rama in rjson:
                _logger.info(rama)
                message_html+="<br/><br/>"+str(rama)

        return warning_model.info( title='MELI WARNING', message="CATEGORY PREDICTOR", message_html=message_html)

    def _get_meli_category_from_predictor(self):
        self.ensure_one()
        meli_util_model = self.env['meli.util']
        meli = meli_util_model.get_new_instance()
        vals = [{
            'title': self.get_title_for_category_predictor(),
            'price': self.get_price_for_category_predictor(),
        }]
        #response = meli.post("/sites/"+self.env.user.company_id._get_ML_sites()+"/category_predictor/predict", vals)
        url = "/sites/"+self.env.user.company_id._get_ML_sites()+"/domain_discovery/search?q="+self.get_title_for_category_predictor()
        _logger.info(url)
        response = meli.get(url)
        rjson = response.json()
        meli_categ = False
        _logger.info(rjson)
        _logger.info(isinstance(rjson, list))
        if rjson and isinstance(rjson, list):
            if "category_id" in rjson[0]:
                #_logger.info("Take first suggestion")
                #meli_categ = self.env['mercadolibre.category'].import_category(rjson[0]['id'])
                meli_categ = self.env['mercadolibre.category'].import_category(rjson[0]['category_id'])
                if (meli_categ==None):
                    _logger.info("Import category failed.")
        return meli_categ, rjson

    def _get_pricelist_for_meli(self):
        pricelist = self.env.user.company_id.mercadolibre_pricelist
        if not pricelist:
            pricelist = self.env['product.pricelist'].search([
                ('currency_id','=',self.env.user.company_id.mercadolibre_currency),
                ('website_id','!=',False),
            ], limit=1)
        if not pricelist:
            pricelist = self.env['product.pricelist'].search([], limit=1)
        return pricelist

    def update_meli_ids(self):
        for tpl in self:
            ml_ids = ""
            coma = ""
            for p in tpl.product_variant_ids:
                if (p.meli_id and len(p.meli_id)):
                    ml_ids = ml_ids + coma + str(p.meli_id)
                    coma = ","
            tpl.meli_ids = ml_ids

    name = fields.Char('Name', size=128, required=True, translate=False, index=True)
    meli_title = fields.Char(string='Nombre del producto en Mercado Libre',size=256)
    meli_description = fields.Text(string='Descripción')
    meli_category = fields.Many2one("mercadolibre.category","Categoría de MercadoLibre")
    meli_buying_mode = fields.Selection( [("buy_it_now","Compre ahora"),("classified","Clasificado")], string='Método de compra')
    meli_price = fields.Char(string='Precio de venta', size=128)
    meli_currency = fields.Selection([("ARS","Peso Argentino (ARS)"),
                                    ("MXN","Peso Mexicano (MXN)"),
                                    ("COP","Peso Colombiano (COP)"),
                                    ("PEN","Sol Peruano (PEN)"),
                                    ("BOB","Boliviano (BOB)"),
                                    ("BRL","Real (BRL)"),
                                    ("CLP","Peso Chileno (CLP)"),
                                    ("CRC","Colon Costarricense (CRC)"),
                                    ("UYU","Peso Uruguayo (UYU)"),
                                    ("USD","Dolar Estadounidense (USD)")],
                                    string='Moneda')
    meli_condition = fields.Selection([ ("new", "Nuevo"),
                                        ("used", "Usado"),
                                        ("not_specified","No especificado")],
                                        'Condición del producto')
    meli_dimensions = fields.Char( string="Dimensiones del producto", size=128)
    meli_pub = fields.Boolean('Meli Publication',help='MELI Product',index=True)
    meli_master = fields.Boolean('Meli Producto Maestro', help='MELI Product Maestro',index=True)
    meli_warranty = fields.Char(string='Garantía', size=256, help='Garantía del producto. Es obligatorio y debe ser un número seguido por una unidad temporal. Ej. 2 meses, 3 años.')
    meli_listing_type = fields.Selection([("free","Libre"),("bronze","Bronce"),("silver","Plata"),("gold","Oro"),("gold_premium","Gold Premium"),("gold_special","Gold Special/Clásica"),("gold_pro","Oro Pro")], string='Tipo de lista')
    meli_attributes = fields.Text(string='Atributos')

    meli_publications = fields.Text(compute=product_template_stats,string='Publicaciones en ML',search=search_template_stats)
    meli_variants_status = fields.Text(compute=product_template_stats,string='Meli Variant Status')

    meli_pub_as_variant = fields.Boolean('Publicar variantes como variantes en ML',help='Publicar variantes como variantes de la misma publicación, no como publicaciones independientes.')
    meli_pub_variant_attributes = fields.Many2many(prod_att_line, string='Atributos a publicar en ML',help='Seleccionar los atributos a publicar')
    meli_pub_principal_variant = fields.Many2one( 'product.product',string='Variante principal',help='Variante principal')

    meli_model = fields.Char(string="Modelo [meli]",size=256)
    meli_brand = fields.Char(string="Marca [meli]",size=256)
    meli_stock = fields.Float(string="Cantidad inicial (Solo para actualizar stock)[meli]")

    meli_product_bom = fields.Char(string="Lista de materiales (skux:1,skuy:2,skuz:4) [meli]")

    meli_product_price = fields.Float(string="Precio [meli]")
    meli_product_cost = fields.Float(string="Costo del proveedor [meli]")
    meli_product_code = fields.Char(string="Codigo de proveedor [meli]")
    meli_product_supplier = fields.Char(string="Proveedor del producto [meli]")

    meli_ids = fields.Char(size=2048,string="MercadoLibre Ids.",help="ML Ids de variantes separados por coma.",index=True)

    meli_catalog_listing = fields.Boolean(string='Catalog Listing', size=256)
    meli_catalog_product_id = fields.Char(string='Catalog Product Id', size=256)
    meli_catalog_item_relations = fields.Char(string='Catalog Item Relations', size=256)
    meli_catalog_automatic_relist = fields.Boolean(string='Catalog Auto Relist', size=256)

    meli_shipping_mode = fields.Char(string="Shipping Mode",help="Shipping modes (por usuario): custom, not_specified, me2. https://api.mercadolibre.com/users/USERID/shipping_preferences",index=True)
    meli_shipping_method = fields.Char(string="Shipping Method",help="Shipping methods: https://api.mercadolibre.com/sites/SITEID/shipping_methods",index=True)

    meli_full_update = fields.Datetime(string="Product update",index=True)
    meli_image_update = fields.Datetime(string="Image update",index=True)
    meli_price_update = fields.Datetime(string="Price update",index=True)
    meli_stock_update = fields.Datetime(string="Stock update",index=True)

    meli_stock_error = fields.Char(string="Stock Error",index=True)
    meli_price_error = fields.Char(string="Price Error",index=True)
    meli_update_error = fields.Char(string="Update Error",index=True)

    meli_update_stock_blocked = fields.Boolean(string="Block Update stock",default=False)

product_template()

class product_product(models.Model):

    _inherit = "product.product"

    def _meli_set_product_price( self, product_template, meli_price, force_variant=False, config=None ):

        company = (config and 'company_id' in config._fields and config.company_id) or self.env.user.company_id
        config = config or company
        _logger.info("_meli_set_product_price: config: "+str(config and config.name))
        ml_price_converted = meli_price
        product = self
        tax_excluded = ml_tax_excluded(self, config=config)

        if ( tax_excluded and product_template.taxes_id ):
            _logger.info("Adjust taxes")
            txfixed = 0
            txpercent = 0
            #_logger.info("Adjust taxes")
            for txid in product_template.taxes_id:
                if (txid.type_tax_use=="sale" and not txid.price_include):
                    if (txid.amount_type=="percent"):
                        txpercent = txpercent + txid.amount
                    if (txid.amount_type=="fixed"):
                        txfixed = txfixed + txid.amount
            if (txfixed>0 or txpercent>0):
                #_logger.info("Tx Total:"+str(txtotal)+" to Price:"+str(ml_price_converted))
                ml_price_converted = txfixed + ml_price_converted / (1.0 + txpercent*0.01)
                _logger.info("Price adjusted with taxes:"+str(ml_price_converted))

        pl = False
        if config.mercadolibre_pricelist:
            pl = config.mercadolibre_pricelist

        if (pl):
            #pass
            pli = self.env['product.pricelist.item']
            if force_variant:
                pli_tpl = False
            else:
                pli_tpl = pli.search([('pricelist_id','in',[pl.id]),('product_tmpl_id','=',product_template.id)])

            pli_var = pli.search([('pricelist_id','in',[pl.id]),('product_id','=',self.id)])

            if (pli_tpl or pli_var):
                return_val = pl.price_get( self.id, 1.0 )
                if (pl.id in return_val):
                    old_price = return_val[pl.id]
                    if pli_tpl:
                        pli_tpl.write({'fixed_price': float(ml_price_converted)})
                    if pli_var:
                        pli_var.write({'fixed_price': float(ml_price_converted)})
            else:
                _logger.info("Creating price")
                if force_variant and not pli_var:
                    pli_var = pli.create({
                            'product_id': product.id,
                            'min_quantity': 0,
                            'applied_on': '0_product_variant',
                            'pricelist_id': pl.id,
                            'compute_price': 'fixed',
                            'currency_id': pl.currency_id.id,
                            'fixed_price': float(ml_price_converted)
                             })
                else:
                    if not force_variant and not pli_tpl:
                        pli_tpl = pli.create({
                                'product_tmpl_id': product_template.id,
                                'min_quantity': 0,
                                'applied_on': '1_product',
                                'pricelist_id': pl.id,
                                'compute_price': 'fixed',
                                'currency_id': pl.currency_id.id,
    				            'fixed_price': float(ml_price_converted)
                                 })

        else:
            if (product_template.lst_price<=1.0):
                _logger.info("_meli_set_product_price lst_price<1.0: "+str(ml_price_converted))
                product_template.write({'lst_price': ml_price_converted})

    def set_meli_price( self, meli=None, config=None, plist=None ):
        company = self.env.user.company_id
        config = config or company
        company = (config and 'company_id' in config._fields and config.company_id) or company
        product = self
        product_tmpl = product.product_tmpl_id
        #_logger.info("set_meli_price: "+str(product_tmpl.list_price)+ " >> "+str(product_tmpl.display_name)+": "+str(product_tmpl.meli_price)+" | "+str(product.display_name)+": "+str(product.meli_price) )

        pl = config.mercadolibre_pricelist or plist

        # NEW OR NULL
        # > Set template meli price
        if ( product_tmpl.meli_price==False
            or ( product_tmpl.meli_price and int(float(product_tmpl.meli_price))==0 ) ):
            product_tmpl.meli_price = product_tmpl.list_price

        # UPDATE
        # Actualizamos el product meli price (todas las variantes en ML deben tener el mismo precio):
        # por eso lo tomamos de la plantilla para simplifiar
        new_price = product_tmpl.list_price
        if ( product.lst_price ):
            new_price = product.lst_price

        if (pl):
            return_val = pl.price_get(product.id,1.0)
            if pl.id in return_val:
                new_price = return_val[pl.id]
            #_logger.info("return_val: ")
            #_logger.info(return_val)
        else:
            #_logger.info( "new_price: " +str(new_price))
            if ( product.meli_price_fixed and product.meli_price):
                new_price = int(float(product.meli_price)) or int(float(product_tmpl_id.meli_price)) or 0
            else:
                if ( product.lst_price ):
                    new_price = product.lst_price

        tax_excluded = ml_tax_excluded(self)
        if ( tax_excluded and product_tmpl.taxes_id ):
            _logger.info("Adjust taxes for publish")
            txfixed = 0
            txpercent = 0
            #_logger.info("Adjust taxes")
            for txid in product_tmpl.taxes_id:
                if (txid.type_tax_use=="sale" and not txid.price_include):
                    if (txid.amount_type=="percent"):
                        txpercent = txpercent + txid.amount
                    if (txid.amount_type=="fixed"):
                        txfixed = txfixed + txid.amount
            if (txfixed>0 or txpercent>0):
                #_logger.info("Tx Total:"+str(txtotal)+" to Price:"+str(ml_price_converted))
                new_price = txfixed + new_price * (1.0 + txpercent*0.01)
                #_logger.info("Price adjusted with taxes:"+str(new_price))

        new_price = round(new_price,2)

        if (product_tmpl.meli_currency and product_tmpl.meli_currency == 'COP'):
            new_price = math.ceil(new_price)

        product_tmpl.meli_price = new_price
        product.meli_price = product_tmpl.meli_price

        product_tmpl.meli_price = str(int(float(product_tmpl.meli_price)))
        #_logger.info("product_tmpl.meli_price updated: " + str(product_tmpl.meli_price))

        product.meli_price = str(int(float(product.meli_price)))
        #_logger.info("product.meli_price updated: " + str(product.meli_price))

        return product.meli_price

    def _meli_set_category( self, product_template, category_id, meli=None, config=None ):

        product = self
        company = self.env.user.company_id
        config = config or company
        www_cats = False
        if 'product.public.category' in self.env:
            www_cats = self.env['product.public.category']
        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)
            if meli.need_login():
                return meli.redirect_login()

        mlcatid = False
        www_cat_id = False

        mlcatid, www_cat_id = self.env["mercadolibre.category"].meli_get_category( category_id, create_missing_website=config.mercadolibre_create_website_categories )

        if (mlcatid):
            product.write( {'meli_category': mlcatid} )
            product_template.write( {'meli_category': mlcatid} )

        if www_cat_id!=False:
            #assign
            product_template.public_categ_ids = [(4,www_cat_id)]

    def _meli_remove_images_unsync( self, product_template, pictures, meli=None, config=None ):
        #atencion aplicar meli_imagen_id y meli_published solo si existe efectivamenete en pictures antes y luego de updatear en ML
        #tambien chequear con hash duplicados... en lugar de meli_imagen_id
        product = self
        company = self.env.user.company_id
        config = config or company

        if not (config.mercadolibre_remove_unsync_images):
            return {}

        ml_pics = {}
        ml_sizes = {}
        ml_bytes = {}

        if not ("product.image" in self.env):
            return {}


        for ix in range(0,len(pictures)):

            ml_imgid = pictures[ix]['id']
            if (ml_imgid):
                ml_pics[ml_imgid] = pictures[ix]

                thumbnail_url = pictures[ix]['url']
                image = urlopen(thumbnail_url).read()
                meli_imagen_bytes = len(image)
                if (str(meli_imagen_bytes) in ml_sizes):
                    _logger.info("Imagen bytes duplicated: "+str(thumbnail_url))
                    ml_bytes[str(meli_imagen_bytes)+str("__")+str(ix)] = pictures[ix]
                else:
                    ml_bytes[str(meli_imagen_bytes)] = pictures[ix]

                _logger.info(ml_imgid)

                duplicates = self.env["product.image"].search([('meli_force_pub','=',False),
                                                                ('meli_imagen_id','=',ml_imgid),
                                                                ('product_tmpl_id','=',product_template.id)])
                if (duplicates and len(duplicates)>1):
                    _logger.info("Removing template duplicates for "+str(ml_imgid)+" :"+str(len(duplicates)-1))
                    for ix in range(1,len(duplicates)):
                        duplicates[ix].unlink()

                try:
                    duplicates = self.env["product.image"].search([('meli_force_pub','=',False),
                                                                ('meli_imagen_id','=',ml_imgid),
                                                                ('product_variant_id','=',product.id)])
                    if (duplicates and len(duplicates)>1):
                        _logger.info("Removing variant duplicates for "+str(ml_imgid)+" :"+str(len(duplicates)-1))
                        for ix in range(1,len(duplicates)):
                            duplicates[ix].unlink()
                except:
                    pass;

        #_logger.info(ml_pics)
        #_logger.info(ml_bytes)

        #_logger.info("Cleaning product template images with meli id but not in ML")
        ml_images = self.env["product.image"].search([('meli_force_pub','=',False),
                                                        ('meli_imagen_id','!=',False),
                                                        ('product_tmpl_id','=',product_template.id)])
        #_logger.info(ml_images)
        if (ml_images and len(ml_images)):
            for ml_image in ml_images:
                if not ml_image.meli_imagen_id in ml_pics and not str(ml_image.meli_imagen_bytes) in ml_bytes:
                    ml_image.unlink()

        try:
            #_logger.info("Cleaning product variant images with meli id not in ML")
            ml_images = self.env["product.image"].search([  ('meli_force_pub','=',False),
                                                            ('meli_imagen_id','!=',False),
                                                            ('product_variant_id','=',product.id)])
            #_logger.info(ml_images)
            if (ml_images and len(ml_images)):
                for ml_image in ml_images:
                    if not ml_image.meli_imagen_id in ml_pics and not str(ml_image.meli_imagen_bytes) in ml_bytes:
                        ml_image.unlink()
        except:
            pass;

    def _meli_set_images( self, product_template, pictures, meli=None, config=None ):
        company = self.env.user.company_id
        config = config or company

        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)

        if not ("product.image" in self.env):
            return {}

        try:
            product = self
            ix_start = 0
            if (not config.mercadolibre_do_not_use_first_image):
                ix_start = 1
                thumbnail_url = pictures[0]['url']
                image = urlopen(thumbnail_url).read()
                image_base64 = base64.encodestring(image)
                set_image_full(product, image_base64)

            if (len(pictures)):
                #complete product images:
                #delete all images...
                _logger.info("Importing all images after principal...")

                #_logger.info(pictures)
                #_logger.info(range(1,len(pictures)))
                for ix in range(ix_start,len(pictures)):
                    pic = pictures[ix]
                    #_logger.info(pic)
                    bin_updating = False
                    resimage = meli.get("/pictures/"+pic['id'], {'access_token':meli.access_token})
                    imgjson = resimage.json()

                    thumbnail_url = pic['secure_url']
                    #_logger.info(imgjson)
                    if 'error' in imgjson:
                        pass;
                    else:
                        if (len(imgjson['variations'])>0):
                            thumbnail_url = imgjson['variations'][0]['secure_url']

                    image = urlopen(thumbnail_url).read()
                    image_base64 = base64.encodestring(image)
                    meli_imagen_bytes = len(image)
                    pimage = False
                    pimg_fields = {
                        #'name': thumbnail_url+' - '+pic["size"]+' - '+pic["max_size"],
                        'meli_imagen_id': pic["id"],
                        'meli_imagen_link': thumbnail_url,
                        'meli_imagen_size': pic["size"],
                        'meli_imagen_max_size': pic["max_size"],
                        'meli_imagen_bytes': meli_imagen_bytes,
                        'product_tmpl_id': product_template.id,
                        'meli_pub': True
                    }
                    #_logger.info(pimg_fields)
                    if (variant_image_ids(product)):
                        #_logger.info("has variant image ids")
                        #_logger.info(variant_image_ids(product))
                        pimage = self.env["product.image"].search([('meli_imagen_id','=',pic["id"]),('product_tmpl_id','=',product_template.id)])
                        #_logger.info(pimage)
                        if (pimage and len(pimage)>1):
                            #unlink all but first
                            _logger.info("Unlink all duplicates for "+str(pic["id"]))
                            for img in pimage:
                                img.unlink()
                            pimage = False
                        if (pimage and get_image_full(pimage)):
                            imagebin = base64.b64decode( get_image_full(pimage) )
                            bin_diff = meli_imagen_bytes - len(imagebin)
                            _logger.info("Image:"+str(len(imagebin))+" vs URLImage:"+str(meli_imagen_bytes)+" diff:"+str(bin_diff) )
                            bin_updating = (abs(bin_diff)>0)
                    else:
                        _logger.info("no variant image ids, using template image ids")
                        if (template_image_ids(product)):
                            _logger.info(template_image_ids(product))
                            pimage = self.env["product.image"].search([('meli_imagen_id','=',pic["id"]),('product_tmpl_id','=',product_template.id)])

                            #remove duplicate images
                            _logger.info(pimage)
                            if (pimage and len(pimage)>1):
                                #unlink all but first
                                _logger.info("Unlink all duplicates for "+str(pic["id"]))
                                pimage.unlink()
                                for img in pimage:
                                    img.unlink()
                                pimage = False

                            if (pimage and get_image_full(pimage)):
                                imagebin = base64.b64decode( get_image_full(pimage) )
                                bin_diff = meli_imagen_bytes - len(imagebin)
                                _logger.info("Image:"+str(len(imagebin))+" vs URLImage:"+str(meli_imagen_bytes)+" diff:"+str(bin_diff) )
                                bin_updating = (abs(bin_diff)>0)


                    #_logger.info(str(pimage==False))
                    if (not pimage or (pimage and len(pimage)==0)):
                        _logger.info("Creating new image")
                        bin_updating = True
                        pimg_fields["name"] = product.meli_title or product.name;
                        pimage = self.env["product.image"].create(pimg_fields)

                    if (pimage):
                        pimage.write(pimg_fields)
                        if (bin_updating):
                            _logger.info("Updating image data.")
                            _logger.info("Image:"+str(meli_imagen_bytes) )
                            set_image_full(pimage, image_base64)
                        else:
                            _logger.info("Already in Odoo")
                            _logger.info(pimage)
        except Exception as e:
            _logger.info("_meli_set_images Exception")
            _logger.info(e, exc_info=True)

    def _get_non_variant_attributes( self, attributes ):

        product = self
        product_template = product.product_tmpl_id

        if (len(attributes) ):
            for att in attributes:
                try:
                    _logger.info(att)
                    #first search by attribute ml id
                    ml_attribute = self.env['mercadolibre.category.attribute'].search([('att_id','=',att['id'])],limit=1)
                    attribute = []

                    #if the product is already created?
                    if (ml_attribute and ml_attribute.id):
                        #_logger.info(ml_attribute)
                        #TODO: this doesnt work if we have duplicated attributes with several ml ids
                        attribute = self.env['product.attribute'].search([('meli_default_id_attribute','=',ml_attribute.id)])
                        #_logger.info(attribute)

                    if (len(attribute) and attribute.id):
                        attribute_id = attribute.id
                        attribute_value_id = self.env['product.attribute.value'].search([('attribute_id','=',attribute_id), ('name','=',att['value_name'])]).id
                        #_logger.info(_logger.info(attribute_id))
                        if attribute_value_id:
                            #_logger.info(attribute_value_id)
                            pass
                        else:
                            _logger.info("Creating attribute value:")
                            _logger.info(att)
                            if (att['value_name']!=None):
                                attribute_value_id = self.env['product.attribute.value'].create({'attribute_id': attribute_id, 'name': att['value_name'] }).id

                        if (attribute_value_id):
                            attribute_line =  self.env[prod_att_line].search([('attribute_id','=',attribute_id),('product_tmpl_id','=',product_template.id)])
                            if (attribute_line and attribute_line.id):
                                #_logger.info(attribute_line)
                                pass
                            else:
                                #_logger.info("Creating att line id:")
                                att_vals = prepare_attribute( product_template.id, attribute_id, attribute_value_id )
                                attribute_line =  self.env[prod_att_line].create(att_vals)

                            if (attribute_line):
                                #_logger.info("Check attribute line values id.")
                                #_logger.info("attribute_line:")
                                #_logger.info(attribute_line)
                                if (attribute_line.value_ids):
                                    #check if values
                                    #_logger.info("Has value ids:")
                                    #_logger.info(attribute_line.value_ids.ids)
                                    if (attribute_value_id in attribute_line.value_ids.ids):
                                        #_logger.info(attribute_line.value_ids.ids)
                                        pass
                                    else:
                                        #_logger.info("Adding value id")
                                        attribute_line.value_ids = [(4,attribute_value_id)]
                                else:
                                    #_logger.info("Adding value id")
                                    attribute_line.value_ids = [(4,attribute_value_id)]

                except Exception as e:
                    _logger.info("Attributes exception:")
                    _logger.info(e, exc_info=True)

    def _get_variations( self, variations ):

        #recorrer los variations>attribute_combinations y agregarlos como atributos de las variantes
        _logger.info("_get_variations:"+str(len(variations)))

        published_att_variants = False
        product = self
        product_template = product.product_tmpl_id

        vindex = -1
        for variation in variations:
            vindex = vindex + 1
            if ('attribute_combinations' in variation):
                _attcomb_str = ""
                variations[vindex]["default_code"] = ""
                for attcomb in variation['attribute_combinations']:
                    namecap = attcomb['name']
                    if (len(namecap)):
                        att = {
                            'name': namecap,
                            'value_name': attcomb['value_name'],
                            'create_variant': default_create_variant,
                            'att_id': False
                        }
                        if ('id' in attcomb):
                            if (attcomb["id"]):
                                if (len(attcomb["id"])):
                                    att["att_id"] = attcomb["id"]
                        if (att["att_id"]==False):
                            namecap = namecap.strip()
                            namecap = namecap[0].upper()+namecap[1:]
                            att["name"] = namecap
                        if ('create_variant' in attcomb):
                            att['create_variant'] = attcomb['create_variant']
                        else:
                            variations[vindex]["default_code"] = variations[vindex]["default_code"]+namecap+":"+attcomb['value_name']+";"
                        #_logger.info(att)
                        if (att["att_id"]):
                            # ML Attribute , we could search first...
                            #attribute = self.env['product.attribute'].search([('name','=',att['name']),('meli_default_id_attribute','!=',False)])
                            #if (len(attribute)==0):
                            # ningun atributo con ese nombre asociado
                            ml_attribute = self.env['mercadolibre.category.attribute'].search([('att_id','=',att['att_id'])])
                            attribute = []
                            if (len(ml_attribute)>1):
                                ml_attribute = self.env['mercadolibre.category.attribute'].search([('att_id','=',att['att_id']),('cat_id','=',(product.meli_category and product.meli_category.id))])
                                if not ml_attribute:
                                    ml_attribute = self.env['mercadolibre.category.attribute'].search([('att_id','=',att['att_id'])])[0]
                                if (len(ml_attribute)==1):
                                    attribute = self.env['product.attribute'].search([('meli_default_id_attribute','=',ml_attribute.id)])
                            if (len(ml_attribute)==1):
                                attribute = self.env['product.attribute'].search([('meli_default_id_attribute','=',ml_attribute.id)])
                            if (len(attribute)==0):
                                attribute = self.env['product.attribute'].search([('name','=',att['name'])])
                        else:
                            #customizado
                            #_logger.info("Atributo customizado:"+str(namecap))
                            attribute = self.env['product.attribute'].search([('name','=',namecap),('meli_default_id_attribute','=',False)])
                            _logger.info(attribute)

                            if (attcomb['name']!=namecap):
                                attribute_duplicates = self.env['product.attribute'].search([('name','=',attcomb['name']),('meli_default_id_attribute','=',False)])
                                _logger.info("attribute_duplicates:")
                                _logger.info(attribute_duplicates)
                                if (len(attribute_duplicates)>=1):
                                    #archive
                                    _logger.info("attribute_duplicates:",len(attribute_duplicates))
                                    for attdup in attribute_duplicates:
                                        _logger.info("duplicate:"+attdup.name+":"+str(attdup.id))
                                        attdup_line =  self.env[prod_att_line].search([('attribute_id','=',attdup.id),('product_tmpl_id','=',product_template.id)])
                                        if (len(attdup_line)):
                                            for attline in attdup_line:
                                                attline.unlink()

                            #buscar en las lineas existentes
                            if (len(attribute)>1):
                                att_line = self.env[prod_att_line].search([('attribute_id','in',attribute.ids),('product_tmpl_id','=',product_template.id)])
                                _logger.info(att_line)
                                if (len(att_line)):
                                    _logger.info("Atributo ya asignado!")
                                    attribute = att_line.attribute_id

                        attribute_id = False
                        if (len(attribute)==1):
                            attribute_id = attribute.id
                        elif (len(attribute)>1):
                            _logger.error("Attributes duplicated names!!!")
                            attribute_id = attribute[0].id

                        #_logger.info(attribute_id)
                        if attribute_id:
                            #_logger.info(attribute_id)
                            pass
                        else:
                            #_logger.info("Creating attribute:")
                            attribute_id = self.env['product.attribute'].create({ 'name': att['name'],'create_variant': att['create_variant'] }).id

                        if (att['create_variant']==default_create_variant):
                            #_logger.info("published_att_variants")
                            published_att_variants = True

                        if (attribute_id):
                            #_logger.info("Publishing attribute")
                            attribute_value_id = self.env['product.attribute.value'].search([('attribute_id','=',attribute_id),('name','=',att['value_name'])]).id
                            #_logger.info(_logger.info(attribute_id))
                            if attribute_value_id:
                                #_logger.info(attribute_value_id)
                                pass
                            else:
                                _logger.info("Creating attribute value:"+str(att))
                                if (att['value_name']!=None):
                                    attribute_value_id = self.env['product.attribute.value'].create({'attribute_id': attribute_id,'name': att['value_name']}).id

                            if (attribute_value_id):
                                #_logger.info("attribute_value_id:")
                                #_logger.info(attribute_value_id)
                                #search for line ids.
                                attribute_line =  self.env[prod_att_line].search([('attribute_id','=',attribute_id),('product_tmpl_id','=',product_template.id)])
                                #_logger.info(attribute_line)
                                if (attribute_line and attribute_line.id):
                                    #_logger.info(attribute_line)
                                    pass
                                else:
                                    #_logger.info("Creating att line id:")
                                    att_vals = prepare_attribute( product_template.id, attribute_id, attribute_value_id )
                                    attribute_line =  self.env[prod_att_line].create(att_vals)

                                if (attribute_line):
                                    #_logger.info("Check attribute line values id.")
                                    #_logger.info("attribute_line:")
                                    #_logger.info(attribute_line)
                                    if (attribute_line.value_ids):
                                        #check if values
                                        #_logger.info("Has value ids:")
                                        #_logger.info(attribute_line.value_ids.ids)
                                        if (attribute_value_id in attribute_line.value_ids.ids):
                                            #_logger.info(attribute_line.value_ids.ids)
                                            pass
                                        else:
                                            #_logger.info("Adding value id")
                                            attribute_line.value_ids = [(4,attribute_value_id)]
                                    else:
                                        #_logger.info("Adding value id")
                                        attribute_line.value_ids = [(4,attribute_value_id)]

        return published_att_variants

    def is_variant_in_combination( self, ml_var_comb_default_code, var_default_code ):
        splits = ml_var_comb_default_code.split(";")
        is_in = True
        for att in splits:
            att_closed = att+";"
            if not att_closed in var_default_code:
                is_in = False
                break;
        return is_in

    def product_meli_get_product( self, meli_id=None ):
        company = self.env.user.company_id
        config = company
        product_obj = self.env['product.product']
        uomobj = self.env[uom_model]
        #pdb.set_trace()

        product = self
        meli_id = meli_id or product.meli_id

        _logger.info("product_meli_get_product: meli_id: "+str(meli_id))
        _logger.info(product.default_code)

        product_template_obj = self.env['product.template']
        product_template = product_template_obj.browse(product.product_tmpl_id.id)

        meli = self.env['meli.util'].get_new_instance(company)

        try:
            response = meli.get("/items/"+str(meli_id), { 'access_token': meli.access_token, 'include_attributes': 'all' } )
            #_logger.info(response)
            rjson = response.json()
            if rjson and 'variations' in rjson:
                vindex = -1
                for var in rjson['variations']:
                    vindex = vindex+1
                    vjson = rjson['variations'][vindex]
                    meli_id_variation = ("id" in var and var["id"])
                    #_logger.info(meli_id_variation)
                    if meli_id_variation:
                        if "attributes" in vjson:
                            for att in vjson["attributes"]:
                                if ("id" in att and att["id"] == "SELLER_SKU"):
                                    rjson['variations'][vindex]["seller_sku"] = att["value_name"]
                                    if (len(rjson["variations"])==1):
                                        rjson['seller_sku'] = att["value_name"]

                                if ("id" in att and att["id"] == "GTIN"):
                                    rjson['variations'][vindex]["barcode"] = att["value_name"]
            #_logger.info(rjson)
        except IOError as e:
            _logger.info( "I/O error({0}): {1}".format(e.errno, e.strerror) )
            return {}
        except Exception as E:
            _logger.info( "Rare error" )
            _logger.info(E, exc_info=True)
            return {}

        des = ''
        desplain = ''
        vid = ''
        if 'error' in rjson:
            return {}

        #TODO: traer la descripcion: con
        #https://api.mercadolibre.com/items/{ITEM_ID}/description?access_token=$ACCESS_TOKEN
        if rjson and 'descriptions' in rjson and rjson['descriptions']:
            response2 = meli.get("/items/"+product.meli_id+"/description", {'access_token':meli.access_token})
            rjson2 = response2.json()
            if 'text' in rjson2:
               des = rjson2['text']
            if 'plain_text' in rjson2:
               desplain = rjson2['plain_text']
            if (len(des)>0):
                desplain = des

        #TODO: verificar q es un video
        if 'video_id' in rjson and rjson['video_id']:
            vid = rjson['video_id']

        #TODO: traer las imagenes
        #TODO:
        pictures = rjson['pictures']
        if pictures and len(pictures):
            #remove all meli images not in pictures:
            product._meli_remove_images_unsync( product_template, pictures )
            product._meli_set_images(product_template, pictures)

        #categories
        product._meli_set_category( product_template, rjson['category_id'] )

        #prices
        force_price_for_variant = True

        # if 2 or more variations, its a variant publication, one price for all else one for each product variant as they are independent
        if "variations" in rjson and len(rjson["variations"])>1:
            force_price_for_variant = False

        try:
            if (float(rjson['price'])>=0.0):
                product._meli_set_product_price( product_template, rjson['price'], force_variant=force_price_for_variant, config=config )
        except Exception as e:
            _logger.info(e, exc_info=True)
            rjson['price'] = 0.0

        imagen_id = ''
        meli_dim_str = ''
        if ('dimensions' in rjson):
            if (rjson['dimensions']):
                meli_dim_str = rjson['dimensions']

        if ('pictures' in rjson):
            if (len(rjson['pictures'])>0):
                imagen_id = rjson['pictures'][0]['id']

        try:
            if (float(rjson['price'])>=0.0):
                product._meli_set_product_price( product_template, rjson['price'] )
        except:
            _logger.info(e, exc_info=True)
            rjson['price'] = 0.0

        try:
            rjson['warranty'] = rjson['warranty'].replace('Garantía del vendedor: ','')
        except:
            pass;

        meli_fields = {
            'name': rjson['title'].encode("utf-8"),
            #'default_code': rjson['id'],
            'meli_imagen_id': imagen_id,
            #'meli_post_required': True,
            'meli_id': rjson['id'],
            'meli_permalink': rjson['permalink'],
            'meli_title': rjson['title'].encode("utf-8"),
            'meli_description': desplain,
            'meli_listing_type': rjson['listing_type_id'],
            'meli_buying_mode':rjson['buying_mode'],
            'meli_price': str(rjson['price']),
            'meli_price_fixed': True,
            'meli_currency': rjson['currency_id'],
            'meli_condition': rjson['condition'],
            'meli_available_quantity': rjson['available_quantity'],
            'meli_warranty': rjson['warranty'],
            'meli_imagen_link': rjson['thumbnail'],
            'meli_video': str(vid),
            'meli_dimensions': meli_dim_str,
        }

        tmpl_fields = {
          'name': meli_fields["name"],
          'description_sale': desplain,
          #'name': str(rjson['id']),
          #'lst_price': ml_price_convert,
          'meli_title': meli_fields["meli_title"],
          'meli_description': meli_fields["meli_description"],
          #'meli_category': meli_fields["meli_category"],
          'meli_listing_type': meli_fields["meli_listing_type"],
          'meli_buying_mode': meli_fields["meli_buying_mode"],
          'meli_price': meli_fields["meli_price"],
          'meli_currency': meli_fields["meli_currency"],
          'meli_condition': meli_fields["meli_condition"],
          'meli_warranty': meli_fields["meli_warranty"],
          'meli_dimensions': meli_fields["meli_dimensions"]
        }

        if (product.name and not company.mercadolibre_overwrite_variant):
            del meli_fields['name']
        if (product_template.name and not company.mercadolibre_overwrite_template):
            del tmpl_fields['name']
        if (product_template.description_sale and not company.mercadolibre_overwrite_template):
            del tmpl_fields['description_sale']

        if ("catalog_listing" in rjson):
            meli_fields["meli_catalog_listing"] = rjson["catalog_listing"]
            if (meli_fields["meli_catalog_listing"]==True):
                tmpl_fields["meli_catalog_listing"] = True

            if ("automatic_relist" in rjson):
                meli_fields["meli_catalog_automatic_relist"] = rjson["automatic_relist"]
                if (meli_fields["meli_catalog_listing"]==True):
                    tmpl_fields["meli_catalog_automatic_relist"] = True

            if ("catalog_product_id" in rjson):
                meli_fields["meli_catalog_product_id"] = rjson["catalog_product_id"]
                if (meli_fields["meli_catalog_listing"]==True):
                    tmpl_fields["meli_catalog_product_id"] = rjson["catalog_product_id"]

            if ("item_relations" in rjson):
                meli_fields["meli_catalog_item_relations"] = rjson["item_relations"]
                if (meli_fields["meli_catalog_listing"]==True):
                    tmpl_fields["meli_catalog_item_relations"] = rjson["item_relations"]

        product.write( meli_fields )
        product_template.write( tmpl_fields )

        if (rjson['available_quantity']>=0):
            if (product_template.type not in ['product']):
                try:
                    product_template.write( { 'type': 'product' } )
                except Exception as e:
                    _logger.info("Set type almacenable ('product') not possible:")
                    _logger.error(e, exc_info=True)
                    pass;
            #TODO: agregar parametro para esto: ml_auto_website_published_if_available  default true
            if (1==1 and rjson['available_quantity']>0):
                product_template.website_published = True

        #TODO: agregar parametro para esto: ml_auto_website_unpublished_if_not_available default false
        if (1==2 and rjson['available_quantity']==0):
            product_template.website_published = False

        posting_fields = {
            'posting_date': str(datetime.now()),
            'meli_id':rjson['id'],
            'product_id':product.id,
            'name': 'Post ('+str(product.meli_id)+'): ' + product.meli_title
        }

        posting = self.env['mercadolibre.posting'].search([('meli_id','=',rjson['id'])])
        posting_id = posting.id

        if not posting_id:
            posting = self.env['mercadolibre.posting'].create((posting_fields))
            posting_id = posting.id
            if (posting):
                posting.posting_query_questions()
        else:
            posting.write({'product_id':product.id })
            posting.posting_query_questions()

        b_search_nonfree_ship = False
        if ('shipping' in rjson):

            if "logistic_type" in rjson["shipping"]:
                product.meli_shipping_logistic_type = rjson["shipping"]["logistic_type"]

            att_shipping = {
                'name': 'Con envío',
                'create_variant': default_no_create_variant
            }
            if ('variations' in rjson):
                #_logger.info("has variations")
                pass
            else:
                rjson['variations'] = []

            if ('free_methods' in rjson['shipping']):
                att_shipping['value_name'] = 'Sí'
                #buscar referencia del template correspondiente
                b_search_nonfree_ship = True
            else:
                att_shipping['value_name'] = 'No'

            rjson['variations'].append({'attribute_combinations': [ att_shipping ]})

        #_logger.info(rjson['variations'])
        #COMPLETING ATTRIBUTES VARIATION INFORMATION FROM /items/[MLID]/variations/[VARID]...
        if ('variations' in rjson and 1==1):
            vindex = -1
            realmeliv = 0
            for variation in rjson['variations']:
                vindex = vindex+1
                #_logger.info(variation)
                _logger.info(rjson['variations'][vindex])
                if 'id' in rjson['variations'][vindex]:
                    _logger.info(vid)
                    realmeliv = realmeliv+1
                    vid = rjson['variations'][vindex]['id']
                    #resvar = meli.get("/items/"+str(product.meli_id)+"/variations/"+str(vid), {'access_token':meli.access_token})
                    #vjson = resvar.json()
                    vjson = variation
                    if ( "error" in vjson ):
                        continue;
                    if ("attributes" in vjson):
                        rjson['variations'][vindex]["attributes"] = vjson["attributes"]
                        for att in vjson["attributes"]:
                            if ("id" in att and att["id"] == "SELLER_SKU"):
                                rjson['variations'][vindex]["seller_sku"] = att["value_name"]
            _logger.info(rjson['variations'])

            if ( realmeliv>0 and 1==1 ):
                #associate var ids for every variant
                product_template.meli_pub_as_variant = True
                if (not product_template.meli_pub_principal_variant
                    or not product_template.meli_pub_principal_variant.id == product.id):
                    for variant in product_template.product_variant_ids:
                        if not product_template.meli_pub_principal_variant:
                            product_template.meli_pub_principal_variant = variant
                        for variation in rjson['variations']:
                            if "seller_sku" in variation and variant.default_code == variation["seller_sku"]:
                                variant.meli_id_variation = variation["id"]
                                variant.meli_pub = True
                                variant.meli_id = product.meli_id
                                variant.meli_available_quantity = variation["available_quantity"]

        published_att_variants = False
        if (company.mercadolibre_update_existings_variants and 'variations' in rjson):
            published_att_variants = self._get_variations( rjson['variations'])

        #_logger.info("product_uom_id")
        product_uom_id = uomobj.search([('name','=','Unidad(es)')])
        if (product_uom_id.id==False):
            product_uom_id = 1
        else:
            product_uom_id = product_uom_id.id

        _product_id = product.id
        _product_name = product.name
        _product_meli_id = product.meli_id

        #this write pull the trigger for create_variant_ids()...
        #_logger.info("rewrite to create variants")
        if (company.mercadolibre_update_existings_variants):
            product_template.write({ 'attribute_line_ids': product_template.attribute_line_ids  })
        #_logger.info("published_att_variants:"+str(published_att_variants))
        if (published_att_variants):
            product_template.meli_pub_as_variant = True

            #_logger.info("Auto check product.template meli attributes to publish")
            for line in  product_template.attribute_line_ids:
                if (line.id not in product_template.meli_pub_variant_attributes.ids):
                    if (line.attribute_id.create_variant):
                        product_template.meli_pub_variant_attributes = [(4,line.id)]

            #_logger.info("check variants")
            for variant in product_template.product_variant_ids:
                #_logger.info("Created variant:")
                #_logger.info(variant)
                variant.meli_pub = product_template.meli_pub
                variant.meli_id = rjson['id']
                #variant.default_code = rjson['id']
                #variant.name = rjson['title'].encode("utf-8")
                has_sku = False

                _v_default_code = ""
                for att in att_value_ids(variant):
                    _v_default_code = _v_default_code + att.attribute_id.name+':'+att.name+';'
                #_logger.info("_v_default_code: " + _v_default_code)
                for variation in rjson['variations']:
                    #_logger.info(variation)
                    #_logger.info("variation[default_code]: " + variation["default_code"])
                    if (len(variation["default_code"]) and variant.is_variant_in_combination( variation["default_code"], _v_default_code )):
                        if ("seller_custom_field" in variation or "seller_sku" in variation):
                            #_logger.info("has_sku")
                            #_logger.info(variation["seller_custom_field"])
                            try:
                                variant.default_code = variation["seller_custom_field"] or variation["seller_sku"]
                            except:
                                pass;
                            variant.meli_id_variation = variation["id"]
                            has_sku = True
                        else:
                            variant.default_code = variant.meli_id+'-'+_v_default_code

                        if ("barcode" in variation):
                            try:
                                bcodes = self.env["product.product"].search([('barcode','=',variation["barcode"])])
                                if bcodes and len(bcodes):
                                    _logger.error("Error barcode already defined! "+str(variation["barcode"]))
                                else:
                                    variant.barcode = barcode
                            except:
                                pass;

                            variant.meli_id_variation = variation["id"]
                            has_sku = True
                        variant.meli_available_quantity = variation["available_quantity"]

                if (has_sku):
                    variant.set_bom()

                #_logger.info('meli_pub_principal_variant')
                #_logger.info(product_template.meli_pub_principal_variant.id)
                if (product_template.meli_pub_principal_variant.id is False):
                    #_logger.info("meli_pub_principal_variant set!")
                    product_template.meli_pub_principal_variant = variant
                    product = variant

                if (_product_id==variant.id):
                    product = variant
        else:
            #NO TIENE variantes pero tiene SKU
            seller_sku = None
            barcode = None

            if not seller_sku and "attributes" in rjson:
                for att in rjson['attributes']:
                    if att["id"] == "SELLER_SKU":
                        seller_sku = att["values"][0]["name"]
                    if att["id"] == "GTIN":
                        barcode = att["values"][0]["name"]

            if (not seller_sku and "seller_custom_field" in rjson):
                seller_sku = rjson["seller_custom_field"]

            if barcode and not product.barcode:
                try:
                    bcodes = self.env["product.product"].search([('barcode','=',barcode)])
                    if bcodes and len(bcodes):
                        _logger.error("Error barcode already defined! "+str(barcode))
                    else:
                        product.barcode = barcode
                except:
                    _logger.error("Error updating barcode")
                    pass;

            if seller_sku and not product.default_code:
                product.default_code = seller_sku
                product.set_bom()

        if (company.mercadolibre_update_local_stock):
            product_template.type = 'product'

            if (len(product_template.product_variant_ids)):
                for variant in product_template.product_variant_ids:

                    _product_id = variant.id
                    _product_name = variant.name
                    _product_meli_id = variant.meli_id

                    if (variant.meli_available_quantity != variant.virtual_available):
                        variant.product_update_stock(stock=variant.meli_available_quantity, meli=meli, config=company)
            else:
                product.product_update_stock(stock=product.meli_available_quantity, meli=meli, config=company)

        #assign envio/sin envio
        #si es (Con envio: Sí): asigna el meli_default_stock_product al producto sin envio (Con evio: No)
        if (b_search_nonfree_ship):
            ptemp_nfree = False
            ptpl_same_name = self.env['product.template'].search([('name','=',product_template.name),('id','!=',product_template.id)])
            #_logger.info("ptpl_same_name:"+product_template.name)
            #_logger.info(ptpl_same_name)
            if len(ptpl_same_name):
                for ptemp in ptpl_same_name:
                    #check if sin envio
                    #_logger.info(ptemp.name)
                    for line in ptemp.attribute_line_ids:
                        #_logger.info(line.attribute_id.name)
                        #_logger.info(line.value_ids)
                        es_con_envio = False
                        try:
                            line.attribute_id.name.index('Con env')
                            es_con_envio = True
                        except ValueError:
                            pass
                            #_logger.info("not con envio")
                        if (es_con_envio==True):
                            for att in line.value_ids:
                                #_logger.info(att.name)
                                if (att.name=='No'):
                                    #_logger.info("Founded")
                                    if (ptemp.meli_pub_principal_variant.id):
                                        #_logger.info("has meli_pub_principal_variant!")
                                        ptemp_nfree = ptemp.meli_pub_principal_variant
                                        if (ptemp_nfree.meli_default_stock_product):
                                            #_logger.info("has meli_default_stock_product!!!")
                                            ptemp_nfree = ptemp_nfree.meli_default_stock_product
                                    else:
                                        if (ptemp.product_variant_ids):
                                            if (len(ptemp.product_variant_ids)):
                                                ptemp_nfree = ptemp.product_variant_ids[0]

            if (ptemp_nfree):
                #_logger.info("Founded ptemp_nfree, assign to all variants")
                for variant in product_template.product_variant_ids:
                    variant.meli_default_stock_product = ptemp_nfree

        if (company.mercadolibre_update_existings_variants and 'attributes' in rjson):
            self._get_non_variant_attributes(rjson['attributes'])

        return {}

    def set_bom(self, has_sku=True):
        #generar lista de materiales si y ssi existe un producto CON ENVIO/SIN ENVIO
        # CONDICION: tener un
        variant = self
        product_template = self.product_tmpl_id
        uomobj = self.env[uom_model]
        if (not ("mrp.bom" in self.env)):
            #_logger.info("no module mrp.bom")
            #_logger.error("Must install Manufacturing Module")
            return {}
        bom = self.env["mrp.bom"]
        bom_l = self.env["mrp.bom.line"]
        #_logger.info("set bom: " + str(has_sku))

        product_uom_id = uomobj.search([('name','=','Unidad(es)')])
        if (product_uom_id.id==False):
            product_uom_id = 1
        else:
            product_uom_id = product_uom_id.id

        if (has_sku and variant.default_code and len(variant.default_code)>2):
            E_S = variant.default_code[-2:]
            #_logger.info("check sin envio code")
            #_logger.info(E_S)
            if (E_S=="CE" or E_S=="SE"):
                #buscamos el sin envio
                #_logger.info("buscamos sin envio")
                sin_envio = variant.default_code[0:-2] + 'SE'
                #_logger.info(sin_envio)
                #pse = self.env["product.product"].search([('default_code','=',sin_envio),('name','=',variant.name)])
                pse = self.env["product.product"].search([  ('default_code','=',sin_envio),
                                                            ('product_tmpl_id','!=',product_template.id),
                                                            ('meli_master','!=',False)])
                if (len(pse)==0):
                    pse = self.env["product.product"].search([  ('default_code','=',sin_envio),
                                                                ('product_tmpl_id','!=',product_template.id)])

                if (len(pse)>1):
                    #pse = pse[0]
                    pse_master = False
                    pmin = 10000
                    for ps in pse:
                        if ps.categ_id:
                            _logger.info("cat/name: ")
                            _logger.info(ps.categ_id.display_name)
                            _logger.info(ps.display_name)
                            #if (ps.categ_id.parent_id==False):
                            _pmin = len(ps.categ_id.display_name)+len(ps.display_name)
                            if (_pmin<pmin):
                                pmin = _pmin
                                pse_master = ps
                                _logger.info("Seleccionado!:" + str(ps.display_name))
                    pse = pse_master

                if (pse):
                    #_logger.info("SE encontrado: " + sin_envio)
                    # igualar stock
                    variant.meli_available_quantity = pse.meli_available_quantity
                    #_logger.info("SE meli_available_quantity: " + str(pse.meli_available_quantity))
                    bom_list = bom.search([('product_tmpl_id','=',product_template.id),('product_id','=',variant.id)])
                    if (bom_list):
                        #_logger.info("bom_list:")
                        #_logger.info(bom_list)
                        pass
                    else:
                        #lista de materiales: KIT (phantom)
                        bl_fields = {
                            "product_tmpl_id": product_template.id,
                            "product_id": variant.id,
                            "type": "phantom",
                            "product_qty": 1,
                            "product_uom_id": product_uom_id
                        }
                        bom_list = bom.create(bl_fields)
                        #_logger.info("bom_list created:")
                        #_logger.info(bom_list)

                    if (bom_list):
                        #check line ids
                        lineids = bom_l.search([('bom_id','=',bom_list.id)])
                        if (lineids):
                            #check if lineids is ok
                            bomline_fields = {
                                'product_id': pse.id
                            }
                            lineids.write(bomline_fields)
                        else:
                            bomline_fields = {
                                'bom_id': bom_list.id,
                                'product_id': pse.id,
                                'product_uom_id': product_uom_id,
                                'product_qty': 1.0
                            }
                            lineids = bom_l.create(bomline_fields)
                            #_logger.info("bom_list line created")
                        variant.meli_default_stock_product = pse
                else:
                    _logger.info("SE no existe?")


    def product_meli_login(self ):

        company = self.env.user.company_id

        meli = self.env['meli.util'].get_new_instance(company)
        if meli.need_login():
            return meli.redirect_login()

    def product_meli_status_close( self ):
        company = self.env.user.company_id
        product_obj = self.env['product.product']
        product = self

        meli = self.env['meli.util'].get_new_instance(company)
        if meli.need_login():
            return meli.redirect_login()

        response = meli.put("/items/"+product.meli_id, { 'status': 'closed' }, {'access_token':meli.access_token})

        return {}

    def product_meli_status_pause( self, meli=False ):
        company = self.env.user.company_id
        product_obj = self.env['product.product']
        product = self
        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)
            if meli.need_login():
                return meli.redirect_login()

        response = meli.put("/items/"+product.meli_id, { 'status': 'paused' }, {'access_token':meli.access_token})

        return {}

    def product_meli_status_active( self, meli=False ):
        company = self.env.user.company_id
        product_obj = self.env['product.product']

        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)
            if meli.need_login():
                return meli.redirect_login()

        if (meli):
            pass;
        else:
            return {}

        for product in self:
            _logger.info("activating "+str(product.meli_id))
            response = meli.put("/items/"+product.meli_id, { 'status': 'active' }, {'access_token':meli.access_token})
            if (response):
                _logger.info(response.json())
            else:
                _logger.info("product_meli_status_active error")
                _logger.info(response)

        return {}

    def product_meli_delete( self ):

        company = self.env.user.company_id
        product_obj = self.env['product.product']
        product = self

        if product.meli_status!='closed':
            self.product_meli_status_close()

        meli = self.env['meli.util'].get_new_instance(company)
        if meli.need_login():
            return meli.redirect_login()

        response = meli.put("/items/"+product.meli_id, { 'deleted': 'true' }, {'access_token':meli.access_token})

        rjson = response.json()
        _logger.info( rjson )
        ML_status = rjson["status"]
        if "error" in rjson:
            ML_status = rjson["error"]
        if "sub_status" in rjson:
            if len(rjson["sub_status"]) and rjson["sub_status"][0]=='deleted':
                product.write({ 'meli_id': '','meli_id_variation': '' })

        return {}

    def product_meli_upload_image( self, meli=False, config=False ):

        company = self.env.user.company_id
        config = config or company

        product_obj = self.env['product.product']
        product = self

        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)
            if meli.need_login():
                return meli.redirect_login()

        first_image_to_publish = get_first_image_to_publish( product )

        if first_image_to_publish==None or first_image_to_publish==False:
            return { 'status': 'error', 'message': 'no image to upload' }
        _logger.info("product_meli_upload_image: ")
        imagebin = base64.b64decode(first_image_to_publish)
        imageb64 = first_image_to_publish
        files = { 'file': ('image.jpg', imagebin, "image/jpeg"), }
        product_image = None
        try:
            hash = hashlib.blake2b()
            hash.update(imagebin)
            #product_image.meli_imagen_hash = hash.hexdigest()
            if (config.mercadolibre_do_not_use_first_image):
                product_image = variant_image_ids(product)[0]
                if (product_image):
                    product_image.meli_imagen_hash = hash.hexdigest()

        except:
            pass;
        response = meli.upload("/pictures", files, { 'access_token': meli.access_token } )

        rjson = response.json()
        if ("error" in rjson):
            #raise osv.except_osv( _('MELI WARNING'), _('No se pudo cargar la imagen en MELI! Error: %s , Mensaje: %s, Status: %s') % ( rjson["error"], rjson["message"],rjson["status"],))
            return rjson
            #return { 'status': 'error', 'message': 'not uploaded'}

        #_logger.info( rjson )

        if ("id" in rjson):
            #guardar id
            product.write( { "meli_imagen_id": rjson["id"], "meli_imagen_link": rjson["variations"][0]["url"] })
            if (product_image):
                product_image.meli_imagen_id = rjson["id"]
                product_image.meli_imagen_link = rjson["variations"][0]["secure_url"]
                product_image.meli_imagen_size = rjson["variations"][0]["size"]
            #asociar imagen a producto
            if product.meli_id:
                return rjson["id"]
                #response = meli.post("/items/"+product.meli_id+"/pictures", { 'id': rjson["id"] }, { 'access_token': meli.access_token } )
            else:
                return { 'status': 'warning', 'message': 'uploaded but not assigned' }

        return { 'status': 'success', 'message': 'uploaded and assigned' }

    def product_meli_upload_multi_images( self, meli=False, config=False  ):

        company = self.env.user.company_id
        config = config or company

        product_obj = self.env['product.product']
        product = self

        if variant_image_ids(product)==None and template_image_ids(product)==None:
            return { 'error': 'product_meli_upload_multi_images error no images to upload', 'status': 'error', 'message': 'no images to upload' }

        image_ids = []

        #loop over images
        var_image_ids = variant_image_ids(product)
        if (var_image_ids and len(var_image_ids)):
            for imix in range(0,len(var_image_ids)):
                if (company.mercadolibre_do_not_use_first_image and imix==0):
                    continue;
                _logger.info("Upload multi image var: "+str(imix))
                product_image = var_image_ids[imix]
                image_ids+= product._meli_upload_image( product_image, meli=meli, config=config )

        product.write( { "meli_multi_imagen_id": "%s" % (image_ids) } )

        #loop over images
        tpl_image_ids = template_image_ids(product)
        if (tpl_image_ids and len(tpl_image_ids)):
            for imix in range(0,len(tpl_image_ids)):
                if (company.mercadolibre_do_not_use_first_image and imix==0):
                    continue;
                _logger.info("Upload multi image tpl: "+str(imix))
                product_image = tpl_image_ids[imix]
                image_ids+= product._meli_upload_image( product_image, meli=meli, config=config )

        product.write( { "meli_multi_imagen_id": "%s" % (image_ids) } )

        return image_ids

    def _meli_upload_image( self, product_image, meli=False, config=False ):

        company = self.env.user.company_id
        config = config or company

        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)

        if meli and meli.need_login():
            return meli.redirect_login()

        image_ids = []
        if (get_image_full(product_image)):
            imagebin = base64.b64decode( get_image_full(product_image) )
            #files = { 'file': ('image.png', imagebin, "image/png"), }
            files = { 'file': ('image.jpg', imagebin, "image/jpeg"), }
            response = meli.upload("/pictures", files, { 'access_token': meli.access_token } )
            rjson = response.json()
            if ("error" in rjson):
                #raise osv.except_osv( _('MELI WARNING'), _('No se pudo cargar la imagen en MELI! Error: %s , Mensaje: %s, Status: %s') % ( rjson["error"], rjson["message"],rjson["status"],))
                return rjson
            else:
                image_ids+= [ { 'id': rjson['id'] }]
                #c = c + 1
                _logger.info( "image_ids:" + str(image_ids) )
                image_uploaded = {}
                ilink = ""
                isize = ""
                if ('variations' in rjson):
                    if (len(rjson['variations'])):
                        #big one, first one XXX-F
                        image_uploaded = rjson['variations'][0]
                else:
                    image_uploaded = rjson

                if 'secure_url' in image_uploaded:
                    ilink = image_uploaded['secure_url']
                if 'size' in image_uploaded:
                    isize = image_uploaded['size']

                product_image.meli_imagen_id = rjson['id']
                product_image.meli_imagen_max_size = rjson['max_size']
                product_image.meli_imagen_link = ilink
                product_image.meli_imagen_size = isize
                try:
                    hash = hashlib.blake2b()
                    hash.update(imagebin)
                    product_image.meli_imagen_hash = hash.hexdigest()
                except:
                    pass;

        return image_ids

    def product_on_change_meli_banner(self, banner_id ):

        banner_obj = self.env['mercadolibre.banner']

        #solo para saber si ya habia una descripcion completada
        product_obj = self.env['product.product']
        product = self
        banner = banner_obj.browse( banner_id )

        #banner.description
        _logger.info( banner.description )
        result = ""
        if (banner.description!="" and banner.description!=False and product.meli_imagen_link!=""):
            imgtag = "<img style='width: 420px; height: auto;' src='%s'/>" % ( product.meli_imagen_link )
            result = banner.description.replace( "[IMAGEN_PRODUCTO]", imgtag )
            if (result):
                _logger.info( "result: %s" % (result) )
            else:
                result = banner.description

        return { 'value': { 'meli_description' : result } }


    def product_get_meli_update( self ):
        #_logger.info("product_get_meli_update: " + str(self) )
        company = self.env.user.company_id
        warningobj = self.env['warning']
        product_obj = self.env['product.product']



        ML_status = "unknown"
        ML_sub_status = ""
        ML_permalink = ""
        ML_state = False
        #meli = None
        #self.meli_status = ML_status
        #self.meli_sub_status = ML_sub_status
        #self.meli_permalink = ML_permalink
        #self.meli_state = ML_state
        #return {}
        meli = self.env['meli.util'].get_new_instance(company)
        #if not meli.access_token:
        #    _logger.info("returning: "+str(meli))
            #return {}

        if meli and meli.need_login():
            ML_status = "unknown"
            ML_permalink = ""
            ML_state = True

        for product in self:
            if product.meli_id and meli and not meli.need_login():
                response = meli.get("/items/"+product.meli_id, {'access_token':meli.access_token} )
                rjson = response.json()
                if "status" in rjson:
                    ML_status = rjson["status"]
                if "permalink" in rjson:
                    ML_permalink = rjson["permalink"]
                if "error" in rjson:
                    ML_status = rjson["error"]
                    ML_permalink = ""
                if "sub_status" in rjson:
                    if len(rjson["sub_status"]):
                        ML_sub_status =  rjson["sub_status"][0]
                        if ( ML_sub_status =='deleted' ):
                            product.write({ 'meli_id': '','meli_id_variation': '' })

            product.meli_status = ML_status
            product.meli_sub_status = ML_sub_status
            product.meli_permalink = ML_permalink
            product.meli_state = ML_state

    def _is_value_excluded(self, att_value ):
        company = self.env.user.company_id
        if (company.mercadolibre_exclude_attributes):
            for att in company.mercadolibre_exclude_attributes:
                if (att.attribute_id.name == att_value.attribute_id.name):
                    if (att.name == att_value.name):
                        return True
        return False


    def _conditions_ok(self):
        conditionok = False
        product = self
        product_tmpl = self.product_tmpl_id

        att_to_pub = []
        for line in product_tmpl.meli_pub_variant_attributes:
            att_to_pub.append(line.attribute_id.name)
        #_logger.info(att_to_pub)

        for att in att_value_ids(product):
            if (att.attribute_id.name in att_to_pub):
                conditionok = True
            if (self._is_value_excluded(att)):
                product.meli_pub = False
                return False

        if (conditionok):
            product.meli_pub = True

        return conditionok

    #return all combinations for this product variants, based on tamplate attributes selected
    def _combination(self):
        var_comb = False
        product = self
        product_tmpl = self.product_tmpl_id

        att_to_pub = []
        for line in product_tmpl.meli_pub_variant_attributes:
            att_to_pub.append(line.attribute_id.name)

        if (len(att_to_pub)==0):
            return False

        price = False
        if (product.meli_price and float(product.meli_price)>0):
            price = product.meli_price
        qty = product.meli_available_quantity

        if (product_tmpl.meli_pub_principal_variant.id and price==False):
            price = product_tmpl.meli_pub_principal_variant.meli_price

        if (product_tmpl.meli_pub_principal_variant.id and (qty==False or qty==0)):
            qty = product_tmpl.meli_pub_principal_variant.meli_available_quantity

        if price==False:
            price = product.lst_price

        if (qty<0):
            qty = 0

        var_comb = {
            "attribute_combinations": [],
            "price": price,
            "available_quantity": qty,
        }
        if (product_tmpl.meli_pub_principal_variant.meli_imagen_id):
            if (len(product_tmpl.meli_pub_principal_variant.meli_imagen_id)):
               #TODO: picture for each variant
               var_comb["picture_ids"] = [ product_tmpl.meli_pub_principal_variant.meli_imagen_id]

        #customized attrs:
        customs = []
        for att in att_value_ids(product):
            if (att.attribute_id.name in att_to_pub):
                if (not att.attribute_id.meli_default_id_attribute.id):
                    customs.append(att)

        customs.sort(key=lambda x: x.attribute_id.name, reverse=True)
        sep = ""
        custom_name = ""
        custom_values = ""
        for att in customs:
            custom_name = custom_name + sep + att.attribute_id.name
            custom_values = custom_values + sep + att.name
            sep = "."

        if (len(customs)):
            att_combination = {
                "name": custom_name,
                "value_name": custom_values,
            }
            var_comb["attribute_combinations"].append(att_combination)

        for att in att_value_ids(product):
            if (att.attribute_id.name in att_to_pub):
                if (att.attribute_id.meli_default_id_attribute.id):
                    if (att.attribute_id.meli_default_id_attribute.variation_attribute):
                        att_combination = {
                            "name":att.attribute_id.meli_default_id_attribute.name,
                            "id": att.attribute_id.meli_default_id_attribute.att_id,
                            "value_name": att.name,
                        }
                        var_comb["attribute_combinations"].append(att_combination)

        return var_comb

    def _is_product_combination(self, variation ):

        var_comb = False
        product = self
        product_tmpl = self.product_tmpl_id

        #_logger.info("_is_product_combination:")
        #_logger.info(variation)

        _self_combinations = product._combination()
        _map_combinations = {}
        #_logger.info('_self_combinations')
        #_logger.info(_self_combinations)

        #create odoo internal analog combination dictionary to compare with ML
        if (_self_combinations and 'attribute_combinations' in _self_combinations):
            for att in _self_combinations['attribute_combinations']:
                #_logger.info(att)
                _map_combinations[att["name"]] = att["value_name"]

        #_logger.info('_map_combinations')
        #_logger.info(_map_combinations)

        _is_p_comb = True

        #compara atributo por atributo, valor del atributo exacto de ML con el de Odoo (TODO: specific ml attribute lines for ML template, one2one ML att/value maps )
        if ('attribute_combinations' in variation):
            #check if every att combination exist in this product
            for att in variation['attribute_combinations']:
                #_logger.info("chech att:"+str(att["name"]))
                if ( att["name"] in _map_combinations):
                    if (_map_combinations[att["name"]]==att["value_name"]):
                        _is_p_comb = True
                        #_logger.info(_is_p_comb)
                    else:
                        _is_p_comb = False
                        #_logger.info(_is_p_comb)
                        break
                else:
                    _is_p_comb = False
                    #_logger.info(_is_p_comb)
                    break

        return _is_p_comb

    def _validate_category_settings( self, body ):
        return body
        for product in self:
            if (product.meli_category and
                str(product.meli_category.meli_father_category_id) in ["MLA122201","MLA1540"]):
                body["price"] = None
                body["currency_id"] = None
                body["condition"] = None
                body["location"] = {
                    "address_line": "mi direccion 1111",
                    "city": {
                        "name": "Capital Federal"
                    },
                    "state": {
                        "name": "Capital Federal"
                    },
                    "country": {
                        "name": "Argentina"
                    }
                }
                return body

    def product_post_variant(self,variant_principal):

        _logger.debug('[DEBUG] product_post_variant, assign meli_id')
        #import pdb; pdb.set_trace()
        for product in self:
            product_tmpl = self.product_tmpl_id
            if (variant_principal):
                product.meli_id = variant_principal.meli_id

    #Add/Update SELLER_SKU attribute, only if present in Odoo, also can update GTIN (barcode)
    def _update_sku_attribute( self, attributes=[], set_sku=True, set_barcode=False ):

        variant = self

        updated_attributes = []
        sku_updated = False
        barcode_updated = False
        attributes = attributes or []

        for att in attributes:

            if (set_sku and "id" in att and att["id"]=="SELLER_SKU" and variant.default_code):
                sku_updated = True
                att = { "id": att["id"], "value_name": variant.default_code }

            elif (set_barcode and "id" in att and att["id"]=="GTIN" and variant.barcode):
                barcode_updated = True
                att = { "id": att["id"], "value_name": variant.barcode }

            updated_attributes.append(att)

        if not sku_updated and set_sku and variant.default_code:
            updated_attributes.append( { "id": "SELLER_SKU", "value_name": variant.default_code } )

        if not barcode_updated and set_barcode and variant.barcode:
            updated_attributes.append( { "id": "GTIN", "value_name": variant.barcode } )

        return updated_attributes

    def product_post(self):
        res = []
        for product in self:
            res.append(product._product_post())

        return res

    def _product_post( self, meli=None, config=None ):

        #import pdb;pdb.set_trace();
        _logger.info('[DEBUG] product_post')
        _logger.info("self.env.context:" + str(self.env.context))

        www_cats = False
        if 'product.public.category' in self.env:
            www_cats = self.env['product.public.category']

        product_obj = self.env['product.product']
        product_tpl_obj = self.env['product.template']
        product = self
        product_tmpl = self.product_tmpl_id
        company = self.env.user.company_id
        if not config:
            config = company
        warningobj = self.env['warning']

        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)
            if meli.need_login():
                return meli.redirect_login()
        #return {}
        #description_sale =  product_tmpl.description_sale
        translation = self.env['ir.translation'].search([('res_id','=',product_tmpl.id),
                                                        ('name','=','product.template,description_sale'),
                                                        ('lang','=','es_AR')])
        if translation:
            #_logger.info("translation")
            #_logger.info(translation.value)
            description_sale = translation.value

        productjson = False
        if (product.meli_id):
            response = meli.get("/items/%s" % product.meli_id, {'access_token':meli.access_token, 'include_attributes': 'all' })
            if (response):
                productjson = response.json()

        #check from company's default
        #_product_post_set_template_configuration
        if config.mercadolibre_listing_type and product_tmpl.meli_listing_type==False:
            product_tmpl.meli_listing_type = config.mercadolibre_listing_type

        if config.mercadolibre_currency and product_tmpl.meli_currency==False:
            product_tmpl.meli_currency = config.mercadolibre_currency

        if config.mercadolibre_condition and product_tmpl.meli_condition==False:
            product_tmpl.meli_condition = config.mercadolibre_condition

        if config.mercadolibre_warranty and product_tmpl.meli_warranty==False:
            product_tmpl.meli_warranty = config.mercadolibre_warranty

        if product_tmpl.meli_title==False or ( product_tmpl.meli_title and len(product_tmpl.meli_title)==0 ):
            product_tmpl.meli_title = product_tmpl.name

        if config.mercadolibre_buying_mode and product_tmpl.meli_buying_mode==False:
            product_tmpl.meli_buying_mode = config.mercadolibre_buying_mode

        #Si la descripcion de template esta vacia la asigna del description_sale
        force_template_description = ( config.mercadolibre_product_template_override_variant
                                        and config.mercadolibre_product_template_override_method
                                        and config.mercadolibre_product_template_override_method in ['default','description','title_and_description']
                                        )
        if force_template_description or product_tmpl.meli_description==False or ( product_tmpl.meli_description and len(product_tmpl.meli_description)==0):
            product_tmpl.meli_description = product_tmpl.description_sale

        #_product_post_set_title
        if (
            ( product.meli_title==False or len(product.meli_title)==0 )
            or
            ( product_tmpl.meli_pub_variant_attributes
                and not product_tmpl.meli_pub_as_variant
                    and len(product_tmpl.meli_pub_variant_attributes) )
            ):
            # _logger.info( 'Assigning title: product.meli_title: %s name: %s' % (product.meli_title, product.name) )
            product.meli_title = product_tmpl.meli_title
            if len(product_tmpl.meli_pub_variant_attributes):
                values = ""
                for line in product_tmpl.meli_pub_variant_attributes:
                    for value in att_value_ids(product):
                        if (value.attribute_id.id==line.attribute_id.id):
                            values+= " "+value.name
                if (not product_tmpl.meli_pub_as_variant):
                    product.meli_title = string.replace(product.meli_title,product.name,product.name+" "+values)

        force_template_title = ( config.mercadolibre_product_template_override_variant
                                 and config.mercadolibre_product_template_override_method
                                 and config.mercadolibre_product_template_override_method in ['title','title_and_description']
                                )

        if ( product_tmpl.meli_title and force_template_title):
            product.meli_title = product_tmpl.meli_title

        if ( product.meli_title and len(product.meli_title)>60 ):
            return warningobj.info( title='MELI WARNING', message="La longitud del título ("+str(len(product.meli_title))+") es superior a 60 caracteres.", message_html=product.meli_title )

        #_product_post_set_price
        product.set_meli_price(meli=meli,config=config)

        if product.meli_price==False or product.meli_price==0.0:
            if product_tmpl.meli_price:
                _logger.info("Assign tmpl price:"+str(product_tmpl.meli_price))
                product.meli_price = product_tmpl.meli_price

        #_product_post_set_base_configuration
        if product.meli_description==False or force_template_description:
            product.meli_description = product_tmpl.meli_description

        if (product_tmpl.meli_description and len(product_tmpl.meli_description)>=0):
            product.meli_description = product_tmpl.meli_description

        if product.meli_category==False:
            product.meli_category=product_tmpl.meli_category
        if product.meli_listing_type==False:
            product.meli_listing_type=product_tmpl.meli_listing_type

        if product_tmpl.meli_listing_type:
            product.meli_listing_type=product_tmpl.meli_listing_type

        if product.meli_buying_mode==False:
            product.meli_buying_mode=product_tmpl.meli_buying_mode

        if product_tmpl.meli_buying_mode:
            product.meli_buying_mode=product_tmpl.meli_buying_mode

        if product.meli_price==False:
            product.meli_price=product_tmpl.meli_price
        if product.meli_currency==False:
            product.meli_currency=product_tmpl.meli_currency
        if product.meli_condition==False:
            product.meli_condition=product_tmpl.meli_condition
        if product.meli_warranty==False:
            product.meli_warranty=product_tmpl.meli_warranty

        if product_tmpl.meli_warranty:
            product.meli_warranty=product_tmpl.meli_warranty

        if product.meli_brand==False or len(product.meli_brand)==0:
            product.meli_brand = product_tmpl.meli_brand
        if product.meli_model==False or len(product.meli_model)==0:
            product.meli_model = product_tmpl.meli_model
        if (product_tmpl.meli_brand):
            product.meli_brand = product_tmpl.meli_brand
        if (product_tmpl.meli_model):
            product.meli_model = product_tmpl.meli_model

        #_product_post_set_attributes
        attributes = []
        variations_candidates = False
        if product_tmpl.attribute_line_ids:
            _logger.info(product_tmpl.attribute_line_ids)
            for at_line_id in product_tmpl.attribute_line_ids:
                atname = at_line_id.attribute_id.name
                #atributos, no variantes! solo con un valor...
                if (len(at_line_id.value_ids)==1):
                    atval = at_line_id.value_ids.name
                    _logger.info(atname+":"+atval)
                    if (atname=="MARCA" or atname=="BRAND"):
                        attribute = { "id": "BRAND", "value_name": atval }
                        attributes.append(attribute)
                    if (atname=="MODELO" or atname=="MODEL"):
                        attribute = { "id": "MODEL", "value_name": atval }
                        attributes.append(attribute)

                    if (at_line_id.attribute_id.meli_default_id_attribute.id):
                        attribute = {
                            "id": at_line_id.attribute_id.meli_default_id_attribute.att_id,
                            "value_name": atval
                        }
                        attributes.append(attribute)
                elif (len(at_line_id.value_ids)>1):
                    variations_candidates = True

            _logger.info(attributes)
            product.meli_attributes = str(attributes)

        if product.meli_brand==False or len(product.meli_brand)==0:
            product.meli_brand = product_tmpl.meli_brand
        if product.meli_model==False or len(product.meli_model)==0:
            product.meli_model = product_tmpl.meli_model

        if product.meli_brand and len(product.meli_brand) > 0:
            attribute = { "id": "BRAND", "value_name": product.meli_brand }
            attributes.append(attribute)
            _logger.info(attributes)
            product.meli_attributes = str(attributes)

        if product.meli_model and len(product.meli_model) > 0:
            attribute = { "id": "MODEL", "value_name": product.meli_model }
            attributes.append(attribute)
            _logger.info(attributes)
            product.meli_attributes = str(attributes)

        #_product_post_set_category
        if www_cats:
            if product.public_categ_ids:
                for cat_id in product.public_categ_ids:
                    #_logger.info(cat_id)
                    if (cat_id.mercadolibre_category):
                        #_logger.info(cat_id.mercadolibre_category)
                        product.meli_category = cat_id.mercadolibre_category
                        product_tmpl.meli_category = cat_id.mercadolibre_category

        if product_tmpl.meli_category and not product.meli_category:
            product.meli_category = product_tmpl.meli_category

        #_product_post_set_quantity
        product.meli_available_quantity = product._meli_available_quantity(meli=meli,config=config)

        #_product_post_set_body
        body = {
            "title": product.meli_title or '',
            "category_id": product.meli_category.meli_category_id or '0',
            "listing_type_id": product.meli_listing_type or '0',
            "buying_mode": product.meli_buying_mode or '',
            "price": product.meli_price  or '0',
            "currency_id": product.meli_currency  or '0',
            "condition": product.meli_condition  or '',
            "available_quantity": product.meli_available_quantity  or '0',
            #"warranty": product.meli_warranty or '',
            "sale_terms":[
                 {
                    "id":"WARRANTY_TYPE",
                    "value_name":"Garantía del vendedor"
                 },
                 {
                    "id":"WARRANTY_TIME",
                    "value_name": product.meli_warranty
                 }
              ],
            #"pictures": [ { 'source': product.meli_imagen_logo} ] ,
            "video_id": product.meli_video  or '',
        }

        body = product._validate_category_settings( body )

        bodydescription = {
            "plain_text": product.meli_description or '',
        }
        # _logger.info( body )
        assign_img = False and product.meli_id

        #store id
        if config.mercadolibre_official_store_id:
            body["official_store_id"] = config.mercadolibre_official_store_id

        #publicando imagenes
        first_image_to_publish = get_first_image_to_publish( product )
        if (productjson and "pictures" in productjson):
            product._meli_remove_images_unsync( product_tmpl, productjson["pictures"] )

        if first_image_to_publish==None:
            return warningobj.info( title='MELI WARNING', message="Debe cargar una imagen de base en el producto, si chequeo el 'Dont use first image' debe al menos poner una imagen adicional en el producto.", message_html="" )
        else:
            # _logger.info( "try uploading image..." )
            resim = product.product_meli_upload_image(meli=meli,config=config)
            if "status" in resim:
                if (resim["status"]=="error" or resim["status"]=="warning"):
                    error_msg = 'MELI: mensaje de error:   ', resim
                    _logger.error(error_msg)
                    if (resim["status"]=="error"):
                        return warningobj.info( title='MELI WARNING', message="Problemas cargando la imagen principal.", message_html=error_msg )
                else:
                    assign_img = True and product.meli_imagen_id

        #modificando datos si ya existe el producto en MLA
        if (product.meli_id):
            body = {
                "title": product.meli_title or '',
                #"buying_mode": product.meli_buying_mode or '',
                "price": product.meli_price or '0',
                #"condition": product.meli_condition or '',
                "available_quantity": product.meli_available_quantity or '0',
                #"warranty": product.meli_warranty or '',
                "sale_terms":[
                     {
                        "id":"WARRANTY_TYPE",
                        "value_name":"Garantía del vendedor"
                     },
                     {
                        "id":"WARRANTY_TIME",
                        "value_name": product.meli_warranty
                     }
                  ],

                "pictures": [],
                "video_id": product.meli_video or '',
            }
            if (productjson):
                if ("attributes" in productjson):
                    if (len(attributes)):
                        dicatts = {}
                        for att in attributes:
                            dicatts[att["id"]] = att
                        attributes_ml =  productjson["attributes"]
                        x = 0
                        for att in attributes_ml:
                            if (att["id"] in dicatts):
                                attributes_ml[x] = dicatts[att["id"]]
                            else:
                                attributes.append(att)
                            x = x + 1

                        body["attributes"] =  attributes
                    else:
                        attributes =  productjson["attributes"]
                        body["attributes"] =  attributes
        else:
            body["description"] = bodydescription

        if len(attributes):
            body["attributes"] =  attributes

        #publicando multiples imagenes
        multi_images_ids = {}
        if (variant_image_ids(product) or template_image_ids(product)):
            multi_images_ids = product.product_meli_upload_multi_images(meli=meli,config=config)
            _logger.info(multi_images_ids)
            if 'status' in multi_images_ids:
                _logger.error(multi_images_ids)
                #return warningobj.info( title='MELI WARNING', message="Error publicando imagenes", message_html="Error: "+str(("error" in multi_images_ids and multi_images_ids["error"]) or "")+" Status:"+str(("status" in multi_images_ids and multi_images_ids["status"]) or "") )
                return warningobj.info( title='MELI WARNING', message="Error publicando imagenes", message_html="Error: "+str(multi_images_ids))

        #_product_post_set_body
        if product.meli_imagen_id:
            if 'pictures' in body.keys():
                body["pictures"] = [ { 'id': product.meli_imagen_id } ]
            else:
                body["pictures"] = [ { 'id': product.meli_imagen_id } ]

            if (multi_images_ids):
                if 'pictures' in body.keys():
                    body["pictures"]+= multi_images_ids
                else:
                    body["pictures"] = multi_images_ids

            if product.meli_imagen_logo:
                if 'pictures' in body.keys():
                    body["pictures"]+= [ { 'source': product.meli_imagen_logo} ]
                else:
                    body["pictures"] = [ { 'source': product.meli_imagen_logo} ]
        else:
            imagen_producto = ""

        if (not variations_candidates):
            if (product.default_code and config.mercadolibre_post_default_code):
                #SKU as attribute is default now
                attribute = { "id": "SELLER_SKU", "value_name": product.default_code }
                attributes.append(attribute)
                product.meli_attributes = str(attributes)
                body["seller_custom_field"] = product.default_code


        if (product_tmpl.meli_pub_as_variant):
            #es probablemente la variante principal
            if (product_tmpl.meli_pub_principal_variant.id):
                #esta definida la variante principal, veamos si es esta
                if (product_tmpl.meli_pub_principal_variant.id == product.id):
                    #esta es la variante principal, si aun el producto no se publico
                    #preparamos las variantes

                    if ( productjson and len(productjson["variations"]) ):
                        #ya hay variantes publicadas en ML
                        varias = {
                            "title": body["title"],
                            "pictures": body["pictures"],
                            "variations": []
                        }

                        #TODO: add pictures from real variant images
                        var_pics = []
                        if (len(body["pictures"])):
                            for pic in body["pictures"]:
                                var_pics.append(pic['id'])

                        _logger.info("Variations already posted, must update them only")
                        vars_updated = self.env["product.product"]
                        for ix in range(len(productjson["variations"]) ):
                            var_info = productjson["variations"][ix]
                            #_logger.info("Variation to update!!")
                            #_logger.info(var_info)
                            var_product = product
                            for pvar in product_tmpl.product_variant_ids:
                                if (pvar._is_product_combination(var_info)):
                                    var_product = pvar
                                    #upgrade variant stock
                                    var_product.meli_available_quantity = var_product._meli_available_quantity(meli=meli,config=config)
                                    vars_updated+=var_product
                            #TODO: add SKU
                            var_attributes = var_product._update_sku_attribute( attributes=("attributes" in var_info and var_info["attributes"]) or [], set_sku=config.mercadolibre_post_default_code)
                            var = {
                                "id": str(var_info["id"]),
                                "price": str(product_tmpl.meli_price),
                                "available_quantity": var_product.meli_available_quantity,
                                "picture_ids": var_pics,
                            }
                            var_attributes and var.update({"attributes": var_attributes })
                            varias["variations"].append(var)
                        #variations = product_tmpl._variations()
                        #varias["variations"] = variations
                        _all_variations = product_tmpl._variations(config=config)
                        _updated_ids = vars_updated.mapped('id')
                        _logger.info(_updated_ids)
                        _new_candidates = product_tmpl.product_variant_ids.filtered(lambda pv: pv.id not in _updated_ids)
                        _logger.info(_new_candidates)
                        if _all_variations:
                            for aix in range(len(_all_variations)):
                                var_info = _all_variations[aix]
                                for pvar in _new_candidates:
                                    if (pvar._is_product_combination(var_info)):
                                        var_attributes = pvar._update_sku_attribute( attributes=("attributes" in var_info and var_info["attributes"]), set_sku=config.mercadolibre_post_default_code )
                                        var_attributes and var_info.update({"attributes": var_attributes })
                                        varias["variations"].append(var_info)
                                        _logger.info("news:")
                                        _logger.info(var_info)

                        _logger.info(varias)
                        responsevar = meli.put("/items/"+product.meli_id, varias, {'access_token':meli.access_token})
                        rjsonv = responsevar.json()
                        _logger.info(rjsonv)
                        if ("error" in rjsonv):
                            error_msg = 'MELI RESP.: <h6>Mensaje de error</h6><br/><h6>Mensaje</h6> %s<br/><h6>Status</h6> %s<br/><h6>Cause</h6> %s<br/><h7>Error completo:</h7><span>%s</span><br/>' % (rjsonv["message"], rjsonv["status"], rjsonv["cause"], rjsonv["error"])
                            _logger.error(error_msg)
                            if (rjsonv["error"]=="forbidden"):
                                url_login_meli = meli.auth_url()
                                return warningobj.info( title='MELI WARNING', message="Debe iniciar sesión en MELI con el usuario correcto.", message_html="<br><br>"+error_msg)
                            else:
                                return warningobj.info( title='MELI WARNING', message="Completar todos los campos y revise el mensaje siguiente.", message_html="<br><br>"+error_msg )


                        if ("variations" in rjsonv):
                            for ix in range(len(rjsonv["variations"]) ):
                                _var = rjsonv["variations"][ix]
                                for pvar in product_tmpl.product_variant_ids:
                                    if (pvar._is_product_combination(_var) and 'id' in _var):
                                        pvar.meli_id_variation = _var["id"]
                                        pvar.meli_price = str(_var["price"])

                        #_logger.debug(responsevar.json())
                        resdes = meli.put("/items/"+product.meli_id+"/description", bodydescription, {'access_token':meli.access_token})
                        #_logger.debug(resdes.json())
                        del body['price']
                        del body['available_quantity']
                        resbody = meli.put("/items/"+product.meli_id, body, {'access_token':meli.access_token})
                        #_logger.debug(resbody.json())
                         #responsevar = meli.put("/items/"+product.meli_id, {"initial_quantity": product.meli_available_quantity, "available_quantity": product.meli_available_quantity }, {'access_token':meli.access_token})
                         #_logger.debug(responsevar)
                         #_logger.debug(responsevar.json())
                        return {}
                    else:
                        variations = product_tmpl._variations(config=config)
                        _logger.info("Variations:")
                        _logger.info(variations)
                        if (variations):
                            body["variations"] = variations
                else:
                    _logger.debug("Variant not able to post, variant principal.")
                    return {}
            else:
                _logger.debug("Variant principal not defined yet. Cannot post.")
                return {}
        else:
            if ( productjson and len(productjson["variations"])==1 ):
                varias = {
                    "title": body["title"],
                    "pictures": body["pictures"],
                    "variations": []
                }
                var_pics = []
                if (len(body["pictures"])):
                    for pic in body["pictures"]:
                        var_pics.append(pic['id'])
                _logger.info("Singl variation already posted, must update it")
                for ix in range(len(productjson["variations"]) ):
                    _logger.info("Variation to update!!")
                    _logger.info(productjson["variations"][ix])
                    var_info = {
                        "id": str(productjson["variations"][ix]["id"]),
                        "price": str(product_tmpl.meli_price),
                        "available_quantity": product.meli_available_quantity,
                        "picture_ids": var_pics
                    }
                    var_attributes = product._update_sku_attribute( attributes=("attributes" in var_info and var_info["attributes"]), set_sku=config.mercadolibre_post_default_code )
                    var_attributes and var.update({"attributes": var_attributes })
                    varias["variations"].append(var_info)

                    #WARNING: only for single variation
                    product.meli_id_variation = productjson["variations"][ix]["id"]
                #variations = product_tmpl._variations()
                #varias["variations"] = variations

                _logger.info(varias)
                responsevar = meli.put("/items/"+product.meli_id, varias, {'access_token':meli.access_token})
                _logger.info(responsevar.json())
                #_logger.debug(responsevar.json())
                resdes = meli.put("/items/"+product.meli_id+"/description", bodydescription, {'access_token':meli.access_token})
                #_logger.debug(resdes.json())
                del body['price']
                del body['available_quantity']
                resbody = meli.put("/items/"+product.meli_id, body, {'access_token':meli.access_token})
                return {}

        #check fields
        if (product.meli_description==False or ( product.meli_description and len(product.meli_description)==0) ):
            return warningobj.info(title='MELI WARNING', message="Debe completar el campo description en la plantilla de MercadoLibre o del producto (Descripción de Ventas)", message_html="<h3>Descripción faltante</h3>")

        #free shipping
        # https://api.mercadolibre.com/users/{user_id}/shipping_modes?category_id={category_id}&item_price=550

        if product.meli_id:
            _logger.info("update post:"+str(body))
            response = meli.put("/items/"+product.meli_id, body, {'access_token':meli.access_token})
            resdescription = meli.put("/items/"+product.meli_id+"/description", bodydescription, {'access_token':meli.access_token})
            rjsondes = resdescription.json()
        else:
            assign_img = True and product.meli_imagen_id
            _logger.info("first post:" + str(body))
            response = meli.post("/items", body, {'access_token':meli.access_token})

        #check response
        # _logger.info( response )
        rjson = response.json()
        _logger.info(rjson)

        #check error
        if "error" in rjson:
            #error_msg = '<h6>Mensaje de error de MercadoLibre: %s; status: %s </h6><h2>Mensaje: %s</h2><br/><h6>Cause: </h6> %s' % (rjson["error"], rjson["status"], rjson["message"], rjson["cause"])
            error_msg = '<h6>Mensaje de error de MercadoLibre</h6><br/><h2>Mensaje: %s</h2><br/><h6>Status</h6> %s<br/><h6>Cause</h6> %s<br/><h6>Error completo:</h6><br/><span>%s</span><br/>' % (rjson["message"], rjson["status"], rjson["cause"], rjson["error"])
            _logger.error(error_msg)
            if (rjson["cause"] and rjson["cause"][0] and "message" in rjson["cause"][0]):
                error_msg+= '<h3>'+str(rjson["cause"][0]["message"])+'</h3>'
            #expired token
            if "message" in rjson and (rjson["error"]=="forbidden" or rjson["message"]=='invalid_token' or rjson["message"]=="expired_token"):
                url_login_meli = meli.auth_url()
                return warningobj.info( title='MELI WARNING', message="Debe iniciar sesión en MELI:  "+str(rjson["message"]), message_html="<br><br>"+error_msg)
            else:
                 #Any other errors
                return warningobj.info( title='MELI WARNING', message="Recuerde completar todos los campos y revise el mensaje siguiente.", message_html="<br><br>"+error_msg )

        #last modifications if response is OK
        if "id" in rjson:
            product.write( { 'meli_id': rjson["id"]} )
            if ("variations" in rjson):
                for ix in range(len(rjson["variations"]) ):
                    _var = rjson["variations"][ix]
                    for pvar in product_tmpl.product_variant_ids:
                        if (pvar._is_product_combination(_var) and 'id' in _var):
                            pvar.meli_id_variation = _var["id"]


        posting_fields = {'posting_date': str(datetime.now()),'meli_id': product.meli_id,'product_id':product.id,'name': 'Post: ' + product.meli_title }

        posting = self.env['mercadolibre.posting'].search( [('meli_id','=',product.meli_id)])
        posting_id = posting.id

        if not posting_id:
            posting_id = self.env['mercadolibre.posting'].create((posting_fields)).id
        else:
            posting.write(( { 'product_id':product.id, 'name': 'Post: ' + product.meli_title }))

        force_meli_active = False
        if ("force_meli_active" in self.env.context):
            force_meli_active = self.env.context.get("force_meli_active")
        if (force_meli_active==True):
            product.product_meli_status_active()

        return {}

    def _meli_available_quantity( self, meli=False, config=None ):

        product = self
        product_tmpl = product.product_tmpl_id
        new_meli_available_quantity = product.meli_available_quantity

        if (product.virtual_available):
            if (product.virtual_available>=0):
                new_meli_available_quantity = product.virtual_available

        # Chequea si es fabricable
        product_fab = False
        if (1==1 and product.virtual_available<=0 and product.route_ids):
            for route in product.route_ids:
                if (route.name in ['Fabricar','Manufacture']):
                    #raise ValidationError("Fabricar")
                    #product.meli_available_quantity = product.meli_available_quantity
                    _logger.info("Fabricar:"+str(new_meli_available_quantity))
                    product_fab = True
            if (not product_fab and product.virtual_available==0):
                new_meli_available_quantity = product.virtual_available

        if (1==2 and 'mrp.bom' in self.env and new_meli_available_quantity<=10000):
            bom_id = self.env['mrp.bom'].search([('product_id','=',product.id)],limit=1)
            if bom_id and bom_id.type == 'phantom':
                _logger.info(bom_id.type)
                #chequear si el componente principal es fabricable
                for bom_line in bom_id.bom_line_ids:
                    if (bom_line.product_id.default_code.find(product_tmpl.code_prefix)==0):
                        _logger.info(product_tmpl.code_prefix)
                        _logger.info(bom_line.product_id.default_code)
                        for route in bom_line.product_id.route_ids:
                            if (route.name in ['Fabricar','Manufacture']):
                                _logger.info("Fabricar")
                                new_meli_available_quantity = 1
                            if (route.name in ['Comprar','Buy']):
                                _logger.info("Comprar")
                                new_meli_available_quantity = bom_line.product_id.virtual_available

        return new_meli_available_quantity

    def product_post_stock( self, context=None, meli=False, config=None ):
        context = context or self.env.context
        _logger.info("meli_oerp product_post_stock context: " + str(context))
        company = self.env.user.company_id
        warningobj = self.env['warning']

        product_obj = self.env['product.product']
        product = self
        product_tmpl = self.product_tmpl_id
        config = config or company

        if not meli or not hasattr(meli, 'client_id'):
            meli = self.env['meli.util'].get_new_instance(company)
            if meli.need_login():
                return meli.redirect_login()

        product.meli_stock_update = ml_datetime(datetime.now())
        product_tmpl.meli_stock_update = product.meli_stock_update

        if "meli_update_stock_blocked" in product_tmpl._fields and product_tmpl.meli_update_stock_blocked:
            error = { "error": "Blocked by product template configuration." }
            product.meli_stock_error = str(error)
            product_tmpl.meli_stock_error = product.meli_stock_error
            return error

        if "meli_update_stock_blocked" in product._fields and product.meli_update_stock_blocked:
            error = { "error": "Blocked by product configuration." }
            product.meli_stock_error = str(error)
            product_tmpl.meli_stock_error = product.meli_stock_error
            return error

        try:
            #self.product_update_stock()
            product_fab = False
            if (1==1 and product.virtual_available<=0 and product.route_ids):
                for route in product.route_ids:
                    if (route.name in ['Fabricar','Manufacture']):
                        _logger.info("Fabricar:"+str(product.meli_available_quantity))
                        product_fab = True

            if (not product_fab):
                product.meli_available_quantity = product._meli_available_quantity(meli=meli,config=config)

            if product.meli_available_quantity<0:
                product.meli_available_quantity = 0

            fields = {
                "available_quantity": product.meli_available_quantity
            }

            _logger.info("post stock:"+str(product.meli_available_quantity))
            #_logger.info("product_tmpl.meli_pub_as_variant:"+str(product_tmpl.meli_pub_as_variant))
            #_logger.info(product_tmpl.meli_pub_principal_variant.id)
            if (product_tmpl.meli_pub_as_variant):
                productjson = False
                if (product_tmpl.meli_pub_principal_variant.id==False and len(product_tmpl.product_variant_ids)):
                    product_tmpl.meli_pub_principal_variant = product_tmpl.product_variant_ids[0]

                if (product_tmpl.meli_pub_principal_variant.id):
                    base_meli_id = product_tmpl.meli_pub_principal_variant.meli_id
                    if (base_meli_id):
                        response = meli.get("/items/%s" % base_meli_id, {'access_token':meli.access_token, 'include_attributes': 'all'})
                        if (response):
                            productjson = response.json()

                #chequeamos la variacion de este producto
                if ( productjson and "variations" in productjson and len(productjson["variations"]) ):
                    varias = {
                        "variations": []
                    }
                    _logger.info("product_post_stock > Update variations stock")
                    found_comb = False
                    pictures_v = []
                    same_price = False
                    for ix in range(len(productjson["variations"]) ):
                        #check if combination is related to this product
                        if 'picture_ids' in productjson["variations"][ix]:
                            if (len(productjson["variations"][ix]["picture_ids"])>len(pictures_v)):
                                pictures_v = productjson["variations"][ix]["picture_ids"]
                        same_price = productjson["variations"][ix]["price"]
                        #_logger.info(productjson["variations"][ix])
                        if (self._is_product_combination(productjson["variations"][ix])):
                            #_logger.info("_is_product_combination! Post stock to variation")
                            #_logger.info(productjson["variations"][ix])
                            found_comb = True
                            #reset meli_id_variation (TODO: resetting must be done outside)
                            product.meli_id_variation = productjson["variations"][ix]["id"]
                            var = {
                                #"id": str( product.meli_id_variation ),
                                "available_quantity": product.meli_available_quantity,
                                #"picture_ids": ['806634-MLM28112717071_092018', '928808-MLM28112717068_092018', '643737-MLM28112717069_092018', '934652-MLM28112717070_092018']
                            }
                            varias["variations"].append(var)
                            #_logger.info(varias)
                            #_logger.info(var)
                            responsevar = meli.put("/items/"+product.meli_id+'/variations/'+str( product.meli_id_variation ), var, {'access_token':meli.access_token})
                            #_logger.info(responsevar.json())
                            if responsevar:
                                rjson = responsevar.json()
                                if rjson:
                                    if "error" in rjson:
                                        _logger.error(rjson)
                                        error = rjson
                                        product.meli_stock_error = str(error)
                                        product_tmpl.meli_stock_error = product.meli_stock_error
                                        return error

                    if found_comb==False:
                        #add combination!!
                        #_logger.info("add combination")
                        addvar = self._combination()
                        #_logger.info(addvar)
                        if addvar:
                            if ('picture_ids' in addvar):
                                if len(pictures_v)>=len(addvar["picture_ids"]):
                                    addvar["picture_ids"] = pictures_v
                            if (config.mercadolibre_post_default_code): #TODO: fixing SKU must be specific parameter
                                addvar["seller_custom_field"] = product.default_code
                            addvar["price"] = same_price
                            #_logger.info("Add variation!")
                            #_logger.info(addvar)
                            responsevar = meli.post("/items/"+product.meli_id+"/variations", addvar, {'access_token':meli.access_token})
                            if responsevar:
                                rjson = responsevar.json()
                                if rjson:
                                    if "error" in rjson:
                                        error = rjson
                                        product.meli_stock_error = str(error)
                                        product_tmpl.meli_stock_error = product.meli_stock_error
                                        return error
                            #_logger.info(responsevar.json())
                #_logger.info("Available:"+str(product_tmpl.virtual_available))
                best_available = 0
                for vr in product_tmpl.product_variant_ids:
                    sum = vr.meli_available_quantity
                    if (sum<0):
                        sum = 0
                    best_available+= sum
                if (best_available>0 and product.meli_status=="paused"):
                    _logger.info("Active!")
                    product.product_meli_status_active()
                elif (best_available<=0 and product.meli_status=="active"):
                    _logger.info("Pause!")
                    product.product_meli_status_pause()
            else:
                if (product.meli_id and not product.meli_id_variation):
                    #_logger.info("meli:"+str(meli))
                    response = meli.get("/items/%s" % product.meli_id, {'access_token':meli.access_token})
                    if (response):
                        pjson = response.json()
                        if "variations" in pjson:
                            if (len(pjson["variations"])==1):
                                product.meli_id_variation = pjson["variations"][0]["id"]

                if (product.meli_id_variation):
                    #_logger.info("Posting using product.meli_id_variation")
                    var = {
                        #"id": str( product.meli_id_variation ),
                        "available_quantity": product.meli_available_quantity,
                        #"picture_ids": ['806634-MLM28112717071_092018', '928808-MLM28112717068_092018', '643737-MLM28112717069_092018', '934652-MLM28112717070_092018']
                    }
                    responsevar = meli.put("/items/"+product.meli_id+'/variations/'+str( product.meli_id_variation ), var, {'access_token':meli.access_token})
                    if (responsevar):
                        rjson = responsevar.json()
                        if rjson:
                            _logger.info(rjson)
                            if ('available_quantity' in rjson):
                                _logger.info( "Posted ok:" + str(rjson['available_quantity']) )
                            if "error" in rjson:
                                error = rjson
                                product.meli_stock_error = str(error)
                                product_tmpl.meli_stock_error = product.meli_stock_error
                                return error
                else:
                    response = meli.put("/items/"+product.meli_id, fields, {'access_token':meli.access_token})
                    if (response):
                        rjson = response.json()
                        if ('available_quantity' in rjson):
                            _logger.info( "Posted ok:" + str(rjson['available_quantity']) )
                        if "error" in rjson:
                            error = rjson
                            product.meli_stock_error = str(error)
                            product_tmpl.meli_stock_error = product.meli_stock_error
                            return error

                if (product.meli_available_quantity<=0 and product.meli_status=="active"):
                    product.product_meli_status_pause(meli=meli)
                elif (product.meli_available_quantity>0 and product.meli_status=="paused"):
                    product.product_meli_status_active(meli=meli)

        except Exception as e:
            _logger.info("product_post_stock > exception error")
            _logger.info(e, exc_info=True)
            error = { 'error': str(e) }
            product.meli_stock_error = str(error)
            product_tmpl.meli_stock_error = product.meli_stock_error
            pass;

        return {}

    #update internal product stock based on meli_default_stock_product
    def product_update_stock(self, stock=False, meli=False, config=None):
        product = self
        uomobj = self.env[uom_model]
        _stock = product.virtual_available

        try:
            if (stock!=False):
                _stock = stock
                if (_stock<0):
                    _stock = 0

            if (product.default_code):
                product.set_bom()

            if (product.meli_default_stock_product):
                _stock = product.meli_default_stock_product._meli_available_quantity(meli=meli,config=config)
                if (_stock<0):
                    _stock = 0

            if (1==2 and _stock>=0 and product._meli_available_quantity(meli=meli,config=config)!=_stock):
                _logger.info("Updating stock for variant." + str(_stock) )
                wh = self.env['stock.location'].search([('usage','=','internal')]).id
                product_uom_id = uomobj.search([('name','=','Unidad(es)')])
                if (product_uom_id.id==False):
                    product_uom_id = 1
                else:
                    product_uom_id = product_uom_id.id

                stock_inventory_fields = get_inventory_fields(product, wh)

                #_logger.info("stock_inventory_fields:")
                #_logger.info(stock_inventory_fields)
                StockInventory = self.env['stock.inventory'].create(stock_inventory_fields)
                #_logger.info("StockInventory:")
                #_logger.info(StockInventory)
                if (StockInventory):
                    stock_inventory_field_line = {
                        "product_qty": _stock,
                        'theoretical_qty': 0,
                        "product_id": product.id,
                        "product_uom_id": product_uom_id,
                        "location_id": wh,
                        'inventory_location_id': wh,
                        "inventory_id": StockInventory.id,
                        #"name": "INV "+ nombre
                        #"state": "confirm",
                    }
                    StockInventoryLine = self.env['stock.inventory.line'].create(stock_inventory_field_line)
                    #print "StockInventoryLine:", StockInventoryLine, stock_inventory_field_line
                    #_logger.info("StockInventoryLine:")
                    #_logger.info(stock_inventory_field_line)
                    if (StockInventoryLine):
                        return_id = stock_inventory_action_done(StockInventory)
                        #_logger.info("action_done:"+str(return_id))
        except Exception as e:
            _logger.info("product_update_stock Exception")
            _logger.info(e, exc_info=True)


    def product_post_price(self, context=None, meli=None):
        context = context or self.env.context
        #company = get_company_selected( self, context=context )

        warningobj = self.env['warning']

        product_obj = self.env['product.product']
        product = self
        product_tmpl = self.product_tmpl_id

        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)
            if meli.need_login():
                return meli.redirect_login()

        product.set_meli_price()

        fields = {
            "price": product.meli_price
        }

        if (product.meli_id and not product.meli_id_variation):
            #_logger.info("meli:"+str(meli))
            response = meli.get("/items/%s" % product.meli_id, {'access_token':meli.access_token})
            if (response):
                pjson = response.json()
                if "variations" in pjson:
                    if (len(pjson["variations"])==1):
                        product.meli_id_variation = pjson["variations"][0]["id"]

        if (product.meli_id_variation):
            #_logger.info("Posting using product.meli_id_variation")
            var = {
                #"id": str( product.meli_id_variation ),
                "price": product.meli_price,
                #"picture_ids": ['806634-MLM28112717071_092018', '928808-MLM28112717068_092018', '643737-MLM28112717069_092018', '934652-MLM28112717070_092018']
            }
            responsevar = meli.put("/items/"+product.meli_id+'/variations/'+str( product.meli_id_variation ), var, {'access_token':meli.access_token})
            if (responsevar):
                rjson = responsevar.json()
                if rjson:
                    #_logger.info(rjson)
                    if (len(rjson) and rjson[0] and 'price' in rjson[0]):
                        _logger.info( "Posted price ok " + str(product.meli_id) + ": " + str(rjson[0]['price']) )
                    if "error" in rjson:
                        _logger.error(rjson)
                        return rjson
        else:
            _logger.info("product_post_price:"+str(fields))
            response = meli.put("/items/"+product.meli_id, fields, {'access_token':meli.access_token})
            if response:
                rjson = response.json()
                if "error" in rjson:
                    _logger.error(rjson)
                    return rjson
        return {}

    def get_title_for_meli(self):
        return self.name

    def action_category_predictor(self):
        return self.product_tmpl_id.action_category_predictor()

    @api.onchange('meli_id') # if these fields are changed, call method
    def change_meli_id(self):
        for p in self:
            if p.product_tmpl_id:
                p.product_tmpl_id.update_meli_ids()

    #typical values
    meli_title = fields.Char(string='Nombre del producto en Mercado Libre',size=256)
    meli_description = fields.Text(string='Descripción')
    meli_category = fields.Many2one("mercadolibre.category","Categoría de MercadoLibre")
    meli_price = fields.Char( string='Precio',help='Precio de venta en ML', size=128)
    meli_dimensions = fields.Char( string="Dimensiones del producto", size=128)
    meli_pub = fields.Boolean('Meli Publication',help='MELI Product',index=True)

    meli_buying_mode = fields.Selection( [("buy_it_now","Compre ahora"),("classified","Clasificado")], string='Método de compra')
    meli_currency = fields.Selection([("ARS","Peso Argentino (ARS)"),
                                        ("MXN","Peso Mexicano (MXN)"),
                                        ("COP","Peso Colombiano (COP)"),
                                        ("PEN","Sol Peruano (PEN)"),
                                        ("BOB","Boliviano (BOB)"),
                                        ("BRL","Real (BRL)"),
                                        ("CLP","Peso Chileno (CLP)"),
                                        ("CRC","Colon Costarricense (CRC)"),
                                        ("UYU","Peso Uruguayo (UYU)"),
                                        ("USD","Dolar Estadounidense (USD)")],
                                        string='Moneda')
    meli_condition = fields.Selection([ ("new", "Nuevo"), ("used", "Usado"), ("not_specified","No especificado")],'Condición del producto')
    meli_warranty = fields.Char(string='Garantía', size=256)
    meli_listing_type = fields.Selection([("free","Libre"),("bronze","Bronce"),("silver","Plata"),("gold","Oro"),("gold_premium","Gold Premium"),("gold_special","Gold Special/Clásica"),("gold_pro","Oro Pro")], string='Tipo de lista')

    #post only fields
    meli_post_required = fields.Boolean(string='Publicable', help='Este producto es publicable en Mercado Libre')
    meli_id = fields.Char(string='ML Id', help='Id del item asignado por Meli', size=256, index=True)
    meli_description_banner_id = fields.Many2one("mercadolibre.banner","Banner")
    meli_buying_mode = fields.Selection(string='Método',help='Método de compra',selection=[("buy_it_now","Compre ahora"),("classified","Clasificado")])
    meli_price_fixed = fields.Boolean(string='Price is fixed')
    meli_available_quantity = fields.Integer(string='Cantidades', help='Cantidad disponible a publicar en ML')
    meli_imagen_logo = fields.Char(string='Imagen Logo', size=256)
    meli_imagen_id = fields.Char(string='Imagen Id', size=256)
    meli_imagen_link = fields.Char(string='Imagen Link', size=256)
    meli_imagen_hash = fields.Char(string='Imagen Hash')
    meli_multi_imagen_id = fields.Char(string='Multi Imagen Ids', size=512)
    meli_video = fields.Char( string='Video (id de youtube)', size=256)

    meli_permalink = fields.Char( compute=product_get_meli_update, size=256, string='Link',help='PermaLink in MercadoLibre' )
    meli_state = fields.Boolean( compute=product_get_meli_update, string='Login',help="Inicio de sesión requerida" )
    meli_status = fields.Char( compute=product_get_meli_update, size=128, string='Status', help="Estado del producto en ML" )
    meli_sub_status = fields.Char( compute=product_get_meli_update, size=128, string='Sub status',help="Sub Estado del producto en ML" )

    meli_attributes = fields.Text(string='Atributos')

    meli_model = fields.Char(string="Modelo",size=256)
    meli_brand = fields.Char(string="Marca",size=256)
    meli_default_stock_product = fields.Many2one("product.product","Producto de referencia para stock")
    meli_id_variation = fields.Char( string='Variation Id',help='Id de Variante de Meli', size=256)

    meli_catalog_listing = fields.Boolean(string='Catalog Listing', size=256)
    meli_catalog_product_id = fields.Char(string='Catalog Product Id', size=256)
    meli_catalog_item_relations = fields.Char(string='Catalog Item Relations', size=256)
    meli_catalog_automatic_relist = fields.Boolean(string='Catalog Auto Relist', size=256)

    meli_shipping_logistic_type = fields.Char(string="Logistic Type",index=True)

    meli_inventory_id = fields.Char(string="Inventory Id",index=True)

    meli_shipping_mode = fields.Char(string="Shipping Mode",help="Shipping modes (por usuario): custom, not_specified, me2. https://api.mercadolibre.com/users/USERID/shipping_preferences",index=True)
    meli_shipping_method = fields.Char(string="Shipping Method",help="Shipping methods: https://api.mercadolibre.com/sites/SITEID/shipping_methods",index=True)

    meli_full_update = fields.Datetime(string="Product update",index=True)
    meli_image_update = fields.Datetime(string="Image update",index=True)
    meli_price_update = fields.Datetime(string="Price update",index=True)
    meli_stock_update = fields.Datetime(string="Stock update",index=True)

    meli_stock_error = fields.Char(string="Stock Error",index=True)
    meli_price_error = fields.Char(string="Price Error",index=True)
    meli_update_error = fields.Char(string="Update Error",index=True)

    meli_update_stock_blocked = fields.Boolean(string="Block Update stock",default=False)

    _defaults = {
        'meli_imagen_logo': 'None',
        'meli_video': ''
    }

    _sql_constraints = [
    #    ('unique_variant_meli_id_variation', 'unique(meli_id,meli_id_variation)', 'Meli Id, Meli Id Variation must be unique!'),
    ]

product_product()
