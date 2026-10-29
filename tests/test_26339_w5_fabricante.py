# -*- coding: utf-8 -*-
"""26.339 W5 (462 Olpa, capacitación 29-oct-2026): la publicación cortaba con
"faltan atributos obligatorios: Fabricante". Si falta MANUFACTURER se completa con la Marca.
Control (código anterior): el helper no existe => AttributeError.
Correr: odoo-bin ... -u meli_oerp --test-enable --test-tags meli_w5 --stop-after-init
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'meli_w5')
class TestW5Fabricante(TransactionCase):

    def setUp(self):
        super().setUp()
        self.tmpl = self.env['product.template'].create({'name': 'W5 prod', 'meli_brand': 'Olpa'})
        self.prod = self.tmpl.product_variant_ids[:1]

    def test_completa_desde_marca(self):
        attrs, ids = [], {}
        self.assertTrue(self.prod._meli_attr_manufacturer_from_brand(attrs, ids))
        self.assertEqual(attrs, [{'id': 'MANUFACTURER', 'value_name': 'Olpa'}])

    def test_no_pisa_fabricante_cargado(self):
        attrs, ids = [{'id': 'MANUFACTURER', 'value_name': 'X'}], {'MANUFACTURER': 'X'}
        self.assertFalse(self.prod._meli_attr_manufacturer_from_brand(attrs, ids))
        self.assertEqual(len(attrs), 1)

    def test_sin_marca_no_agrega(self):
        self.tmpl.meli_brand = False
        attrs, ids = [], {}
        self.assertFalse(self.prod._meli_attr_manufacturer_from_brand(attrs, ids))
        self.assertEqual(attrs, [])
