# -*- coding: utf-8 -*-

import logging

from odoo import models, api, fields
import odoo.addons.decimal_precision as dp
from odoo.tools.translate import _
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT as DTF

_logger = logging.getLogger(__name__)

class MeliCampaign(models.Model):

    _name = 'meli.campaign'
    _description = u'Campañas de Oferta MELI'
    
    meli_id = fields.Char(u'MELI ID')
    name = fields.Char(u'Nombre')
    description = fields.Text(string=u'Descripcion')
    state = fields.Selection([
        ('test','Pruebas'),
        ('pending','Pendiente'),
        ('active','Activa'),
        ('inactive','Inactiva'),
        ], string=u'Estado', index=True, readonly=True)
    date_from = fields.Datetime(u'Desde')
    date_to = fields.Datetime(u'Hasta')
    offers_reception_deadline = fields.Datetime(u'Fecha maxima de Publicacion')
    rule_ids = fields.One2many('meli.campaign.rule', 'meli_campaign_id', u'Requisitos')
    active = fields.Boolean(u'Activo?', default=True)
    
    @api.model
    def find_create(self, campaign_json):
        campaign = self.search([('meli_id','=',campaign_json['id'])])
        campaign_vals = self._prepare_campaign_vals(campaign_json)
        if campaign:
            _logger.info("Actualizando Campaña: %s ID: %s ", campaign.name, campaign.meli_id)
            campaign.write(campaign_vals)
        else:
            _logger.info("Creando Campaña: %s ID: %s ", campaign_vals['name'], campaign_vals['meli_id'])
            campaign = self.create(campaign_vals)
        return campaign
    
    @api.model
    def _prepare_campaign_vals(self, campaign_json):
        meli_util = self.env['meli.util']
        meli_categ_model = self.env['mercadolibre.category']
        meli_categ_recs = meli_categ_model.browse()
        campaign_vals = {
            'meli_id': campaign_json['id'],
            'name': campaign_json['name'],
            'description': campaign_json.get('description'),
            'state': campaign_json.get('status'),
            'date_from': meli_util.convert_to_datetime(campaign_json.get('start_time')).strftime(DTF),
            'date_to': meli_util.convert_to_datetime(campaign_json.get('end_time')).strftime(DTF),
            'offers_reception_deadline': meli_util.convert_to_datetime(campaign_json.get('offers_reception_deadline')).strftime(DTF),
        }
        rule_ids = [(5, 0)]
        for rule in campaign_json.get('requisites', []):
            params = rule.get('parameters', {})
            meli_categ_recs = meli_categ_model.browse()
            for categ_id in rule.get('categories', []):
                meli_categ_recs |= meli_categ_model.import_category(categ_id)
            rule_ids.append((0, 0, {
                'name': rule.get('name', ''),
                'description': rule.get('description', ''),
                'criteria': rule.get('criteria', ''),
                'currency': params.get('currency', ''),
                'value': params.get('value', ''),
                'meli_listing_type': params.get('type', ''),
                'meli_categ_ids': [(6, 0, meli_categ_recs.ids)],             
            }))
        campaign_vals['rule_ids'] = rule_ids
        return campaign_vals
    
class MeliCampaignRule(models.Model):

    _name = 'meli.campaign.rule'
    _description = u'Requisitos de Campañas de Oferta MELI'
    
    meli_campaign_id = fields.Many2one('meli.campaign', u'Campaña', ondelete="cascade")
    name = fields.Char(u'Nombre')
    description = fields.Text(string=u'Descripcion')
    criteria = fields.Selection([
        ('original_price','Precio Original'),
        ('retail_price','Precio Retail'),
        ('NA','Ninguno'),
        ], string=u'Criterio', readonly=True)
    meli_categ_ids = fields.Many2many('mercadolibre.category', 
        'meli_campaign_rule_category_rel', 'rule_id', 'category_id', u'Categorias')
    currency = fields.Char(u'Moneda')
    value = fields.Float(u'Valor', digits=dp.get_precision('Account'))
    meli_listing_type = fields.Selection([
        ("free","Libre"),
        ("bronze","Bronce"),
        ("silver","Plata"),
        ("gold","Oro"),
        ("gold_premium","Gold Premium"),
        ("gold_special","Gold Special"),
        ("gold_pro","Oro Pro"),
        ], string='Tipo de lista')
    
