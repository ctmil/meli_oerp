# -*- coding: utf-8 -*-
"""26.392 (PLAN-2026-11-10-meli-grupos-categoria-tax-included, pedidos MINT e-learning):
1. Los grupos ML quedan en una categoría (16-18) / privilegio (19+) propio «Mercado Libre», en cadena
   Lector < Encargado, y el form de usuario los muestra como UN selector sin modo desarrollador.
   En 16-18, además, la categoría Ventas vuelve a ser selector (los grupos ML la rompían).
2. «Tax Included» visible para un admin sin modo desarrollador (base.group_system).
3. La Redirect Uri sugerida sale con https si la URL base es http y el host no es local.
"""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'meli', 'meli_26392')
class TestGruposCategoria26392(TransactionCase):

    def setUp(self):
        super().setUp()
        self.reader = self.env.ref('meli_oerp.group_mercadolibre_reader')
        self.manager = self.env.ref('meli_oerp.group_mercadolibre_manager')
        self.privileges = 'privilege_id' in self.env['res.groups']._fields

    def _by_app(self, group):
        for app, kind, gs, category_name in self.env['res.groups'].get_groups_by_application():
            if group in gs:
                return app, kind, gs, category_name
        return None

    def test_01_grupos_en_categoria_propia(self):
        if self.privileges:
            priv = self.env.ref('meli_oerp.res_groups_privilege_mercadolibre')
            self.assertEqual(self.reader.privilege_id, priv)
            self.assertEqual(self.manager.privilege_id, priv)
            self.assertTrue(priv.category_id, "el privilegio necesita categoría para aparecer en el form")
        else:
            cat = self.env.ref('meli_oerp.module_category_mercadolibre')
            self.assertEqual(self.reader.category_id, cat)
            self.assertEqual(self.manager.category_id, cat)

    def test_02_encargado_incluye_lector(self):
        implied = self.manager.trans_implied_ids if 'trans_implied_ids' in self.manager._fields \
            else self.manager.all_implied_ids
        self.assertIn(self.reader, implied)
        gfield = 'group_ids' if 'group_ids' in self.env['res.users']._fields else 'groups_id'
        user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Encargado ML 26392', 'login': 'encargado_ml_26392',
            gfield: [(6, 0, [self.env.ref('base.group_user').id, self.manager.id])]})
        self.assertTrue(user.has_group('meli_oerp.group_mercadolibre_reader'))

    def test_03_form_usuario_selector_sin_modo_dev(self):
        if self.privileges:
            # 19+: el form agrupa por privilegio; un grupo sin privilegio cae en «extra» (sólo modo dev).
            hier = self.env['res.groups']._get_view_group_hierarchy()
            priv = self.env.ref('meli_oerp.res_groups_privilege_mercadolibre')
            self.assertIn(priv.id, hier['privileges'])
            ids = hier['privileges'][priv.id]['group_ids']
            self.assertLess(ids.index(self.reader.id), ids.index(self.manager.id), "Lector antes que Encargado")
            cats = [c for c in hier['categories'] if priv.id in c['privilege_ids']]
            self.assertTrue(cats, "el privilegio no aparece en ninguna sección del form de usuario")
            return
        res = self._by_app(self.reader)
        self.assertTrue(res)
        app, kind, gs, _cat = res
        self.assertEqual(kind, 'selection', "los grupos ML tienen que ser un selector (las casillas son sólo modo dev)")
        self.assertNotIn(app.get_external_id().get(app.id), self.env['res.users']._get_hidden_extra_categories()
                         if hasattr(self.env['res.users'], '_get_hidden_extra_categories') else [])
        self.assertLess(list(gs).index(self.reader), list(gs).index(self.manager))
        sales = self.env.ref('sales_team.group_sale_salesman')
        sres = self._by_app(sales)
        self.assertEqual(sres[1], 'selection', "Ventas dejó de ser selector (grupos ajenos en su categoría)")

    def _assert_raw_group_system(self, model):
        """El nodo del campo en la vista del módulo: group_system, no group_no_one (en 19+ los tests
        corren con group_no_one activo y get_view no discrimina)."""
        from lxml import etree
        views = self.env['ir.ui.view'].search([('model', '=', model), ('arch_db', 'ilike', 'mercadolibre_tax_included')])
        nodes = []
        for v in views:
            nodes += etree.fromstring(v.arch_db.encode()).xpath("//field[@name='mercadolibre_tax_included']")
        self.assertTrue(nodes, "no se encontró el campo en ninguna vista de %s" % model)
        for n in nodes:
            self.assertNotIn('group_no_one', n.get('groups') or '', "Tax Included sigue en modo desarrollador")

    def test_04_tax_included_visible_admin_sin_modo_dev(self):
        self._assert_raw_group_system('res.company')
        admin = self.env.ref('base.user_admin')
        view = self.env.ref('base.view_company_form')
        arch = self.env['res.company'].with_user(admin).get_view(view_id=view.id, view_type='form')['arch']
        self.assertIn('name="mercadolibre_secret_key"', arch)  # control: el filtro por grupos actuó
        self.assertIn('name="mercadolibre_tax_included"', arch, "Tax Included oculto sin modo desarrollador")

    def test_05_redirect_sugerida_https(self):
        from odoo.addons.meli_oerp.models.company import _meli_https_url
        self.assertEqual(_meli_https_url('http://odoo19.example.com'), 'https://odoo19.example.com')
        self.assertEqual(_meli_https_url('http://odoo19.example.com:80'), 'https://odoo19.example.com')
        self.assertEqual(_meli_https_url('http://odoo.example.com:8069/x'), 'https://odoo.example.com:8069/x')
        self.assertEqual(_meli_https_url('https://ya.example.com'), 'https://ya.example.com')
        for local in ('http://localhost:8069', 'http://127.0.0.1:8069', 'http://[::1]:8069'):
            self.assertEqual(_meli_https_url(local), local)
        company = self.env.company
        with patch.object(type(company), 'get_base_url', lambda self: 'http://odoo19.example.com/'):
            self.assertEqual(company._meli_suggested_redirect_uri(), 'https://odoo19.example.com/meli_login')
