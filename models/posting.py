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

from ..melisdk.meli import Meli

import logging
_logger = logging.getLogger(__name__)

from .meli_oerp_config import *
from dateutil.parser import *
from datetime import *

from . import versions
from .versions import *


class mercadolibre_posting_update(models.TransientModel):
    _name = "mercadolibre.posting.update"
    _description = "Update Posting Questions"

    def posting_update(self, context=None ):
        context = context or self.env.context
        posting_ids = False
        _logger.info("context:")
        _logger.info(context)
        if ('active_ids' in context):
            posting_ids = context['active_ids']
        #_logger.info("ids %s", ''.join(ids))
        #posting_ids = ids
        posting_obj = self.env['mercadolibre.posting']

        if (posting_ids):
            for posting_id in posting_ids:

        #    _logger.info("posting_update: %s " % (posting_id) )

                posting = posting_obj.browse(posting_id)
                posting.posting_query_questions()

        return {}

mercadolibre_posting_update()


class mercadolibre_posting(models.Model):
    _name = "mercadolibre.posting"
    _description = "Posting en MercadoLibre"

    def _posting_update( self ):

        company = self.env.user.company_id
        posting_obj = self.env['mercadolibre.posting']

        for posting in self:
            update_status = "ok"
            posting.posting_update = update_status
            posting.posting_query_questions()
            #res = {}
            #res[posting.id] = update_status
            #return res

    def posting_query_questions( self ):

        #get with an item id
        company = self.env.user.company_id
        posting_obj = self.env['mercadolibre.posting']

        for posting in self:

            log_msg = 'posting_query_questions: %s' % (posting.meli_id)
            #_logger.info(log_msg)

            CLIENT_ID = company.mercadolibre_client_id
            CLIENT_SECRET = company.mercadolibre_secret_key
            ACCESS_TOKEN = company.mercadolibre_access_token
            REFRESH_TOKEN = company.mercadolibre_refresh_token

            #
            meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN )
            if (posting.meli_id):
                pass;
            else:
                continue;
            response = meli.get("/items/"+posting.meli_id, {'access_token':meli.access_token})
            product_json = response.json()
            #_logger.info( product_json )

            if "error" in product_json:
                ML_status = product_json["error"]
            else:
                ML_status = product_json["status"]
                ML_permalink = product_json["permalink"]
                ML_price = product_json["price"]
                #ML_sku = product_json["seller_custom_field"]
                posting.write( { 'meli_status': ML_status, 'meli_permalink': ML_permalink, 'meli_price': ML_price } )

            if (not company.mercadolibre_cron_get_questions):
                return {}

            response = meli.get("/questions/search?item_id="+posting.meli_id, {'access_token':meli.access_token})
            questions_json = response.json()
            questions_obj = self.env['mercadolibre.questions']

            if 'questions' in questions_json:
                questions = questions_json['questions']
                #_logger.info( questions )
                cn = 0
                for Question in questions:
                    cn = cn + 1

                    question_answer = Question['answer']

                    question_fields = {
                        'posting_id': posting.id,
                        'question_id': Question['id'],
                        'date_created': ml_datetime(Question['date_created']),
                        'item_id': Question['item_id'],
                        'seller_id': Question['seller_id'],
                        'text': Question['text'].encode("utf-8"),
                        'status': Question['status'],
                    }

                    if (question_answer):
                        question_fields['answer_text'] = question_answer['text'].encode("utf-8")
                        question_fields['answer_status'] = question_answer['status']
                        question_fields['answer_date_created'] = ml_datetime(question_answer['date_created'])

                    question = questions_obj.search( [('question_id','=',question_fields['question_id'])])
                    if not question:
    	                question = questions_obj.create( ( question_fields ))
                    else:
                        if question:
                            question.write( (question_fields) )


        return {}


    def posting_query_all_questions( self, cr, uid, ids, context=None ):

        return {}

    posting_date = fields.Date('Fecha del posting');
    name = fields.Char('Name');
    meli_id = fields.Char('Id del item asignado por Meli', size=256);
    product_id = fields.Many2one('product.product','product_id');
    meli_status = fields.Char( string="Estado del producto en MLA", size=256 );
    meli_permalink = fields.Char( string="Permalink en MercadoLibre", size=512 );
    meli_price = fields.Char(string='Precio de venta', size=128);
    posting_questions = fields.One2many( 'mercadolibre.questions','posting_id','Questions' );
    posting_update = fields.Char( compute=_posting_update, string="Posting Update", store=False );
    meli_seller_custom_field = fields.Char('Sellect Custom Field or SKU',size=256);

mercadolibre_posting()
