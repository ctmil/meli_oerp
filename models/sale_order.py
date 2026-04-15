# -*- coding: utf-8 -*-

from odoo import fields, osv, models, api
from odoo.tools import html_escape
from markupsafe import Markup
import re
import odoo.addons.decimal_precision as dp

# Traducción de códigos de cancelación ML → español
_MELI_CANCEL_CODES_ES = {
    'expired_order':              'Orden vencida — plazo de pago superado (más de 20 días)',
    'buyer_cancel_pre_payment':   'El comprador canceló antes de realizar el pago',
    'buyer_cancel_accepted':      'Devolución solicitada por el comprador y aceptada',
    'seller_cancel':              'El vendedor canceló la orden',
    'meli_cancel':                'Cancelado por MercadoLibre',
    'non_payment':                'Pago no realizado',
    'out_of_stock':               'Sin stock disponible al momento de la venta',
    'refund_obligatory':          'Devolución obligatoria (reembolso)',
    'chargeback':                 'Contracargo bancario',
    'payment_issue':              'Problema con el método de pago',
    'system_cancel':              'Cancelado automáticamente por el sistema',
    'receiver_absent':            'Receptor ausente al momento de la entrega',
    'fraud':                      'Fraude detectado',
    'duplicate':                  'Orden duplicada',
    'forced_close':               'Cierre forzado por MercadoLibre',
    'quality_issue':              'Problema de calidad reportado',
    'user_request':               'Solicitado por el usuario',
    'internal_ml':                'Proceso interno de MercadoLibre',
    'not_delivery':               'No se realizó la entrega',
    'return_expired':             'Plazo de devolución vencido',
    'not_yet_shipped':            'No despachado en el tiempo requerido',
    'buyer_not_pick_up':          'El comprador no retiró el paquete',
    'bad_debt':                   'Deuda incobrable',
}

_MELI_REQUESTED_BY_ES = {
    'meli':     'MercadoLibre',
    'buyer':    'Comprador',
    'seller':   'Vendedor',
    'system':   'Sistema automático',
    'admin':    'Administrador ML',
    'mediator': 'Mediador',
}

class SaleOrder(models.Model):

    _inherit = "sale.order"

    meli_order_id = fields.Many2one('mercadolibre.orders', u'Meli Order Id',
        copy=False, readonly=True)
    meli_status = fields.Selection( [
        #Initial state of an order, and it has no payment yet.
                                        ("confirmed","Confirmado"),
        #The order needs a payment to become confirmed and show users information.
                                      ("payment_required","Pago requerido"),
        #There is a payment related with the order, but it has not accredited yet
                                    ("payment_in_process","Pago en proceso"),
        #The order has a related payment and it has been accredited.
                                    ("paid","Pagado"),
        #The order has not completed by some reason.
                                    ("cancelled","Cancelado")], string='Order Status')

    meli_status_detail = fields.Text(string='Status detail, in case the order was cancelled.')
    meli_date_created = fields.Datetime('Creation date')
    meli_date_closed = fields.Datetime('Closing date')

