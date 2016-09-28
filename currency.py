
from openerp import models, fields, api, _

class res_currency(models.Model):
    _inherit = 'res.currency'

    @api.one
    @api.onchange('rate') # if these fields are changed, call method
    def check_change_rate(self):
        import pdb;pdb.set_trace();
        self.update_prices()

    @api.model
    def update_prices(self):
        # Moneda en USD
        currency_obj = self.pool.get('res.currency')
        currency_usd = currency_obj.search(['name','=','USD'])
        products = self.env['product.product'].search([])
        for product in products:
            if product.list_price > 0 and currency_usd.rate>0:
                   product.meli_price = product.list_price / currency_usd.rate


res_currency()


class res_currency_rate(models.Model):
    _inherit = 'res.currency.rate'

    @api.one
    @api.onchange('rate') # if these fields are changed, call method
    def check_change_rate(self):
        import pdb;pdb.set_trace();
        self.update_prices()

    @api.model
    def update_prices(self):
        # Moneda en USD
        #currency_obj = self.pool.get('res.currency')
        currency_usd = self.env['res.currency'].search(['name','=','USD'], context)
        products = self.env['product.product'].search([])
        for product in products:
            if product.list_price > 0 and currency_usd.rate>0:
                   product.meli_price = product.list_price / currency_usd.rate.rate


res_currency_rate()

