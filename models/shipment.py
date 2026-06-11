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

from odoo import fields, models, api
import logging
from .meli_oerp_config import *

#from ..melisdk.meli import Meli

import json

import logging
_logger = logging.getLogger(__name__)

from urllib.request import urlopen
import requests
import base64
import io
import zipfile
try:
    base64encode = base64.encodestring
except:
    base64encode = base64.encodebytes
    pass;

import mimetypes
from . import orders
from . import product
from . import product_post
from . import posting
from . import res_partner

# pdf2image es opcional - solo se usa para generar preview JPG de etiquetas PDF
PDF2IMAGE_AVAILABLE = False
try:
    from pdf2image import convert_from_bytes
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    convert_from_bytes = None
    _logger.info("pdf2image no disponible - La preview de etiquetas PDF no estará habilitada")

from dateutil.parser import *
from datetime import *

from . import versions
from .versions import *

#
#     https://www.odoo.com/fr_FR/forum/aide-1/question/solved-call-report-and-save-result-to-attachment-133244
#


#
# https://api.mercadolibre.com/shipment_labels?shipment_ids=20178600648,20182100995&response_type=pdf&access_token=
class mercadolibre_shipment_print(models.TransientModel):
    _name = "mercadolibre.shipment.print"
    _description = "Impresión de etiquetas"

    def __shipment_stock_picking_print(self):
        return self.shipment_print()

    def shipment_print(self, context=None, meli=None, config=None):
        context = context or self.env.context
        company = self.env.user.company_id
        if not config:
            config = company

        _logger.info( "shipment_print context: " + str(context) )
        active_ids = ('active_ids' in context and context['active_ids']) or []
        shipment_ids = []
        #check if model is stock_picking or mercadolibre.shipment
        #stock.picking > sale_id is the order, then the shipment is sale_id.meli_shipment
        active_model = context.get("active_model")
        #_logger.info( "shipment_print active_model: " + str(active_model) )

        if active_model == "stock.picking":
            shipment_ids_from_pick = []
            for spick_id in active_ids:
                spick = self.env["stock.picking"].browse(spick_id)
                sale_order = spick.sale_id
                if sale_order and sale_order.meli_shipment:
                    shipment_ids_from_pick.append(sale_order.meli_shipment.id)
            shipment_ids = shipment_ids_from_pick
            #_logger.info("stock.picking shipment_ids:"+str(shipment_ids))

        if active_model == "sale.order":
            shipment_ids_from_order = []
            for order_id in active_ids:
                sale_order = self.env["sale.order"].browse(order_id)
                if sale_order and sale_order.meli_shipment:
                    shipment_ids_from_order.append(sale_order.meli_shipment.id)
            shipment_ids = shipment_ids_from_order
            #_logger.info("sale.order shipment_ids:"+str(shipment_ids))

        shipment_obj = self.env['mercadolibre.shipment']
        warningobj = self.env['meli.warning']

        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)
            if meli.need_login():
                return meli.redirect_login()

        #_logger.info("shipment_print")
        #_logger.info(shipment_ids)

        return self.shipment_print_report(shipment_ids=shipment_ids,meli=meli,config=config,include_ready_to_print=self.include_ready_to_print)

    def shipment_sale_order_print( self, context=None, meli=None, config=None):
        _logger.info("shipment_sale_order_print")
        context = context or self.env.context
        company = self.env.user.company_id
        if not config:
            config = company
        order_ids = ('active_ids' in context and context['active_ids']) or []
        #product_obj = self.env['product.template']
        sale_obj = self.env['sale.order']
        shipment_obj = self.env['mercadolibre.shipment']
        warningobj = self.env['meli.warning']

        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)
            if meli.need_login():
                return meli.redirect_login()

        sep = ""
        shipment_ids= []

        for order_id in order_ids:
            #sacar la orden relacionada
            #de la orden sacar el shipping id
            sorder = sale_obj.browse(order_id)
            shipid = None
            shipment = None
            if (sorder):
                if (sorder.meli_shipment):
                    shipid = sorder.meli_shipment.id
                if ( (not shipid) and len(sorder.meli_orders) ):
                    shipment = shipment_obj.search([('shipping_id','=',sorder.meli_orders[0].shipping_id)])
                    if (shipment and shipment.status=="ready_to_ship"):
                        shipid = shipment.id
            else:
                continue;

            if (shipid):
                #shipment = shipment_obj.browse(shipid)
                #shipment.update()
                shipment_ids.append(shipid)

        return self.shipment_print_report(shipment_ids=shipment_ids,meli=meli,config=config,include_ready_to_print=self.include_ready_to_print)


    def _get_labels_urls_auto_print(self, shipment_ids=[], meli=None, config=None, include_ready_to_print=None):
        data = self._get_shipment_labels_data(
            shipment_ids=shipment_ids,
            meli=meli,
            config=config,
            include_ready_to_print=include_ready_to_print
        )

        urls = [token_data["url"] for token_data in data["by_token"].values()]

        return {
            "urls": urls,
            "print_mode": data["print_mode"],
            "count": len(urls),
        }


    def _get_shipment_labels_data(
        self,
        shipment_ids=[],
        meli=None,
        config=None,
        include_ready_to_print=None
    ):
        shipment_obj = self.env["mercadolibre.shipment"]

        # ------------------------------------------------------------
        # 1) Decide print_mode ONCE (authoritative decision)
        # ------------------------------------------------------------
        if config and "mercadolibre_shipment_print_guide_mode" in config._fields:
            resolved_print_mode = config.mercadolibre_shipment_print_guide_mode or "zpl"
        else:
            resolved_print_mode = "zpl"

        result = {
            "by_token": {},
            "shipments_status": {
                "ready": [],
                "not_ready": []
            },
            "print_mode": resolved_print_mode,
        }

        # ------------------------------------------------------------
        # 2) Iterate shipments (NO print_mode mutation here)
        # ------------------------------------------------------------
        for shipid in shipment_ids:
            shipment = shipment_obj.browse(shipid)

            ship_report = shipment.shipment_print(
                meli=meli,
                config=config,
                include_ready_to_print=include_ready_to_print
            )

            is_already_printed = shipment.substatus == "printed"
            has_printable_status = shipment.status in ("ready_to_ship", "shipped")
            should_include = (
                has_printable_status
                and (not is_already_printed or include_ready_to_print)
            )

            if should_include:
                atoken = ship_report.get("access_token")
                if atoken:
                    result["by_token"].setdefault(
                        atoken,
                        {"shipment_ids": [], "url": None}
                    )
                    result["by_token"][atoken]["shipment_ids"].append(
                        shipment.shipping_id
                    )
                    result["shipments_status"]["ready"].append(
                        {
                            "shipment_id": shipment.shipping_id,
                            "status": shipment.status,
                            "substatus": shipment.substatus,
                        }
                    )
            else:
                result["shipments_status"]["not_ready"].append(
                    {
                        "shipment_id": shipment.shipping_id,
                        "status": shipment.status,
                        "substatus": shipment.substatus,
                    }
                )

        # ------------------------------------------------------------
        # 3) Build FINAL MELI URLs (single source of truth)
        # ------------------------------------------------------------
        response_type = "zpl2" if resolved_print_mode in ("zpl", "zpl_txt") else "pdf"

        for atoken, token_data in result["by_token"].items():
            token_data["url"] = (
                "https://api.mercadolibre.com/shipment_labels"
                f"?shipment_ids={','.join(token_data['shipment_ids'])}"
                f"&response_type={response_type}"
                f"&access_token={atoken}"
            )

        return result



    def shipment_stock_picking_print(self, context=None, meli=None, config=None):
        _logger.info("shipment_stock_picking_print")
        context = context or self.env.context
        company = self.env.user.company_id
        if not config:
            config = company
        picking_ids = ('active_ids' in context and context['active_ids']) or []
        #product_obj = self.env['product.template']
        picking_obj = self.env['stock.picking']
        shipment_obj = self.env['mercadolibre.shipment']
        warningobj = self.env['meli.warning']

        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)
            if meli.need_login():
                return meli.redirect_login()

        sep = ""
        shipment_ids= []

        for pick_id in picking_ids:
            #sacar la orden relacionada
            #de la orden sacar el shipping id
            pick = picking_obj.browse(pick_id)
            shipid = None
            shipment = None
            if (pick and pick.sale_id):
                if (pick.sale_id.meli_shipment):
                    shipid = pick.sale_id.meli_shipment.id
                if ( (not shipid) and len(pick.sale_id.meli_orders) ):
                    shipment = shipment_obj.search([('shipping_id','=',pick.sale_id.meli_orders[0].shipping_id)])
                    if (shipment and shipment.status in ("ready_to_ship", "shipped")):
                        shipid = shipment.id
            else:
                continue;

            if (shipid):
                #shipment = shipment_obj.browse(shipid)
                #shipment.update()
                shipment_ids.append(shipid)

        return self.shipment_print_report(shipment_ids=shipment_ids,meli=meli,config=config,include_ready_to_print=self.include_ready_to_print)

    def shipment_print_report(self, shipment_ids=[], meli=None, config=None, include_ready_to_print=None):
        full_ids = ""
        reporte = ""
        sep = ""
        full_url_link_pdf = {}
        shipment_obj = self.env['mercadolibre.shipment']
        warningobj = self.env['meli.warning']

        for shipid in shipment_ids:
            shipment = shipment_obj.browse(shipid)
            ship_report = shipment.shipment_print( meli=meli, config=config, include_ready_to_print=include_ready_to_print )

            print_mode = mercadolibre_shipment_print_guide_mode
            if (config and "mercadolibre_shipment_print_guide" in config._fields):
                if (config["mercadolibre_shipment_print_guide_mode"]):
                    print_mode = config["mercadolibre_shipment_print_guide_mode"]        

            reporte = reporte + sep + str( ship_report['message'] )

            if (shipment and shipment.status=="ready_to_ship"):
                atoken = ship_report['access_token']
                if atoken and not (atoken in full_url_link_pdf):
                    full_url_link_pdf[atoken] = { 'full_ids': '', 'comma': '', 'full_link': '' }

                if atoken and atoken in full_url_link_pdf:
                    full_url_link_pdf[atoken]['full_ids'] += full_url_link_pdf[atoken]['comma'] + shipment.shipping_id
                    full_url_link_pdf[atoken]['comma']  = ","

                    full_url_link_pdf[atoken]['full_link'] = "https://api.mercadolibre.com/shipment_labels?shipment_ids="+full_url_link_pdf[atoken]['full_ids']+"&response_type=pdf&access_token="+atoken
                    if (print_mode in ("zpl","zpl_txt")):
                        full_url_link_pdf[atoken]['full_link'] = "https://api.mercadolibre.com/shipment_labels?shipment_ids="+full_url_link_pdf[atoken]['full_ids']+"&response_type=zpl2&access_token="+atoken

            sep = "<br>"+"\n"

        full_links = ''
        for atoken in full_url_link_pdf:
            #_logger.info('atoken:'+str(atoken))
            full_ids+= full_url_link_pdf[atoken]['full_ids']
            full_link = full_url_link_pdf[atoken]['full_link']
            #_logger.info(full_link)
            if full_link:
                full_links+= '<a href="'+full_link+'" target="_blank"><strong><u>Descargar PDF/ZPL</u></strong></a>'

        # full_url_link_pdf = {'otken': {'full_link': "https://api.mercadolibre.com/shipment_labels?shipment_ids=43272588025&amp;response_type=pdf&amp;access_token=APP_USR-6866649250908201-040908-e22cf17b7005c0ee37b953b972c7c53b-1682539048"}}
        self.full_links= json.dumps(full_url_link_pdf)
        if (full_links):
            return warningobj.info( title='Impresión de etiquetas', message="Abrir links para descargar PDF/ZPL", message_html=""+full_ids+'<br><br>'+full_links+"<br><br>Reporte de no impresas:<br>"+reporte )
        else:
            return warningobj.info( title='Impresión de etiquetas: Estas etiquetas ya fueron todas impresas.', message=reporte )


    include_ready_to_print = fields.Boolean(string="Include Ready To Print",default=False)
    full_links = fields.Text(default='{}')

    print_mode = fields.Selection(string="Modo",help="PDF o ZPL2",selection=[('pdf','PDF'),('zpl','ZPL')])
    #&savePdf=Y
    #&response_type=zpl2