#        'meli_order_items': fields.one2many('mercadolibre.order_items','order_id','Order Items' ),
#        'meli_payments': fields.one2many('mercadolibre.payments','order_id','Payments' ),
    meli_shipping = fields.Text(string="Shipping")
    shipping_id = fields.Char(u'ID de Entrega')
    shipping_name = fields.Char(u'Metodo de Entrega')
    shipping_method_id = fields.Char(u'ID de Metodo de Entrega')
    shipping_cost = fields.Float(u'Costo de Entrega', digits=dp.get_precision('Account'))
    shipping_seller_cost = fields.Float(u'Costo de Entrega (Vendedor)')
    shipping_status = fields.Selection([
        ('to_be_agreed', 'A Convenir(Acuerdo entre comprador y vendedor)'),
        ('pending','Pendiente'),
        ('handling','Pago Recibido/No Despachado'),
        ('ready_to_ship','Listo para Entregar'),
        ('shipped','Enviado'),
        ('delivered','Entregado'),
        ('not_delivered','No Entregado'),
        ('not_verified','No Verificado'),
        ('cancelled','cancelled'),
        ('closed','Cerrado'),
        ('error','Error'),
        ('active','Activo'),
        ('not_specified','No especificado'),
        ('stale_ready_to_ship','A Punto de Enviar'),
        ('stale_shipped','Enviado'),
    ], string=u'Estado de Entrega', index=True, readonly=True, related='meli_order_id.shipping_status', store=True)
    shipping_substatus = fields.Selection([
        #subestados de pending
        ('cost_exceeded','Costo Excedido'),
        ('under_review','Bajo Revision'),
        ('reviewed','Revisado'),
        ('fraudulent','Fraudulento'),
        ('waiting_for_payment','Esperando pago se acredite'),
        ('shipment_paid','Costo de envio pagado'),
        #subestados de handling
        ('regenerating','Regenerado'),
        ('waiting_for_label_generation','Esperando Impresion de etiqueta'),
        ('invoice_pending','Facturacion Pendiente'),
        ('waiting_for_return_confirmation','Esperando Confirmacion de devolucion'),
        ('return_confirmed','Devolucion Confirmada'),
        ('manufacturing','Fabricado'),
        #subestados de ready_to_ship
        ('ready_to_print','Etiqueta no Impresa'),
        ('printed','Etiqueta Impresa'),
        ('in_pickup_list','En Lista de Entrega'),
        ('ready_for_pkl_creation','Listo para crear PKL'),
        ('ready_for_pickup','Listo para Entrega en tienda'),
        ('ready_for_dropoff','Listo para dropoff'),
        ('picked_up','Retirado en tienda'),
        ('stale','A Punto de enviar'),
        ('dropped_off','Caido'),
        ('in_hub','En Centro'),
        ('measures_ready','Medidas listas'),
        ('waiting_for_carrier_authorization','Esperando aprobacion de courrier'),
        ('authorized_by_carrier','Aprobado por Courrier'),
        ('in_packing_list','En lista de empaque'),
        ('in_plp','En PLP'),
        ('in_warehouse','En Bodega'),
        ('ready_to_pack','Listo para empacar'),
        #subestados de shipped
        ('delayed','Retrasado'),
        ('waiting_for_withdrawal','Esperando Retirada'),
        ('contact_with_carrier_required','Se requiere contacto con el transportista'),
        ('receiver_absent','Receptor ausente'),
        ('reclaimed','Reclamado'),
        ('not_localized','No localizado'),
        ('forwarded_to_third','Enviado a Tercero'),
        ('soon_deliver','Pronto a entregar'),
        ('refused_delivery','Entrega rechazada'),
        ('bad_address','Mala direccion'),
        ('negative_feedback','No enviado por malos conmentarios del comprador'),
        ('need_review','Necesita revision'),
        ('operator_intervention','Necesita intervencion del operador'),
        ('claimed_me','Reclamo del vendedor'),
        ('retained','Paquete Retenido'),
        #subestados de delivered
        ('damaged','Dañado'),
        ('fulfilled_feedback','Cumplido por los comentarios del comprador'),
        ('no_action_taken','Ninguna acción tomada por el comprador'),
        ('double_refund','Doble Reembolso'),
        #subestados de not_delivered
        ('returning_to_sender','Returning to sender'),
        ('stolen','Robado'),
        ('returned','Devuelto'),
        ('confiscated','Confiscado'),
        ('to_review','Envio Cerrado'),
        ('destroyed','Destruido'),
        ('lost','Perdido'),
        ('cancelled_measurement_exceeded','Cancelado por exeso de medidas'),
        ('returned_to_hub','Devuelto al centro'),
        ('returned_to_agency','Devuelto a agencia'),
        ('picked_up_for_return','Devuelto para regocer en local'),
        ('returning_to_warehouse','Devolviendo a Almacen'),
        ('returned_to_warehouse','Devuelto a Almacen'),
        #subestados de cancelled
        ('recovered','Recuperado'),
        ('label_expired','Etiqueta Expirada'),
        ('cancelled_manually','Cancelado manualmente'),
        ('fraudulent','Cancelado fraudulento'),
        ('return_expired','Devuelto por expiracion'),
        ('return_session_expired','Sesion de devolucion expirada'),
        ('unfulfillable','Imposible de llenar'),
    ], string=u'Estado de Impresion/Entrega', index=True, readonly=True, related='meli_order_id.shipping_substatus', store=True)
    shipping_mode = fields.Selection([
        ('me2','Mercado Envio'),
    ], string=u'Metodo de envio', readonly=True)
    meli_total_amount = fields.Char(string='Total amount')
    meli_currency_id = fields.Char(string='Currency')
