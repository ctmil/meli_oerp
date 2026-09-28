# -*- coding: utf-8 -*-
"""Tests de _fetch_meli_user_product_id (backport 26.x -> 13.0, Lenceria 131).

Se ejecutan SIN Odoo: el metodo es una funcion pura sobre el json del item.
    python3 tests/test_user_product_id.py
"""
import os, re, sys, textwrap

RUTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "product.py")


def cargar_metodo():
    src = open(RUTA, encoding="utf-8", errors="ignore").read()
    m = re.search(r"\n(    def _fetch_meli_user_product_id.*?)\n    def product_meli_get_product", src, re.S)
    assert m, "no se encontro _fetch_meli_user_product_id en models/product.py"
    ns = {}
    exec("class P:\n" + "\n".join("    " + l for l in textwrap.dedent(m.group(1)).splitlines()), ns)
    return ns["P"](), ns["P"]._fetch_meli_user_product_id


CASOS = [
    # (nombre, item_json, meli_id_variation, esperado, pasar_meli_id)
    ("sin meli_id devuelve None", {"user_product_id": "MLAU1"}, None, None, False),
    ("sin item_json devuelve None", None, None, None, True),
    ("item simple con upid", {"user_product_id": "MLAU1"}, None, "MLAU1", True),
    ("item sin upid ni variaciones", {"id": "MLA1"}, None, None, True),
    ("variacion exacta pedida", {"user_product_id": "MLAU0", "variations": [
        {"id": "1", "user_product_id": "MLAU_A"}, {"id": "2", "user_product_id": "MLAU_B"}]}, "2", "MLAU_B", True),
    ("sin variacion, un solo upid distinto", {"variations": [
        {"id": "1", "user_product_id": "MLAU_A"}, {"id": "2", "user_product_id": "MLAU_A"}]}, None, "MLAU_A", True),
    ("sin variacion, dos upid -> cae al del item", {"user_product_id": "MLAU_ITEM", "variations": [
        {"id": "1", "user_product_id": "MLAU_A"}, {"id": "2", "user_product_id": "MLAU_B"}]}, None, "MLAU_ITEM", True),
    # Regresion del ticket #425: NUNCA devolver str(lista). Sin item-level upid y con
    # varios upid distintos, la respuesta correcta es None.
    ("dos upid y sin item upid -> None (regresion #425)", {"variations": [
        {"id": "1", "user_product_id": "MLAU_A"}, {"id": "2", "user_product_id": "MLAU_B"}]}, None, None, True),
    # El caso de Lenceria hoy: publicaciones viejas, sin user_product_id en ninguna variacion.
    ("variaciones sin upid (el caso de Lenceria hoy)", {"variations": [{"id": "1"}, {"id": "2"}]}, None, None, True),
    # Regresion del TypeError que tiene 16.0: el isinstance() protegia solo el .get()
    # y dos lineas mas abajo se hacia var["id"] sin proteger.
    ("variacion que no es dict no rompe", {"variations": [
        "basura", {"id": "2", "user_product_id": "MLAU_B"}]}, "2", "MLAU_B", True),
    ("variations vacio cae al item", {"variations": [], "user_product_id": "MLAU_I"}, None, "MLAU_I", True),
    # COMPORTAMIENTO HEREDADO DE 16.0, no lo cambiamos en el backport: si se pide una
    # variacion que no existe, devuelve el upid de otra variacion en vez de None.
    # Escalado a domain-meli el 28-sep-2026. El test fija lo que HACE, no lo que deberia.
    ("variacion pedida inexistente -> devuelve el de otra (heredado)", {"variations": [
        {"user_product_id": "MLAU_X"}]}, "9", "MLAU_X", True),
]


def main():
    P, f = cargar_metodo()
    ok = fallas = 0
    for nombre, item, var, esperado, con_id in CASOS:
        try:
            r = f(P, meli_id=("MLA123" if con_id else None), meli_id_variation=var, item_json=item)
            if r == esperado:
                ok += 1
                print("  [OK   ] %s" % nombre)
            else:
                fallas += 1
                print("  [FALLA] %s -> %r (esperado %r)" % (nombre, r, esperado))
        except Exception as e:
            fallas += 1
            print("  [ERROR] %s -> %s: %s" % (nombre, type(e).__name__, e))
    print("\n  %d OK / %d fallas sobre %d casos" % (ok, fallas, len(CASOS)))
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
