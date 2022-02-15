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

from odoo import fields, osv, models
import logging
from . import versions
from .versions import *
#https://api.mercadolibre.com/questions/search?item_id=MLA508223205

class mercadolibre_questions(models.Model):
    _name = "mercadolibre.questions"
    _description = "Preguntas en MercadoLibre"

    name = fields.Char(string="Name")
    posting_id = fields.Many2one("mercadolibre.posting","Posting")
    #product_id = fields.Many2one("product.product","Product")
    question_id = fields.Char('Question Id')
    date_created = fields.Date('Creation date')
    item_id = fields.Char(string="Item ID",size=255)
    seller_id = fields.Char(string="Seller ID",size=255)
    text = fields.Text("Question Text")
    status = fields.Selection( [("UNANSWERED","Question is not answered yet."),
                                ("ANSWERED","Question was answered."),
                                ("CLOSED_UNANSWERED","The item is closed and the question was never answered."),
                                ("UNDER_REVIEW","The item is under review and the question too."),
                                ("BANNED","The item was banned")],
                                string='Question Status')
    answer_date_created = fields.Date('Answer creation date')
    answer_status = fields.Selection( [("ACTIVE","Active"),("DISABLED","Disabled"),("BANNED","Banned")], string='Answer Status')
    answer_text = fields.Text("Answer Text")


    def compute_answer_link( self ):
        company = self.env.user.company_id
        for q in self:
            if q.item_id and q.question_id:       
                q.answer_link = company.get_ML_LINK_URL()+"preguntas/vendedor/articulo/"+str(q.item_id)+"?question_id="+str(q.question_id)

    answer_link = fields.Char(string="Answer Link",compute=compute_answer_link)

    def prepare_question_fields( self, Question, meli=None, config=None ):
        question_fields = {
            'name': ''+str(Question['item_id']),
            'posting_id': "posting_id" in Question and Question["posting_id"],
            'question_id': Question['id'],
            'date_created': ml_datetime(Question['date_created']),
            'item_id': Question['item_id'],
            'seller_id': Question['seller_id'],
            'text': Question['text'].encode("utf-8"),
            'status': Question['status'],
        }
        return question_fields

    def fetch( self, question_id=None, meli=None, config=None ):
        Question = None
        if not meli:
            meli = self.env['meli.util'].get_new_instance(config)
        if meli.need_login():
            return meli.redirect_login()
        response = meli.get("/questions/"+str(question_id), {'access_token':meli.access_token})
        if response:
            questions_json = response.json()
            if 'error' in questions_json:
                _logger.error(questions_json)
            else:
                Question = questions_json
                
        return Question

    def process_question( self, question_id=None, Question=None, meli=None, config=None ):
        questions_obj = self
        question = None
        if question_id and not Question:
            Question = questions_obj.fetch( question_id=question_id, meli=meli, config=config )


        if (Question and 'id' in Question):
            question_answer = 'answer' in Question and Question['answer']

            question_fields = self.prepare_question_fields( Question=Question, meli=meli, config=config )

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

        return question

mercadolibre_questions()
