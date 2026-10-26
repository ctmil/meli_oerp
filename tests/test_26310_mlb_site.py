# -*- coding: utf-8 -*-
"""Brasil A / A4 (26.310): una empresa de Brasil SIN 'Moneda predeterminada' de ML cargada caia en
el sitio MLA (_get_ML_sites terminaba en `return "MLA"`): el login iba a auth.mercadolibre.com.ar y los
links a mercadolibre.com.ar. Ahora el fallback usa el pais de la compania (MELI_COUNTRY_SITE).
Sin red: el cliente ML simulado no devuelve /sites.
"""
from odoo.tests import TransactionCase, tagged


class _MeliSinSites:
    access_token = 'TEST'

    def get(self, path, params=None):
        return None


@tagged('post_install', '-at_install', 'meli', 'meli_26310')
class TestMLBSite26310(TransactionCase):

    def _company(self, country_xmlid, currency=False):
        company = self.env.user.company_id
        company.country_id = self.env.ref(country_xmlid)
        company.mercadolibre_currency = currency
        return company

    def test_brasil_sin_moneda_es_mlb(self):
        company = self._company('base.br')
        meli = _MeliSinSites()
        self.assertEqual(company._get_ML_sites(meli=meli), 'MLB')
        self.assertIn('mercadolivre.com.br', company.get_ML_AUTH_URL(meli=meli))

    def test_argentina_sin_moneda_sigue_mla(self):
        company = self._company('base.ar')
        self.assertEqual(company._get_ML_sites(meli=_MeliSinSites()), 'MLA')

    def test_moneda_configurada_manda(self):
        company = self._company('base.br', 'ARS')
        self.assertEqual(company._get_ML_sites(meli=_MeliSinSites()), 'MLA')
