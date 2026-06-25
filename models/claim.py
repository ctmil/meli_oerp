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
#
# Reclamos / disputas post-venta de MercadoLibre (post-purchase claims).
#
# FASE 1 (este archivo): modelo + sincronizacion de SOLO LECTURA desde la API
#   - GET /post-purchase/v1/claims/search   (listado por vendedor)
#   - GET /post-purchase/v1/claims/{id}     (detalle)
# Espeja el patron de mercadolibre.questions (fetch/process/sync).
#
# Pendiente FASE 2 (no incluido aca, para no tocar produccion sin validar):
#   - wiring del topic "claims" en el dispatcher de notificaciones (notification.py)
#   - acciones: enviar mensaje al reclamo, proponer resolucion, subir evidencia
#     (POST /claims/{id}/actions/...), que SI mutan en MercadoLibre.
#
# NOTA: la forma exacta del JSON de /claims debe validarse contra un reclamo
# real del vendedor; los campos se parsean defensivamente (.get).
##############################################################################

from odoo import fields, models, api
import logging
from . import versions
from .versions import *

_logger = logging.getLogger(__name__)


class mercadolibre_claim(models.Model):
    _name = "mercadolibre.claim"
    _description = "Reclamos / disputas post-venta en MercadoLibre"
    _order = "date_created desc"

    name = fields.Char(string="Name")
    claim_id = fields.Char(string="Claim Id", index=True)
    company_id = fields.Many2one("res.company", string="Empresa")

    # Vinculacion con la venta/orden ML
    resource = fields.Char(string="Resource", help="Tipo de recurso reclamado (order / purchase / shipment).")
    resource_id = fields.Char(string="Resource Id", index=True, help="Id del recurso (ej. order_id o pack_id).")
    order_id = fields.Many2one("mercadolibre.orders", string="Orden ML")

    # Clasificacion del reclamo
    type = fields.Selection([
        ("mediations", "Mediacion"),
        ("cancellations", "Cancelacion"),
        ("return", "Devolucion"),
        ("fulfillment", "Fulfillment"),
        ("change", "Cambio"),
        ("service", "Servicio"),
    ], string="Tipo")
    stage = fields.Selection([
        ("claim", "Reclamo"),
        ("dispute", "Disputa (intervino ML)"),
        ("recontact", "Recontacto"),
        ("none", "Sin etapa"),
    ], string="Etapa")
    status = fields.Selection([
        ("opened", "Abierto"),
        ("closed", "Cerrado"),
        ("in_process", "En proceso"),
        ("solved", "Resuelto"),
    ], string="Estado")
    reason_id = fields.Char(string="Reason Id", help="Codigo de motivo del reclamo (catalogo ML).")

    date_created = fields.Datetime(string="Creado")
    last_updated = fields.Datetime(string="Ultima actualizacion")

    # Datos crudos para inspeccion / debugging (no para logica de negocio)
    players_json = fields.Text(string="Players (JSON)", help="Partes del reclamo (comprador, vendedor, ML).")
    resolution_json = fields.Text(string="Resolution (JSON)", help="Resolucion propuesta/aplicada.")
    raw_json = fields.Text(string="Raw (JSON)")

    _unique_claim_id = versions.UniqueIndex('claim_id', message='Claim id already exists!')
    _sql_constraints = versions.sql_constraints_if_no_unique_index([
        ('unique_claim_id', 'claim_id', 'Claim id already exists!'),
    ])

    def compute_claim_link(self):
        company = self.env.user.company_id
        for c in self:
            if c.claim_id:
                c.claim_link = company.get_ML_LINK_URL() + "reclamos/" + str(c.claim_id)

    claim_link = fields.Char(string="Claim Link", compute=compute_claim_link)

    # ------------------------------------------------------------------ #
    #  Parseo defensivo del JSON de un reclamo                            #
    # ------------------------------------------------------------------ #
    def prepare_claim_fields(self, Claim, meli=None, config=None):
        import json as _json
        resource = Claim.get("resource") or (Claim.get("resource_type") or "")
        resource_id = Claim.get("resource_id") or ""
        claim_fields = {
            'name': "Reclamo %s" % str(Claim.get("id") or ""),
            'claim_id': str(Claim.get("id") or ""),
            'resource': resource,
            'resource_id': str(resource_id),
            'type': Claim.get("type"),
            'stage': Claim.get("stage"),
            'status': Claim.get("status"),
            'reason_id': Claim.get("reason_id"),
            'date_created': ml_datetime(Claim.get("date_created")) if Claim.get("date_created") else False,
            'last_updated': ml_datetime(Claim.get("last_updated")) if Claim.get("last_updated") else False,
            'players_json': _json.dumps(Claim.get("players")) if Claim.get("players") else False,
            'resolution_json': _json.dumps(Claim.get("resolution")) if Claim.get("resolution") else False,
            'raw_json': _json.dumps(Claim),
        }
        # Intentar vincular con la orden ML por resource_id (cuando resource=order)
        if resource_id and resource in ("order", "purchase", ""):
            order = self.env['mercadolibre.orders'].search(
                [('order_id', '=', str(resource_id))], limit=1)
            if order:
                claim_fields['order_id'] = order.id
                claim_fields['company_id'] = order.company_id.id if order.company_id else False
        return claim_fields

    def fetch_claim(self, claim_id=None, meli=None, config=None):
        Claim = None
        if not meli:
            meli = self.env['meli.util'].get_new_instance(config)
        if meli.need_login():
            return meli.redirect_login()
        response = meli.get("/post-purchase/v1/claims/" + str(claim_id),
                            {'access_token': meli.access_token})
        if response:
            cjson = response.json()
            if isinstance(cjson, dict) and 'error' in cjson:
                _logger.error("fetch_claim error: %s", cjson)
            else:
                Claim = cjson
        return Claim

    def process_claim(self, claim_id=None, Claim=None, meli=None, config=None):
        claims_obj = self
        claim = None
        if claim_id and not Claim:
            Claim = claims_obj.fetch_claim(claim_id=claim_id, meli=meli, config=config)
        if Claim and 'id' in Claim:
            claim_fields = self.prepare_claim_fields(Claim=Claim, meli=meli, config=config)
            claim = claims_obj.search([('claim_id', '=', claim_fields['claim_id'])], limit=1)
            if not claim:
                claim = claims_obj.create(claim_fields)
            else:
                claim.write(claim_fields)
        return claim

    # ------------------------------------------------------------------ #
    #  Sincronizacion (read-only): trae los reclamos del vendedor         #
    # ------------------------------------------------------------------ #
    def sync_claims(self, meli=None, config=None, status="opened", limit=50):
        """Lista los reclamos del vendedor y los upserta localmente.
        Read-only contra MercadoLibre. Devuelve la cantidad procesada."""
        if not config:
            config = self.env.user.company_id
        if not meli:
            meli = self.env['meli.util'].get_new_instance(config)
        if meli.need_login():
            _logger.warning("sync_claims: requiere login ML para la cuenta %s", config and config.id)
            return 0
        params = {'access_token': meli.access_token, 'limit': limit}
        if status:
            params['status'] = status
        response = meli.get("/post-purchase/v1/claims/search", params)
        if not response:
            return 0
        rjson = response.json()
        if isinstance(rjson, dict) and 'error' in rjson:
            _logger.error("sync_claims error: %s", rjson)
            return 0
        data = rjson.get("data") if isinstance(rjson, dict) else rjson
        count = 0
        for Claim in (data or []):
            cid = Claim.get("id")
            if not cid:
                continue
            # El search a veces trae el detalle parcial; refrescar el completo
            full = self.fetch_claim(claim_id=cid, meli=meli, config=config) or Claim
            self.process_claim(Claim=full, meli=meli, config=config)
            count += 1
        _logger.info("sync_claims: %s reclamos procesados (status=%s) cuenta=%s",
                     count, status, config and config.id)
        return count

    @api.model
    def cron_sync_claims(self, status="opened", limit=50):
        """Cron READ-ONLY: sincroniza reclamos abiertos de cada compania con
        conexion ML configurada. Desactivado por defecto en el cron data."""
        companies = self.env['res.company'].search([])
        total = 0
        for company in companies:
            try:
                meli = self.env['meli.util'].get_new_instance(company)
                if not meli or meli.need_login():
                    continue
                total += self.sync_claims(meli=meli, config=company, status=status, limit=limit)
            except Exception as e:
                _logger.warning("cron_sync_claims: cuenta %s fallo: %s", company.id, e)
        _logger.info("cron_sync_claims: total %s reclamos sincronizados", total)
        return total
