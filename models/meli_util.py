# -*- coding: utf-8 -*-

import pytz

from odoo import models, api, fields
import odoo.addons.decimal_precision as dp
from odoo.tools.translate import _

import requests
try:
    from urllib import urlencode
except ImportError:
    from urllib.parse import urlencode
import logging
_logger = logging.getLogger(__name__)

from .meli_oerp_config import REDIRECT_URI
from ..melisdk.meli import Meli

#from ..melisdk.sdk3 import meli
import meli
from meli.rest import ApiException
from meli.api_client import ApiClient

from datetime import datetime

configuration = meli.Configuration(
    host = "https://api.mercadolibre.com"
)

class MeliApi( meli.RestClientApi ):

    AUTH_URL = "https://auth.mercadolibre.com.ar/authorization"
    needlogin_state = True

    client_id = ""
    client_secret = ""
    access_token = ""
    refresh_token = ""
    redirect_uri = ""
    response = ""
    code = ""
    rjson = {}

    user = {}

    def need_login(self):
        return self.needlogin_state

    def json(self):
        return self.rjson

    def get(self, path, params={}):
        try:
            atok = ("access_token" in params and params["access_token"]) or ""
            #_logger.info("MeliApi.get(%s,%s)" % (path,str(atok)) )
            self.response = self.resource_get(resource=path, access_token=atok)
            self.rjson = self.response
        except ApiException as e:
            self.rjson =  {
                "error": "%s" % e
            }
        return self

    def post(self, path, body=None, params={}):
        try:
            atok = ("access_token" in params and params["access_token"]) or ""
            #_logger.info("MeliApi.post(%s,%s)  %s" % (path,str(atok),str(body)) )
            self.response = self.resource_post(resource=path, access_token=atok, body=body )
            self.rjson = self.response
        except ApiException as e:
            self.rjson = {
                "error": "%s" % e
            }
        return self

    def put(self, path, body=None, params={}):
        try:
            atok = ("access_token" in params and params["access_token"]) or ""
            #_logger.info("MeliApi.put(%s,%s)  %s" % (path,str(atok),str(body)) )
            self.response = self.resource_put(resource=path, access_token=atok, body=body )
            self.rjson = self.response
        except ApiException as e:
            self.rjson = {
                "error": "%s" % e
            }
        return self

    def delete(self, path, params={}):
        try:
            atok = ("access_token" in params and params["access_token"]) or ""
            #_logger.info("MeliApi.delete(%s,%s)  %s" % (path,str(atok),str(body)) )
            self.response = self.resource_delete(resource=path, access_token=atok )
            self.rjson = self.response
        except ApiException as e:
            self.rjson = {
                "error": "%s" % e
            }
        return self

    def auth_url(self, redirect_URI=None):
        now = datetime.now()
        url = ""
        if redirect_URI:
            self.redirect_uri = redirect_URI
        random_id = str(now)
        params = { 'client_id': self.client_id, 'response_type':'code', 'redirect_uri':self.redirect_uri,'state': random_id}
        url = self.AUTH_URL  + '?' + urlencode(params)
        _logger.info("Authorize Login here: "+str(url))
        return url

    def redirect_login(self):
        url_login_meli = str(self.auth_url())
        return {
            "type": "ir.actions.act_url",
            "url": url_login_meli,
            "target": "self",
        }

    def authorize(self, code, redirect_uri=None):
        api_client = ApiClient()
        api_auth_client = meli.OAuth20Api(api_client)
        if redirect_uri:
            self.redirect_uri = redirect_uri
        grant_type = 'authorization_code'
        response_info = api_auth_client.get_token(grant_type=grant_type,
                                            client_id=self.client_id,
                                            client_secret=self.client_secret,
                                            redirect_uri=self.redirect_uri,
                                            code=code,
                                            refresh_token=self.refresh_token)
        _logger.info("MeliApi authorize:"+str(response_info))
        if 'access_token' in response_info:
            self.access_token = response_info['access_token']
            if 'refresh_token' in response_info:
                self.refresh_token = response_info['refresh_token']
            else:
                self.refresh_token = ''
        return response_info


