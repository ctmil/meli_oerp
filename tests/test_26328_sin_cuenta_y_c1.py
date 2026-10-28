# -*- coding: utf-8 -*-
"""26.328 (PLAN-2026-10-28-meli-warnings): sin cuenta ML conectada, abrir la UI dejaba en el log
`GET /sites: Auth error status=403` (12 por recorrido): _get_ML_sites consultaba /sites con token vacio.
Y C-1: NameError latentes (variables inexistentes) en caminos de company/category/product/versions.
Sin red: cliente ML simulado.
"""
from odoo.tests import TransactionCase, tagged


class _Resp:
    def __init__(self, data):
        self._d = data
        self.rjson = data

    def json(self):
        return self._d


class _Meli:
    seller_id = '123'

    def __init__(self, token, routes=None):
        self.access_token = token
        self.routes = routes or {}
        self.calls = []

    def get(self, path, params=None, **kw):
        self.calls.append(path)
        for k, v in self.routes.items():
            if path.startswith(k):
                return _Resp(v)
        return _Resp({})

    def need_login(self):
        return False

    def auth_url(self):
        return 'https://auth.example/login'


@tagged('post_install', '-at_install', 'meli', 'meli_26328')
class TestSinCuentaYC1(TransactionCase):

    def test_sites_sin_token_no_consulta_ml(self):
        company = self.env.company
        for token in ('', False, 'PASIVA'):
            meli = _Meli(token)
            company._get_ML_sites(meli=meli)
            self.assertEqual(meli.calls, [], "sin token no se llama a /sites (403 + WARNING en el log)")

    def test_sites_con_token_sigue_consultando(self):
        meli = _Meli('APP_USR-1-123', {'/sites': [{'id': 'MLA', 'default_currency_id': 'ARS'}]})
        self.env.company._get_ML_sites(meli=meli)
        self.assertEqual(meli.calls, ['/sites'])

    def test_c1_currencies(self):
        meli = _Meli('APP_USR-1-123', {'/currencies': [{'id': 'ARS', 'description': 'Peso'}]})
        util = self.env['meli.util']
        orig = type(util).get_new_instance
        type(util).get_new_instance = lambda self, *a, **k: meli
        try:
            self.assertEqual(self.env.company._get_ML_currencies(), [('ARS', 'Peso')])
        finally:
            type(util).get_new_instance = orig

    def test_c1_fetch_list_token_invalido_no_borra_tokens(self):
        company = self.env.company
        company.write({'mercadolibre_access_token': 'TOK-123', 'mercadolibre_refresh_token': 'RT',
                       'mercadolibre_seller_id': '123'})
        seq = [{'results': [], 'paging': {'total': 500}, 'scroll_id': 'S1'},
               {'error': 'x', 'message': 'invalid_token'}]
        meli = _Meli('TOK-123')
        meli.get = lambda path, params=None, **kw: _Resp(seq.pop(0))
        # el ERROR del token invalido es el log esperado del escenario: se verifica y no ensucia el log del build
        with self.assertLogs('odoo.addons.meli_oerp.models.company', level='ERROR') as logs:
            res = company.fetch_list_meli_ids(meli=meli)
        self.assertTrue(any('invalid_token' in m for m in logs.output), logs.output)
        self.assertEqual(res.get('type'), 'ir.actions.act_url')
        self.assertEqual(company.mercadolibre_refresh_token, 'RT')

    def test_c1_existing_sku_recorre_todos(self):
        prods = self.env['product.product'].create([{'name': 'P%s' % i, 'default_code': 'SKU-C1-%s' % i} for i in range(2)])
        meli = _Meli('TOK-123', {'/users/': {'results': []}})
        util = self.env['meli.util']
        orig = type(util).get_new_instance
        type(util).get_new_instance = lambda self, *a, **k: meli
        company_cls = type(self.env.company)
        orig_rate = company_cls.MELI_SKU_RATE_LIMIT
        company_cls.MELI_SKU_RATE_LIMIT = 0
        try:
            self.env.company.get_all_items_from_existing_sku(prods)
        finally:
            type(util).get_new_instance = orig
            company_cls.MELI_SKU_RATE_LIMIT = orig_rate
        self.assertEqual(len(meli.calls), 2)

    def test_c1_set_meli_price_precio_fijo_menor_a_uno(self):
        p = self.env['product.product'].create({'name': 'Precio C1'})
        p.product_tmpl_id.write({'meli_price': '7'})
        p.write({'meli_price_fixed': True, 'meli_price': '0.5'})
        p.set_meli_price()  # antes: NameError product_tmpl_id

    def test_c1_stock_inventory_action_done(self):
        from odoo.addons.meli_oerp.models.versions import stock_inventory_action_done
        vals = {'name': 'Stock C1'}
        if 'is_storable' in self.env['product.product']._fields:
            vals.update(type='consu', is_storable=True)
        else:
            vals.update(type='product')
        p = self.env['product.product'].create(vals)
        stock_inventory_action_done(p, product=p, stock=11, config=self.env.company)
        self.assertEqual(p.with_context(warehouse_id=False).qty_available, 11)

    def test_c1_meli_get_category_enlaza_sitio(self):
        if 'product.public.category' not in self.env:
            self.skipTest('sin website_sale')
        cat = self.env['mercadolibre.category'].create({'name': 'C1', 'meli_category_id': 'MLA_C1_TEST'})
        pub = self.env['product.public.category'].create({'name': 'C1 sitio'})
        cls = type(self.env['mercadolibre.category'])
        orig = cls.create_ecommerce_category
        cls.create_ecommerce_category = lambda self, **k: pub.id
        try:
            self.env['mercadolibre.category'].meli_get_category('MLA_C1_TEST', meli=_Meli('TOK'))
        finally:
            cls.create_ecommerce_category = orig
        self.assertEqual(cat.public_category, pub)
