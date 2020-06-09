# -*- coding: utf-8 -*-

from odoo import models, api, fields
import odoo.addons.decimal_precision as dp
from odoo.tools.translate import _
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT as DTF
from odoo.exceptions import UserError, ValidationError

class MeliCampaignRecord(models.Model):

    _name = 'meli.campaign.record'
    _description = u'Registros de Campañas MELI'
    
    campaign_id = fields.Many2one('meli.campaign', u'Campaña', 
        required=True, readonly=True, states={'draft':[('readonly',False)]}, ondelete="restrict")
    pricelist_id = fields.Many2one('product.pricelist', u'Tarifa de Venta',
        required=True, ondelete="restrict")
    name = fields.Char(u'Nombre', 
        required=True, readonly=True, states={'draft':[('readonly',False)]})
    description = fields.Text(string=u'Descripcion',
        readonly=True, states={'draft':[('readonly',False)]})
    line_ids = fields.One2many('meli.campaign.record.line', 
        'meli_campaign_id', u'Productos en Oferta', copy=False, auto_join=True)
    state = fields.Selection([
        ('draft','Borrador'),
        ('pending_approval','Enviado a Meli/Esperando Aprobacion'),
        ('published','Publicado en MELI'),
        ('done','Campaña Terminada'),
        ('rejected','Cancelado'),
        ], string=u'Estado', index=True, readonly=True, default = u'draft', )


    def action_set_products(self):
        self.ensure_one()
        wizard_model = self.env['wizard.set.products.campaign']
        wizard = wizard_model.create({
            'meli_campaign_id': self.id,
            'action_type': self.env.context.get('action_type') or 'set',
        })
        action = self.env.ref('meli_oerp.action_wizard_set_products_campaign').read()[0]
        action['res_id'] = wizard.id
        return action


    def action_publish_to_meli(self):
        self.ensure_one()
        warning_model = self.env['warning']
        messages = self.line_ids.filtered(lambda x: x.state == 'draft').action_publish_to_meli()
        state = 'published'
        #si algun producto se quedo esperando aprobacion,
        #el estado general sera esperando aprobacion de Meli
        if self.line_ids.filtered(lambda x: x.state == 'pending_approval'):
            state = 'pending_approval'
        if messages:
            return warning_model.info(title='Ofertas', message=u"\n".join(messages))
        self.state = state
        return True


    def action_done_publish(self):
        self.mapped('line_ids').filtered(lambda x: x.state != 'rejected').write({'state': 'done'})
        self.write({'state': 'done'})
        return True


    def action_cancel_publish(self):
        self.ensure_one()
        warning_model = self.env['warning']
        messages = self.line_ids.filtered(lambda x: x.state != 'rejected').action_unpublish_to_meli()
        if messages:
            return warning_model.info(title='Cancelar Oferta', message=u"\n".join(messages))
        self.write({'state': 'rejected'})
        return True


    def action_recompute_prices(self):
        self.ensure_one()
        #pasar la lista de precios y actualizar los precios
        for line in self.with_context(pricelist=self.pricelist_id.id).line_ids:
            line.write({
                'price_unit': line.product_template_id.list_price,
                'list_price': line.product_template_id.price,
                'meli_price': line.product_template_id.price,
            })
        return True


    def action_update_prices_to_meli(self):
        warning_model = self.env['warning']
        #los nuevos productos publicarlos
        messages = self.mapped('line_ids').filtered(lambda x: x.state == 'draft').action_publish_to_meli()
        #actualizar todas las lineas que esten activas
        messages.extend(self.mapped('line_ids').filtered(lambda x: x.state in ('pending_approval', 'published')).action_update_to_meli())
        if messages:
            return warning_model.info(title='Actualizar Ofertas', message=u"\n".join(messages))
        return True


    def unlink(self):
        for campaign in self:
            if campaign.state not in ('draft',):
                raise UserError(u"No puede Eliminar esta Campaña, intente cancelarla")
        res = super(MeliCampaignRecord, self).unlink()
        return res