class mercadolibre_shipment_update(models.TransientModel):
    _name = "mercadolibre.shipment.update"
    _description = "Actualizar datos de envio"

    def shipment_update(self, context=None, config=None, meli=None):
        context = context or self.env.context
        company = self.env.user.company_id
        if not config:
            config = company
        shipment_ids = ('active_ids' in context and context['active_ids']) or []
        #product_obj = self.env['product.template']
        shipment_obj = self.env['mercadolibre.shipment']
        warningobj = self.env['meli.warning']

        #_logger.info("shipment_update")
        #_logger.info(shipment_ids)
        #_logger.info( "shipment_update: context: "+str(context)+" meli: "+str(meli)+ " config: " +str(config) )


        for shipid in shipment_ids:
            shipment = shipment_obj.browse(shipid)
            if (shipment):
                shipment.update(meli=meli,config=config)


class mercadolibre_shipment_item(models.Model):
    _name = "mercadolibre.shipment.item"
    _description = "Item de Envio de MercadoLibre"

    shipment_id = fields.Many2one("mercadolibre.shipment",string="Shipment")
    name = fields.Char(string='Name', index=True)
    description = fields.Char(string="Description", index=True)
    item_id = fields.Char(string="Item Id (meli id)", index=True)
    variation_id = fields.Char(string="Variation Id", index=True)
    order_id = fields.Char(string="Order Id", index=True)
    data = fields.Text(string="Full Item Data")


