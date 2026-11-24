# -*- coding: utf-8 -*-
"""Tests 13.0.26.445: family_name 'None'.

La importacion guardaba str(rjson['family_name']): con un null de ML quedaba el TEXTO 'None' y al publicar ML
armaba el titulo "None <Color> <Talle>" y moderaba el item. Se verifica: (1) el helper; (2) la importacion
ya no hace str() del family_name; (3) el armado del body y la preparacion de la plantilla pasan por el
helper; (4) la migracion 13.0.26.445 toca solo 'None'/'False' exactos.
Sin Odoo: el helper se extrae de models/product.py.
    python3 tests/test_26445_family_name_none_sin_odoo.py
"""
import os, re, sys

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SRC = open(os.path.join(BASE, "models", "product.py"), encoding="utf-8").read().replace("\r\n", "\n")
MIG = os.path.join(BASE, "migrations", "13.0.26.445", "post-migrate.py")

FALLAS = []
def check(nombre, got, exp):
    ok = got == exp
    print(("OK  " if ok else "FAIL") + " " + nombre + ("" if ok else "  got=%r exp=%r" % (got, exp)))
    if not ok: FALLAS.append(nombre)


def test_helper():
    m = re.search(r"^MELI_FAMILY_NAME_EMPTY = .*?^def meli_family_name_clean\(value\):.*?\n(?=\n\n)", SRC, re.M | re.S)
    check("helper presente", bool(m), True)
    if not m:
        return
    ns = {}
    exec(m.group(0), ns)
    f = ns["meli_family_name_clean"]
    for v in (None, False, "", "  ", "None", "False", " None "):
        check("vacio: %r" % (v,), f(v), False)
    check("nombre real", f("Camison Solero"), "Camison Solero")
    check("solo el valor exacto", f("None Celeste"), "None Celeste")


def test_usos():
    check("importacion sin str(rjson['family_name'])", "str(rjson['family_name'])" in SRC, False)
    check("importacion con el helper", "'meli_family_name': meli_family_name_clean(rjson.get('family_name'))," in SRC, True)
    check("preparacion de plantilla con el helper", "if not meli_family_name_clean(product_tmpl.meli_family_name):" in SRC, True)
    crudos = re.findall(r'body\["(?:family_name|title)"\]\s*=.*(?<![\w(])product\.meli_family_name(?!\))', SRC)
    check("body: ningun product.meli_family_name crudo", crudos, [])


def test_migracion():
    src = open(MIG, encoding="utf-8").read()
    check("migracion: solo 'None'/'False' exactos", "WHERE btrim(meli_family_name) IN ('None', 'False')" in src, True)
    check("migracion: instalacion nueva no hace nada", "if not version:\n        return" in src, True)


if __name__ == "__main__":
    test_helper(); test_usos(); test_migracion()
    print("\n%d FALLAS" % len(FALLAS) if FALLAS else "\nTODO OK")
    sys.exit(1 if FALLAS else 0)