class MeliUtil(models.AbstractModel):

    _name = 'meli.util'
    _description = u'Utilidades para Mercado Libre'

    def get_meli_state( self ):
        return self.get_new_instance()

    @api.model
    def get_new_instance(self, company=None):

        if not company:
            company = self.env.user.company_id

        #CLIENT_ID = company.mercadolibre_client_id
        #CLIENT_SECRET = company.mercadolibre_secret_key
        #ACCESS_TOKEN = company.mercadolibre_access_token
        #REFRESH_TOKEN = company.mercadolibre_refresh_token
        #REDIRECT_URI = company.mercadolibre_redirect_uri
        #CODE = company.mercadolibre_code

        api_client = ApiClient()
        api_rest_client = MeliApi(api_client)
        api_rest_client.client_id = company.mercadolibre_client_id
        api_rest_client.client_secret = company.mercadolibre_secret_key
        api_rest_client.access_token = company.mercadolibre_access_token
        api_rest_client.refresh_token = company.mercadolibre_refresh_token
        api_rest_client.redirect_uri = company.mercadolibre_redirect_uri
        api_auth_client = meli.OAuth20Api(api_client)
        grant_type = 'authorization_code' # or 'refresh_token' if you need get one new token

        #api_response = api_instance.get_token(grant_type=grant_type, client_id=CLIENT_ID, client_secret=CLIENT_SECRET, redirect_uri=REDIRECT_URI, code=CODE, refresh_token=REFRESH_TOKEN)
        #taken from res.company get_meli_state()
        api_rest_client.needlogin_state = False
        message = "Login to ML needed in Odoo."

        #pdb.set_trace()
        try:
            if not (company.mercadolibre_seller_id==False):
                response = api_rest_client.get("/users/"+str(company.mercadolibre_seller_id), {'access_token':api_rest_client.access_token} )

                #_logger.info("get_new_instance connection response:"+str(response))
                rjson = response.json()
                #_logger.info(rjson)
                if "error" in rjson:
                    api_rest_client.needlogin_state = True

                    _logger.error(rjson)

                    if rjson["error"]=="not_found":
                        api_rest_client.needlogin_state = True

                    if "message" in rjson:
                        message = rjson["message"]
                        if (rjson["message"]=="expired_token" or rjson["message"]=="invalid_token"):
                            api_rest_client.needlogin_state = True
                            try:
                                #refresh = meli.get_refresh_token()
                                refresh = api_auth_client.get_token(grant_type=grant_type,
                                                                    client_id=company.mercadolibre_client_id,
                                                                    client_secret=company.mercadolibre_secret_key,
                                                                    redirect_uri=company.mercadolibre_redirect_uri,
                                                                    code=company.mercadolibre_code,
                                                                    refresh_token=company.mercadolibre_refresh_token)
                                _logger.info("need to refresh:"+str(refresh))
                                if (refresh):
                                    refjson = refresh.json()
                                    api_rest_client.access_token = refjson["access_token"]
                                    api_rest_client.refresh_token = refjson["refresh_token"]
                                    api_rest_client.code = ''
                                    company.write({ 'mercadolibre_access_token': api_rest_client.access_token,
                                                    'mercadolibre_refresh_token': api_rest_client.refresh_token,
                                                    'mercadolibre_code': '' } )
                                    api_rest_client.needlogin_state = False
                            except Exception as e:
                                _logger.error(e)
                else:
                    #saving user info, brand, official store ids, etc...
                    response.user = rjson
            else:
                api_rest_client.needlogin_state = True

            if api_rest_client.access_token=='' or api_rest_client.access_token==False:
                api_rest_client.needlogin_state = True

        except requests.exceptions.ConnectionError as e:
            #raise osv.except_osv( _('MELI WARNING'), _('NO INTERNET CONNECTION TO API.MERCADOLIBRE.COM: complete the Cliend Id, and Secret Key and try again'))
            api_rest_client.needlogin_state = True
            error_msg = 'MELI WARNING: NO INTERNET CONNECTION TO API.MERCADOLIBRE.COM: complete the Cliend Id, and Secret Key and try again '
            _logger.error(error_msg)

        #        except requests.exceptions.HTTPError as e:
        #            _logger.info( "And you get an HTTPError:", e.message )

        if api_rest_client.needlogin_state:

            company.write({'mercadolibre_access_token': '', 'mercadolibre_refresh_token': '', 'mercadolibre_code': '' } )

            if (company.mercadolibre_refresh_token and company.mercadolibre_cron_mail):
                # we put the job_exception in context to be able to print it inside
                # the email template
                context = {
                    'job_exception': message,
                    'dbname': self._cr.dbname,
                }

                _logger.debug(
                    "Sending scheduler error email with context=%s", context)

                self.env['mail.template'].browse(
                    company.mercadolibre_cron_mail.id
                ).with_context(context).sudo().send_mail( (company.id), force_send=True)

        #_logger.info("ML_state: need login? "+str(ML_state))
        for comp in company:
            comp.mercadolibre_state = api_rest_client.needlogin_state

        return api_rest_client

    @api.model
    def get_url_meli_login(self, app_instance):
        if not company:
            company = self.env.user.company_id
        REDIRECT_URI = company.mercadolibre_redirect_uri
        url_login_meli = app_instance.auth_url(redirect_URI=REDIRECT_URI)
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