class mercadolibre_shipment(models.Model):
    _name = "mercadolibre.shipment"
    _description = "Envio de MercadoLibre"

    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Name',index=True)
    site_id = fields.Char(string='Site id',index=True)
    posting_id = fields.Many2one("mercadolibre.posting",string="Posting")
    shipping_id = fields.Char(string='Envio Id',index=True)
    order_id = fields.Char(string='Order Id',index=True)
    order = fields.Many2one("mercadolibre.orders",string="Order")
    orders = fields.Many2many("mercadolibre.orders",string="Orders (carrito)")
    shipment_items = fields.One2many("mercadolibre.shipment.item","shipment_id",string="Items")
    sale_order = fields.Many2one('sale.order',string="Sale Order",help="Pedido de venta relacionado en Odoo")

    company_id = fields.Many2one("res.company", related="order.company_id",string="Company",index=True)


    mode = fields.Char(string='Mode')
    shipping_mode = fields.Char(string='Shipping mode')

    date_created = fields.Datetime(string='Creation date')
    last_updated = fields.Datetime(string='Last updated')

    order_cost = fields.Float(string='Order Cost')
    base_cost = fields.Float(string='Base Cost')
    shipping_amount = fields.Float(string='Shipping Amount')
    shipping_cost = fields.Float(string='Shipping Cost')
    shipping_seller_cost = fields.Float(string='Shipping Seller Cost')
    shipping_list_cost = fields.Float(string='Shipping List Cost')
    shipping_receiver_cost = fields.Float(string='Shipping Receiver Cost',
        help='Costo del envío a cargo del comprador (receiver.cost de /shipments/{id}/costs). '
             'Para órdenes pack/ME2 donde el flete no viene en payment.shipping_amount ni en shipping_option.cost.')
    promoted_amount = fields.Float(string='Promoted amount')

    #state = fields.Selection(string="State",)
    status = fields.Char(string="Status",index=True)
    substatus = fields.Char(string="Sub Status",index=True)
    status_history = fields.Text(string="status_history",index=True)
    tracking_number = fields.Char(string="Tracking number",index=True)
    tracking_method = fields.Char(string="Tracking method",index=True)
    comments = fields.Char(string="Tracking Custom Comments")


    date_first_printed = fields.Datetime(string='First Printed date',index=True)

    receiver_id = fields.Char(string='Receiver Id',index=True)
    receiver_address_id = fields.Char('Receiver address id')
    receiver_address_phone = fields.Char('Phone')
    receiver_address_name = fields.Char('Nombre')
    receiver_address_comment = fields.Char('Comment')

    receiver_address_line = fields.Char('Receiver Address Line')
    receiver_street_name = fields.Char('Calle')
    receiver_street_number = fields.Char('Nro')
    receiver_city = fields.Char('Ciudad')
    receiver_city_code = fields.Char(string='Codigo Ciudad')
    receiver_state = fields.Char('Estado')
    receiver_state_code = fields.Char('Estado ID')
    receiver_state_id = fields.Many2one('res.country.state',string='State')
    receiver_zip_code = fields.Char(string='Zip Code')

    receiver_country = fields.Char('Pais')
    receiver_country_code = fields.Char('Código Pais')
    receiver_country_id = fields.Many2one('res.country',string='Country')
    receiver_latitude = fields.Char('Latitud')
    receiver_longitude = fields.Char('Longitud')

    sender_id = fields.Char(string='Sender Id',index=True)
    sender_address_id = fields.Char('Sender Address Id')
    sender_address_line = fields.Char('Sender Address Line')
    sender_address_comment = fields.Text('Sender Address Comment')

    sender_street_name = fields.Char('Sender Address Street Name')
    sender_street_number = fields.Char('Sender Address Street Number')
    sender_city = fields.Char('Sender Address City')
    sender_state = fields.Char('Sender Address State')
    sender_country = fields.Char('Sender Address Country')
    sender_latitude = fields.Char('Sender Address Latitude')
    sender_longitude = fields.Char('Sender Address Longitude')

    logistic_type = fields.Char('Logistic type',index=True)

    # Lead time / Delivery estimates (from /shipments/{id} lead_time object)
    shipping_method_id = fields.Char(string='Shipping Method ID')
    shipping_method_type = fields.Char(string='Shipping Method Type')  # standard, express
    shipping_method_name = fields.Char(string='Shipping Method Name')
    shipping_method_deliver_to = fields.Char(string='Deliver To')  # address, agency
    service_id = fields.Char(string='Service ID')
    cost_type = fields.Char(string='Cost Type')  # free, charged, partially_free

    estimated_delivery_date = fields.Datetime(string='Estimated Delivery Date')
    estimated_delivery_type = fields.Char(string='Estimated Delivery Type')  # known, unknown, known_frame
    estimated_delivery_shipping = fields.Integer(string='Estimated Shipping Time')
    estimated_delivery_handling = fields.Integer(string='Estimated Handling Time')
    estimated_delivery_unit = fields.Char(string='Estimated Delivery Unit')  # hour
    estimated_delivery_offset_date = fields.Datetime(string='Estimated Delivery Offset Date')
    estimated_handling_limit = fields.Datetime(string='Estimated Handling Limit')
    estimated_delivery_extended = fields.Datetime(string='Estimated Delivery Extended')
    estimated_delivery_limit = fields.Datetime(string='Estimated Delivery Limit')
    estimated_delivery_final = fields.Datetime(string='Estimated Delivery Final')
    estimated_buffering_date = fields.Datetime(string='Buffering Date', help='Fecha límite para despachar (self_service: hasta cuándo llevar el paquete a la agencia)')
    estimated_schedule_limit = fields.Datetime(string='Estimated Schedule Limit', help='Límite de horario programado')
    estimated_pay_before = fields.Datetime(string='Pay Before', help='Pagar antes de esta fecha para asegurar la entrega estimada')
    pickup_promise_from = fields.Datetime(string='Pickup Promise From', help='Inicio del rango de retiro por el transportista')
    pickup_promise_to = fields.Datetime(string='Pickup Promise To', help='Fin del rango de retiro por el transportista')
    desired_promised_delivery = fields.Datetime(string='Desired Promised Delivery', help='Fecha de entrega prometida deseada')
    delay = fields.Char(string='Delay')

    # Status history (JSON text)
    status_history_json = fields.Text(string='Status History JSON')

    # Status history dates (parsed from status_history object)
    date_handling = fields.Datetime(string='Fecha preparación', help='Fecha en que se empezó a preparar el envío')
    date_ready_to_ship = fields.Datetime(string='Fecha listo para enviar', help='Fecha en que el envío quedó listo para despachar')
    date_shipped = fields.Datetime(string='Fecha despachado', help='Fecha en que el envío fue despachado')
    date_delivered = fields.Datetime(string='Fecha entregado', help='Fecha en que el envío fue entregado al comprador')
    date_first_visit = fields.Datetime(string='Fecha primera visita', help='Fecha de la primera visita de entrega')
    date_not_delivered = fields.Datetime(string='Fecha no entregado', help='Fecha en que se registró como no entregado')
    date_returned = fields.Datetime(string='Fecha devuelto', help='Fecha en que el envío fue devuelto')
    date_cancelled = fields.Datetime(string='Fecha cancelado', help='Fecha en que el envío fue cancelado')

    pdf_link = fields.Char('Pdf link')
    pdf_file = fields.Binary(string='Pdf File',attachment=True)
    pdf_filename = fields.Char(string='Pdf Filename')
    pdfimage_file = fields.Binary(string='Pdf Image File',attachment=True)
    pdfimage_filename = fields.Char(string='Pdf Image Filename')

    seller_id = fields.Many2one("res.users",string="Seller",index=True)

    pack_order = fields.Boolean(string="Carrito de compra")

    _unique_shipping_id = versions.UniqueIndex('shipping_id', message='Meli Shipping id already exists!')

    # ------------------------------------------------------------------ #
    #  Computed: estado del límite de despacho respecto al momento actual  #
    # ------------------------------------------------------------------ #
    handling_limit_status = fields.Selection([
        ('none',    'Sin fecha límite'),
        ('ok',      'En plazo'),
        ('urgent',  'Urgente (< 4 h)'),
        ('overdue', 'Vencido'),
    ], compute='_compute_handling_limit_status', store=False,
       string="Estado límite despacho")

    @api.depends('estimated_handling_limit', 'estimated_buffering_date')
    def _compute_handling_limit_status(self):
        now = fields.Datetime.now()
        for rec in self:
            ehl = rec.estimated_handling_limit or rec.estimated_buffering_date
            if not ehl:
                rec.handling_limit_status = 'none'
            elif ehl < now:
                rec.handling_limit_status = 'overdue'
            elif ehl < now + timedelta(hours=4):
                rec.handling_limit_status = 'urgent'
            else:
                rec.handling_limit_status = 'ok'

    # ------------------------------------------------------------------ #
    #  Gate: ¿se puede imprimir la etiqueta?                              #
    # ------------------------------------------------------------------ #
    def can_print_label(self):
        """Returns (can_print: bool, reason: str).
        Fulfillment orders are managed by ML; all others require ready_to_ship.
        estimated_handling_limit is a dispatch DEADLINE, not a printing gate.
        """
        if self.logistic_type == 'fulfillment':
            return False, "ME Full (Fulfillment): ML gestiona el envío, no se imprime etiqueta."
        if self.status not in ('ready_to_ship', 'shipped'):
            return False, "El envío aún no está listo para despachar (estado: %s)." % (self.status or 'sin estado')
        return True, ""

    # ------------------------------------------------------------------ #
    #  Chatter: notificar cambios en el límite de despacho                #
    # ------------------------------------------------------------------ #
    def write(self, vals):
        old_limit = {r.id: r.estimated_handling_limit for r in self}
        res = super().write(vals)
        if 'estimated_handling_limit' in vals:
            for rec in self:
                new_val = rec.estimated_handling_limit
                old_val = old_limit.get(rec.id)
                if new_val == old_val:
                    continue
                sorder = rec.sale_order
                if not sorder:
                    continue
                if new_val:
                    # Odoo Datetime → string local para el mensaje
                    limit_str = fields.Datetime.to_string(new_val)
                    if old_val:
                        body = "📦 <b>Límite de despacho ML actualizado:</b> %s → %s" % (
                            fields.Datetime.to_string(old_val), limit_str)
                    else:
                        body = "📦 <b>Límite de despacho ML:</b> %s (tipo logístico: %s)" % (
                            limit_str, rec.logistic_type or 'no especificado')
                else:
                    body = "📦 Límite de despacho ML eliminado."
                try:
                    sorder.message_post(body=body)
                    for picking in sorder.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel')):
                        picking.message_post(body=body)
                except Exception:
                    pass
        return res

    def create_shipment( self ):
        return {}

    def _update_sale_order_shipping_info( self, order, meli=None, config=None ):

        company = (config and 'company_id' in config._fields and config.company_id) or ("company_id" in self._fields and self.company_id) or self.env.user.company_id
        company_domain = ['|',('company_id','=',False),('company_id','=',company.id)]
        company_only_domain = [('company_id','=',company.id)]
        company_domain = company_only_domain
        product_tpl = self.env['product.template']
        product_obj = self.env['product.product']
        saleorderline_obj = self.env['sale.order.line']

        for shipment in self:
            #_logger.info("_update_sale_order_shipping_info")
            sorder = shipment.sale_order

            if (sorder.state in ['done']) or ("locked" in sorder._fields and sorder.locked):
                # Order is locked/done: skip structural changes (carrier, delivery line
                # creation, address sync) but still update purchase_price on the existing
                # delivery line.  shipping_seller_cost often arrives after the order is
                # already confirmed, and without this the margin stays at 0.
                try:
                    ship_cost_for_pp = (
                        shipment.shipping_seller_cost
                        or (sorder and sorder.meli_shipping_seller_cost)
                        or shipment.shipping_list_cost
                        or 0.0
                    )
                    if ship_cost_for_pp:
                        delivery_line = get_delivery_line(sorder)
                        if delivery_line and 'purchase_price' in delivery_line._fields:
                            product = delivery_line.product_id
                            new_pp = sorder._ml_get_purchase_price_from_amount(
                                product=product,
                                amount=ship_cost_for_pp,
                                amount_type="tax_included",
                                quantity=1.0)
                            if not delivery_line.purchase_price or abs(delivery_line.purchase_price - new_pp) > 0.01:
                                delivery_line.purchase_price = new_pp
                except Exception as e:
                    _logger.warning("purchase_price update on locked order %s failed: %s", sorder.name, e)
                continue;

            if (not sorder or not order):
                continue;

            including_shipping_cost = "mercadolibre_including_shipping_cost" in config._fields and config.mercadolibre_including_shipping_cost
            including_shipping_cost = including_shipping_cost or "always"

            if (sorder and sorder.meli_update_forbidden):
                _logger.error("Forbidden to update sale order by meli_oerp" )
                return {'error': 'Forbidden to update sale order by meli_oerp' }

            sorder.meli_shipping_cost = shipment.shipping_cost
            #sorder.meli_shipping_seller_cost = shipment.shipping_seller_cost
            sorder.meli_shipping_list_cost = shipment.shipping_list_cost
            sorder.meli_shipment_logistic_type = shipment.logistic_type or shipment.mode

            order.shipping_cost = shipment.shipping_cost
            #order.shipping_seller_cost = shipment.shipping_seller_cost
            order.shipping_list_cost = shipment.shipping_list_cost
            order.shipment_logistic_type = shipment.logistic_type or shipment.mode

            if (sorder.partner_shipping_id):
                partner_shipping_id = sorder.partner_shipping_id
                if (partner_shipping_id and "meli_update_forbidden" in partner_shipping_id._fields and not partner_shipping_id.meli_update_forbidden):
                    partner_shipping_id.street = shipment.receiver_address_line
                    partner_shipping_id.street2 = shipment.receiver_address_comment
                    partner_shipping_id.city = shipment.receiver_city
                    if shipment.receiver_address_phone and not ("XXXX" in shipment.receiver_address_phone):
                        partner_shipping_id.phone = shipment.receiver_address_phone
                #sorder.partner_id.state = ships.receiver_state

            ship_name = shipment.tracking_method or (shipment.mode=="me1" and "ME1 - zip") or (shipment.mode=="custom" and "Personalizado")  or (shipment.logistic_type=="self_service" and "Personalizado MFlex")


            if not ship_name or len(ship_name)==0:
                continue;

            ship_default_code = ship_name

            if (shipment.mode=="me1"):
                product_shipping_id = product_obj.search([('default_code','ilike','ENVIO-ME1')]
                                                            + company_domain,
                                                            order="company_id asc",
                                                            limit=1 )
                ship_default_code = 'ENVIO-ME1'
            else:
                product_shipping_id = product_obj.search([('default_code','ilike','ENVIO')]
                                                         + company_domain,
                                                         order="company_id asc",
                                                         limit=1)
                if (len(product_shipping_id)==0):
                    product_shipping_id = product_obj.search(['|','|',('default_code','=','ENVIO'),
                            ('default_code','=',ship_name),
                            ('name','=',ship_name)]
                            + company_domain,
                            order="company_id asc",
                            limit=1)

            if len(product_shipping_id):
                #_logger.info("_update_sale_order_shipping_info ")
                product_shipping_id = product_shipping_id[0]
            else:
                product_shipping_id = None
                # categ_id is NOT NULL on product.template; resolve a safe
                # default (the standard "All" category) before creating the
                # shipping service product, falling back to any existing
                # category or creating one if none exist.
                default_categ = self.env.ref('product.product_category_all', raise_if_not_found=False)
                if not default_categ:
                    default_categ = self.env['product.category'].search([], limit=1)
                if not default_categ:
                    default_categ = self.env['product.category'].create({'name': 'All'})
                ship_prod = {
                    "name": ship_name,
                    "default_code": ship_default_code,
                    "type": "service",
                    #"taxes_id": None
                    "categ_id": default_categ.id,
                    "company_id": company.id
                }
                #_logger.info(ship_prod)
                product_shipping_tpl = product_tpl.create((ship_prod))
                if (product_shipping_tpl):
                    product_shipping_id = product_shipping_tpl.product_variant_ids[0]
            #_logger.info(product_shipping_id)

            if (not product_shipping_id):
                #_logger.info('Failed to create shipping product service')
                continue

            #CO
            if "enable_charges" in product_shipping_id._fields:
                product_shipping_id.enable_charges = True

            ship_carrier = {
                "name": ship_name,
                "company_id": (self.company_id and self.company_id.id),
            }
            ship_carrier["product_id"] = product_shipping_id.id

            # 1) Buscar en tabla de mapeo meli_oerp.carrier.mapping
            ship_carrier_id = self.env["meli_oerp.carrier.mapping"].resolve_carrier(
                meli_name=ship_name,
                company=company,
                product_shipping_id=product_shipping_id,
            )

            # 2) Fallback: buscar delivery.carrier por nombre
            if not ship_carrier_id:
                ship_carrier_id = self.env["delivery.carrier"].search(
                    [('name', '=ilike', ship_carrier['name'])] + company_domain,
                    order="company_id asc", limit=1)
            if not ship_carrier_id:
                ship_carrier_id = self.env["delivery.carrier"].search(
                    [('name', '=ilike', ship_carrier['name'])],
                    order="company_id asc", limit=1)

            # 3) Último recurso: crear carrier nuevo
            if not ship_carrier_id:
                ship_carrier_id = self.env["delivery.carrier"].create(ship_carrier)

            # Respetar el producto del carrier mapeado. La tabla de mapeo existe
            # para REUTILIZAR carriers ya configurados sin duplicar: si el carrier
            # resuelto (p.ej. Flex desde el mapeo) YA tiene producto, se conserva.
            # Solo se le asigna el servicio de envío resuelto por nombre cuando el
            # carrier todavía no tiene producto (recién creado o sin configurar).
            if ship_carrier_id and product_shipping_id and not ship_carrier_id.product_id:
                try:
                    ship_carrier_id.product_id = product_shipping_id
                except Exception as e:
                    _logger.warning("No se pudo asignar product_id al carrier %s: %s", ship_carrier_id.name, e)

            # De acá en más usar el producto EFECTIVO del carrier: la línea de envío
            # nativa toma el producto de carrier_id.product_id (ver set_delivery_line/
            # get_delivery_line en versions.py), así que el precio, el chequeo de
            # compañía y el coste quedan consistentes con el carrier mapeado.
            if ship_carrier_id and ship_carrier_id.product_id:
                product_shipping_id = ship_carrier_id.product_id

            all_company_ok = False
            if ship_carrier_id and product_shipping_id:
                all_company_ok = ship_carrier_id.company_id == sorder.company_id and product_shipping_id.company_id == sorder.company_id
                already_notified = sorder.message_ids.filtered(
                    lambda m: m.body and "Companias Coinciden OK" in (m.body or "")
                )
                if not already_notified:
                    sorder.message_post(body=str("Companias Coinciden OK, Carrier, Servicio de envio y Pedido"))

                if all_company_ok == False:
                    #try and check to set or change products and carriers
                    if not ship_carrier_id or not product_shipping_id:
                        message_str_error = str("Companias no coinciden en Carrier, Servicio y Orden")
                        message_str_error+= str("\n")
                        message_str_error+= str( ( ship_carrier_id and str(ship_carrier_id.company_id or "Carrier sin Empresa") ) or "Sin Carrier" )
                        message_str_error+= str("\n")
                        message_str_error+= str( (product_shipping_id and str(product_shipping_id.company_id or "Servicio de envio sin Empresa")) or "Sin servicio de envio" )
                        sorder.message_post(body=message_str_error)
            else:
                sorder.message_post(body=str("Sin servicio de envio o carrier."))




            stock_pickings = self.env["stock.picking"].search([('sale_id','=',sorder.id),('name','like','OUT')])
            #carrier_id = self.env["delivery.carrier"].search([('name','=',)])
            for st_pick in stock_pickings:
                #if ( 1==2 and ship_carrier_id ):
                #    st_pick.carrier_id = ship_carrier_id
                st_pick.carrier_tracking_ref = shipment.tracking_number

            # Actualizar nombre del sale.order con nro de seguimiento o ID envío
            # Solo si la cuenta tiene mercadolibre_so_name_tracking activado.
            # Antes de f943fcd este bloque no existia; se agregó sin el gate
            # causando rename incondicional de todas las órdenes.
            _so_name_tracking = (
                config
                and 'mercadolibre_so_name_tracking' in config._fields
                and config.mercadolibre_so_name_tracking
            )
            if sorder and _so_name_tracking:
                base_name = (sorder.name or "").split(" | ")[0]
                if shipment.tracking_number:
                    sorder.name = base_name + " | " + str(shipment.tracking_number)
                elif shipment.shipping_id:
                    sorder.name = base_name + " | " + str(shipment.shipping_id)

            if (shipment.tracking_method == "MEL Distribution"):
                #_logger.info('MEL Distribution, not adding to order')
                pass;
                #continue

            mercadolibre_use_payment_shipping_amount = True
            if (config and "mercadolibre_use_payment_shipping_amount" in config._fields):
                mercadolibre_use_payment_shipping_amount = config.mercadolibre_use_payment_shipping_amount

            # Chequeo final: asegurar que los pagos tengan shipping_amount cargado
            # ANTES de calcular la línea de envío. Si el fetch a MercadoPago falló en
            # la primera pasada del import, payments_shipment_amount queda en 0 y la
            # línea saldría en 0 hasta un 'Actualizar' manual; esto lo recupera en la
            # misma pasada (solo re-consulta MP si está en 0).
            if order and not order.payments_shipment_amount:
                order._ensure_payment_shipping_amounts(meli=meli, config=config)
                order.invalidate_recordset(['payments_shipment_amount'])

            del_price = order.payments_shipment_amount;

            if not mercadolibre_use_payment_shipping_amount:
                del_price = shipment.shipping_cost

            # Fallback órdenes pack/ME2: si ni el pago (payment.shipping_amount) ni
            # shipping_option.cost traen el flete (queda 0), usar el costo del envío a
            # cargo del comprador (receiver.cost de /shipments/{id}/costs).
            if not del_price and shipment.shipping_receiver_cost:
                del_price = shipment.shipping_receiver_cost

            delivery_price = ml_product_price_conversion( self, product_related_obj=product_shipping_id, price=del_price, config=config ),
            if type(delivery_price)==tuple and len(delivery_price):
                delivery_price = delivery_price[0]

            conflict = abs( sorder.meli_paid_amount - sorder.meli_total_amount + (sorder.meli_discount_seller_amount or sorder.meli_coupon_amount) ) > 1.0

            received_amount = sorder.meli_amount_to_invoice( meli=meli, config=config )
            conflict = ( received_amount == 0.0 )

            if conflict:
                #_logger.error("Order totals conflict, manual check needed.")
                continue;
            #if (1==2):
            #    received_amount = sorder.meli_total_amount

            #_logger.info("delivery_price:"+str(delivery_price)+" received_amount: "+str(received_amount) +" amount_total:"+str(sorder.amount_total) )
            shipment_amount_cond = abs(received_amount - sorder.amount_total)>1.0 and (delivery_price>0.0)

            #_logger.info("shipment_amount_cond:"+str(shipment_amount_cond))

            shipment_amount_cond_fix = (sorder.amount_total - received_amount)>1.0 and (delivery_price>0.0)
            #_logger.info("shipment_amount_cond_fix:"+str(shipment_amount_cond_fix))

            shipment_amount_cond_fix2 = (sorder.amount_total - received_amount)<-1.0 and (delivery_price>0.0)
            #_logger.info("shipment_amount_cond_fix2:"+str(shipment_amount_cond_fix))

            #_logger.info("ship_carrier_id:"+str(ship_carrier_id)+" sorder.carrier_id:"+str(sorder.carrier_id))

            if shipment_amount_cond_fix:
                #_logger.info("shipment_cond: "+str(shipment_amount_cond)+" paid: "+str(received_amount)+" vs total: "+str(sorder.amount_total))
                if ( ship_carrier_id and sorder.carrier_id):
                    delivery_price = 0.0
                    #_logger.info("set_delivery_line:"+str(delivery_price))
                    if (not including_shipping_cost=="never"):
                        set_delivery_line( sorder, delivery_price, "Defined by MELI" )
                delivery_price = 0.0

            if shipment_amount_cond_fix2 and ship_carrier_id and sorder.carrier_id:
                #_logger.info("set_delivery_line (fix2):"+str(delivery_price))
                if (not including_shipping_cost=="never"):
                    set_delivery_line( sorder, delivery_price, "Defined by MELI" )


            if ship_carrier_id and (not sorder.carrier_id or sorder.carrier_id != ship_carrier_id):
                #_logger.info("set_delivery_line (set/update carrier):"+str(delivery_price))
                sorder.carrier_id = ship_carrier_id
                delivery_message = "Defined by MELI"
                if (not including_shipping_cost=="never"):
                    set_delivery_line(sorder, delivery_price, delivery_message )

            if (sorder.carrier_id):
                #activar para cuando no se quiere incluir en la factura? mejor setear para no ser facturado.. cuando es 0
                if ((1==2 and delivery_price<=0.0) or including_shipping_cost=="never"):
                    sorder._remove_delivery_line()

                #UPDATE PRICE
                delivery_line = get_delivery_line(sorder)

                if delivery_line and abs(delivery_line.price_unit-delivery_price)>1.0:
                    delivery_message = "Defined by MELI"
                    #_logger.info("Agregar delivery line delivery_price:"+str(delivery_price))
                    set_delivery_line(sorder, delivery_price, delivery_message )


                # Set purchase_price (Coste) on the delivery line for margin calculation.
                # Priority: shipping_seller_cost (what ML charges the seller) > shipping_list_cost (fallback)
                # Also check sorder.meli_shipping_seller_cost as it may have been set from payment processing
                # before the shipment object got the value (timing issue).
                ship_cost_for_purchase_price = (
                    shipment.shipping_seller_cost
                    or (sorder and sorder.meli_shipping_seller_cost)
                    or shipment.shipping_list_cost
                    or 0.0
                )
                if ship_cost_for_purchase_price:
                    delivery_line = get_delivery_line( sorder )
                    if delivery_line and 'purchase_price' in delivery_line._fields:
                        new_purchase_price = sorder._ml_get_purchase_price_from_amount(
                            product=product_shipping_id,
                            amount=ship_cost_for_purchase_price,
                            amount_type="tax_included",
                            quantity=1.0 )
                        # Only write if value actually changed (avoid unnecessary triggers)
                        if delivery_line.purchase_price != new_purchase_price:
                            delivery_line.purchase_price = new_purchase_price

                if 1==1 and delivery_price<=0.0:
                    #_logger.info("Procesar delivery_price == 0")
                    delivery_line = get_delivery_line(sorder)
                    if delivery_line:
                        #_logger.info("Procesar delivery_price == 0 setear qty_to_invoice en 0")
                        # Only write if value actually changed (avoid unnecessary triggers)
                        if delivery_line.price_unit != 0.0:
                            delivery_line.price_unit = 0.0
                        if delivery_line.qty_to_invoice != 0:
                            delivery_line.qty_to_invoice = 0
                    #_logger.info("Procesar delivery_price == 0 remover linea")
                    #sorder._remove_delivery_line()
                elif delivery_price > 0.0:
                    # When delivery has a real cost (e.g. ENVIO-ME1), ensure qty_to_invoice=1
                    # so the line appears on the invoice. Carrier products typically use
                    # invoice_policy='delivery' which computes qty_to_invoice=0 until the
                    # picking is done — but for MeLi we invoice on payment, not on delivery.
                    delivery_line = get_delivery_line(sorder)
                    if delivery_line and delivery_line.state not in ('cancel',):
                        _expected_qty = delivery_line.product_uom_qty or 1.0
                        if delivery_line.qty_to_invoice != _expected_qty:
                            try:
                                delivery_line.qty_to_invoice = _expected_qty
                                _logger.info(
                                    "MELI shipment: restored qty_to_invoice=%.2f on delivery line "
                                    "for SO %s (price=%.2f, product=%s)",
                                    _expected_qty, sorder.name, delivery_price,
                                    delivery_line.product_id.default_code or delivery_line.product_id.name,
                                )
                            except Exception as _e:
                                _logger.warning(
                                    "MELI shipment: could not restore qty_to_invoice for SO %s: %s",
                                    sorder.name, _e,
                                )
                #_logger.info("Finished _update_sale_order_shipping_info")
            return



            #REMOVE OLD SALE ORDER ITEM SHIPPING ITEM
            saleorderline_item_fields = {
                'company_id': company.id,
                'order_id': sorder.id,
                'meli_order_item_id': 'ENVIO',
                'price_unit': delivery_price,
                'product_id': product_shipping_id.id,
                'product_uom_qty': 1.0,
                'name': "Shipping " + str(shipment.shipping_mode),
            }
            uom_field = SaleOrderLineUomField( self )
            saleorderline_item_fields[uom_field] = product_shipping_id.uom_id.id
            saleorderline_item_ids = saleorderline_obj.search( [('meli_order_item_id','=',saleorderline_item_fields['meli_order_item_id']),
                                                                ('order_id','=',sorder.id)] )

            if not saleorderline_item_ids and (del_price>0):
                #saleorderline_item_ids = saleorderline_obj.create( ( saleorderline_item_fields ))
                pass;
            else:
                if (1==2 and del_price>0):
                    saleorderline_item_ids.write( ( saleorderline_item_fields ) )
                else:
                    try:
                        #_logger.info("removing saleorderline_item_ids")
                        pass;
                        #saleorderline_item_ids.unlink()
                    except:
                        #_logger.info("Could not unlink.")
                        pass;

    def _get_or_create_delivery_address(self, parent_partner, shipping_vals, create_if_not_found=False):
        Partner = self.env['res.partner']

        # 1) Try to find a similar existing delivery address
        existing = Partner.find_similar_delivery_address(
            parent_partner=parent_partner,
            address_vals=shipping_vals,
            similarity_threshold=0.82,  # tune per backend if needed
        )
        if existing:
            return existing
    
        if create_if_not_found:
            # 2) If none found, create a new child delivery contact
            shipping_vals = dict(shipping_vals)  # copy
            shipping_vals.update({
                'parent_id': parent_partner.id,
                'commercial_partner_id': parent_partner.id,
                'type': 'delivery',
            })
            return Partner.create(shipping_vals)

        return Partner

    def partner_delivery_id( self, partner_id=None, Receiver=None, config=None ):
        #_logger.info("Processing partner_delivery_id for partner:"+str(partner_id and partner_id.name)+" Receiver:"+str(Receiver)+" config:"+str(config) )
        if (not Receiver or not partner_id):
            _logger.info("partner_delivery_id > no Partner or no Receiver")
            return None

        if (config and not config.mercadolibre_cron_get_orders_shipment_client):
            #_logger.info("Processing partner_delivery_id no config.mercadolibre_cron_get_orders_shipment_client")
            return None

        orders_obj = self.env['mercadolibre.orders']

        partner_shipping_id = None

        deliv_id = self.env["res.partner"].search([("parent_id","=",partner_id.id),
                                                ("type","=","delivery"),
                                                #('street','=',partner_id.street)
                                                ],
                                            limit=1)

        #_logger.info("partner_delivery_id > Receiver: "+str(Receiver) )

        # Ensure delivery partner always has a valid name (constraint: res_partner_check_name)
        receiver_name = Receiver.get("receiver_name") or ""
        if not receiver_name:
            receiver_name = partner_id.name or "Entrega MeLi"

        pdelivery_fields = {
            "type": "delivery",
            "parent_id": partner_id.id,
            'name': receiver_name,
            'street': Receiver['address_line'],
            #'street2': meli_buyer_fields['name'],
            'city': orders_obj.city(Receiver),
            'country_id': orders_obj.country(Receiver),
            'state_id': orders_obj.state(orders_obj.country(Receiver),Receiver),
            'zip': ("zip_code" in Receiver and Receiver["zip_code"]) or None
            #'zip': meli_buyer_fields['name'],
            #'phone': orders_obj.full_phone( Receiver ),
            #'email':contactfields['billingInfo_email'],
        }

        full_phone = orders_obj.full_phone( Receiver )
        if full_phone and not ("XXXX" in full_phone):
            pdelivery_fields['phone'] = full_phone
        if partner_id and partner_id.lang:
            pdelivery_fields["lang"] =  partner_id.lang

        pdelivery_fields.update(orders_obj.fix_locals(Receiver))
        
        #TODO: agregar un campo para diferencia cada delivery res partner al shipment y orden asociado, crear un binding usando values diferentes... y listo
        deliv_id = self.env["res.partner"].search([("parent_id","=",pdelivery_fields['parent_id']),
                                                    ("type","=","delivery"),
                                                    ('street','=',pdelivery_fields['street'])],
                                                    limit=1)
        
        deliv_id = deliv_id or self._get_or_create_delivery_address( parent_partner=partner_id, shipping_vals=pdelivery_fields  )

        if not deliv_id or len(deliv_id)==0:
            #_logger.info("Create partner delivery")
            respartner_obj = self.env['res.partner']
            try:
                deliv_id = respartner_obj.create(pdelivery_fields)
                if deliv_id:
                    #_logger.info("Created Res Partner Delivery "+str(deliv_id))
                    partner_shipping_id = deliv_id
            except Exception as e:
                _logger.error("Created res.partner delivery issue.")
                _logger.info(e, exc_info=True)
                pass;
        else:
            # Safety: never overwrite the buyer/parent partner with shipping data
            if deliv_id.id == partner_id.id:
                _logger.warning("partner_delivery_id: deliv_id matched buyer partner %s, skipping write to avoid name overwrite", partner_id.name)
                return None
            try:
                hchanges = False
                del pdelivery_fields["parent_id"]
                del pdelivery_fields["country_id"]
                del pdelivery_fields["state_id"]
                del pdelivery_fields["type"]
                for f in pdelivery_fields:
                    if f in deliv_id._fields:
                        if pdelivery_fields[f] != deliv_id[f]:
                            hchanges = True
                if hchanges:
                    deliv_id.write(pdelivery_fields)
                partner_shipping_id = deliv_id
            except:
                _logger.error("Updating res.partner delivery issue.")
                pass;
        #_logger.info("Processing partner_delivery_id partner_shipping_id:"+str(partner_shipping_id and partner_shipping_id.name) )
        return partner_shipping_id

    #Return shipment object based on mercadolibre.orders "order"
    def fetch_shipment( self, order, meli=None, config=None ):
        #_logger.info("ship fetch")
        company = (config and "company_id" in config._fields and config.company_id) or config or self.env.user.company_id
        if not config:
            config = company
        company_only_domain = [('company_id','=',company.id)]
        company_none_domain = [('company_id','=',False)]  

        sale_order_pack = None
        saleorder_obj = self.env['sale.order']
        saleorderline_obj = self.env['sale.order.line']
        product_obj = self.env['product.product']
        pricelist_obj = self.env['product.pricelist']
        respartner_obj = self.env['res.partner']

        orders_obj = self.env['mercadolibre.orders']
        shipment_obj = self.env['mercadolibre.shipment']
        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)
            if meli.need_login():
                return meli.redirect_login()

        ship_id = False
        shipment = None
        #_logger.info("order: "+str(order))
        if (order and "shipping_id" in order._fields and order.shipping_id):
            ship_id = order.shipping_id
        else:
            _logger.info("No hay orden o shipping_id")
            return None

        ship_json = None
        if meli.access_token=="PASIVA":
            ship_json = {
                "id": ship_id,
                "logistic_type": order.shipment_logistic_type,
                "order_cost": 0,
                "base_cost": 0,
                "date_created": "",
                "last_updated": "",
                "site_id": "MLM",
                "order_id": order.order_id,
                "mode": "custom",
                "shipping_option": {
                    "name": "custom",
                    "cost": order.shipping_cost,
                    "list_cost": order.shipping_list_cost,
                },
                "receiver_address": {
                    "id": "ID_RECEPTORGLOBAL",
                    "receiver_phone": "XXXX",
                    "receiver_name": "RECEPTORGLOBAL",
                    "address_line": "ADDRESSLINE",
                    "comment": "",
                    "street_name": "STREETNAME",
                    "street_number": "11111",
                    "city": { "id": "MEX", "name": "México" },
                    "state": { "id": "DF", "name": "México" },
                    "country": { "id": "MX", "name": "México" },
                    "latitude": "00",
                    "longitude": "00",
                },
                "status": "undefined",
                "substatus": "undefined",
                "tracking_number": "XXXX",
                "tracking_method": "MMMM",
                "comments": "",
                "date_first_printed": "",
                "receiver_id": "GLOBALCOMPRADOR",
                "sender_id": "ZZZ",
            }
            response = True
        else:
            response = meli.get("/shipments/"+ str(ship_id),  {'access_token':meli.access_token})
        if (response):
            ship_json = ship_json or response.json()
            #_logger.info( ship_json )

            if "error" in ship_json:
                _logger.error( ship_json["error"] )
                _logger.error( ship_json["message"] )
            else:
                #_logger.info("Saving shipment fields")
                rcosts = None
                if meli.access_token=="PASIVA":
                    rcosts = {
                        "algo": True
                    }
                    rescosts = True
                else:
                    rescosts = meli.get("/shipments/"+ str(ship_id)+str('/costs'),  {'access_token':meli.access_token})
                if rescosts:
                    rcosts = rcosts or rescosts.json()
                    ship_json['costs'] = rcosts
                    recdiscounts = 'receiver' in rcosts and 'discounts' in rcosts['receiver'] and rcosts['receiver']['discounts']
                    if recdiscounts:
                        for discount in recdiscounts:
                            if 'promoted_amount' in discount:
                                ship_json['promoted_amount'] =  discount['promoted_amount'] or 0.0
                    # Costo del envío a cargo del COMPRADOR (receiver.cost). En órdenes
                    # pack/ME2 el flete no viene en payment.shipping_amount ni en
                    # shipping_option.cost — sí acá, en /costs → receiver.cost.
                    _receiver = (isinstance(rcosts, dict) and rcosts.get('receiver')) or {}
                    ship_json['receiver_cost'] = (isinstance(_receiver, dict) and _receiver.get('cost')) or 0.0

                seller_id = None
                if config.mercadolibre_seller_user:
                    seller_id = config.mercadolibre_seller_user.id
                ship_fields = {
                    "name": "MSO ["+str(ship_id)+"] "+str("")+str(ship_json["status"])+"/"+str(ship_json["substatus"])+str(""),
                    'company_id': company.id,
                    'seller_id': seller_id,
                    "order": order.id,
                    "shipping_id": ship_json["id"],
                    "site_id": ship_json["site_id"],
                    "order_id": ship_json["order_id"],
                    "mode": ship_json["mode"],
                    "shipping_mode": ship_json["shipping_option"]["name"],
                    "date_created": ml_datetime(ship_json["date_created"]),
                    "last_updated": ml_datetime(ship_json["last_updated"]),
                    "order_cost": ship_json["order_cost"],
                    "shipping_cost": ("cost" in ship_json["shipping_option"] and ship_json["shipping_option"]["cost"]) or 0.0,
                    "shipping_list_cost": ("list_cost" in ship_json["shipping_option"] and ship_json["shipping_option"]["list_cost"]) or 0.0,
                    "shipping_receiver_cost": ('receiver_cost' in ship_json and ship_json['receiver_cost']) or 0.0,
                    "base_cost": ship_json["base_cost"],
                    'promoted_amount': ('promoted_amount' in ship_json and ship_json['promoted_amount']) or 0.0,
                    "status": ship_json["status"],
                    "substatus": ship_json["substatus"],
                    #"status_history": ship_json["status_history"],
                    "tracking_number": ship_json["tracking_number"],
                    "tracking_method": ship_json["tracking_method"],
                    "comments": ship_json["comments"] or '',
                    "date_first_printed": ml_datetime(ship_json["date_first_printed"]),
                    "receiver_id": ship_json["receiver_id"],
                    "sender_id": ship_json["sender_id"],
                    "logistic_type": ("logistic_type" in ship_json and ship_json["logistic_type"]) or ""
                }

                # Parse status_history
                if "status_history" in ship_json and ship_json["status_history"]:
                    import json
                    sh = ship_json["status_history"]
                    try:
                        ship_fields["status_history_json"] = json.dumps(sh)
                    except Exception:
                        pass
                    for sh_key, sh_field in [
                        ("date_handling", "date_handling"),
                        ("date_ready_to_ship", "date_ready_to_ship"),
                        ("date_shipped", "date_shipped"),
                        ("date_delivered", "date_delivered"),
                        ("date_first_visit", "date_first_visit"),
                        ("date_not_delivered", "date_not_delivered"),
                        ("date_returned", "date_returned"),
                        ("date_cancelled", "date_cancelled"),
                    ]:
                        if sh.get(sh_key):
                            ship_fields[sh_field] = ml_datetime(sh[sh_key])

                # Parse shipping_option estimated delivery (fallback when no lead_time)
                shipping_option = ship_json.get("shipping_option") or {}
                if shipping_option:
                    so_edt = shipping_option.get("estimated_delivery_time") or {}
                    if so_edt and so_edt.get("date") and not ship_fields.get("estimated_delivery_date"):
                        ship_fields["estimated_delivery_date"] = ml_datetime(so_edt["date"])
                    if so_edt and so_edt.get("pay_before"):
                        ship_fields["estimated_pay_before"] = ml_datetime(so_edt["pay_before"])
                    so_edl = shipping_option.get("estimated_delivery_limit") or {}
                    if so_edl and so_edl.get("date") and not ship_fields.get("estimated_delivery_limit"):
                        ship_fields["estimated_delivery_limit"] = ml_datetime(so_edl["date"])
                    so_edf = shipping_option.get("estimated_delivery_final") or {}
                    if so_edf and so_edf.get("date") and not ship_fields.get("estimated_delivery_final"):
                        ship_fields["estimated_delivery_final"] = ml_datetime(so_edf["date"])
                    so_buf = shipping_option.get("buffering") or {}
                    if so_buf.get("date"):
                        ship_fields["estimated_buffering_date"] = ml_datetime(so_buf["date"])
                    so_esl = shipping_option.get("estimated_schedule_limit") or {}
                    if so_esl.get("date"):
                        ship_fields["estimated_schedule_limit"] = ml_datetime(so_esl["date"])
                    so_pprom = shipping_option.get("pickup_promise") or {}
                    if so_pprom.get("from"):
                        ship_fields["pickup_promise_from"] = ml_datetime(so_pprom["from"])
                    if so_pprom.get("to"):
                        ship_fields["pickup_promise_to"] = ml_datetime(so_pprom["to"])
                    so_dpd = shipping_option.get("desired_promised_delivery") or {}
                    if so_dpd.get("from"):
                        ship_fields["desired_promised_delivery"] = ml_datetime(so_dpd["from"])

                # Parse lead_time data (delivery estimates, shipping method, etc.)
                lead_time = ship_json.get("lead_time") or {}
                if lead_time:
                    sm = lead_time.get("shipping_method") or {}
                    ship_fields.update({
                        "shipping_method_id": sm.get("id", ""),
                        "shipping_method_type": sm.get("type", ""),
                        "shipping_method_name": sm.get("name", ""),
                        "shipping_method_deliver_to": sm.get("deliver_to", ""),
                        "service_id": lead_time.get("service_id", ""),
                        "cost_type": lead_time.get("cost_type", ""),
                    })

                    edt = lead_time.get("estimated_delivery_time") or {}
                    if edt:
                        ship_fields.update({
                            "estimated_delivery_type": edt.get("type", ""),
                            "estimated_delivery_date": ml_datetime(edt.get("date")),
                            "estimated_delivery_shipping": edt.get("shipping", 0),
                            "estimated_delivery_handling": edt.get("handling", 0),
                            "estimated_delivery_unit": edt.get("unit", ""),
                        })
                        offset = edt.get("offset") or {}
                        if offset.get("date"):
                            ship_fields["estimated_delivery_offset_date"] = ml_datetime(offset["date"])

                    ehl = lead_time.get("estimated_handling_limit") or {}
                    if ehl.get("date"):
                        ship_fields["estimated_handling_limit"] = ml_datetime(ehl["date"])

                    ede = lead_time.get("estimated_delivery_extended") or {}
                    if ede.get("date"):
                        ship_fields["estimated_delivery_extended"] = ml_datetime(ede["date"])

                    edl = lead_time.get("estimated_delivery_limit") or {}
                    if edl.get("date"):
                        ship_fields["estimated_delivery_limit"] = ml_datetime(edl["date"])

                    edf = lead_time.get("estimated_delivery_final") or {}
                    if edf.get("date"):
                        ship_fields["estimated_delivery_final"] = ml_datetime(edf["date"])

                    delays = lead_time.get("delay") or []
                    if delays:
                        ship_fields["delay"] = ",".join(str(d) for d in delays)

                if "receiver_address" in ship_json and ship_json["receiver_address"]:
                    ship_fields.update({
                        "receiver_address_id": ship_json["receiver_address"]["id"],
                        "receiver_address_phone": ship_json["receiver_address"]["receiver_phone"],
                        "receiver_address_name": ship_json["receiver_address"]["receiver_name"],
                        "receiver_address_line": ship_json["receiver_address"]["address_line"],
                        "receiver_address_comment": ship_json["receiver_address"]["comment"],
                        "receiver_street_name": ship_json["receiver_address"]["street_name"],
                        "receiver_street_number": ship_json["receiver_address"]["street_number"],
                        "receiver_city": ship_json["receiver_address"]["city"]["name"],
                        "receiver_city_code": ship_json["receiver_address"]["city"]["id"],
                        "receiver_state": ship_json["receiver_address"]["state"]["name"],
                        "receiver_state_code": ship_json["receiver_address"]["state"]["id"],
                        "receiver_country": ship_json["receiver_address"]["country"]["name"],
                        "receiver_country_code": ship_json["receiver_address"]["country"]["id"],
                        "receiver_latitude": ship_json["receiver_address"]["latitude"],
                        "receiver_longitude": ship_json["receiver_address"]["longitude"],
                        "receiver_zip_code": (("zip_code" in ship_json["receiver_address"]) and ship_json["receiver_address"]["zip_code"]) or False
                    })
                    receiver_phone = ("receiver_phone" in ship_json["receiver_address"] and ship_json["receiver_address"]["receiver_phone"] and not "XXXX" in ship_json["receiver_address"]["receiver_phone"] and ship_json["receiver_address"]["receiver_phone"])
                    if receiver_phone:
                        ship_fields.update({"receiver_address_phone": receiver_phone })

                if "sender_address" in ship_json and ship_json["sender_address"]:
                    ship_fields.update({
                        "sender_address_id": ship_json["sender_address"]["id"],
                        "sender_address_line": ship_json["sender_address"]["address_line"],
                        "sender_address_comment": ship_json["sender_address"]["comment"],
                        "sender_street_name": ship_json["sender_address"]["street_name"],
                        "sender_street_number": ship_json["sender_address"]["street_number"],
                        "sender_city": ship_json["sender_address"]["city"]["name"],
                        "sender_state": ship_json["sender_address"]["state"]["name"],
                        "sender_country": ship_json["sender_address"]["country"]["name"],
                        "sender_latitude": ship_json["sender_address"]["latitude"],
                        "sender_longitude": ship_json["sender_address"]["longitude"],
                    });

                items_json = []

                if meli.access_token=="PASIVA":
                    response2 = True
                    oitems = order
                    #buscar las ordenes asociadas al pack_id
                    if order.pack_id:
                        oitems = self.env["mercadolibre.orders"].search([("pack_id","=",order.pack_id)])

                    for oitem in oitems:
                        itemjson = {
                            "order_id": oitem.order_id,
                            "id": oitem.id,
                            "item_id": oitem.order_items and oitem.order_items[0].order_item_id,
                            "description": oitem.order_items and oitem.order_items[0].posting_id.name,
                            "variation_id": oitem.order_items and oitem.order_items[0].seller_sku,
                        }
                        items_json.append(itemjson)
                else:
                    response2 = meli.get("/shipments/"+ str(ship_id)+"/items",  {'access_token':meli.access_token})

                all_orders = []
                all_orders_ids = []

                if (response2):
                    items_json = items_json or response2.json()
                    if "error" in items_json:
                        _logger.error( items_json["error"] )
                        _logger.error( items_json["message"] )
                    else:
                        if (len(items_json)>1 or ( len(items_json)==1 and order.pack_order==True ) ):
                            #_logger.info("Es carrito")
                            ship_fields["pack_order"] = True
                        else:
                            ship_fields["pack_order"] = False

                        full_orders = False
                        
                        coma = ""
                        packed_order_ids =""
                        items_json_sorted = sorted(items_json, key=lambda x: x["order_id"], reverse=False)
                        #_logger.info("items_json_sorted:"+str(items_json_sorted))
                        for item in items_json_sorted:
                            #check mercadolibre_orders for full pack
                            if "order_id" in item:
                                #search order, if not present search orders...
                                #search by meli_order_id in mercadolibre.orders
                                #_logger.info(item)
                                item_order = orders_obj.search( [("order_id",'=',item["order_id"])], limit=1 )
                                if len(item_order):
                                    all_orders.append(item_order)
                                    all_orders_ids.append(item_order.id)
                                    packed_order_ids+= coma + item["order_id"]
                                    coma = ","
                        full_orders = ( len(items_json) == len(all_orders) )
                        for ordi in all_orders:
                            if (ordi.order_id==ordi.name):
                                full_orders = False
                                break;

                        #_logger.info(items_json)
                        #_logger.info("full_orders:"+str(full_orders))
                        if (full_orders):
                            #We can create order with all items now
                            ship_fields["orders"] = [(6, 0, all_orders_ids)]

                #shipment = shipment_obj.search([('shipping_id','=', ship_id)],limit=1)
                query = """SELECT id
                FROM   mercadolibre_shipment
                WHERE
                shipping_id = '%s'
                """ % (ship_id)
                cr = MeliCr( self )
                respquery = cr.execute(query)
                results = cr.fetchall()
                shipment_ids = results
                shipment = False
                #_logger.info("shipment_ids:"+str(shipment_ids)+" ship_id:"+str(ship_id))
                if (not shipment_ids):
                #if ( or len(shipment)==0):
                    #_logger.info("Importing shipment: " + str(ship_id))
                    #_logger.info(str(ship_fields))
                    shipment = shipment_obj.create((ship_fields))
                    if (shipment):
                        #_logger.info("Created shipment ok!")
                        pass;
                else:
                    #_logger.info("Updating shipment: " + str(ship_id))
                    shipment = shipment_obj.sudo().browse(shipment_ids and shipment_ids[0])
                    if (shipment):
                        shipment.write((ship_fields))

                if shipment and items_json:
                    #mercadolibre.shipment.item
                    #_logger.info("items_json: "+str(items_json))
                    for item in items_json:
                        shipment.update_item(item)

                    # Generar preview JPG de la etiqueta PDF (solo si pdf2image está disponible)
                    if PDF2IMAGE_AVAILABLE:
                        try:
                            if shipment.pdf_filename and not shipment.pdfimage_filename:
                                data = base64.b64decode(shipment.pdf_file)
                                images = convert_from_bytes(data, dpi=300, fmt='jpg')
                                for image in images:
                                    image_filename = "/tmp/%s-page%d.jpg" % ("Shipment_" + shipment.shipping_id, images.index(image))
                                    image.save(image_filename, "JPEG")
                                    if images.index(image) == 0:
                                        imgdata = urlopen("file://" + image_filename).read()
                                        shipment.pdfimage_file = base64encode(imgdata)
                                        shipment.pdfimage_filename = "Shipment_" + shipment.shipping_id + ".jpg"
                        except Exception as e:
                            _logger.debug("Error converting pdf to jpg: %s", str(e))
                            pass

                #associate order if it was non pack order created bir orders.py
                if (ship_fields["pack_order"]==False):
                    sorder = self.env["sale.order"].search( [ ('meli_order_id','=',ship_fields["order_id"]) ], limit=1 )
                    if sorder:
                        shipment.sale_order = sorder[0]
                        sorder.meli_shipment = shipment
                        #_logger.info("setting meli_shipping_amount:"+str(sorder)+" all_orders: " +str(all_orders))
                        if all_orders:
                            sorder.meli_shipping_amount = all_orders and all_orders[0] and all_orders[0].payments_shipment_amount

                #if its a pack order, create it, oif full_orders were fetched (we can force this now)
                #_logger.info("full_orders:"+str(full_orders))
                #_logger.info("all_orders:"+str(all_orders))
                if (full_orders and ship_fields["pack_order"]):
                    plistid = None
                    if (config and config.mercadolibre_pricelist):
                        plistid = config.mercadolibre_pricelist
                    else:
                        error = { "error": "orders_update_order_json (shipment) > no pricelist defined. Check config pricelist config: " + str(config and config.name)+" pricelist: "+str(config and config.mercadolibre_pricelist) }
                        _logger.error(error)
                        #_logger.info( "orders_update_order_json > filter:" + str(error) )
                        return error


                    #buyer_ids = buyers_obj.search([  ('buyer_id','=',buyer_fields['buyer_id'] ) ] )
                    partner_invoice_meli_order_id = str(all_orders[0]['pack_id'] or all_orders[0]['id'])
                    partner_id = respartner_obj.search([  ('meli_buyer_id','=',ship_fields['receiver_id'] ) ]+company_only_domain, limit=1 )
                    if not partner_id:
                        partner_id = respartner_obj.search([  ('meli_buyer_id','=',ship_fields['receiver_id'] ) ]+company_none_domain, limit=1 )

                    partner_invoice_id = respartner_obj.search([  ('meli_order_id','=',partner_invoice_meli_order_id ) ]+company_only_domain, limit=1 )
                    if not partner_invoice_id:
                        partner_invoice_id = respartner_obj.search([  ('meli_order_id','=',partner_invoice_meli_order_id ) ]+company_none_domain, limit=1 ) or partner_id

                    original_contact_partner_id = partner_id
                    partner_shipping_id = None
                    if "receiver_address" in ship_json:
                        if config.mercadolibre_cron_get_orders_shipment_client:
                            partner_shipping_id = self.partner_delivery_id( partner_id=original_contact_partner_id, Receiver=ship_json["receiver_address"], config=config )


                    mercadolibre_contact_partner_id = ("mercadolibre_contact_partner" in config._fields and config.mercadolibre_contact_partner)
                    if (mercadolibre_contact_partner_id):
                        mercadolibre_contact_partner_id.meli_update_forbidden = True

                    mercadolibre_invoice_partner_id = ("mercadolibre_invoice_partner" in config._fields and config.mercadolibre_invoice_partner)
                    if (mercadolibre_invoice_partner_id):
                        mercadolibre_invoice_partner_id.meli_update_forbidden = True

                    mercadolibre_shipping_partner_id = ("mercadolibre_shipping_partner" in config._fields and config.mercadolibre_shipping_partner)
                    if (mercadolibre_shipping_partner_id):
                        mercadolibre_shipping_partner_id.meli_update_forbidden = True

                    partner_id =  mercadolibre_contact_partner_id or partner_id
                    partner_invoice_id = mercadolibre_invoice_partner_id or partner_invoice_id
                    partner_shipping_id = mercadolibre_shipping_partner_id or partner_shipping_id


                    if (partner_id.id):
                        oname = "pack_id" in all_orders[0] and all_orders[0]["pack_id"] and str(  "ML %s" % ( str(all_orders[0]["pack_id"]) ) )
                        oname = oname or str("ML %s" % ( str(all_orders[0]["order_id"]) ) )
                        #sorder_pack = self.env["sale.order"].search( [ '|',('meli_order_id','=',packed_order_ids), ('name','like', str(oname)) ], order="id asc", limit=1 )
                        sorder_pack = self.env["sale.order"].search( [ ('meli_order_id','=',packed_order_ids) ], order="id asc", limit=1 )
                        if (sorder_pack and sorder_pack.meli_update_forbidden):
                            _logger.error("Forbidden to update sale order by meli_oerp" )
                            return {'error': 'Forbidden to update sale order by meli_oerp' }

                        sorder = sorder_pack
                        totales = {}
                        totales['total_amount'] = 0
                        totales['paid_amount'] = 0
                        totales['coupon_amount'] = 0
                        totales['financing_fee_amount'] = 0
                        totales['shipping_amount'] = 0

                        mercadolibre_use_payment_shipping_amount = True
                        if (config and "mercadolibre_use_payment_shipping_amount" in config._fields):
                            mercadolibre_use_payment_shipping_amount = config.mercadolibre_use_payment_shipping_amount
                        
                        for oi in all_orders:
                            ord = oi
                            totales['total_amount']+= ord["total_amount"]
                            totales['paid_amount']+= ord["paid_amount"]
                            totales['coupon_amount']+= ord["coupon_amount"]
                            totales['financing_fee_amount']+= ord["financing_fee_amount"]
                            if mercadolibre_use_payment_shipping_amount:
                                totales['shipping_amount']+= ord.payments_shipment_amount
                            else:
                                totales['shipping_amount'] = shipment.shipping_cost

                        #fix ML order_json... for pack_order "shipping_cost" added
                        if not mercadolibre_use_payment_shipping_amount and shipment.shipping_cost:
                            totales['paid_amount']+= shipment.shipping_cost

                        # Fallback pack/ME2: el flete del COMPRADOR (receiver.cost) no viene
                        # en los pagos ni en shipping_option.cost — sumarlo una vez al total
                        # del pack para que la factura cierre con lo que pagó el comprador.
                        if not totales['shipping_amount'] and shipment.shipping_receiver_cost:
                            totales['shipping_amount'] = shipment.shipping_receiver_cost
                            totales['paid_amount'] += shipment.shipping_receiver_cost

                        order_json = {
                            "id": all_orders[0]["order_id"],
                            'status': all_orders[0]["status"],
                            'status_detail': all_orders[0]["status_detail"] or '' ,
                            'total_amount': totales["total_amount"],
                            'paid_amount': totales["paid_amount"], #added shipment.shipping_cost,
                            'coupon': { "amount": totales["coupon_amount"] },
                            'financing_fee_amount': totales['financing_fee_amount'],
                            'currency_id': all_orders[0]["currency_id"],
                            "date_created": all_orders[0]["date_created"],
                            "date_closed": all_orders[0]["date_closed"],
                        }

                        meli_order_fields = self.env['mercadolibre.orders'].prepare_sale_order_vals( order_json=order_json, meli=meli, config=config, sale_order=sorder_pack, shipment=shipment )
                        #meli_order_fields.update({
                        #    'partner_id': partner_id.id,
                        #    'pricelist_id': plistid.id,
                        #})
                        meli_order_fields.update({
                            #TODO: "add parameter for pack_id":
                            #'name': "ML %i" % ( all_orders[0]["pack_id"] ),
                            #'name': "ML %s" % ( str(all_orders[0]["order_id"]) ),
                            'pricelist_id': plistid and plistid.id,
                            #'meli_order_id': '%i' % (order_json["id"]),
                            'meli_order_id': packed_order_ids,
                            'meli_orders': [(6, 0, all_orders_ids)],
                            'meli_shipping_id': shipment.shipping_id,
                            'meli_shipping': shipment,
                            'meli_shipment': shipment.id,
                            #'meli_status': all_orders[0]["status"],
                            #'meli_status_detail': all_orders[0]["status_detail"] or '' ,
                            #'meli_total_amount': shipment.order_cost,
                            'meli_shipping_amount': totales["shipping_amount"],
                            'meli_shipping_cost': shipment.shipping_cost,
                            'meli_shipping_list_cost': shipment.shipping_list_cost,
                            #'meli_paid_amount': shipment.order_cost,
                            'meli_fee_amount': 0.0,
                            #'meli_currency_id': all_orders[0]["currency_id"],
                            'meli_date_created': ml_datetime(all_orders[0]["date_created"]) or all_orders[0]["date_created"],
                            'meli_date_closed': ml_datetime(all_orders[0]["date_closed"]) or all_orders[0]["date_created"],
                        })
                        #TODO: agregar un campo para diferencia cada delivery res partner al shipment y orden asociado, crear un binding usando values diferentes... y listo
                        #_logger.info("ship_json[receiver_address]:"+str(ship_json["receiver_address"]) )
                        if ('account.payment.term' in self.env):
                            inmediate_or_not = ('mercadolibre_payment_term' in config._fields and config.mercadolibre_payment_term) or ('mercadolibre_payment_term' in company._fields and company.mercadolibre_payment_term) or None
                            if inmediate_or_not:
                                meli_order_fields["payment_term_id"] = inmediate_or_not.id


                        if partner_id:
                            partner_already_set = (sorder and sorder.partner_id and sorder.partner_id.id == partner_id.id)
                            if not partner_already_set:
                                meli_order_fields.update({'partner_id': (partner_id and partner_id.id)})

                        if partner_invoice_id:
                            partner_invoice_already_set = (sorder and sorder.partner_invoice_id and sorder.partner_invoice_id.id == partner_invoice_id.id)
                            if not partner_invoice_already_set:
                                meli_order_fields.update({'partner_invoice_id': (partner_invoice_id and partner_invoice_id.id)})


                        if partner_shipping_id:
                            sorder = sorder_pack
                            shipping_partner_already_set = (sorder and sorder.partner_shipping_id and sorder.partner_shipping_id.id == partner_shipping_id.id)
                            update_shipping = not sorder or (sorder and not sorder.partner_shipping_id)
                            update_shipping = update_shipping or not shipping_partner_already_set
                            if (update_shipping):
                                meli_order_fields['partner_shipping_id'] = partner_shipping_id.id

                        if ("pack_id" in all_orders[0] and all_orders[0]["pack_id"]):
                            meli_order_fields['name'] = "ML %s" % ( str(all_orders[0]["pack_id"]) )
                            #meli_order_fields['pack_id'] = all_orders[0]["pack_id"]

                        if (not sorder_pack and config.mercadolibre_seller_user):
                            meli_order_fields["user_id"] = config.mercadolibre_seller_user.id
                        if (not sorder_pack and config.mercadolibre_seller_team):
                            meli_order_fields["team_id"] = config.mercadolibre_seller_team.id

                        if (len(sorder_pack)):
                            sorder_pack = sorder_pack[0]
                            #_logger.info("Update sale.order pack")
                            #_logger.info(meli_order_fields)
                            is_locked = (sorder_pack and sorder_pack.state in ["done"]) or ("locked" in sorder_pack._fields and sorder_pack.locked)
                            if (sorder_pack.state in ['sale','done']) or is_locked:
                                del meli_order_fields["pricelist_id"]

                            #sorder_pack.meli_fix_team( meli=meli, config=config )
                            if (sorder_pack.state in ['draft']):
                                _logger.info("Pack Sale Order writing")
                                sorder_pack.write(meli_order_fields)
                            #sorder_pack.meli_fix_team( meli=meli, config=config )
                        else:
                            # Sanitize vals for compatibility with auditlog (copy.deepcopy)
                            safe_fields = {}
                            for k, v in meli_order_fields.items():
                                if hasattr(v, '_ids'):
                                    safe_fields[k] = v.id if len(v) == 1 else v.ids
                                else:
                                    safe_fields[k] = v
                            sorder_pack = self.env["sale.order"].create(safe_fields)
                            #_logger.info("Create sale.order pack: ALL PASS OK")
                            if sorder_pack:
                                sorder_pack.meli_fix_team( meli=meli, config=config )
                                meli_message_post(order, "Sale order created (pack)!", config=config)
                    
                        if (sorder_pack.id):
                            shipment.sale_order = sorder_pack
                            sorder_pack.meli_shipment = shipment

                            order.sale_order = sorder_pack
                            order.shipping_cost = shipment.shipping_cost
                            #order.shipping_seller_cost = shipment.shipping_seller_cost
                            
                            order.shipping_list_cost = shipment.shipping_list_cost

                            #creating and updating all items related to ml.orders
                            sorder_pack.meli_fee_amount = 0.0

                            for mOrder in all_orders:
                                #Each Order one product with one price and one quantity
                                mOrder.sale_order = sorder_pack
                                product_related_obj = mOrder.order_items and (mOrder.order_items[0].product_id or mOrder.order_items[0].posting_id.product_id)
                                if not (product_related_obj):
                                    #error = { 'error': 'No product related to meli_id '+str(Item['item']['id']), 'item': str(Item['item']) }
                                    _logger.error("Error adding order line: product not found in database: " + str(mOrder.order_items and mOrder.order_items[0]["order_item_title"]) )
                                    #mOrder and mOrder.message_post(body=str(error["error"])+"\n"+str(error["item"]),message_type=order_message_type)
                                    continue;
                                unit_price = mOrder.order_items and mOrder.order_items[0]["unit_price"]

                                tax_field = SaleOrderLineTaxField( self )
                                uom_field = SaleOrderLineUomField( self )
                                saleorderline_item_fields = {
                                    'company_id': company.id,
                                    'order_id': shipment.sale_order.id,
                                    'meli_order_item_id': mOrder.order_items[0]["order_item_id"],
                                    'meli_order_item_iva': mOrder.order_items[0]["order_item_iva"],
                                    'meli_order_item_variation_id': mOrder.order_items[0]["order_item_variation_id"],
                                    'product_id': product_related_obj.id,
                                    'product_uom_qty': mOrder.order_items[0]["quantity"],                                    
                                    'name': product_related_obj.display_name or mOrder.order_items[0]["order_item_title"],
                                }
                                saleorderline_item_fields[uom_field] = product_related_obj.uom_id.id
                                
                                if (mOrder.fee_amount):
                                    sorder_pack.meli_fee_amount = sorder_pack.meli_fee_amount + mOrder.fee_amount

                                saleorderline_item_fields.update( order._set_product_unit_price( product_related_obj, mOrder.order_items[0], config=config ) )

                                saleorderline_item_ids = saleorderline_obj.search( [('meli_order_item_id','=',saleorderline_item_fields['meli_order_item_id']),
                                                                                    ('meli_order_item_variation_id','=',saleorderline_item_fields['meli_order_item_variation_id']),
                                                                                    ('order_id','=',shipment.sale_order.id)] )

                                if not saleorderline_item_ids:
                                    if sorder_pack.amount_total<(sorder_pack.meli_paid_amount-(sorder_pack.meli_discount_seller_amount or sorder_pack.meli_coupon_amount)):
                                        #_logger.info("Sale Order Pack Create line")
                                        saleorderline_item_ids = saleorderline_obj.create( ( saleorderline_item_fields ))
                                
                                
                                if saleorderline_item_ids:
                                    #_logger.info(saleorderline_item_ids:"+str(saleorderline_item_ids))
                                    #_logger.info(product_related_obj taxes_id:"+str(product_related_obj.taxes_id))
                                    #_logger.info(product_related_obj taxes_id:"+str(product_related_obj.taxes_id and product_related_obj.taxes_id.company_id))
                                    #_logger.info(saleorderline_item_ids tax:"+str(saleorderline_item_ids[tax_field]))
                                    #_logger.info(saleorderline_item_ids tax company_id:"+str(saleorderline_item_ids[tax_field].company_id))
                                    tax_iva_name = saleorderline_item_ids.meli_order_item_iva
                                    tax_iva_name = tax_iva_name
                                    tax_iva_id = None
                                    if tax_iva_name and product_related_obj.taxes_id:
                                        for txid in product_related_obj.taxes_id:
                                            if ( tax_names_equivalent(txid.name,tax_iva_name) ):
                                                tax_iva_id = txid

                                    for tid in saleorderline_item_ids[tax_field]:

                                        if (tid.company_id.id!=sorder.company_id.id 
                                            or (tax_iva_id and tax_iva_id!=tid) ):
                                            #remove
                                            saleorderline_item_ids[tax_field] = [(3, tid.id)]

                                    if not saleorderline_item_ids[tax_field] and product_related_obj.taxes_id:
                                        for txid in product_related_obj.taxes_id:
                                            if (txid.company_id.id==sorder.company_id.id):
                                                if (tax_iva_id):
                                                    if (tax_iva_id!=tid):
                                                        #add
                                                        saleorderline_item_ids[tax_field] = [(4, txid.id)]
                                                else:
                                                    #add
                                                    saleorderline_item_ids[tax_field] = [(4, txid.id)]
                                    is_locked = ((sorder_pack and sorder_pack.state in ["done","sale"]) 
                                                or ("locked" in sorder_pack._fields and sorder_pack.locked))
                                    if (is_locked):
                                        #_logger.warning("Orden bloqueada no se puede actualizar linea de la orden")
                                        pass;
                                    else:
                                        #_logger.info("sale order line to write")
                                        saleorderline_item_ids.write( ( saleorderline_item_fields ) )
                    else:
                        #_logger.info("partner receiver id not founded:"+str(ship_fields['receiver_id']))
                        pass;

        if (shipment):
            # FIX: Copy order.shipping_seller_cost to shipment BEFORE _update_sale_order_shipping_info
            # so that purchase_price on the delivery line is calculated with the actual seller cost.
            # shipping_seller_cost comes from payment charges_details (type="shipping" / name="shp_fulfillment")
            # and is set on the order during payment processing, which runs before fetch_shipment.
            # Previously this copy happened in orders.py AFTER fetch_shipment returned,
            # causing _update_sale_order_shipping_info to use shipping_seller_cost=0.
            if order and order.shipping_seller_cost:
                shipment.shipping_seller_cost = order.shipping_seller_cost

            shipment._update_sale_order_shipping_info( order, meli=meli, config=config )

        return shipment

    def update_item( self, item=None ):
        shipment = self
        sitem = None
        if not item or not "order_id" in item or not "item_id" in item:
            return None

        #_logger.info("update shipment:"+str(item))
        if "variation_id" in item and item["variation_id"]:
            sitem = self.env["mercadolibre.shipment.item"].search([ ("shipment_id","=",shipment.id),("order_id","=",item["order_id"]), ("item_id","=",item["item_id"]), ("variation_id","=",item["variation_id"]) ],limit=1)
        else:
            sitem = self.env["mercadolibre.shipment.item"].search([ ("shipment_id","=",shipment.id),("order_id","=",item["order_id"]), ("item_id","=",item["item_id"])],limit=1)

        ifields = {
            "name": str(item["description"])+"-"+str(item["item_id"])+"-"+str(item["variation_id"])+"-"+str(item["order_id"]),
            "item_id": str(item["item_id"]),
            "variation_id": str(item["variation_id"]),
            "order_id": str(item["order_id"]),
            "shipment_id": shipment.id,
            "data": str(item)
        }
        #_logger.info("update shipment ifields:"+str(ifields))
        if sitem:
            sitem.write(ifields)
        else:
            sitem = self.env["mercadolibre.shipment.item"].create(ifields)
        return sitem

    def update( self, context=None, meli=None, config=None ):

        #_logger.info( "update: context: "+str(context)+ " meli: "+str(meli)+ " config: " +str(config) )

        self.fetch_shipment( self.order, meli=meli, config=config )

        return {}

    def shipment_query( self, meli=None, config=None ):

        company = self.env.user.company_id
        if not config:
            config = company
        if not meli:
            meli = self.env['meli.util'].get_new_instance(company)
            if meli.need_login():
                return meli.redirect_login()

        orders_obj = self.env['mercadolibre.orders']
        shipment_obj = self.env['mercadolibre.shipment']


        #orders_query = "/orders/search?seller="+config.mercadolibre_seller_id+"&sort=date_desc"

        # https://api.mercadolibre.com/shipment_labels?shipment_ids=20178600648,20182100995&response_type=pdf&access_token=
        # https://api.mercadolibre.com/shipments/27693158904?access_token=APP_USR-3069131366650174-120509-8746c1a831468e99f84105cd631ff206-246057399


        return {}

    def shipment_print( self, meli=None, config=None, include_ready_to_print=None ):

        context = self.env.context
        company = self.env.user.company_id

        shipment= self
        shipment.update()

        if not meli:
            meli = self.env['meli.util'].get_new_instance( company )

        ship_report = { 'message': '', 'access_token': meli.access_token }
        print_mode = "pdf"
        if (config and "mercadolibre_shipment_print_guide" in config._fields):
            if (config and "mercadolibre_shipment_print_guide_mode" in config._fields):
                print_mode = config["mercadolibre_shipment_print_guide_mode"]        

        if (shipment and shipment.status=="ready_to_ship"):

            #full_str_ids = full_str_ids + comma + shipment
            if (print_mode=='pdf'):
                download_url = "https://api.mercadolibre.com/shipment_labels?shipment_ids="+shipment.shipping_id+"&response_type=pdf&access_token="+meli.access_token
            if (print_mode in ('zpl','zpl_txt')):
                download_url = "https://api.mercadolibre.com/shipment_labels?shipment_ids="+shipment.shipping_id+"&response_type=zpl2&access_token="+meli.access_token
    
            shipment.pdf_link = download_url

            if (shipment.substatus=="printed" or include_ready_to_print):            

                try:
                    if print_mode == 'pdf':
                        data = urlopen(shipment.pdf_link).read()
                        shipment.pdf_filename = "Shipment_" + shipment.shipping_id + ".pdf"
                        shipment.pdf_file = base64.b64encode(data)
                        # Generar preview JPG (solo si pdf2image está disponible)
                        if PDF2IMAGE_AVAILABLE:
                            try:
                                images = convert_from_bytes(data, dpi=300, fmt='jpg')
                                if len(images) > 0:
                                    for image in images:
                                        image_filename = "/tmp/%s-page%d.jpg" % ("Shipment_" + shipment.shipping_id, images.index(image))
                                        image.save(image_filename, "JPEG")
                                        if images.index(image) == 0:
                                            imgdata = urlopen("file://" + image_filename).read()
                                            shipment.pdfimage_file = base64.b64encode(imgdata)
                                            shipment.pdfimage_filename = "Shipment_" + shipment.shipping_id + ".jpg"
                            except Exception as img_e:
                                _logger.debug("Error generating PDF preview: %s", str(img_e))

                    if print_mode in ('zpl', 'zpl_txt'):
                        data = urlopen(shipment.pdf_link).read()
                        is_zip = data[:2] == b'PK'
                        if print_mode == 'zpl_txt':
                            # ML entrega la etiqueta ZPL2 dentro de un ZIP. En modo
                            # "ZPL (txt)" se extrae el contenido plano del zip y se guarda
                            # como .zpl directo (sin el empaquetado). Si ML ya devolviera
                            # ZPL plano, se usa tal cual.
                            if is_zip:
                                try:
                                    with zipfile.ZipFile(io.BytesIO(data)) as zf:
                                        names = zf.namelist()
                                        if names:
                                            data = zf.read(names[0])
                                except Exception as zerr:
                                    _logger.warning("No se pudo extraer ZPL del zip para %s: %s", shipment.shipping_id, zerr)
                            shipment.pdf_filename = "Shipment_"+shipment.shipping_id+".zpl"
                        else:
                            # "ZPL (zip)": se conserva el paquete tal cual lo entrega ML.
                            shipment.pdf_filename = "Shipment_"+shipment.shipping_id+(".zip" if is_zip else ".zpl")
                        shipment.pdf_file = base64.b64encode(data)


                except Exception as e:
                    _logger.info("Exception!")
                    _logger.info(e, exc_info=True)
                    #return warningobj.info( title='Impresión de etiquetas: Error descargando guias', message=download_url )
                    if (print_mode=='pdf'):
                        ship_report['message'] = "Error descargando pdf:" + str(shipment.shipping_id) + " - Status: " + str(shipment.status) + " - SubStatus: " + str(shipment.substatus)+'<a href="'+download_url+'" target="_blank"><strong><u>Descargar PDF</u></strong></a>'
                    if (print_mode in ('zpl','zpl_txt')):
                        ship_report['message'] = "Error descargando zpl:" + str(shipment.shipping_id) + " - Status: " + str(shipment.status) + " - SubStatus: " + str(shipment.substatus)+'<a href="'+download_url+'" target="_blank"><strong><u>Descargar PDF</u></strong></a>'

                    #sep = "<br>"+"\n"

        else:
            ship_report['message'] = str(shipment.shipping_id) + " - Status: " + str(shipment.status) + " - SubStatus: " + str(shipment.substatus)
            #sep = "<br>"+"\n"

        return ship_report



