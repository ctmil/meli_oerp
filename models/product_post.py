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

from odoo import fields, osv, models, _
from odoo.tools.translate import _
import pdb
import logging
_logger = logging.getLogger(__name__)

import json
from datetime import datetime

#from bottle import Bottle, run, template, route, request
#import json
from .meli_oerp_config import *

from .warning import warning

from ..melisdk.meli import Meli

class product_template_post(models.TransientModel):
    _name = "mercadolibre.product.template.post"
    _description = "Wizard de Product Template Posting en MercadoLibre"

    force_meli_pub = fields.Boolean(string="Marcar para publicar",help="Marcar producto y sus variantes para publicación en ML, y de todos los seleccionados",default=False)
    force_meli_active = fields.Boolean(string="Activación",help="Activa en ML las publicaciones de todos los productos seleccionados",default=False)
    type = fields.Selection([('post','Alta'),('put','Editado'),('delete','Borrado')], string='Tipo de operación' )
    posting_date = fields.Date('Fecha del posting')
    #'company_id': fields.many2one('res.company',string='Company'),
    #'mercadolibre_state': fields.related( 'res.company', 'mercadolibre_state', string="State" )
    post_stock = fields.Boolean(string="Actualizar Stock",help="No actualiza el producto completo, solo el stock",default=False)
    post_price = fields.Boolean(string="Acutalizar Precio",help="No actualiza el producto completo, solo el precio",default=False)


    def pretty_json( self, data ):
        return json.dumps( data, sort_keys=False, indent=4 )

    def product_template_post(self, context=None):

        context = context or self.env.context
        company = self.env.user.company_id
        product_ids = ('active_ids' in context and context['active_ids']) or []
        product_obj = self.env['product.template']

        warningobj = self.env['meli.warning']

        meli = self.env['meli.util'].get_new_instance(company)
        if meli.need_login():
            return meli.redirect_login()

        res = {}
        _logger.info("context in product_template_post:")
        _logger.info(self.env.context)
        custom_context = {
            'force_meli_pub': self.force_meli_pub,
            'force_meli_active': self.force_meli_active,
            'post_stock': self.post_stock,
            'post_price': self.post_price
        }
        posted_products = 0
        for product_id in product_ids:
            product = product_obj.browse(product_id)
            if (product):
                if (self.force_meli_pub and not product.meli_pub):
                    product.meli_pub = True
                if (product.meli_pub):

                    if self.post_stock:
                        res = product.with_context(custom_context).product_template_post_stock(meli=meli)
                    if self.post_price:
                        res = product.with_context(custom_context).product_template_post_price(meli=meli)
                    if not self.post_stock and not self.post_price:
                        res = product.with_context(custom_context).product_template_post()

                    if (res and 'name' in res):
                        return res

                    posted_products+=1

        if (posted_products==0 and not 'name' in res):
            res = warningobj.info( title='MELI WARNING', message="Se intentaron publicar 0 productos. Debe forzar las publicaciones o marcar el producto con el campo Meli Publication, debajo del titulo.", message_html="" )

        return res

product_template_post()

class product_template_update(models.TransientModel):
    _name = "mercadolibre.product.template.update"
    _description = "Wizard de Product Template Update en MercadoLibre"

    force_meli_pub = fields.Boolean(string="Forzar importación",help="Forzar importación de todos los seleccionados",default=False)
    type = fields.Selection([('post','Alta'),('put','Editado'),('delete','Borrado')], string='Tipo de operación' )
    posting_date = fields.Date('Fecha del posting')

    meli_id = fields.Char(string="MercadoLibre Id (MLMXXXXXXX) a importar.")
    force_create_variants = fields.Boolean(string="Forzar creacion/cambios de variantes",help="Forzar creacion de variantes (Modifica el producto de Odoo / Rompe Stock)",default=False)

	    #'company_id': fields.many2one('res.company',string='Company'),
	    #'mercadolibre_state': fields.related( 'res.company', 'mercadolibre_state', string="State" )


    def pretty_json( self, data ):
        return json.dumps( data, sort_keys=False, indent=4 )

    def product_template_update(self, context=None):
        context = context or self.env.context
        company = self.env.user.company_id
        product_ids = ('active_ids' in context and context['active_ids']) or []
        product_obj = self.env['product.template']

        warningobj = self.env['meli.warning']

        meli = self.env['meli.util'].get_new_instance(company)
        if meli.need_login():
            return meli.redirect_login()

        meli_id = False
        if self.meli_id:
            meli_id = self.meli_id
        res = {}
        for product_id in product_ids:
            product = product_obj.browse(product_id)
            if (product):
                if self.force_meli_pub and not product.meli_pub:
                    product.meli_pub = True
                    for variant in product.product_variant_ids:
                        variant.meli_pub = True
                if (product.meli_pub):
                        res = product.product_template_update(meli_id=meli_id)

            if res and 'name' in res:
                return res

        return res

product_template_update()

