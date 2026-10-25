# Test #529/#543 (descuento del vendedor doble, IVA de todas las compañias, `auto`, 401) —
# `odoo shell -d <db_de_prueba> < este_archivo`. Bloquea la red y hace ROLLBACK. NO correr contra produccion.
env = globals()["env"]  # lo inyecta `odoo shell`: declarado para el lint de Odoo (undefined-variable)
import requests
requests.Session.request = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("RED BLOQUEADA"))
R = []
def check(n, c):
    R.append((n, bool(c))); print(("OK   " if c else "FAIL ") + n)
def fill(model, vals):
    M = env[model]
    for fn, f in M._fields.items():
        if f.required and fn not in vals and f.store and not f.default and not f.compute and not f.related:
            if f.type == 'many2one':
                vals[fn] = env[f.comodel_name].search([], limit=1).id
            elif f.type in ('char', 'text'):
                vals[fn] = 'banco'
            elif f.type == 'selection':
                vals[fn] = f.get_values(env)[0]
    return M.create(vals)
def tax(name, comp, amount=21.0):
    vals = {'name': name, 'amount': amount, 'amount_type': 'percent', 'type_tax_use': 'sale',
            'company_id': comp.id, 'price_include': False}
    if 'price_include_override' in env['account.tax']._fields:
        vals.pop('price_include'); vals['price_include_override'] = 'tax_excluded'
    if 'country_id' in env['account.tax']._fields and not comp.country_id:
        comp.country_id = env.ref('base.ar')
    if 'country_id' in env['account.tax']._fields:
        vals['country_id'] = comp.country_id.id
    if 'tax_group_id' in env['account.tax']._fields:
        _gc = 'company_id' in env['account.tax.group']._fields
        g = env['account.tax.group'].search([('company_id', '=', comp.id)] if _gc else [], limit=1)
        if not g:
            gv = {'name': 'IVA banco', 'company_id': comp.id} if _gc else {'name': 'IVA banco'}
            if 'country_id' in env['account.tax.group']._fields: gv['country_id'] = comp.country_id.id
            g = env['account.tax.group'].sudo().create(gv)
        vals['tax_group_id'] = g.id
    return env['account.tax'].with_company(comp).create(vals)
class _Resp:
    def __init__(self, data): self.data = data
    def json(self): return self.data
class _M:
    access_token = 'x'
    def __init__(self, data): self.data = data
    def get(self, *a, **k): return _Resp(self.data)

from odoo.addons.meli_oerp.models import versions as V
A = env.company
B = env['res.company'].create({'name': 'Cia B banco 529', 'currency_id': A.currency_id.id, 'country_id': (A.country_id or env.ref('base.ar')).id})
env.user.company_ids = [(4, B.id)]
tA = tax('IVA 21 A banco', A); tB = tax('IVA 21 B banco', B)
prod = env['product.product'].create({'name': 'Prod banco 529', 'list_price': 100.0})
prod.product_tmpl_id.sudo().write({'taxes_id': [(6, 0, [tA.id, tB.id])]})
prod_notax = env['product.product'].create({'name': 'Prod sin IVA banco 529'})
prod_notax.product_tmpl_id.sudo().write({'taxes_id': [(5, 0, 0)]})

# --- Bug 3: descuento del vendedor (payload real de la orden Kindon 2000019046887762) ---
KINDON = {'details': [
    {'type': 'discount', 'items': [{'id': 'MLA1', 'quantity': 1, 'amounts': {'total': 687.5, 'seller': 687.5}}],
     'supplier': {'funding_mode': 'seller'}},
    {'type': 'coupon', 'coupon': {'id': 1}, 'items': [{'id': 'MLA1', 'quantity': 1, 'amounts': {'total': 2062.5, 'seller': 0.0}}]}]}
order = fill('mercadolibre.orders', {'order_id': 'T529A', 'name': 'T529A', 'coupon_amount': 2062.5})
order._fetch_order_discounts(meli=_M(KINDON))
check('B3-1 Kindon: la oferta de precio (type discount, ya en unit_price) NO cuenta como descuento a restar',
      abs(order.discount_seller_amount - 0.0) < 0.01)
