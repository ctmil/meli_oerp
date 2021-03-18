# -*- coding: utf-8 -*-

import pytz

from odoo import models, api, fields
import odoo.addons.decimal_precision as dp
from odoo.tools.translate import _

import requests
import json
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
    seller_id = ""

    response = ""
    code = ""
    rjson = {}

    user = {}

    def need_login(self):
        return self.needlogin_state

    def json(self):
        return self.rjson

    def call_get(self, resource=None, access_token=None, **params ):
        return {}

    def get(self, path, params={}):
        try:
            atok = ("access_token" in params and params["access_token"]) or ""
            scroll_id = ("scroll_id" in params and params["scroll_id"]) or None
            if atok:
                del params["access_token"]
            if scroll_id:
                del params["scroll_id"]
            if params:
                path+="?"+urlencode(params)
                if scroll_id:
                    path+="&scroll_id="+scroll_id
            #_logger.info("MeliApi.get(%s,%s)" % (path,str(atok)) )
            self.response = self.resource_get(resource=path, access_token=atok)
            #if params:
            #   self.response = self.call_get( resource=path, access_token=atok, **params)
            self.rjson = self.response
        except ApiException as e:
            self.rjson = {
                "error": "%s" % str("get error"),
                "status": e.status,
                "cause": e.reason,
                "message": e.body
            }
            pass;
        except:
            pass;
        return self

    def post(self, path, body=None, params={}):
        try:
            atok = ("access_token" in params and params["access_token"]) or ""
            #_logger.info("MeliApi.post(%s,%s)  %s" % (path,str(atok),str(body)) )
            self.response = self.resource_post(resource=path, access_token=atok, body=body )
            self.rjson = self.response
        except ApiException as e:
            self.rjson = {
                "error": "%s" % str("post error"),
                "status": e.status,
                "cause": e.reason,
                "message": e.body
            }
            pass;
        except:
            pass;
        return self

    def put(self, path, body=None, params={}):
        try:
            atok = ("access_token" in params and params["access_token"]) or ""
            #_logger.info("MeliApi.put(%s,%s)  %s" % (path,str(atok),str(body)) )
            self.response = self.resource_put(resource=path, access_token=atok, body=body )
            self.rjson = self.response
        except ApiException as e:
            self.rjson = {
                "error": "%s" % str("put error"),
                "status": e.status,
                "cause": e.reason,
                "message": e.body
            }
            pass;
        except:
            pass;
        return self

    def delete(self, path, params={}):
        try:
            atok = ("access_token" in params and params["access_token"]) or ""
            #_logger.info("MeliApi.delete(%s,%s)  %s" % (path,str(atok),str(body)) )
            self.response = self.resource_delete(resource=path, access_token=atok )
            self.rjson = self.response
        except ApiException as e:
            self.rjson = {
                "error": "%s" % e,
                "status": e.status,
                "cause": e.reason,
                "message": e.body
            }
        except:
            pass;
        return self

    def upload(self, path, files, params={}):
        try:
            atok = ("access_token" in params and params["access_token"]) or ""
            headers = {'Accept': 'application/json', 'Content-type':'multipart/form-data'}
            params = {"access_token":atok}
            #headers = {'Authorization': 'Bearer '+atok}
            headers = {}
            uri = configuration.host+str(path)
            _logger.info(headers)
            self.response = requests.post(uri, files=files, params=urlencode(params), headers=headers)
            self.rjson = self.response.json()
        except Exception as e:
            self.rjson = {
                "error": "%s" % e
            }
        except:
            pass;
        return self

    def uploadfiles( self, path, files, params={}):
        try:
            atok = ("access_token" in params and params["access_token"]) or ""
            headers = {'Accept': 'application/json', 'Content-type':'multipart/form-data'}
            params = {}
            headers = {'Authorization': 'Bearer '+atok}
            uri = configuration.host+str(path)
            _logger.info(headers)
            self.response = requests.post(uri, files=files, params=urlencode(params), headers=headers)
            self.rjson = self.response.json()
        except Exception as e:
            self.rjson = {
                "error": "%s" % e
            }
        except:
            pass;
        return self

    def auth_url(self, redirect_URI=None):
        now = datetime.now()
        url = ""
        if redirect_URI:
            self.redirect_uri = redirect_URI
        random_id = str(now)
        params = { 'client_id': self.client_id, 'response_type':'code', 'redirect_uri':self.redirect_uri, 'state': random_id}
        url = self.AUTH_URL  + '?' + urlencode(params)
        #_logger.info("Authorize Login here: "+str(url))
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
        #_logger.info("MeliApi authorize:"+str(response_info))
        if 'access_token' in response_info:
            self.access_token = response_info['access_token']
            if 'refresh_token' in response_info:
                self.refresh_token = response_info['refresh_token']
            else:
                self.refresh_token = ''
        return response_info

    def get_refresh_token(self, code=None, redirect_uri=None):
        api_client = ApiClient()
        api_auth_client = meli.OAuth20Api(api_client)
        grant_type = 'refresh_token'
        response_info = api_auth_client.get_token(grant_type=grant_type,
                                            client_id=self.client_id,
                                            client_secret=self.client_secret,
                                            #redirect_uri=self.redirect_uri,
                                            #code=code,
                                            refresh_token=self.refresh_token)
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

        api_client = ApiClient()
        api_rest_client = MeliApi(api_client)
        api_rest_client.client_id = company.mercadolibre_client_id
        api_rest_client.client_secret = company.mercadolibre_secret_key
        api_rest_client.access_token = company.mercadolibre_access_token or ''
        api_rest_client.refresh_token = company.mercadolibre_refresh_token
        api_rest_client.redirect_uri = company.mercadolibre_redirect_uri
        api_rest_client.seller_id = company.mercadolibre_seller_id
        api_rest_client.AUTH_URL = company.get_ML_AUTH_URL(meli=api_rest_client)
        api_auth_client = meli.OAuth20Api(api_client)
        grant_type = 'authorization_code' # or 'refresh_token' if you need get one new token
        last_token = api_rest_client.access_token

        #api_response = api_instance.get_token(grant_type=grant_type, client_id=CLIENT_ID, client_secret=CLIENT_SECRET, redirect_uri=REDIRECT_URI, code=CODE, refresh_token=REFRESH_TOKEN)
        #taken from res.company get_meli_state()
        api_rest_client.needlogin_state = False
        message = "Login to ML needed in Odoo."

        #pdb.set_trace()
        try:
            if not (company.mercadolibre_seller_id==False) and api_rest_client.access_token!='':
                response = api_rest_client.get("/users/"+str(company.mercadolibre_seller_id), {'access_token':api_rest_client.access_token} )

                #_logger.info("get_new_instance connection response:"+str(response))
                rjson = response.json()
                #_logger.info(rjson)
                if "error" in rjson:

                    if company.mercadolibre_cron_refresh:
                        internals = {
                            "application_id": company.mercadolibre_client_id,
                            "user_id": company.mercadolibre_seller_id,
                            "topic": "internal",
                            "resource": "get_new_instance #"+str(company.name),
                            "state": "PROCESSING"
                        }
                        noti = self.env["mercadolibre.notification"].start_internal_notification( internals )

                        errors = str(rjson)+"\n"
                        logs = str(rjson)+"\n"

                        api_rest_client.needlogin_state = True

                        _logger.error(rjson)

                        if rjson["error"]=="not_found":
                            api_rest_client.needlogin_state = True
                            logs+= "NOT FOUND"+"\n"

                        if "message" in rjson:
                            message = rjson["message"]
                            if "message" in message:
                                #message is e.body, fix thiss
                                try:
                                    mesjson = json.loads(message)
                                    message = mesjson["message"]
                                except:
                                    message = "invalid_token"
                                    pass;
                            logs+= str(message)+"\n"
                            _logger.info("message: " +str(message))
                            if (message=="expired_token" or message=="invalid_token"):
                                api_rest_client.needlogin_state = True
                                try:
                                    #refresh = meli.get_refresh_token()
                                    refresh = api_rest_client.get_refresh_token()
                                    _logger.info("Refresh result: "+str(refresh))
                                    if (refresh):
                                        #refjson = refresh.json()
                                        refjson = refresh
                                        logs+= str(refjson)+"\n"
                                        if "access_token" in refjson:
                                            api_rest_client.access_token = refjson["access_token"]
                                            api_rest_client.refresh_token = refjson["refresh_token"]
                                            api_rest_client.code = ''
                                            company.write({ 'mercadolibre_access_token': api_rest_client.access_token,
                                                            'mercadolibre_refresh_token': api_rest_client.refresh_token,
                                                            'mercadolibre_code': '' } )
                                            api_rest_client.needlogin_state = False
                                except Exception as e:
                                    errors += str(e)
                                    logs += str(e)
                                    _logger.error(e)
                                    pass;
                                except:
                                    pass;

                        noti.stop_internal_notification( errors=errors , logs=logs )

                else:
                    #saving user info, brand, official store ids, etc...
                    #if "phone" in rjson:
                    #    _logger.info("phone:")
                    response.user = rjson


            else:
                api_rest_client.needlogin_state = True

            #        except requests.exceptions.HTTPError as e:
            #            _logger.info( "And you get an HTTPError:", e.message )

        except requests.exceptions.ConnectionError as e:
            #raise osv.except_osv( _('MELI WARNING'), _('NO INTERNET CONNECTION TO API.MERCADOLIBRE.COM: complete the Cliend Id, and Secret Key and try again'))
            api_rest_client.needlogin_state = True
            error_msg = 'MELI WARNING: NO INTERNET CONNECTION TO API.MERCADOLIBRE.COM: complete the Cliend Id, and Secret Key and try again '
            _logger.error(error_msg)

        if api_rest_client.access_token=='' or api_rest_client.access_token==False:
            api_rest_client.needlogin_state = True

        try:
            if api_rest_client.needlogin_state:
                _logger.error("Need login for "+str(company.name))

                if (company.mercadolibre_cron_refresh and company.mercadolibre_cron_mail):
                    company.write({'mercadolibre_access_token': '', 'mercadolibre_refresh_token': '', 'mercadolibre_code': '', 'mercadolibre_cron_refresh': False } )

                    # we put the job_exception in context to be able to print it inside
                    # the email template
                    context = {
                        'job_exception': message,
                        'dbname': self._cr.dbname,
                    }

                    _logger.info(
                        "Sending scheduler error email with context=%s", context)
                    _logger.info("Sending to company:" + str(company.name)+ " mail:" + str(company.email)  )
                    rese = self.env['mail.template'].browse(
                                company.mercadolibre_cron_mail.id
                            ).with_context(context).sudo().send_mail( (company.id), force_send=True)
                    _logger.info("Result sending:" + str(rese) )
                company.write({'mercadolibre_access_token': '', 'mercadolibre_refresh_token': '', 'mercadolibre_code': '', 'mercadolibre_cron_refresh': False } )

        except Exception as e:
            _logger.error(e)

        for comp in company:
            if (last_token!=comp.mercadolibre_access_token):#comp.mercadolibre_state!=api_rest_client.needlogin_state:
                _logger.info("mercadolibre_state : "+str(api_rest_client.needlogin_state))
                comp.mercadolibre_state = api_rest_client.needlogin_state
            #else:
            #    _logger.info("mercadolibre_state already set: "+str(api_rest_client.needlogin_state))

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
