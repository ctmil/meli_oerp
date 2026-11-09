# -*- coding: utf-8 -*-
"""26.385 (PLAN-2026-11-09-meli-credenciales-visibles, pedido MINT): un admin SIN modo desarrollador
tiene que poder conectar la versión Base desde Compañía > MercadoLibre.
Antes: App Id / Redirect Uri / Vendedor Id con groups=base.group_no_one (sólo modo dev), el login nunca
completaba el Vendedor Id (y sin él get_new_instance queda en 'necesita login'), y get_url_meli_login
usaba 'company' sin definir. Sin red: cliente ML simulado.
"""
from odoo.tests import TransactionCase, tagged


class _Meli:
    def __init__(self, token='APP_USR-1234-110926-abc-777001', refresh='TG-REFRESH'):
        self.access_token = token
        self.refresh_token = refresh
        self.redirect_uri = None

    def auth_url(self, redirect_URI=None):
        if redirect_URI:
            self.redirect_uri = redirect_URI
        return 'https://auth.example/authorization?redirect_uri=%s' % (self.redirect_uri or '')

    def redirect_login(self):
        return {'type': 'ir.actions.act_url', 'url': self.auth_url(), 'target': 'self'}


@tagged('post_install', '-at_install', 'meli', 'meli_26385')
class TestCredencialesVisibles(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.company.write({'mercadolibre_seller_id': False, 'mercadolibre_redirect_uri': False})

    def _patch_instance(self, meli):
        util = type(self.env['meli.util'])
        orig = util.get_new_instance
        util.get_new_instance = lambda s, *a, **k: meli
        self.addCleanup(setattr, util, 'get_new_instance', orig)

    def test_vista_admin_sin_modo_dev_ve_credenciales(self):
        admin = self.env.ref('base.user_admin')
        view = self.env.ref('base.view_company_form')
        arch = self.env['res.company'].with_user(admin).get_view(view_id=view.id, view_type='form')['arch']
        # control: lo que ya se veía sigue viéndose (prueba que el filtro por grupos actuó)
        self.assertIn('name="mercadolibre_secret_key"', arch)
        for fname in ('mercadolibre_client_id', 'mercadolibre_redirect_uri', 'mercadolibre_seller_id',
                      'mercadolibre_redirect_uri_suggested'):
            self.assertIn('name="%s"' % fname, arch, "%s oculto sin modo desarrollador" % fname)

    def test_redirect_sugerida(self):
        expected = self.company.get_base_url().rstrip('/') + '/meli_login'
        self.assertEqual(self.company._meli_suggested_redirect_uri(), expected)
        self.assertEqual(self.company.mercadolibre_redirect_uri_suggested, expected)

    def test_login_completa_redirect_vacia(self):
        meli = _Meli()
        self._patch_instance(meli)
        res = self.company.meli_login()
        expected = self.company._meli_suggested_redirect_uri()
        self.assertEqual(self.company.mercadolibre_redirect_uri, expected)
        self.assertEqual(res.get('type'), 'ir.actions.act_url')

    def test_login_no_pisa_redirect_cargada(self):
        self.company.mercadolibre_redirect_uri = 'https://otro.example.com/meli_login'
        self._patch_instance(_Meli())
        self.company.meli_login()
        self.assertEqual(self.company.mercadolibre_redirect_uri, 'https://otro.example.com/meli_login')

    def test_store_login_completa_vendedor_desde_respuesta(self):
        meli = _Meli()
        self.company._meli_store_login({'access_token': meli.access_token, 'user_id': 777001}, 'TG-CODE', meli)
        self.assertEqual(self.company.mercadolibre_seller_id, '777001')
        self.assertEqual(self.company.mercadolibre_access_token, meli.access_token)
        self.assertEqual(self.company.mercadolibre_refresh_token, 'TG-REFRESH')
        self.assertTrue(self.company.mercadolibre_cron_refresh)

    def test_store_login_vendedor_desde_token_si_no_viene_user_id(self):
        meli = _Meli(token='APP_USR-1234-110926-abc-888002')
        self.company._meli_store_login({'access_token': meli.access_token}, 'TG-CODE', meli)
        self.assertEqual(self.company.mercadolibre_seller_id, '888002')

    def test_store_login_no_pisa_vendedor(self):
        self.company.mercadolibre_seller_id = '555'
        meli = _Meli()
        with self.assertLogs('odoo.addons.meli_oerp.models.company', level='WARNING'):
            self.company._meli_store_login({'user_id': 777001}, 'TG-CODE', meli)
        self.assertEqual(self.company.mercadolibre_seller_id, '555')

    def test_get_url_meli_login_sin_company(self):
        self.company.mercadolibre_redirect_uri = 'https://cliente.example.com/meli_login'
        res = self.env['meli.util'].get_url_meli_login(_Meli())
        self.assertIn('https://cliente.example.com/meli_login', res['url'])
