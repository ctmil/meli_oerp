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
import base64
import mimetypes
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

    def _calculate_sync_status( self ):
        sync_status = self.check_sync_status()
        _logger.info('self: ' + str(self.report_import))
        _logger.info('self._origin: ' + str(self._origin))
        _logger.info('self._origin.report_import: ' + str(self._origin.report_import))
        for imp in self:
            report_import_link = str('report_import_link' in sync_status and str(sync_status['report_import_link']))
            _logger.info('_calculate_sync_status: ' + str(imp)+" sync_status:"+report_import_link)
            imp.import_status = "Idle "+str(report_import_link)
            imp.actives_to_sync = str(0)
            imp.paused_to_sync = str(0)
            imp.closed_to_sync = str(0)
            #imp.report_import = None
            imp.report_import_link =  ""
            if "actives_to_sync" in sync_status:
                imp.actives_to_sync = str(sync_status['actives_to_sync'])
                imp.paused_to_sync = str(sync_status['paused_to_sync'])
                imp.closed_to_sync = str(sync_status['closed_to_sync'])
                #imp.report_import = 'report_import' in sync_status and sync_status['report_import'] and sync_status['report_import'].id
                _logger.info('_calculate_sync_status: imp.report_import > ' + str(imp.report_import))
                if imp.report_import:
                    imp.report_import_link = 'report_import_link' in sync_status and str(sync_status['report_import_link'])
                    _logger.info('_calculate_sync_status: imp.report_import_link > ' + str(imp.report_import_link))


    actives_to_sync = fields.Char(string="Products actives to sync",compute=_calculate_sync_status)
    paused_to_sync = fields.Char(string="Products paused to sync",compute=_calculate_sync_status)
    closed_to_sync = fields.Char(string="Products closed to sync",compute=_calculate_sync_status)
    import_status = fields.Char(string="Import Status",compute=_calculate_sync_status)
    report_import_link = fields.Char(string="Report Link", compute=_calculate_sync_status)

    force_meli_website_published = fields.Boolean(string="Force Website Published", default=False)
    force_meli_website_category_create_and_assign = fields.Boolean(string="Force Website Categories", default=False)

    batch_processing_unit = fields.Integer(string="Numero de lotes a procesar por iteracion (0 - 100)", default=50 )
    batch_processing_unit_offset = fields.Integer(string="Offset", default=0 )
    batch_processing_status = fields.Char(string="Status proceso por lotes")
    batch_processing = fields.Boolean(string="Batch Processing Active",default=False)
    batch_actives_to_sync = fields.Boolean(string="Process Actives To Sync",default=False)
    batch_paused_to_sync = fields.Boolean(string="Process Paused To Sync",default=False)

    report_import = fields.Many2one( "ir.attachment",string="Reporte Importación")


    def pretty_json( self, data ):
        return json.dumps( data, sort_keys=False, indent=4 )

    def check_sync_status( self, context=None, config=None, meli=None ):
        context = context or self.env.context
        _logger.info("check_sync_status:"+str(context))
        company = self.env.user.company_id
        config = config or company
        #product_obj = self.env['product.product']
        #meli_ids = product_obj.search([('meli_id','!=',False)]).mapped('meli_id')
        #_logger.info("meli_ids:"+str(meli_ids))

        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)
            if meli.need_login():
                return meli.redirect_login()

        results = []
        post_state_filter = {}

        meli_id = self.meli_id

        post_state_filter = { 'status': 'active' }
        if meli_id:
            post_state_filter.update( { 'meli_id': meli_id } )
        response = meli.get("/users/"+config.mercadolibre_seller_id+"/items/search", {'access_token':meli.access_token,
                                                                                        'offset': 0,
                                                                                        **post_state_filter } )
        rjson = response.json()
        _logger.info( rjson )
        if 'error' in rjson:
            _logger.error(rjson)
        if 'results' in rjson:
            results = rjson['results']
        totalmax = 0
        if 'paging' in rjson:
            totalmax = rjson['paging']['total']
        _logger.info( "totalmax: "+str(totalmax) )
        actives_to_sync = str(totalmax)

        post_state_filter = { 'status': 'paused' }
        if meli_id:
            post_state_filter.update( { 'meli_id': meli_id } )
        response = meli.get("/users/"+config.mercadolibre_seller_id+"/items/search", {'access_token':meli.access_token,
                                                                                        'offset': 0,
                                                                                        **post_state_filter } )
        rjson = response.json()
        _logger.info( rjson )
        if 'error' in rjson:
            _logger.error(rjson)
        if 'results' in rjson:
            results = rjson['results']
        totalmax = 0
        if 'paging' in rjson:
            totalmax = rjson['paging']['total']
        _logger.info( "totalmax: "+str(totalmax) )
        paused_to_sync = str(totalmax)



        post_state_filter = { 'status': 'closed' }
        if meli_id:
            post_state_filter.update( { 'meli_id': meli_id } )
        response = meli.get("/users/"+config.mercadolibre_seller_id+"/items/search", {'access_token':meli.access_token,
                                                                                        'offset': 0,
                                                                                        **post_state_filter } )

        rjson = response.json()
        _logger.info( rjson )
        if 'error' in rjson:
            _logger.error(rjson)
        if 'results' in rjson:
            results = rjson['results']
        totalmax = 0
        if 'paging' in rjson:
            totalmax = rjson['paging']['total']
        _logger.info( "totalmax: "+str(totalmax) )
        closed_to_sync = str(totalmax)


        #check last import Status
        attachments = self.env["ir.attachment"].search([('res_id','=',self.id)], order='id desc')
        last_attachment = None
        report_import_link = ""
        if attachments:
            last_attachment = attachments[0]
            report_import_link = "/web/content/"+str(last_attachment.id)+"?download=true&access_token="+str(last_attachment.access_token)


        result =  {
            'actives_to_sync': actives_to_sync,
            'paused_to_sync': paused_to_sync,
            'closed_to_sync': closed_to_sync
        }

        result.update({'report_import': last_attachment})
        result.update({'report_import_link': report_import_link})

        _logger.info(result)
        return result

    def check_import_status( self ):
        _logger.info('Processing import status ' + str(self.import_status))

        return {
            "type": "set_scrollTop",
        }

    def create_full_report( self, context=None, config=None, meli=None):
        _logger.info("Creating full report")
        context = context or self.env.context
        company = self.env.user.company_id

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
            "force_meli_website_category_create_and_assign": self.force_meli_website_category_create_and_assign,
            "batch_processing_unit": self.batch_processing_unit,
            "batch_processing_unit_offset": self.batch_processing_unit_offset,
            "batch_actives_to_sync": self.batch_actives_to_sync,
            "batch_paused_to_sync": self.batch_paused_to_sync,
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
        _logger.info("import res:"+str(res))
        if res and "json_report" in res:
            if "paging" in res:
                if "next_offset" in res["paging"]:
                    self.batch_processing_unit_offset = res["paging"]["next_offset"]

            #update batch_processing_unit_offset
            json_report = res["json_report"]
            full_report = json_report["synced"]+json_report["missing"]+json_report["duplicates"]
            csv_report_header = ""
            csv_report = ""

            sep = ""
            for field in full_report[0]:
                csv_report_header+= sep+str(field)
                sep = ";"

            for sync in full_report:
                sep = ""
                for field in sync:
                    csv_report+= sep+'"'+str(sync[field])+'"'
                    sep = ";"
                csv_report+= "\n"

            csv_report_attachment_last = self.env["ir.attachment"].search([('res_id','=',self.id)], order='id desc', limit=1 )
            if (csv_report_attachment_last):
                csv_report_last = csv_report_attachment_last.index_content
                csv_report = csv_report_last+"\n"+csv_report
            else:
                csv_report = csv_report_header+"\n"+csv_report
            #_logger.info(csv_report)

            b64_csv = base64.b64encode(csv_report.encode())
            ATTACHMENT_NAME = "MassiveImport"

            csv_report_attachment = self.env['ir.attachment'].create({
                'name': ATTACHMENT_NAME+'.csv',
                'type': 'binary',
                'datas': b64_csv,
                #'datas_fname': ATTACHMENT_NAME + '.csv',
                'access_token': self.env['ir.attachment']._generate_access_token(),
                #'store_fname': ATTACHMENT_NAME+'.csv',
                'res_model': 'mercadolibre.product.template.import',
                'res_id': self.id,
                'mimetype': 'text/csv'
            })

            csv_report_attachment_link= ''
            if csv_report_attachment:
                self.report_import = csv_report_attachment.id
                csv_report_attachment_link = "/web/content/"+str(csv_report_attachment.id)+"?download=true&access_token="+str(csv_report_attachment.access_token)
                self.report_import_link = csv_report_attachment_link
                #<a class="fa fa-download" t-attf-title="Download Attachment {{asset.name}}" t-attf-href="/web/content/#{asset.attachment.id}?download=true&amp;access_token=#{asset.attachment.access_token}" target="_blank"></a>

            res.update({'csv_report':  csv_report, 'csv_report_attachment':  csv_report_attachment, 'csv_report_attachment_link': csv_report_attachment_link })

            _logger.info('Processing import status ' + str(self.import_status)+ " report_import:"+str(self.report_import))

        return res



product_template_import()
