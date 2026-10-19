# -*- coding: utf-8 -*-
"""Casos de la regla de match de SKU por TOKEN (#543) — SIN Odoo.

Correr:  python3 meli_oerp/tests/test_sku_token_pure.py   (desde la raiz de addons)
NO esta en tests/__init__.py a proposito: carga models/sku_token.py por ruta para no
importar el paquete del modulo (que importa odoo). Integracion con Odoo (helpers ORM,
import, binding, ventas, opcion apagada = identico): meli_oerp_multiple/tests/shell_sku_token_match.py.
"""
import importlib.util
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "meli_sku_token", os.path.join(_HERE, "..", "models", "sku_token.py"))
st = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(st)

CATALOG = {'21342': ['P1'], '21170': ['P2'], '3': ['P3'], '4011030': ['P4'],
           'CBPSR001': ['P5', 'P6']}  # CBPSR001 repetido en Odoo


def lookup(tok):
    return CATALOG.get(tok.upper(), [])


class TestSkuTokens(unittest.TestCase):

    def test_tokens(self):
        self.assertEqual(st.meli_sku_tokens('21342-ALIMENTO  PERRO/20K'), ['21342', 'ALIMENTO', 'PERRO', '20K'])
        self.assertEqual(st.meli_sku_tokens('21342'), [])            # sin separador: ya lo cubre el exacto
        self.assertEqual(st.meli_sku_tokens('A-B', ''), ['A', 'B'])   # vacio = default '- /'
        self.assertEqual(st.meli_sku_tokens('A|B-C', '|'), ['A', 'B-C'])
        self.assertEqual(st.meli_sku_tokens('X-x-X'), [])             # dedup case-insensitive
        self.assertEqual(st.meli_sku_tokens(None), [])
        self.assertEqual(st.meli_sku_tokens(['a-b']), [])
        self.assertEqual(st.like_escape('A_1%'), 'A\\_1\\%')

    def test_pick(self):
        self.assertEqual(st.meli_sku_token_pick('21342-ALIMENTO PERRO 20K', None, lookup), (['P1'], '21342', st.RESULT_OK))
        self.assertEqual(st.meli_sku_token_pick('ALIMENTO CORDERO 3K-21170', None, lookup)[0], ['P2'])
        self.assertEqual(st.meli_sku_token_pick('99999-NADA', None, lookup)[2], st.RESULT_NO_MATCH)
        self.assertEqual(st.meli_sku_token_pick('4011030-ROYAL X 3 KG', None, lookup)[2], st.RESULT_AMBIGUOUS_TOKENS)
        self.assertEqual(st.meli_sku_token_pick('CBPSR001-COMBO', None, lookup)[2], st.RESULT_AMBIGUOUS_PRODUCT)
        self.assertEqual(st.meli_sku_token_pick('21342', None, lookup)[2], st.RESULT_NO_TOKENS)
        self.assertEqual(st.meli_sku_token_pick('cbx-21342', None, lookup)[0], ['P1'])


if __name__ == '__main__':
    unittest.main()
