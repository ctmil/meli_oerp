# -*- coding: utf-8 -*-
"""get_billing_info: el endpoint NUEVO de datos fiscales se usa cuando responde 200 — SIN Odoo.

Correr:  python3 meli_oerp/tests/test_billing_info_endpoint_pure.py   (NO esta en tests/__init__.py)
Carga por AST SOLO get_billing_info y _normalize_billing_info_v2 de models/orders.py (no importa odoo).
ORDERS_PY=<ruta> permite apuntarlo a otra copia (p.ej. el codigo previo al fix).

Bug (26.289): se decidia por getattr(response,'status_code') pero meli.get() devuelve el propio
cliente (sin status_code) => siempre 0 => siempre el endpoint viejo /orders/<id>/billing_info.
El FakeMeli replica el contrato real: get() -> self, json() -> rjson, error HTTP = dict con error/status.
"""
import ast
import logging
import os
import textwrap
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PATH = os.environ.get("ORDERS_PY") or os.path.join(_HERE, "..", "models", "orders.py")
_WANTED = ("get_billing_info", "_normalize_billing_info_v2")


def _load():
    src = open(_PATH, encoding="utf-8").read()
    tree = ast.parse(src)
    lines = src.splitlines()
    ns = {"_logger": logging.getLogger("test_billing_info")}
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in _WANTED and node.name not in found:
            found.add(node.name)
            code = textwrap.dedent("\n".join(lines[node.lineno - 1:node.end_lineno]))
            exec(compile(code, "orders.py:%s" % node.name, "exec"), ns)
    assert found == set(_WANTED), found
    return ns


NS = _load()


class FakeSelf(object):
    order_id = None
    get_billing_info = NS["get_billing_info"]
    _normalize_billing_info_v2 = NS["_normalize_billing_info_v2"]


class FakeMeli(object):
    """Contrato de MeliApiNoSDK: get() devuelve self; sin atributo status_code."""
    access_token = "tok"

    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self.rjson = None

    def get(self, path, params=None, extra_headers=None, **kw):
        self.calls.append(path)
        self.rjson = self.routes[path]
        return self

    def json(self):
        return self.rjson


NEW = "/orders/billing-info/MLA/B1"
OLD = "/orders/777/billing_info"
V2 = {"site_id": "MLA", "buyer": {"billing_info": {
    "name": "Ana", "last_name": "Perez",
    "identification": {"type": "DNI", "number": "123"},
    "taxes": {"taxpayer_type": {"description": "Consumidor Final"}},
    "address": {"street_name": "Calle", "zip_code": "1000", "state": {"name": "CABA"}}}}}
LEGACY = {"billing_info": {"doc_type": "DNI", "doc_number": "999"}}
DATA = {"id": 777, "site_id": "MLA", "buyer": {"billing_info": {"id": "B1"}}}


class T(unittest.TestCase):
    def run_it(self, routes):
        m = FakeMeli(routes)
        res = FakeSelf().get_billing_info(order_id=777, meli=m, data=DATA)
        return m, res

    def test_nuevo_200_se_usa_y_no_se_llama_al_viejo(self):
        m, res = self.run_it({NEW: V2, OLD: LEGACY})
        self.assertEqual(m.calls, [NEW])
        self.assertEqual(res["DOC_NUMBER"], "123")
        self.assertEqual(res["FIRST_NAME"], "Ana")

    def test_nuevo_404_cae_al_viejo(self):
        err = {"error": "http_404", "status": 404, "message": "not found"}
        m, res = self.run_it({NEW: err, OLD: LEGACY})
        self.assertEqual(m.calls, [NEW, OLD])
        self.assertEqual(res["doc_number"], "999")

    def test_nuevo_410_cae_al_viejo(self):
        err = {"message": "gone", "error": "gone", "status": 410}
        m, res = self.run_it({NEW: err, OLD: LEGACY})
        self.assertEqual(m.calls, [NEW, OLD])
        self.assertEqual(res["doc_number"], "999")

    def test_nuevo_vacio_cae_al_viejo(self):
        m, res = self.run_it({NEW: {}, OLD: LEGACY})
        self.assertEqual(m.calls, [NEW, OLD])
        self.assertEqual(res["doc_number"], "999")


if __name__ == "__main__":
    unittest.main()
