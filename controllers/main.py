# -*- coding: utf-8 -*-

import base64

from odoo import http, api

from ..melisdk.meli import Meli

from odoo import fields, osv
from odoo.http import Controller, Response, request, route

import pdb
import logging
_logger = logging.getLogger(__name__)


from odoo.addons.web.controllers.main import content_disposition

class MercadoLibre(http.Controller):
    @http.route('/meli/', auth='public')
    def index(self):

        cr, uid, context = request.cr, request.uid, request.context
        #company = request.registry.get('res.company').browse(cr,uid,1)
        company = request.env.user.company_id
        REDIRECT_URI = company.mercadolibre_redirect_uri
        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key
        ACCESS_TOKEN = company.mercadolibre_access_token
        REFRESH_TOKEN = company.mercadolibre_refresh_token

        if (ACCESS_TOKEN==''):
            meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET)
            return "<a href='"+meli.auth_url(redirect_URI=REDIRECT_URI)+"'>Login</a>"

        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET, access_token=ACCESS_TOKEN, refresh_token=REFRESH_TOKEN)
        response = meli.get("/items/MLA533830652")

        return "MercadoLibre for Odoo 8/9/10/11/12/13 - Moldeo Interactive: %s " % response.content

    @http.route(['/meli_notify'], type='json', auth='public')
    def meli_notify(self,**kw):
        _logger.info("meli_notify")
        #_logger.info(kw)
        company = request.env.user.company_id
        result = company.meli_notifications()
        if (result and "error" in result):
            return Response(result["error"],content_type='text/html;charset=utf-8',status=result["status"])
        else:
            return ""

class MercadoLibreLogin(http.Controller):

    @http.route(['/meli_login'], type='http', auth="user", methods=['GET'], website=True)
    def index(self, **codes ):
        cr, uid, context = request.cr, request.uid, request.context
        #company = request.registry.get('res.company').browse(cr,uid,1)
        company = request.env.user.company_id
        REDIRECT_URI = company.mercadolibre_redirect_uri
        CLIENT_ID = company.mercadolibre_client_id
        CLIENT_SECRET = company.mercadolibre_secret_key

        meli = Meli(client_id=CLIENT_ID,client_secret=CLIENT_SECRET)

        codes.setdefault('code','none')
        codes.setdefault('error','none')
        if codes['error']!='none':
            message = "ERROR: %s" % codes['error']
            return "<h5>"+message+"</h5><br/>Retry: <a href='"+meli.auth_url(redirect_URI=REDIRECT_URI)+"'>Login</a>"

        if codes['code']!='none':
            _logger.info( "Meli: Authorize: REDIRECT_URI: %s, code: %s" % ( REDIRECT_URI, codes['code'] ) )
            meli.authorize( codes['code'], REDIRECT_URI)
            ACCESS_TOKEN = meli.access_token
            REFRESH_TOKEN = meli.refresh_token
            company.write({'mercadolibre_access_token': ACCESS_TOKEN, 'mercadolibre_refresh_token': REFRESH_TOKEN, 'mercadolibre_code': codes['code'] } )
            return 'LOGGED WIT CODE: %s <br>ACCESS_TOKEN: %s <br>REFRESH_TOKEN: %s <br>MercadoLibre for Odoo 8 - Moldeo Interactive <br><a href="javascript:window.history.go(-2);">Volver a Odoo</a> <script>window.history.go(-2)</script>' % ( codes['code'], ACCESS_TOKEN, REFRESH_TOKEN )
        else:
            return "<a href='"+meli.auth_url(redirect_URI=REDIRECT_URI)+"'>Login</a>"

class MercadoLibreAuthorize(http.Controller):
    @http.route('/meli_authorize/', auth='public')
    def index(self):
        return "AUTHORIZE: MercadoLibre for Odoo 8 - Moldeo Interactive"


class MercadoLibreLogout(http.Controller):
    @http.route('/meli_logout/', auth='public')
    def index(self):
        return "LOGOUT: MercadoLibre for Odoo 8 - Moldeo Interactive"

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
