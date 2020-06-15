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

import os
import logging
_logger = logging.getLogger(__name__)

import requests
from datetime import datetime

from odoo import fields, osv, models, api
from odoo.tools.translate import _
from odoo import tools

from . import versions
from .versions import *

#https://api.mercadolibre.com/questions/search?item_id=MLA508223205
#https://api.mercadolibre.com/myfeeds?app_id=3219083410743656&offset=1&limit=5&access_token=APP_USR-3219083410743656-110520-aac05cf817595680f2f2bfed74062e3f-387126569
#
#{
#      "_id": "5dc1f402b5365146406663c0",
#      "resource": "/items/MLC482192418",
#      "user_id": 387126569,
#      "topic": "items",
#      "application_id": 3219083410743656,
#      "attempts": 1,
#      "sent": "2019-11-05T22:13:22.377Z",
#      "received": "2019-11-05T22:13:22.354Z",
#      "request": {},
#      "response": {}
#},

class MercadolibreNotification(models.Model):
    _name = "mercadolibre.notification"
    _description = "Notificaciones en MercadoLibre"
    _rec_name = 'notification_id'

    notification_id = fields.Char(string='Notification Id',required=True,index=True)
    application_id = fields.Char(string='Application Id', index=True)
    user_id = fields.Char('User Id')
    topic = fields.Char('Topic', index=True)
    sent = fields.Datetime('Sent')
    received = fields.Datetime('Received', index=True)
    resource = fields.Char("Resource", index=True)
    attempts = fields.Integer('Attempts')

    state = fields.Selection([
		("RECEIVED","Notification received."),
		("PROCESSING","Processing notification."),
        ("FAILED","Notification process with errors"),
		("SUCCESS","Notification processed.")
		], string='Notification State', index=True )
    processing_started = fields.Datetime( string="Processing started" )
    processing_ended = fields.Datetime( string="Processing ended" )
    processing_errors = fields.Text( string="Processing errors log" )

    _sql_constraints = [
        #('ref_uniq', 'unique(notification_id, application_id, user_id, topic)', 'Notification Id must be unique!'),
        ('unique_notification_id', 'unique(notification_id)', 'Notification Id must be unique!'),
    ]

    def _prepare_values(self, values):
        vals = {
            "notification_id": values["_id"],
            "application_id": values["application_id"],
            "user_id": values["user_id"],
            "topic": values["topic"],
            "resource": values["resource"],
            "received": values["received"],
            "sent": values["sent"],
            "attempts": values["attempts"],
            "state": "RECEIVED"
        }
        return vals

    def fetch_lasts(self):
        _logger.info("fetch_lasts")
        company = self.env.user.company_id
        meli_util_model = self.env['meli.util']
        meli = meli_util_model.get_new_instance(company)
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        try:
            #_logger.info("access_token:"+str(ACCESS_TOKEN))
            response = meli.get("/myfeeds", {'app_id': company.mercadolibre_client_id,'offset': 1, 'limit': 10,'access_token':meli.access_token} )
            rjson = response.json()
            #_logger.info(rjson)
            if ("messages" in rjson):
                for n in rjson["messages"]:
                    try:
                        if ("_id" in n):
                            if (n["topic"]=="questions"):
                                nn = self.search([('notification_id','=',n["_id"])])
                                if (len(nn)==0):
                                    vals = self._prepare_values(values=n)
                                    noti = self.create(vals)
                                    _logger.info("Created new QUESTION notification")
                                    if (noti):
                                        noti._process_notification_question()

                            if (n["topic"] in ["order","created_orders","orders_v2"]):
                                nn = self.search([('notification_id','=',n["_id"])])
                                if (len(nn)==0):
                                    vals = self._prepare_values(values=n)
                                    noti = self.create(vals)
                                    _logger.info("Created new ORDER notification.")
                                    if (noti):
                                        noti._process_notification_order()

                            if (1==2 and n["topic"]=="items"):
                                nn = self.search([('notification_id','=',n["_id"])])
                                if (len(nn)==0):
                                    vals = self._prepare_values(values=n)
                                    noti = self.create(vals)
                                    _logger.info("Created new ITEM notification.")

                            if (n["topic"] in ["payments"]):
                                nn = self.search([('notification_id','=',n["_id"])])
                                if (len(nn)==0):
                                    vals = self._prepare_values(values=n)
                                    noti = self.create(vals)
                                    _logger.info("Created new PAYMENT notification.")

                    except:
                        _logger.error("Error creating notification.")
                        return {"error": "Error creating notification.", "status": "520" }
                        pass;
        except:
            _logger.error("Error connecting to Meli")
            return {"error": "Error connecting to Meli.", "status": "520" }
            pass;

        self.process_notifications()

        #ok send ACK 200
        return ""

    def _process_notification_question(self):
        _logger.info("_process_notification_question")

        company = self.env.user.company_id
        meli_util_model = self.env['meli.util']
        meli = meli_util_model.get_new_instance(company)
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        for noti in self:

            noti.state = 'PROCESSING'
            #noti.attempts+= 1
            noti.processing_started = ml_datetime(str(datetime.now()))

            try:
                questions = meli.get(""+str(noti.resource), {'access_token':meli.access_token} )
                qjson =  questions.json()
                if ('error' in qjson):
                    noti.state = 'FAILED'
                    noti.processing_errors = str(qjson['error'])
                if ("item_id" in qjson):
                    posting = self.env["mercadolibre.posting"].search([('meli_id','=',qjson["item_id"])])
                    if (posting and len(posting)):
                        rsjson = posting.posting_query_questions()
                        if ('error' in rsjson):
                            noti.state = 'FAILED'
                            noti.processing_errors = str( rsjson['error'] )
                        else:
                            noti.state = 'SUCCESS'
                            noti.processing_errors = str(rsjson)
                    else:
                        noti.state = 'FAILED'
                        noti.processing_errors = str( "Posting not found related to question" )
            except Exception as E:
                noti.state = 'FAILED'
                noti.processing_errors = str(E)
            finally:
                noti.processing_ended = ml_datetime(str(datetime.now()))



    def _process_notification_order(self):
        _logger.info("_process_notification_order")

        company = self.env.user.company_id
        meli_util_model = self.env['meli.util']
        meli = meli_util_model.get_new_instance(company)
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        for noti in self:

            noti.state = 'PROCESSING'
            #noti.attempts+= 1
            noti.processing_started = ml_datetime(str(datetime.now()))

            try:
                res = meli.get(""+str(noti.resource), {'access_token':meli.access_token} )
                ojson =  res.json()
                _logger.info(ojson)
                if ('error' in ojson):
                    noti.state = 'FAILED'
                    noti.processing_errors = str(ojson['error'])
                if ("id" in ojson):

                    morder = self.env["mercadolibre.orders"].search( [('order_id','=',ojson["id"])], limit=1 )

                    _logger.info(str(morder))
                    pdata = { "id": False, "order_json": ojson }

                    if (morder and len(morder)):
                        pdata["id"] =  morder.id

                    rsjson = morder.orders_update_order_json( pdata )
                    _logger.info(str(rsjson))

                    if ('error' in rsjson):
                        noti.state = 'FAILED'
                        noti.processing_errors = str(rsjson['error'])
                    else:
                        noti.state = 'SUCCESS'
                        noti.processing_errors = str(rsjson)

            except Exception as E:
                noti.state = 'FAILED'
                noti.processing_errors = str(E)
            finally:
                noti.processing_ended = ml_datetime(str(datetime.now()))

    def process_notification(self):
        _logger.info("_process_notification")

        company = self.env.user.company_id
        meli_util_model = self.env['meli.util']
        meli = meli_util_model.get_new_instance(company)
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        for noti in self:

            if (noti.topic and len(noti.topic)):

                if (noti.topic in ["questions"]):
                    noti._process_notification_question()

                if (noti.topic in ["order","created_orders","orders_v2"]):
                    noti._process_notification_order()


    def process_notifications(self):
        #process all
        _logger.info("Processing received notifications")
        received = self.search([('state','=','RECEIVED')])
        if (received and len(received)):
            for noti in received:
                noti.process_notification()