#        'buyer': fields.many2one( "mercadolibre.buyers","Buyer"),
#       'meli_seller': fields.text( string='Seller' ),


    meli_cancel_banner = fields.Html(
        compute='_compute_meli_cancel_banner',
        string='Banner cancelación ML',
        sanitize=False,
    )

    @api.depends('meli_status_detail', 'state')
    def _compute_meli_cancel_banner(self):
        for order in self:
            detail = (order.meli_status_detail or '').strip().lstrip('|').strip()
            if not detail or order.state != 'cancel':
                order.meli_cancel_banner = False
                continue

            # Parse: "code: description (solicitado por: X, fecha: Y)"
            code = desc = by_raw = date_raw = ''
            m = re.match(
                r'^(\w+):\s*(.+?)(?:\s*\(solicitado\s+por:\s*([^,]+),\s*fecha:\s*([^)]+)\))?$',
                detail.strip(),
            )
            if m:
                code     = m.group(1) or ''
                desc     = (m.group(2) or '').strip()
                by_raw   = (m.group(3) or '').strip()
                date_raw = (m.group(4) or '').strip()
            else:
                desc = detail  # fallback: show raw text

            code_es = _MELI_CANCEL_CODES_ES.get(code, code.replace('_', ' ').title() if code else 'Motivo desconocido')
            by_es   = _MELI_REQUESTED_BY_ES.get(by_raw.lower(), by_raw) if by_raw else ''

            # Format ISO date: 2026-02-01T23:31:35.000-04:00 → 01/02/2026 23:31
            date_display = date_raw
            if date_raw:
                try:
                    from datetime import datetime as _dt
                    d = _dt.fromisoformat(date_raw[:19])  # strip tz for simple parse
                    date_display = d.strftime('%d/%m/%Y %H:%M')
                except Exception:
                    pass

            # Build safe HTML lines
            code_line = Markup(
                '<div style="margin-bottom:4px;">'
                '<span style="font-size:13px;color:#495057;">'
                '<b>Código:</b> {code_es}'
                '<span style="color:#888;font-size:11px;"> ({code})</span>'
                '</span></div>'
            ).format(code_es=html_escape(code_es), code=html_escape(code)) if code else Markup('')

            desc_line = Markup(
                '<div style="margin-bottom:4px;">'
                '<span style="font-size:13px;color:#495057;">'
                '<b>Descripción original:</b> {desc}'
                '</span></div>'
            ).format(desc=html_escape(desc)) if desc else Markup('')

            meta_parts = []
            if by_es:
                meta_parts.append(Markup('<b>Solicitado por:</b> {v}').format(v=html_escape(by_es)))
            if date_display:
                meta_parts.append(Markup('<b>Fecha:</b> {v}').format(v=html_escape(date_display)))
            meta_line = Markup(
                '<div style="font-size:12px;color:#6c757d;margin-top:2px;">{content}</div>'
            ).format(content=Markup(' &nbsp;·&nbsp; ').join(meta_parts)) if meta_parts else Markup('')

            order.meli_cancel_banner = Markup("""
<div style="position:relative;overflow:hidden;background:#fff8e1;
            border-left:5px solid #e53935;border-radius:4px;
            padding:14px 20px 14px 16px;margin-bottom:12px;">
  <div style="position:absolute;top:18px;right:-24px;background:#e53935;
              color:#fff;font-size:10px;font-weight:700;padding:5px 44px;
              transform:rotate(45deg);letter-spacing:1.5px;
              box-shadow:0 1px 4px rgba(0,0,0,.25);white-space:nowrap;">
    CANCELADO ML
  </div>
  <div style="display:flex;align-items:flex-start;gap:12px;padding-right:70px;">
    <span style="font-size:28px;line-height:1;flex-shrink:0;">🚫</span>
    <div>
      <div style="font-size:15px;font-weight:700;color:#b71c1c;margin-bottom:8px;">
        Orden cancelada por MercadoLibre
      </div>
      {code_line}{desc_line}{meta_line}
    </div>
  </div>
</div>
""").format(code_line=code_line, desc_line=desc_line, meta_line=meta_line)

    def action_print_tag_delivery(self):
        meli_orders = self.mapped('meli_order_id').filtered(lambda x: x.status == 'paid')
        if meli_orders:
            return meli_orders.action_print_tag_delivery()

class SaleOrderLine(models.Model):

    _inherit = "sale.order.line"

    meli_order_item_id = fields.Char('Meli Order Item Id')
