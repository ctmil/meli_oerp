# -*- coding: utf-8 -*-

import base64

from odoo import http, api


from odoo import fields, http
from odoo.http import Controller, Response, request, route
try:
    from odoo.http import content_disposition
except ImportError:
    from odoo.addons.web.controllers.main import content_disposition
    pass;
import json
import sys
import pprint
pp = pprint.PrettyPrinter(indent=4)

import pdb
import logging
_logger = logging.getLogger(__name__)


from ..models.versions import *
from ..models.meli_util import _meli_mask

def _get_headers(filename, filetype, content):
    return [
        ('Content-Type', filetype),
        ('Content-Length', len(content)),
        ('Content-Disposition', content_disposition(filename)),
        ('X-Content-Type-Options', 'nosniff'),
    ]
    
class MercadoLibre(http.Controller):

    # [#661] Fuera /meli/ (página informativa) y /meli/image/* (sin usos): sólo quedan el webhook y el login.

    # csrf=False is required because this endpoint is a webhook called
    # from MercadoLibre servers — they cannot provide an Odoo CSRF token.
    # Authentication is done inside the handler by validating the
    # notification payload (user_id/app_id).
    #
    # The /odoo/meli_notify aliases exist so the webhook works no matter
    # whether the ML app was configured with https://<host>/meli_notify
    # or https://<host>/odoo/meli_notify (Odoo 17+ backend prefix).
    @http.route(
        ['/meli_notify', '/odoo/meli_notify'],
        type=route_typejson, auth='public', methods=["POST"], csrf=False,
    )
    def meli_notify(self,**kw):
        _logger.info("meli_notify")
        #_logger.info(kw)
        company = request.env.user.company_id
        _logger.info(request.env.user)
        _logger.info(company)
        #_logger.info(company.display_name)
        #_logger.info(kw)
        #_logger.info(request)
        data = json.loads(request.httprequest.data)
        _logger.info(data)
        result = company.meli_notifications(data)
        if (result and "error" in result):
            return Response(result["error"],content_type='text/html;charset=utf-8',status=result["status"])
        else:
            return ""

    @http.route(['/meli_notify', '/odoo/meli_notify'], type='http', auth='public', methods=["GET"])
    def meli_notify_http(self,**kw):
        _logger.info("meli_notify_http")
        #_logger.info(kw)
        company = request.env.user.company_id
        _logger.info(request.env.user)
        _logger.info(company)
        #_logger.info(company.display_name)
        #_logger.info(kw)
        #_logger.info(request)
        #data = json.loads(request.httprequest.data)
        #_logger.info(data)
        #result = company.meli_notifications(data)
        #if (result and "error" in result):
        #    return Response(result["error"],content_type='text/html;charset=utf-8',status=result["status"])
        #else:
        return ""


class MercadoLibreLogin(http.Controller):

    @http.route(['/meli_login'], type='http', auth="user", methods=['GET'], website=True)
    def index(self, **codes ):
        company = request.env.user.company_id
        meli_util_model = request.env['meli.util']
        meli = meli_util_model.get_new_instance(company)

        codes.setdefault('code','none')
        codes.setdefault('error','none')
        if codes['error']!='none':
            message = "ERROR: %s" % codes['error']
            return "<h5>"+message+"</h5><br/>Retry (check your redirect_uri field in MercadoLibre company configuration, also the actual user and public user default company must be the same company ): <a href='"+meli.auth_url(redirect_URI=company.mercadolibre_redirect_uri)+"'>Login</a>"

        if codes['code']!='none':
            _logger.info( "Meli: Authorize: REDIRECT_URI: %s" % ( company.mercadolibre_redirect_uri ) )
            resp = meli.authorize( codes['code'], company.mercadolibre_redirect_uri)
            company.write( { 'mercadolibre_access_token': meli.access_token,
                             'mercadolibre_refresh_token': meli.refresh_token,
                             'mercadolibre_code': codes['code'],
                             'mercadolibre_cron_refresh': True } )
            # [#661] La página de login nunca muestra el código ni los tokens.
            return 'CONECTADO A MERCADOLIBRE <br>MercadoLibre Publisher for Odoo - Copyright Moldeo Interactive <br><a href="javascript:window.history.go(-2);">Volver a Odoo</a> <script>window.history.go(-2)</script>'
        else:
            return "<a href='"+meli.auth_url()+"'>Try to Login Again Please</a>"

# [#661] Fuera /meli_authorize/ y /meli_logout/ (páginas informativas; la desconexión es un botón del
# formulario) y /download/saveas (ejecutaba un método elegido por quien llamaba; ningún módulo la usaba).
