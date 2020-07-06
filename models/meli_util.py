# -*- coding: utf-8 -*-

import pytz

from odoo import models, api, fields
import odoo.addons.decimal_precision as dp
from odoo.tools.translate import _

from .meli_oerp_config import REDIRECT_URI
from ..melisdk.meli import Meli

class MeliUtil(models.AbstractModel):

    _name = 'meli.util'
    _description = u'Utilidades para Mercado Libre'
    
    @api.model
    def get_new_instance(self, company=None):
        if not company:
            company = self.env.user.company_id
        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token
        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)
        return meli
    
    @api.model
    def get_url_meli_login(self, meli):
        url_login_meli = meli.auth_url(redirect_URI=REDIRECT_URI)
        return {
            "type": "ir.actions.act_url",
            "url": url_login_meli,
            "target": "self",
        }
        
    def convert_to_datetime(self, date_str):
        if not date_str:
            return False
        date_str = date_str.replace('T', ' ')
        date_convert = fields.Datetime.from_string(date_str)
        fields_model = self.env['ir.fields.converter']
        from_zone = fields_model._input_tz()
        to_zone = pytz.UTC
        #si no hay informacion de zona horaria, establecer la zona horaria
        if not date_convert.tzinfo:
            date_convert = from_zone.localize(date_convert)
        date_convert = date_convert.astimezone(to_zone)
        return date_convert