


class res_currency(models.Model):
    _inherit = 'res.currency'

    @api.model
    def update_prices(self):
        # Moneda en USD
        currency_usd = res.env['res.currency].search([('name','=','USD')])
        products = self.env['product.product'].search([])
        for product in products:
            if product.list_price > 0:
                   product.meli_price = product_list_price / currency.silent_rate

    @api.onchange('silent_rate') # if these fields are changed, call method
    def check_change(self):
        self.update_prices()
