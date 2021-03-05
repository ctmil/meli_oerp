# -*- coding: utf-8 -*-

import base64

from odoo import http, api


from odoo import fields, osv, http
from odoo.http import Controller, Response, request, route, JsonRequest
from odoo.addons.web.controllers.main import content_disposition
import json
import sys
import pprint
pp = pprint.PrettyPrinter(indent=4)

import pdb
import logging
_logger = logging.getLogger(__name__)


from ..models.versions import *

class MercadoLibre(http.Controller):
    @http.route('/meli/', auth='public')
    def index(self):
        company = request.env.user.company_id
        meli_util_model = request.env['meli.util']
        meli = meli_util_model.get_new_instance(company)
        if meli.need_login():
            return "<a href='"+meli.auth_url()+"'>Login Please</a>"

        return "MercadoLibre Publisher for Odoo - Copyright Moldeo Interactive 2021"

    @http.route(['/meli_notify'], type='json', auth='public')
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

    @http.route('/meli/image/<int:product_id>', type='http', auth="public")
    @http.route('/meli/image/<int:product_id>/<int:image_id>', type='http', auth="public")
    def meli_image(self, product_id, image_id=None, **kw):

        #browse and read image data to browser
        product = request.env["product.product"].browse(int(product_id))

        if image_id:
            filename = '%s_%s' % ("product.image".replace('.', '_'), str(product_id)+str("_")+str(image_id))
            product_image = request.env["product.image"].browse( int(image_id) )
            if product_image:
                filecontent = base64.b64decode( get_image_full( product_image ) )
            else:
                return ""
        else:
            filename = '%s_%s' % ("meli.image".replace('.', '_'), product_id)
            filecontent = base64.b64decode( get_image_full( product ) )

        return request.make_response(filecontent,
                                     [('Content-Type', 'application/octet-stream'),
                                      ('Content-Disposition', content_disposition(filename))])


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
            _logger.info( "Meli: Authorize: REDIRECT_URI: %s, code: %s" % ( company.mercadolibre_redirect_uri, codes['code'] ) )
            resp = meli.authorize( codes['code'], company.mercadolibre_redirect_uri)
            company.write( { 'mercadolibre_access_token': meli.access_token,
                             'mercadolibre_refresh_token': meli.refresh_token,
                             'mercadolibre_code': codes['code'],
                             'mercadolibre_cron_refresh': True } )
            return 'LOGGED WITH CODE: %s <br>ACCESS_TOKEN: %s <br>REFRESH_TOKEN: %s <br>MercadoLibre Publisher for Odoo - Copyright Moldeo Interactive <br><a href="javascript:window.history.go(-2);">Volver a Odoo</a> <script>window.history.go(-2)</script>' % ( codes['code'], meli.access_token, meli.refresh_token )
        else:
            return "<a href='"+meli.auth_url()+"'>Try to Login Again Please</a>"

class MercadoLibreAuthorize(http.Controller):
    @http.route('/meli_authorize/', auth='public')
    def index(self):
        return "AUTHORIZE: MercadoLibre for Odoo - Moldeo Interactive"


class MercadoLibreLogout(http.Controller):
    @http.route('/meli_logout/', auth='public')
    def index(self):
        return "LOGOUT: MercadoLibre for Odoo - Moldeo Interactive"

class Download(http.Controller):
    """
    Example of utilisation:

    1) Add a "Download" button of type "object" on your form view

    2) Define the method for downloading the file

    from odoo import api, models
    from odoo.tools ustr


    class StockMove(models.Model):
        _inherit = 'stock.move'


        def _get_datas(self):
            self.ensure_one()
            return ustr("Stock n°%s") % self.id


        def button_get_file(self):
            self.ensure_one()
            return {
                'type': 'ir.actions.act_url',
                'url': '/download/saveas?model=%(model)s&record_id=%(record_id)s&method=%(method)s&filename=%(filename)s' % {
                    'filename': 'stock_infos.txt',
                    'model': self._name,
                    'record_id': self.id,
                    'method': '_get_datas',
                },
                'target': 'self',
            }

    """

    @http.route('/download/saveas', type='http', auth="public")
    def saveas(self, model, record_id, method, encoded=False, filename=None, **kw):
        """ Download link for files generated on the fly.

        :param str model: name of the model to fetch the data from
        :param str record_id: id of the record from which to fetch the data
        :param str method: name of the method used to fetch data, decorated with @api.one
        :param bool encoded: whether the data is encoded in base64
        :param str filename: the file's name, if any
        :returns: :class:`werkzeug.wrappers.Response`
        """
        Model = request.env[model].browse(int(record_id))
        datas = getattr(Model, method)()
        if not datas:
            return request.not_found()
        filecontent = datas[0]
        if not filecontent:
            return request.not_found()
        if encoded:
            filecontent = base64.b64decode(filecontent)
        if not filename:
            filename = '%s_%s' % (model.replace('.', '_'), record_id)
        return request.make_response(filecontent,
                                     [('Content-Type', 'application/octet-stream'),
                                      ('Content-Disposition', content_disposition(filename))])
