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
import logging
import meli_oerp_config

import logging
_logger = logging.getLogger(__name__)

from meli_oerp_config import *
from melisdk.meli import Meli

class mercadolibre_posting_update(osv.osv_memory):
    _name = "mercadolibre.posting.update"
    _description = "Update Posting Questions"
    
    def posting_update(self, cr, uid, ids, context=None):

        posting_ids = context['active_ids']
        posting_obj = self.pool.get('mercadolibre.posting')

        for posting_id in posting_ids:

            _logger.info("posting_update: %s " % (posting_id) )

            posting = posting_obj.browse(cr,uid, posting_id)
            posting_obj.posting_query_questions( cr, uid, posting_id )

        return {}

mercadolibre_posting_update()


class mercadolibre_posting(osv.osv):
    _name = "mercadolibre.posting"
    _description = "Posting en MercadoLibre"

    def posting_update( self, cr, uid, ids, field_name, attributes, context=None):

        log_msg = 'posting_update: %s' % (field_name)
        _logger.info(log_msg)

        user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        company = user_obj.company_id

        posting_obj = self.pool.get('mercadolibre.posting')
        posting = posting_obj.browse(cr, uid, ids[0])
     
        update_status = "ok"

        self.posting_query_questions( cr, uid, ids[0] )

        res = {}		
        for posting in self.browse(cr,uid,ids):
            res[posting.id] = update_status
        return res

    def posting_query_questions( self, cr, uid, id, context=None ):

        #get with an item id
        user_obj = self.pool.get('res.users').browse(cr, uid, uid)
        company = user_obj.company_id

        posting_obj = self.pool.get('mercadolibre.posting')
        posting = posting_obj.browse(cr, uid, id )

        log_msg = 'posting_query_questions: %s' % (posting.meli_id)
        _logger.info(log_msg)

        

        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        #
        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN )

        response = meli.get("/items/"+posting.meli_id, {'access_token':meli.access_token})
        product_json = response.json()
        #_logger.info( product_json )

        if "error" in product_json:
            ML_status = product_json["error"]
        else:
            ML_status = product_json["status"]
            ML_permalink = product_json["permalink"]
            ML_price = product_json["price"]
            posting.write( { 'meli_status': ML_status, 'meli_permalink': ML_permalink, 'meli_price': ML_price } )
        
        response = meli.get("/questions/search?item_id="+posting.meli_id, {'access_token':meli.access_token})
        questions_json = response.json()
        #_logger.info( questions_json )

        questions_obj = self.pool.get('mercadolibre.questions')

        if 'questions' in questions_json:
            questions = questions_json['questions']
            _logger.info( questions )
            cn = 0
            for Question in questions:
                cn = cn + 1
                _logger.info(cn)
                _logger.info(Question )

#{
#   'status': u'UNANSWERED', 
#   'seller_id': 171319838, 
#   'from': {
#      'answered_questions': 0, 
#      'id': 171329758
#   }, 
#   'deleted_from_listing': False, 
#   'text': 'Pregunta que hago para testear el m\xf3dulo de meli_oerp en Odoo....??',
#   'answer': None, 
#   'item_id': u'MLA548679961', 
#   'date_created': '2015-03-04T12:04:48.000-04:00', 
#   'hold': False,
#   'id': 3471012014
#}

##{
#   'status': 'ACTIVE', 
#   'text': 'Ok recibiose la pregunta correctamente, ahora viendo si sale esta respuesta! Saludos\nMas saludos',
#   'date_created': '2015-03-04T13:00:53.000-04:00'
#}

                question_answer = Question['answer']

                question_fields = {
                    'posting_id': posting.id,
                    'question_id': Question['id'],
                    'date_created': Question['date_created'],
                    'item_id': Question['item_id'],
                    'seller_id': Question['seller_id'],
                    'text': Question['text'],
                    'status': Question['status'],
                }

                if (question_answer):
                    question_fields['answer_text'] = question_answer['text']
                    question_fields['answer_status'] = question_answer['status']
                    question_fields['answer_date_created'] = question_answer['date_created']
                
                question_fetch_ids = questions_obj.search(cr,uid,[('question_id','=',question_fields['question_id'])])

                if not question_fetch_ids:
	                question_fetch_ids = questions_obj.create(cr,uid,( question_fields ))
                else:
                    questions_obj.write(cr,uid, question_fetch_ids[0], ( question_fields ) )


        return {}


    def posting_query_all_questions( self, cr, uid, ids, context=None ):

        return {}

    _columns = {
        'posting_date': fields.date('Fecha del posting'), 
        'name': fields.char('Name'),
        'meli_id': fields.char('Id del item asignado por Meli', size=256),
        'product_id': fields.many2one('product.product','product_id'),
        'meli_status': fields.char( string="Estado del producto en MLA", size=256 ),
        'meli_permalink': fields.char( string="Permalink en MercadoLibre", size=512 ), 
        'meli_price': fields.char(string='Precio de venta', size=128),
        'posting_questions': fields.one2many( 'mercadolibre.questions','posting_id','Questions' ),
        'posting_update': fields.function( posting_update, method=True, type='char', string="Posting Update", store=False ),
    }    

mercadolibre_posting()

