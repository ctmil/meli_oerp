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
import json
import logging
_logger = logging.getLogger(__name__)

import requests
from datetime import datetime, timedelta

from odoo import fields, models, api
from odoo.tools.translate import _
from odoo import tools

from . import versions
from .versions import *

import hashlib
import random

#https://api.mercadolibre.com/questions/search?item_id=MLA<id>
#https://api.mercadolibre.com/myfeeds?app_id=<app_id>&offset=1&limit=5&access_token=<TOKEN>
#
#{
#      "_id": "5dc1f402b5365146406663c0",
#      "resource": "/items/MLC<id>",
#      "user_id": 387126569,
#      "topic": "items",
#      "application_id": <app_id>,
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
    user_id = fields.Char(string='User Id')
    topic = fields.Char(string='Topic', index=True)
    sent = fields.Datetime(string='Sent')
    received = fields.Datetime(string='Received', index=True)
    resource = fields.Char(string="Resource", index=True)
    attempts = fields.Integer(string='Attempts')
    parameters = fields.Text(string="Parameters")

    state = fields.Selection([
		("RECEIVED","Notification received."),
		("PROCESSING","Processing notification."),
        ("FAILED","Notification process with errors"),
		("SUCCESS","Notification processed.")
		], string='Notification State', index=True )
    processing_started = fields.Datetime( string="Processing started" )
    processing_ended = fields.Datetime( string="Processing ended" )
    processing_errors = fields.Text( string="Processing Errors log" )
    processing_logs = fields.Text( string="Processing Logs" )
    last_json_response = fields.Text( string="Last JSON Response", help="Último JSON recibido de la API de MercadoLibre" )
    company_id = fields.Many2one("res.company",string="Company",index=True)
    seller_id = fields.Many2one("res.users",string="Seller")

    _unique_notification_id = versions.UniqueIndex('notification_id', message='Notification Id must be unique!')

    # 26.338 (#696 sigue): el GC corre dentro del autovacuum diario y NO puede bloquear ni esperar a nadie.
    # Staging 393 (19.0, 29-oct): SerializationFailure en el DELETE por lotes de 1000 mientras el cron 177
    # (meli_oerp_multiple cron_order_notifications) marcaba duplicados; en prod el que pierde puede ser
    # el cron de ventas. Ahora: candidatos por SQL plano con tope, lotes FOR UPDATE SKIP LOCKED que
    # re-chequean las condiciones, savepoint por lote (y fila a fila si el lote choca), lock_timeout
    # corto, y se excluye el working set del cron de ordenes. Sin commits: lo hace el autovacuum
    # (que commitea después de CADA método @api.autovacuum: cada GC es su propia transacción).
    _GC_BATCH_SIZE = 500
    _GC_MAX_BATCHES = 20
    _GC_LOCK_TIMEOUT = '2s'
    _GC_RECENT_HOURS = 24
    _GC_ORDER_MAX_ATTEMPTS = 24  # = MELI_ORDER_NOTI_MAX_ATTEMPTS de meli_oerp_multiple (cron 177)
    # 26.425 (un caso): el tope fijo 500x20 = 10.000/día quedaba por debajo de lo que entra en una
    # cuenta grande (del orden de 9.000 notificaciones/día) y no alcanzaba para bajar un atraso. Ahora el tope
    # por corrida es ICP meli_oerp.gc_max_rows (default 50.000; vale para notificaciones y chatter).
    # Sólo cambia CUÁNTO de lo ya vencido se borra por día, no QUÉ se borra.
    _GC_MAX_ROWS_DEFAULT = 50000

    # Condiciones de borrado (alias n). Se evalúan al elegir candidatos y OTRA VEZ al bloquear.
    _GC_WHERE = """
        n.state IN ('SUCCESS', 'FAILED')
        AND COALESCE(n.received, n.create_date) < %(limit_dt)s
        AND COALESCE(n.write_date, n.create_date) < %(recent_dt)s
        AND NOT (n.state = 'FAILED' AND n.topic = 'orders_v2'
                 AND COALESCE(n.attempts, 0) < %(max_attempts)s)
        AND NOT EXISTS (
            SELECT 1 FROM mercadolibre_notification s
             WHERE s.resource = n.resource AND s.id <> n.id
               AND (s.state IN ('RECEIVED', 'PROCESSING')
                    OR (s.state = 'FAILED' AND s.topic = 'orders_v2'
                        AND COALESCE(s.attempts, 0) < %(max_attempts)s)))
    """

    @api.model
    def _gc_meli_icp_int(self, key, default):
        """Entero de ir.config_parameter; vacío o inválido => default. 20.0 usa get_str, 16-19 get_param."""
        ICP = self.env['ir.config_parameter'].sudo()
        getter = getattr(ICP, 'get_str', None) or ICP.get_param
        try:
            raw = getter(key, '')
            return int(raw) if raw not in (None, False, '') else default
        except (TypeError, ValueError):
            return default

    @api.model
    def _gc_meli_max_rows(self):
        cap = self._gc_meli_icp_int('meli_oerp.gc_max_rows', self._GC_MAX_ROWS_DEFAULT)
        return cap if cap > 0 else self._GC_MAX_ROWS_DEFAULT

    @api.model
    def _gc_meli_locked_delete(self, table, alias, where, ids, params, label):
        """Borra de `table` las filas de `ids` que se puedan bloquear YA y sigan cumpliendo `where`
        (constante con alias `alias` y parámetros %(..)s). Savepoint propio; si choca (lock /
        serialización / deadlock / FK de otro módulo que restringe el borrado) lo deshace y devuelve
        None para que el llamador decida (saltear o ir fila a fila)."""
        import psycopg2.errors as pg_errors
        cr = self.env.cr
        skip = (pg_errors.LockNotAvailable, pg_errors.SerializationFailure, pg_errors.DeadlockDetected,
                pg_errors.ForeignKeyViolation)
        try:
            with cr.savepoint(flush=False):
                # table/alias/where son constantes de clase (o armadas desde metadatos del ORM): sin datos externos
                cr.execute(  # pylint: disable=sql-injection
                    "SELECT {a}.id FROM {t} {a} WHERE {a}.id = ANY(%(ids)s) AND ({w}) FOR UPDATE OF {a} SKIP LOCKED"
                    .format(t=table, a=alias, w=where),
                    dict(params, ids=list(ids)), log_exceptions=False)
                locked = [r[0] for r in cr.fetchall()]
                if not locked:
                    return 0
                cr.execute(  # pylint: disable=sql-injection
                    "DELETE FROM {t} WHERE id = ANY(%(ids)s)".format(t=table),
                    {'ids': locked}, log_exceptions=False)
                return cr.rowcount
        except skip as e:
            _logger.info("%s: lote de %s salteado (%s)", label, len(ids), type(e).__name__)
            return None

    @api.model
    def _gc_meli_run_batches(self, table, alias, where, ids, params, batch_size, label):
        """Recorre `ids` en lotes con lock_timeout corto; si un lote choca, fila a fila.
        Devuelve (borradas, salteadas)."""
        cr = self.env.cr
        cr.execute("SHOW lock_timeout")
        prev_lock_timeout = cr.fetchone()[0]
        cr.execute("SELECT set_config('lock_timeout', %s, true)", (self._GC_LOCK_TIMEOUT,))
        total = skipped = 0
        try:
            for i in range(0, len(ids), batch_size):
                chunk = ids[i:i + batch_size]
                done = self._gc_meli_locked_delete(table, alias, where, chunk, params, label)
                if done is None and len(chunk) > 1:
                    # el lote chocó: fila a fila, para no perder todo el lote por una sola
                    done = 0
                    for one in chunk:
                        d = self._gc_meli_locked_delete(table, alias, where, [one], params, label)
                        if d is None:
                            skipped += 1
                        else:
                            done += d
                elif done is None:
                    skipped += 1
                    done = 0
                total += done
        finally:
            cr.execute("SELECT set_config('lock_timeout', %s, true)", (prev_lock_timeout,))
        return total, skipped

    def _gc_meli_delete_chunk(self, ids, params):
        """(compat 26.338) Lote de notificaciones: ver _gc_meli_locked_delete."""
        return self._gc_meli_locked_delete('mercadolibre_notification', 'n', self._GC_WHERE, ids, params,
                                           '_gc_meli_notifications')

    @api.autovacuum
    def _gc_meli_notifications(self, batch_size=None, max_batches=None):
        """Retención (#696): borra notificaciones TERMINADAS (SUCCESS/FAILED) más viejas que
        ICP meli_oerp.notification_days (default 90; 0 = no borrar). Nunca toca RECEIVED/PROCESSING
        (meli_oerp_multiple guarda en processing_logs datos de trabajo: internal_job / sales).
        26.338: nunca bloquea ni espera. Tampoco toca el working set del cron de órdenes: FAILED
        orders_v2 reintentables, notificaciones de un resource con hermanas vivas, ni nada escrito
        en las últimas 24 h. Lo que choca se saltea y lo toma la próxima vuelta.
        26.425: tope por corrida = ICP meli_oerp.gc_max_rows (default 50.000) salvo que el llamador
        pase batch_size/max_batches explícitos (tests)."""
        days = self._gc_meli_icp_int('meli_oerp.notification_days', 90)
        if days <= 0:
            return 0
        explicit_cap = bool(batch_size or max_batches)
        batch_size = int(batch_size or self._GC_BATCH_SIZE)
        max_batches = int(max_batches or self._GC_MAX_BATCHES)
        cap = batch_size * max_batches if explicit_cap else self._gc_meli_max_rows()
        now = fields.Datetime.now()
        params = {
            'limit_dt': now - timedelta(days=days),
            'recent_dt': now - timedelta(hours=self._GC_RECENT_HOURS),
            'max_attempts': self._GC_ORDER_MAX_ATTEMPTS,
        }
        cr = self.env.cr
        self.env['mercadolibre.notification'].flush_model()
        cr.execute("SELECT n.id FROM mercadolibre_notification n WHERE " + self._GC_WHERE  # pylint: disable=sql-injection
                   + " ORDER BY n.id LIMIT %(cap)s", dict(params, cap=cap))
        ids = [r[0] for r in cr.fetchall()]
        if not ids:
            return 0
        try:
            total, skipped = self._gc_meli_run_batches('mercadolibre_notification', 'n', self._GC_WHERE, ids, params,
                                                       batch_size, '_gc_meli_notifications')
        finally:
            self.env['mercadolibre.notification'].invalidate_model()
        if total or skipped:
            _logger.info("_gc_meli_notifications: %s notificaciones terminadas anteriores a %s borradas "
                         "(%s días; %s salteadas por estar en uso)", total, params['limit_dt'], days, skipped)
        return total

    # ------------------------------------------------------------------------------------------
    # 26.425 (un caso): limpieza del CHATTER de los modelos meli. Una cuenta grande juntó 187.030
    # mail.message 'notification' en mercadolibre.orders (115.701 de más de 30 días: «Pack Order, dont
    # create», «Sale order created (pack)!», «Warning: sale order not created!»…), 5.547 en
    # mercadolibre.shipment y 290 en mercadolibre.account: ~1,5 GB de mail_message sin valor después
    # de unos días. NUNCA toca sale.order / account.move / stock.picking (ventas, facturas, entregas).
    #
    # Qué borra: mail.message con model IN _GC_CHATTER_MODELS, message_type = 'notification' (los
    # avisos automáticos del módulo; NUNCA 'comment' = notas y mensajes de personas, ni 'email'),
    # con date anterior a hoy - ICP meli_oerp.chatter_days. Default 0 = APAGADO (no cambia nada
    # a nadie sin que lo pida). Mínimo efectivo 7 días (_GC_CHATTER_MIN_DAYS).
    # Qué conserva aunque sea viejo: con adjuntos, destacados (starred / bookmarked), con tracking de
    # campos, con un mail.mail asociado (correo en cola o con error), con respuestas (hijos), con
    # reacciones, con una notificación de bandeja de entrada SIN LEER, y los que llevan la marca
    # `<!-- meli-once:… -->` (guardas "postear una sola vez" de versions.meli_message_post).
    #
    # Efecto funcional (medido sobre origin/19.0, 19-nov-2026): los lectores de chatter del suite son
    # de-dupe y miran OTROS modelos o sólo lo reciente — meli_message_already_posted /
    # meli_message_text_posted / sale_order._meli_ready_note_posted / sorder.message_ids[:50]
    # (orders.py "PRODUCTO NO ENCONTRADO") operan sobre sale.order; el único lector sobre
    # mercadolibre.account (meli_oerp_multiple _meli_injobs_alert) mira sólo los mensajes de HOY.
    # => con N >= 7 días no hay efecto funcional. Si mañana alguien postea con once_key sobre estos
    # modelos, la exclusión por marca evita que el aviso se repita.
    #
    # Mecánica: la misma del GC de notificaciones (candidatos con tope, lotes FOR UPDATE SKIP LOCKED
    # que re-chequean, savepoint, lock_timeout corto, fila a fila si choca). DELETE por SQL: las tablas
    # hijas (mail_notification, mail_tracking_value, rels m2m, mail_message_translation, link previews…)
    # tienen ondelete=cascade en el core; parent_id es set null. Un FK de terceros que restrinja el
    # borrado hace saltear ESA fila (ForeignKeyViolation en el savepoint), no rompe el lote.
    # No se usa unlink() a propósito: en 17+ manda un bus 'mail.message/delete' por partner y en cuentas
    # grandes son decenas de miles de mensajes por corrida.
    _GC_CHATTER_MODELS = ('mercadolibre.orders', 'mercadolibre.shipment', 'mercadolibre.account')
    _GC_CHATTER_BATCH_SIZE = 1000
    _GC_CHATTER_MIN_DAYS = 7
    _GC_CHATTER_ONCE_MARKER = '%meli-once:%'

    @api.model
    def _gc_meli_chatter_where(self):
        """Condiciones (alias m) armadas desde los metadatos del ORM de ESTA versión de Odoo:
        16-19 tienen starred_partner_ids y mail_tracking_value; 20 tiene bookmarked_partner_ids y el
        tracking como message_type propio. Sólo se agregan las que existen."""
        Msg = self.env['mail.message']
        conds = [
            "m.model IN %(models)s",
            "m.message_type = 'notification'",
            "m.date < %(limit_dt)s",
            "COALESCE(m.body, '') NOT LIKE %(once_marker)s",
        ]
        for fname in ('attachment_ids', 'starred_partner_ids', 'bookmarked_partner_ids'):
            f = Msg._fields.get(fname)
            if f is not None and f.type == 'many2many' and f.store and f.relation and f.column1:
                conds.append("NOT EXISTS (SELECT 1 FROM %s r WHERE r.%s = m.id)" % (f.relation, f.column1))
        for comodel, col in (('mail.tracking.value', 'mail_message_id'), ('mail.mail', 'mail_message_id'),
                             ('mail.message', 'parent_id'), ('mail.message.reaction', 'message_id')):
            if comodel in self.env and col in self.env[comodel]._fields:
                conds.append("NOT EXISTS (SELECT 1 FROM %s x WHERE x.%s = m.id)" % (self.env[comodel]._table, col))
        if 'mail.notification' in self.env:
            conds.append("NOT EXISTS (SELECT 1 FROM mail_notification x WHERE x.mail_message_id = m.id"
                         " AND x.notification_type = 'inbox' AND NOT COALESCE(x.is_read, false))")
        return " AND ".join(conds)

    @api.autovacuum
    def _gc_meli_chatter(self, batch_size=None, max_rows=None):
        """26.425 (un caso): borra avisos automáticos viejos del chatter de mercadolibre.orders /
        mercadolibre.shipment / mercadolibre.account (ver el bloque de arriba). ICP
        meli_oerp.chatter_days (default 0 = apagado; 1..6 => 7). Tope por corrida = ICP
        meli_oerp.gc_max_rows (default 50.000). Devuelve la cantidad borrada."""
        days = self._gc_meli_icp_int('meli_oerp.chatter_days', 0)
        if days <= 0:
            return 0
        if days < self._GC_CHATTER_MIN_DAYS:
            days = self._GC_CHATTER_MIN_DAYS
        batch_size = int(batch_size or self._GC_CHATTER_BATCH_SIZE)
        cap = int(max_rows or self._gc_meli_max_rows())
        models_present = tuple(m for m in self._GC_CHATTER_MODELS if m in self.env)
        if not models_present:
            return 0
        params = {
            'models': models_present,
            'limit_dt': fields.Datetime.now() - timedelta(days=days),
            'once_marker': self._GC_CHATTER_ONCE_MARKER,
        }
        where = self._gc_meli_chatter_where()
        cr = self.env.cr
        self.env['mail.message'].flush_model()
        cr.execute("SELECT m.id FROM mail_message m WHERE " + where  # pylint: disable=sql-injection
                   + " ORDER BY m.id LIMIT %(cap)s", dict(params, cap=cap))
        ids = [r[0] for r in cr.fetchall()]
        if not ids:
            return 0
        try:
            total, skipped = self._gc_meli_run_batches('mail_message', 'm', where, ids, params,
                                                       batch_size, '_gc_meli_chatter')
        finally:
            self.env['mail.message'].invalidate_model()
            for m in models_present:
                self.env[m].invalidate_model(['message_ids'])
        if total or skipped:
            _logger.info("_gc_meli_chatter: %s mensajes automáticos del chatter (%s) anteriores a %s borrados "
                         "(%s días; %s salteados por estar en uso)", total, ", ".join(models_present),
                         params['limit_dt'], days, skipped)
        return total

    def _prepare_values(self, values):
        company = self.env.user.company_id
        seller_id = None
        if company.mercadolibre_seller_user:
            seller_id = company.mercadolibre_seller_user.id
        vals = {
            "notification_id": values["_id"],
            "application_id": values["application_id"],
            "user_id": values["user_id"],
            "topic": values["topic"],
            "resource": values["resource"],
            "received": ml_datetime(values["received"]),
            "sent": ml_datetime(values["sent"]),
            "attempts": values["attempts"],
            "state": "RECEIVED",
            'company_id': company.id,
            'seller_id': seller_id
        }
        if "processing_started" in values:
            vals["processing_started"] = values["processing_started"]
        return vals

    def fetch_lasts(self, data=False, company=None):
        if not company:
            company = self.env.user.company_id
        _logger.info("fetch_lasts: "+str(company.name))
        _logger.info("user: "+str(self.env.user.name))
        if company.mercadolibre_seller_user:
            _logger.info("seller user: "+str(company.mercadolibre_seller_user.name))
        meli_util_model = self.env['meli.util']
        meli = meli_util_model.get_new_instance(company)
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        messages = []

        try:
            if data:
                if str(company.mercadolibre_client_id) != str(data["application_id"]):
                    return {"error": "company.mercadolibre_client_id and application_id does not match!", "status": "520" }

                if (not "_id" in data):
                    date_time = ml_datetime( str( datetime.now() ) )
                    base_str = str(data["application_id"]) + str(data["user_id"]) + str(date_time)
                    hash = hashlib.md5()
                    hash.update( base_str.encode() )
                    hexhash = str("n")+hash.hexdigest()
                    data["_id"] = hexhash
                messages.append(data)

            #must upgrade to /missed_feeds
            #response = meli.get("/myfeeds", {'app_id': company.mercadolibre_client_id,'offset': 1, 'limit': 10,'access_token':meli.access_token} )
            #rjson = response.json()

            #if ("messages" in rjson):
            #    for n in rjson["messages"]:
            #        messages.append(n)

        except Exception as e:
            _logger.error("Error connecting to Meli, myfeeds")
            _logger.info(e, exc_info=True)
            return {"error": "Error connecting to Meli.", "status": "520" }

        #process all notifications
        for n in messages:
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

                    if (n["topic"]=="items"):
                        nn = self.search([('notification_id','=',n["_id"])])
                        if (len(nn)==0):
                            vals = self._prepare_values(values=n)
                            noti = self.create(vals)
                            _logger.info("Created new ITEM notification.")
                            if (noti):
                                noti._process_notification_item()

                    if (n["topic"] in ["payments"]):
                        nn = self.search([('notification_id','=',n["_id"])])
                        if (len(nn)==0):
                            vals = self._prepare_values(values=n)
                            noti = self.create(vals)
                            _logger.info("Created new PAYMENT notification.")

            except Exception as e:
                _logger.error("Error creating notification.")
                _logger.info(e, exc_info=True)
                return {"error": "Error creating notification.", "status": "520" }

        self.process_notifications(limit=1)

        #ok send ACK 200
        return ""

    def _process_notification_question(self):
        #_logger.info("_process_notification_question")

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
                    noti.processing_errors = str( ('message' in qjson and qjson['message']) or qjson['error'])
                if ("item_id" in qjson):
                    posting = self.env["mercadolibre.posting"].search([('meli_id','=',qjson["item_id"])])
                    if (posting and len(posting)):
                        rsjson = posting.posting_query_questions()
                        if ('error' in rsjson):
                            noti.state = 'FAILED'
                            noti.processing_errors = str( ('message' in rsjson and rsjson['message']) or rsjson['error'] )
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
        #_logger.info("_process_notification_order")

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
                _logger.debug(ojson)

                # Guardar último JSON de respuesta
                noti.last_json_response = json.dumps(ojson, indent=2, ensure_ascii=False, default=str) if ojson else None

                if (ojson and 'error' in ojson):
                    noti.state = 'FAILED'
                    noti.processing_errors = str(ojson['error'])
                if (ojson and "id" in ojson):

                    morder = self.env["mercadolibre.orders"].search( [('order_id','=',ojson["id"])], limit=1 )

                    _logger.info(str(morder))
                    pdata = { "id": False, "order_json": ojson }

                    if (morder and len(morder)):
                        pdata["id"] =  morder.id

                    # Skip invoice validation on notifications to avoid AFIP concurrent numbering issues
                    rsjson = morder.with_context(meli_skip_invoice_validation=True).orders_update_order_json( pdata )
                    _logger.debug("rsjson:"+str(rsjson))

                    if (rsjson and 'error' in rsjson and meli_is_update_forbidden_error(rsjson)):
                        # 26.309 (caso-K02): venta bloqueada (meli_update_forbidden) => no es un fallo y
                        # reintentar no cambia nada: se cierra sin reintento.
                        noti.state = 'SUCCESS'
                        noti.processing_errors = "Skipped: venta bloqueada para actualizar desde ML (meli_update_forbidden)"
                    elif (rsjson and 'error' in rsjson):
                        noti.state = 'FAILED'
                        noti.processing_errors = str(rsjson['error'])
                    else:
                        noti.state = 'SUCCESS'
                        noti.processing_errors = str(rsjson)

            except Exception as E:
                noti.state = 'FAILED'
                noti.processing_errors = str(E)
                _logger.error("_process_notification_order:"+str(E))
            finally:
                noti.processing_ended = ml_datetime(str(datetime.now()))

    def _process_notification_item(self):
        """Process item notification to update publication status."""
        #_logger.info("_process_notification_item")

        company = self.env.user.company_id
        meli_util_model = self.env['meli.util']
        meli = meli_util_model.get_new_instance(company)

        for noti in self:

            noti.state = 'PROCESSING'
            noti.processing_started = ml_datetime(str(datetime.now()))

            try:
                # Resource format: /items/MLA<id>
                resource = str(noti.resource)
                if not resource.startswith('/items/'):
                    noti.state = 'FAILED'
                    noti.processing_errors = f"Invalid item resource format: {resource}"
                    continue

                meli_id = resource.replace('/items/', '')

                # Fetch item data from ML API with include_attributes=all
                response = meli.get(resource, {'access_token': meli.access_token, 'include_attributes': 'all'})
                item_json = response.json()

                # Guardar último JSON de respuesta
                noti.last_json_response = json.dumps(item_json, indent=2, ensure_ascii=False, default=str) if item_json else None

                if 'error' in item_json:
                    noti.state = 'FAILED'
                    noti.processing_errors = str(item_json.get('message', item_json.get('error', 'Unknown error')))
                    continue

                # Find binding by meli_id
                binding = None
                # Try meli_oerp_multiple binding first
                if 'mercadolibre.product' in self.env:
                    binding = self.env['mercadolibre.product'].search([('meli_id', '=', meli_id)], limit=1)

                if binding:
                    # Use the new method from binding model
                    result = binding.process_item_notification(item_json=item_json, meli=meli)
                    if result.get('error'):
                        noti.state = 'FAILED'
                        noti.processing_errors = str(result['error'])
                    else:
                        noti.state = 'SUCCESS'
                        noti.processing_logs = f"Status updated: {result.get('status', 'N/A')} ({result.get('sub_status', '')})"
                else:
                    # Try meli_oerp posting model
                    if 'mercadolibre.posting' in self.env:
                        posting = self.env['mercadolibre.posting'].search([('meli_id', '=', meli_id)], limit=1)
                        if posting:
                            # Update status on legacy posting model
                            new_status = item_json.get('status', '')
                            if new_status and hasattr(posting, 'meli_status'):
                                posting.meli_status = new_status
                            noti.state = 'SUCCESS'
                            noti.processing_logs = f"Posting status: {new_status}"
                        else:
                            noti.state = 'FAILED'
                            noti.processing_errors = f"No binding found for item: {meli_id}"
                    else:
                        noti.state = 'FAILED'
                        noti.processing_errors = f"No binding found for item: {meli_id}"

            except Exception as E:
                noti.state = 'FAILED'
                noti.processing_errors = str(E)
                _logger.error("_process_notification_item:" + str(E))
            finally:
                noti.processing_ended = ml_datetime(str(datetime.now()))

    def process_notification(self):
        #_logger.info("_process_notification")

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

                if (noti.topic in ["items"]):
                    noti._process_notification_item()

    def process_notifications(self, limit=None):
        #process all
        _logger.info("Processing received notifications #")
        received = None
        if (limit==None):
            received = self.search([('topic','like','orders_v2'),('state','=','RECEIVED')], order='id desc', limit=10)
        else:
            received = self.search([('topic','like','orders_v2'),('state','=','RECEIVED')], order='id desc', limit=1)

        if (received and len(received)):
            _logger.info( "#" + str(len(received)) )
            for noti in received:
                noti.process_notification()

    def start_internal_notification(self, internals):
        noti = None
        date_time = ml_datetime( str( datetime.now() ) )
        base_str = str(internals["application_id"]) + str(internals["user_id"]) + str(date_time)

        hash = hashlib.md5()
        hash.update( base_str.encode() )
        hexhash = str("i-")+hash.hexdigest()+str("#")+str(int(random.random()*900000+100000))

        internals["processing_started"] = date_time
        internals["_id"] = hexhash
        internals["received"] = date_time
        internals["sent"] = date_time
        internals["attempts"] = 1
        internals["state"] = "RECEIVED"

        vals = self._prepare_values(values=internals)
        if vals:
            noti = self.sudo().create(vals)

        return  noti

    def stop_internal_notification(self, errors="", logs=""):
        self.processing_ended = ml_datetime( str( datetime.now() ) )
        self.processing_errors = str(errors)
        self.processing_logs = str(logs)
        self.state = 'SUCCESS'
