
from odoo import models, fields, api
from odoo.tools.translate import _
import math

class res_currency_rate(models.Model):
    _inherit = 'res.currency.rate'


    @api.onchange('rate') # if these fields are changed, call method
    def check_change_rate(self):
        self.update_prices()

    @api.model
    def update_prices(self):
        #import pdb;pdb.set_trace();
        products = self.env['product.product'].search([])

        pricelists = self.env['product.pricelist'].search([])
        #pricelist = pricelists[0]
        for pricelist in pricelists:
            if self.currency_id.name == pricelist.currency_id.name:
                for product in products:
                    if self.rate>0 and not product.meli_price_fixed:
                        new_price = math.ceil( product.lst_price / self.rate )
                        vals = {
                            'meli_price': str(new_price)
                        }
                        product.write(vals)
                        product.product_post()


res_currency_rate()