COUPON_SELLER = {'details': [{'type': 'coupon', 'coupon': {'id': 2}, 'items': [{'id': 'MLM1', 'quantity': 2, 'amounts': {'seller': 118.9, 'total': 118.9}}]}]}
order2 = fill('mercadolibre.orders', {'order_id': 'T529B', 'name': 'T529B', 'coupon_amount': 118.9})
order2._fetch_order_discounts(meli=_M(COUPON_SELLER))
check('B3-2 cupon financiado por el vendedor SIGUE contando (no esta en unit_price)', abs(order2.discount_seller_amount - 118.9) < 0.01)

Item = {'unit_price': 54312.5, 'quantity': 1, 'item': {'id': 'MLA1'}}
pu = order._set_product_unit_price(prod, Item, config=A)['price_unit']
check('B3-3 Kindon: price_unit neto x 1,21 = 54.312,50 (precio ML), no 53.625 (%.2f)' % (pu * 1.21), abs(pu * 1.21 - 54312.5) < 0.05)

# prorrateo: orden de 2 items (1000 y 3000), descuento del vendedor 400 => 100 y 300
o3 = fill('mercadolibre.orders', {'order_id': 'T529C', 'name': 'T529C', 'discount_seller_amount': 400.0})
for uid, up in (('I1', 1000.0), ('I2', 3000.0)):
    fill('mercadolibre.order_items', {'order_id': o3.id, 'order_item_id': uid, 'unit_price': str(up), 'quantity': 1})
_it = {'items_total': 4000.0} if 'items_total' in o3._set_product_unit_price.__code__.co_varnames else {}  # 26.229: el llamador pasa el bruto de la orden
p1 = o3._set_product_unit_price(prod_notax, {'unit_price': 1000.0, 'quantity': 1}, config=A, **_it)['price_unit']
p2 = o3._set_product_unit_price(prod_notax, {'unit_price': 3000.0, 'quantity': 1}, config=A, **_it)['price_unit']
check('B3-4 prorrateo: 900 + 2700 = 3600 (antes 600 + 2600 = 3200: el descuento entraba dos veces) [%.2f, %.2f]' % (p1, p2),
      abs(p1 - 900) < 0.01 and abs(p2 - 2700) < 0.01)

# --- Bug 6: impuestos de una sola compañia ---
rates = getattr(V, 'ml_sale_tax_rates', None)
check('B6-1 ml_sale_tax_rates(cia A) = 21 % (no 42 %)', rates is not None and rates(prod.product_tmpl_id.taxes_id, A)[0] == 21.0)
A.mercadolibre_tax_included = 'tax_excluded'
conv = prod._meli_price_converted(meli_price=121.0, config=A)
check('B6-2 importar precio ML 121 con tax_excluded => 100 (no 85,21) [%.2f]' % conv, abs(conv - 100.0) < 0.01)

# --- Bug 5: `auto` determinista ---
A.mercadolibre_tax_included = 'auto'
grp = env.ref('account.group_show_line_subtotals_tax_excluded', raise_if_not_found=False)
exp = env.user.has_group('account.group_show_line_subtotals_tax_excluded') if grp else False
got = V.ml_tax_excluded(prod, config=A)
check('B5-1 auto: grupo %s => %s (sin cambiar el significado)' % ('existe' if grp else 'NO existe (17+)', exp), got == exp)
A.mercadolibre_tax_included = 'tax_included'
check('B5-2 tax_included explicito => False', V.ml_tax_excluded(prod, config=A) is False)

# --- Bug 2: 401 de ML ---
from odoo.addons.meli_oerp.models import meli_util as MU
f = getattr(MU, 'meli_is_auth_error', None)
check('B2-1 401 {"code":"unauthorized","message":"invalid access token"} es error de token',
      f is not None and f({'code': 'unauthorized', 'message': 'invalid access token'}))
check('B2-2 respuesta normal de /orders/search NO es error de token',
      f is not None and not f({'results': [], 'paging': {'total': 0}}))
check('B2-3 429 / not_found NO son error de token',
      f is not None and not f({'status': 429, 'message': 'too many requests'}) and not f({'error': 'not_found', 'status': 404}))

env.cr.rollback()
print('TOTAL', len(R), 'FAIL', len([1 for _n, ok in R if not ok]), [n for n, ok in R if not ok])
