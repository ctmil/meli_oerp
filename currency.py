
from openerp import models, fields, api, _

class res_currency_rate(models.Model):
    _inherit = 'res.currency.rate'

    @api.one
    @api.onchange('rate') # if these fields are changed, call method
    def check_change_rate(self):
        self.update_prices()

    @api.model
    def update_prices(self):
        products = self.env['product.product'].search([])
        import pdb;pdb.set_trace();
        for product in products:
            if self.rate>0:
                product.meli_price = str(product.lst_price / self.rate)


res_currency_rate()