class AccountInvoice(models.Model):
    _inherit = acc_inv_model

    @api.model
    def _get_shipment(self):
        ret = {}
        ret["shipping_id"] = ''
        ret["pdfimage_filename"] = ''
        ret["pdfimage_file"] = ''
        ret["receiver_address_name"] = ''
        ret["receiver_address_line"] = ''
        ret["receiver_address_phone"] = ''
        ret["receiver_city"] = ''
        ret["receiver_state"] = ''
        ret["tracking_method"] = ''
        if (self.origin):
            order = self.env["sale.order"].search([('name','=',self.origin)])
            if (order.id):
                #_logger.info("Order found in _get_shipment:"+str(order.name))
                #if (order.meli_order_id)
                if (order.meli_shipment):
                    shipment = order.meli_shipment
                    ret["shipping_id"] = order.meli_shipment.shipping_id
                    ret["pdfimage_filename"] = shipment.pdfimage_filename
                    ret["pdfimage_file"] = shipment.pdfimage_file
                    ret["receiver_address_name"] = shipment.receiver_address_name
                    ret["receiver_address_line"] = shipment.receiver_address_line
                    ret["receiver_address_phone"] = (shipment.receiver_address_phone and not "XXXX" in shipment.receiver_address_phone and shipment.receiver_address_phone)
                    ret["receiver_city"] = shipment.receiver_city
                    ret["receiver_state"] = shipment.receiver_state
                    ret["tracking_method"] = shipment.tracking_method

                    ret["items"] = []
                    for order_item in shipment.order.order_items:
                        ret["items"].append({'quantity':order_item.quantity, 'name': order_item.posting_id.product_id.name})

                else:
                    #_logger.info("No meli_shipping_id found for:"+str(order.meli_shipping_id))
                    pass;
            else:
                #_logger.info("No order found for:"+str(self.origin))
                pass;
        return ret

    @api.model
    def _get_meli_shipment(self):
        ret = False
        if (self.origin):
            order = self.env["sale.order"].search([('name','=',self.origin)])
            if (order.id):
                #_logger.info("Order found in _get_shipment:"+str(order.name))
                #if (order.meli_order_id)
                if (order.meli_shipment):
                    return order.meli_shipment

        return ret
