# -*- coding: utf-8 -*-
"""#153 (26.347): comprador AR sin documento en billing_info ⇒ Consumidor Final + 'Sigd'.

Sin documento la factura va al contacto principal, creado sin datos fiscales (tipo 'VAT',
responsabilidad vacía) ⇒ ARCA rechaza la factura. El helper le pone CF + Sigd; un contacto con
DNI/CUIT o con responsabilidad cargada no se toca, y fuera de AR no hace nada.
"""
from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestCfSinDoc(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.res_cf = cls.env.ref('l10n_ar.res_CF', raise_if_not_found=False)
        cls.it_sigd = cls.env.ref('l10n_ar.it_Sigd', raise_if_not_found=False)
        cls.it_dni = cls.env.ref('l10n_ar.it_dni', raise_if_not_found=False)
        cls.it_cuit = cls.env.ref('l10n_ar.it_cuit', raise_if_not_found=False)
        cls.res_ri = cls.env.ref('l10n_ar.res_IVARI', raise_if_not_found=False)
        cls.it_vat = cls.env.ref('l10n_latam_base.it_vat', raise_if_not_found=False)
        cls.orders = cls.env['mercadolibre.orders']
        cls.co_ar = cls.env['res.company'].create({
            'name': 'MELI AR 153', 'country_id': cls.env.ref('base.ar').id})
        cls.co_mx = cls.env['res.company'].create({
            'name': 'MELI MX 153', 'country_id': cls.env.ref('base.mx').id})

    def setUp(self):
        super().setUp()
        if not (self.res_cf and self.it_sigd):
            self.skipTest('l10n_ar no instalado')

    def _buyer(self, **vals):
        v = {'name': 'Comprador ML sin doc'}
        if self.it_vat:
            v['l10n_latam_identification_type_id'] = self.it_vat.id
        v.update(vals)
        return self.env['res.partner'].create(v)

    def test_sin_documento_queda_cf_sigd(self):
        p = self._buyer()
        self.assertFalse(p.l10n_ar_afip_responsibility_type_id)
        self.assertTrue(self.orders._meli_ar_default_consumidor_final(p, self.co_ar))
        self.assertEqual(p.l10n_ar_afip_responsibility_type_id, self.res_cf)
        self.assertEqual(p.l10n_latam_identification_type_id, self.it_sigd)
        # idempotente
        self.assertFalse(self.orders._meli_ar_default_consumidor_final(p, self.co_ar))

    def test_con_dni_no_se_toca(self):
        p = self._buyer(l10n_latam_identification_type_id=self.it_dni.id, vat='30123456')
        self.assertFalse(self.orders._meli_ar_default_consumidor_final(p, self.co_ar))
        self.assertFalse(p.l10n_ar_afip_responsibility_type_id)
        self.assertEqual(p.l10n_latam_identification_type_id, self.it_dni)
        self.assertEqual(p.vat, '30123456')

    def test_con_cuit_no_se_toca(self):
        p = self._buyer(l10n_latam_identification_type_id=self.it_cuit.id, vat='20123456786',
                        l10n_ar_afip_responsibility_type_id=self.res_ri.id)
        self.assertFalse(self.orders._meli_ar_default_consumidor_final(p, self.co_ar))
        self.assertEqual(p.l10n_ar_afip_responsibility_type_id, self.res_ri)
        self.assertEqual(p.l10n_latam_identification_type_id, self.it_cuit)

    def test_con_responsabilidad_sin_vat_no_se_toca(self):
        p = self._buyer(l10n_ar_afip_responsibility_type_id=self.res_ri.id)
        self.assertFalse(self.orders._meli_ar_default_consumidor_final(p, self.co_ar))
        self.assertEqual(p.l10n_ar_afip_responsibility_type_id, self.res_ri)

    def test_fuera_de_ar_no_hace_nada(self):
        p = self._buyer()
        self.assertFalse(self.orders._meli_ar_default_consumidor_final(p, self.co_mx))
        self.assertFalse(p.l10n_ar_afip_responsibility_type_id)

    def test_contacto_hijo_escribe_en_el_comercial(self):
        parent = self._buyer(name='Comprador padre')
        child = self.env['res.partner'].create({'name': 'Hijo', 'parent_id': parent.id, 'type': 'invoice'})
        self.assertTrue(self.orders._meli_ar_default_consumidor_final(child, self.co_ar))
        self.assertEqual(parent.l10n_ar_afip_responsibility_type_id, self.res_cf)
