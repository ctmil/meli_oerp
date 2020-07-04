# -*- coding: utf-8 -*-

from odoo import fields, osv, models, api
import odoo.addons.decimal_precision as dp

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
        ('cost_exceeded','Costo Exedido'),
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

    
    def action_print_tag_delivery(self):
        meli_orders = self.mapped('meli_order_id').filtered(lambda x: x.status == 'paid')
        if meli_orders:
            return meli_orders.action_print_tag_delivery()

class SaleOrderLine(models.Model):
    
    _inherit = "sale.order.line"

    meli_order_item_id = fields.Char('Meli Order Item Id')