class product_post(models.TransientModel):
    _name = "mercadolibre.product.post"
    _description = "Wizard de Product Posting en MercadoLibre"

    force_meli_pub = fields.Boolean(string="Forzar publicación",help="Forzar publicación de todos los seleccionados",default=False)
    force_meli_active = fields.Boolean(string="Forzar activación",help="Forzar activaciónde todos los seleccionados",default=False)
    type = fields.Selection([('post','Alta'),('put','Editado'),('delete','Borrado')], string='Tipo de operación' )
    posting_date = fields.Date('Fecha del posting')
	    #'company_id': fields.many2one('res.company',string='Company'),
	    #'mercadolibre_state': fields.related( 'res.company', 'mercadolibre_state', string="State" )
    post_stock = fields.Boolean(string="Actualizar Stock",help="No actualiza el producto, solo el stock",default=False)
    post_price = fields.Boolean(string="Acutalizar Precio",help="No actualiza el producto, solo el precio",default=False)


    def pretty_json( self, data ):
        return json.dumps( data, sort_keys=False, indent=4 )

    def product_post(self, context=None):
        context = context or self.env.context
        company = self.env.user.company_id
        product_ids = ('active_ids' in context and context['active_ids']) or []
        product_obj = self.env['product.product']

        warningobj = self.env['meli.warning']

        meli = self.env['meli.util'].get_new_instance(company)
        if meli.need_login():
            return meli.redirect_login()

        res = {}
        for product_id in product_ids:
            product = product_obj.browse(product_id)
            #import pdb;pdb.set_trace();
            if (self.force_meli_pub and not product.meli_pub):
                product.meli_pub = True

            if (product.meli_pub):

                if self.post_stock:
                    res = product.product_post_stock(meli=meli)
                if self.post_price:
                    res = product.product_post_price(meli=meli)
                if not self.post_stock and not self.post_price:
                    res = product.product_post()

            #Pausa
            #if (product.meli_pub==False and product.meli_id):
            #    res = product.product_meli_status_pause()

            if res and 'name' in res:
                return res

        return res

product_post()


class product_product_update(models.TransientModel):
    _name = "mercadolibre.product.product.update"
    _description = "Wizard de Product Product Update en MercadoLibre"

    force_meli_pub = fields.Boolean(string="Forzar importación",help="Forzar importación de todos los seleccionados",default=False)
    #type = fields.Selection([('post','Alta'),('put','Editado'),('delete','Borrado')], string='Tipo de operación' );
    #posting_date = fields.Date('Fecha del posting');
	    #'company_id': fields.many2one('res.company',string='Company'),
	    #'mercadolibre_state': fields.related( 'res.company', 'mercadolibre_state', string="State" )


    def pretty_json( self, data ):
        return json.dumps( data, sort_keys=False, indent=4 )

    def product_product_update(self, context=None):
        context = context or self.env.context
        company = self.env.user.company_id
        product_ids = ('active_ids' in context and context['active_ids']) or []
        product_obj = self.env['product.product']

        warningobj = self.env['meli.warning']

        meli = self.env['meli.util'].get_new_instance(company)
        if meli.need_login():
            return meli.redirect_login()

        res = {}
        for product_id in product_ids:
            product = product_obj.browse(product_id)
            if (product):
                if self.force_meli_pub and not product.meli_pub:
                    product.meli_pub = True
                    #for variant in product.product_variant_ids:
                    #    variant.meli_pub = True
                    product.product_tmpl_id.meli_pub = True
                    for variant in product.product_tmpl_id.product_variant_ids:
                        variant.meli_pub = True
                if (product.meli_pub):
                    res = product.product_meli_get_product()

            if res and 'name' in res:
                return res

        return res

product_product_update()



class product_template_import(models.TransientModel):

    _name = "mercadolibre.product.template.import"
    _description = "Wizard de Product Template Import en MercadoLibre"

    post_state = fields.Selection([('all','Todos'),('active','Activos'),('paused','Pausados'),('closed','Cerrados')], default='all', string='Filtrar publicaciones por estado',help='Estado de productos a importar (todos, activos o pausados)' )
    meli_id = fields.Char(string="MercadoLibre Id's (MLMXXXXXXX, MLMYYYYYYY, MLM.... ) a importar.")
    force_create_variants = fields.Boolean( string="Forzar creacion/cambios de variantes", help="Forzar creacion de variantes (Modifica el producto de Odoo / Rompe Stock)", default=False )
    force_dont_create = fields.Boolean( string="No crear productos (Encontrar por SKU)", default=True )
    force_meli_pub = fields.Boolean(string="Force Meli Pub", default=True)

    force_meli_website_published = fields.Boolean(string="Force Website Published", default=False)
    force_meli_website_category_create_and_assign = fields.Boolean(string="Force Website Categories", default=False)


    def pretty_json( self, data ):
        return json.dumps( data, sort_keys=False, indent=4 )

    def product_template_import(self, context=None):

        context = context or self.env.context
        company = self.env.user.company_id
        #product_ids = ('active_ids' in context and context['active_ids']) or []
        #product_obj = self.env['product.template']

        _logger.info("product_template_import context:"+str(context))

        warningobj = self.env['meli.warning']

        meli = self.env['meli.util'].get_new_instance(company)
        if meli.need_login():
            return meli.redirect_login()

        custom_context = {
            "post_state": self.post_state,
            "meli_id": self.meli_id,
            "force_meli_pub": self.force_meli_pub,
            "force_create_variants": self.force_create_variants,
            "force_dont_create": self.force_dont_create,
            "force_meli_website_published": self.force_meli_website_published,
            "force_meli_website_category_create_and_assign": self.force_meli_website_category_create_and_assign
        }

        _logger.info("product_template_import custom_context:"+str(custom_context))

        meli_id = False
        if self.meli_id:
            meli_id = self.meli_id

        res = {}

        res = company.product_meli_get_products(context=custom_context)
        #for product_id in product_ids:
        #    product = product_obj.browse(product_id)
        #    if (product):
        #        if self.force_meli_pub and not product.meli_pub:
        #            product.meli_pub = True
        #            for variant in product.product_variant_ids:
        #                variant.meli_pub = True
        #        if (product.meli_pub):
        #                res = product.product_template_update(meli_id=meli_id)

        #    if res and 'name' in res:
        #        return res

        return res

product_template_import()