class MeliCampaignRecordLine(models.Model):

    _name = 'meli.campaign.record.line'
    _description = u'Productos o Ofertar en Campañas'

    meli_campaign_id = fields.Many2one('meli.campaign.record',
        u'Registro de Campaña', ondelete="cascade", auto_join=True)
    product_template_id = fields.Many2one('product.template',
        u'Plantilla de Producto', ondelete="restrict", auto_join=True)
    price_unit = fields.Float(u'Precio Unitario', digits=dp.get_precision('Product Price'))
    list_price = fields.Float(u'Precio Unitario(Tarifa)', digits=dp.get_precision('Product Price'))
    meli_price = fields.Float(u'Precio Unitario(MELI)', digits=dp.get_precision('Product Price'))
    declared_free_shipping = fields.Boolean(u'Envio Gratis?')
    declared_oro_premium_full = fields.Boolean(u'Premium?')
    declared_stock = fields.Float(u'Stock Declarado', digits=dp.get_precision('Product Unit of Measure'))
    review_reasons_ids = fields.One2many('meli.campaign.record.review.reason',
        'meli_campaign_line_id', u'Razones de Revision', readonly=True, copy=False, auto_join=True)
    state = fields.Selection([
        ('draft','Borrador'),
        ('pending_approval', 'Enviado a Meli/Esperando Aprobacion'),
        ('published','Publicado en MELI'),
        ('done','Campaña Terminada'),
        ('rejected','Cancelado'),
        ], string=u'Estado', default = u'draft')


    def action_publish_to_meli(self):
        meli_util_model = self.env['meli.util']
        company = self.env.user.company_id
        meli = meli_util_model.get_new_instance()
        params = {'access_token': meli.access_token}
        messages = []
        msj = ""
        for line in self:
            post_data = {
                'item_id': line.product_template_id.meli_id,
                'deal_price': line.meli_price,
                'regular_price': line.price_unit,
                'declared_free_shipping': line.declared_free_shipping,
                'declared_oro_premium_full': line.declared_oro_premium_full,
            }
            url = "/users/%s/deals/%s/proposed_items" % (company.mercadolibre_seller_id, line.meli_campaign_id.campaign_id.meli_id)
            response = meli.post(url, post_data, params)
            rjson = response.json()
            if rjson.get('error'):
                msj = rjson.get('message') or "Error Publicando Oferta"
                messages.append("%s. Producto ID: %s" % (msj, line.product_template_id.meli_id))
                continue
            vals_line = {
                'state':  rjson.get('status'),
            }
            review_reason = []
            for review in rjson.get('review_reasons', []):
                review_reason.append((0, 0, {
                    'reason_type': review.get('reason_type', ''),
                    'reason_requisite': (review.get('requisite') or {}).get('name', ''),
                    'message_key': review.get('message_key', ''),
                    }))
            if vals_line:
                line.write(vals_line)
        return messages


    def action_unpublish_to_meli(self):
        meli_util_model = self.env['meli.util']
        company = self.env.user.company_id
        meli = meli_util_model.get_new_instance()
        params = {'access_token': meli.access_token}
        messages = []
        #los productos publicados en meli enviar a cancelarlos
        #los que no han sido publicados, solo cambiarle el estado
        lines_unpublish = self.filtered(lambda x: x.state in ('pending_approval', 'published', 'done'))
        lines_cancel = self - lines_unpublish
        if lines_cancel:
            lines_cancel.write({'state': 'rejected'})
        for line in lines_unpublish:
            url = "/users/%s/deals/%s/proposed_items/%s" % (company.mercadolibre_seller_id, line.meli_campaign_id.campaign_id.meli_id, line.product_template_id.meli_id)
            response = meli.delete(url, params)
            rjson = response.json()
            if rjson.get('error'):
                msj = rjson.get('message') or "Error Eliminando Oferta"
                messages.append("%s. Producto ID: %s" % (msj, line.product_template_id.meli_id))
                continue
            vals_line = {
                'state':  rjson.get('status'),
            }
            if vals_line:
                line.write(vals_line)
        return messages


    def action_update_to_meli(self):
        meli_util_model = self.env['meli.util']
        company = self.env.user.company_id
        meli = meli_util_model.get_new_instance()
        params = {'access_token': meli.access_token}
        messages = []
        for line in self:
            post_data = {
                'deal_price': line.meli_price,
                'declared_free_shipping': line.declared_free_shipping,
                'declared_oro_premium_full': line.declared_oro_premium_full,
            }
            url = "/users/%s/deals/%s/proposed_items/%s" % (company.mercadolibre_seller_id, line.meli_campaign_id.campaign_id.meli_id, line.product_template_id.meli_id)
            response = meli.put(url, post_data, params)
            rjson = response.json()
            if rjson.get('error'):
                msj = rjson.get('message') or "Error Actualizando Oferta"
                messages.append("%s. Producto ID: %s" % (msj, line.product_template_id.meli_id))
                continue
        return messages

class MeliCampaignRecordRevisionReason(models.Model):

    _name = 'meli.campaign.record.review.reason'
    _description = u'Razones de Revision en Ofertas'

    meli_campaign_line_id = fields.Many2one('meli.campaign.record.line',
        u'Producto en Oferta', ondelete="cascade", auto_join=True)
    reason_type = fields.Char(u'Tipo de Razon')
    reason_requisite = fields.Char(u'Requisito')
    message_key = fields.Char(u'Mensaje')
    
