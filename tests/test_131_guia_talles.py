# -*- coding: utf-8 -*-
"""Tests 131 (13.0.26.263): guia de talles — fila correcta (search_row_id) y eleccion de la guia de la marca.

Se ejecutan SIN Odoo (harness: los metodos se extraen de models/ y corren sobre registros falsos):
    python3 tests/test_131_guia_talles.py
Datos: guias reales de Lenceria Divina leidas de ML el 21-oct-2026 (9172274 Ana Grant, 2309930 deville).
"""
import os, re, sys, json, logging, types
try:
    import unidecode
except ImportError:  # sin la lib: equivalente suficiente para estos casos (quita acentos)
    import unicodedata
    unidecode = types.SimpleNamespace(unidecode=lambda s: unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode())

AQUI = os.path.dirname(os.path.abspath(__file__))
CAT = os.path.join(AQUI, "..", "models", "category.py")
PROD = os.path.join(AQUI, "..", "models", "product.py")


def metodo(ruta, nombre):
    src = open(ruta, encoding="utf-8").read()
    m = re.search(r"^    def " + re.escape(nombre) + r"\(.*?(?=^    (?:def |@|[A-Za-z_]+ = fields\.|_[A-Z_]+ = )|^class |\Z)", src, re.M | re.S)
    assert m, nombre
    code = "\n".join((l[4:] if l.startswith("    ") else ("" if not l.strip() else "#" + l.lstrip())) for l in m.group(0).splitlines())
    def really_compare(a, b, sensitive=False):
        a = unidecode.unidecode(str(a).capitalize()); b = unidecode.unidecode(str(b).capitalize())
        return a == b
    ns = {"json": json, "unidecode": unidecode, "_logger": logging.getLogger("t"), "really_compare": really_compare}
    exec(code, ns)
    return ns[nombre]


class RS(list):
    """recordset falso: lo justo para filtered/mapped/len/|."""
    def filtered(self, f): return RS([r for r in self if f(r)])
    def mapped(self, k): return [getattr(r, k) for r in self]
    def __or__(self, o): return RS(list(self) + [x for x in o if x not in self])
    def __bool__(self): return len(self) > 0
    def ensure_one(self): assert len(self) == 1
    def browse(self): return RS()
    def __getattr__(self, k):
        assert len(self) == 1, k
        return getattr(self[0], k)


class Obj(object):
    def __init__(self, **kw): self.__dict__.update(kw)


def col(att, val, num=None): return Obj(id=0, att_id=att, name=att, value=val, number=num)


def chart(meli_id, filas, nombre="g"):
    rows = RS(Obj(row_id="%s:%s" % (meli_id, i), attribute_values=RS(cols)) for i, cols in filas)
    c = Obj(meli_id=meli_id, main_attribute_id="SIZE", rows=rows, name=json.dumps({"MLA": nombre}), site_id="MLA")
    for n in ("search_row_id", "_search_row_id_legacy", "_meli_chart_label", "_meli_chart_sizes"):
        f = metodo(CAT, n); setattr(c, n, (lambda f: (lambda *a, **k: f(RS([c]), *a, **k)))(f))
    c.ensure_one = lambda: None
    return c


def ana_grant():
    # filas reales 9172274: SIZE / FILTRABLE_SIZE (prepare_vals guarda sólo el 1er valor) / BUST_CIRCUMFERENCE_FROM
    F = [(1, "80", ["80"], 80), (2, "90", ["90"], 90), (3, "90C", ["90", "95"], 93), (4, "95", ["95"], 95),
         (5, "95C", ["95", "100"], 97), (6, "100", ["100"], 100), (7, "100C", ["100", "105"], 103),
         (8, "105", ["105"], 105), (9, "105C", ["105", "110"], 108), (10, "110", ["110"], 110),
         (11, "110C", ["110", "115"], 113), (12, "115", ["115"], 115), (13, "120", ["120"], 120)]
    return chart("9172274", [(i, [col("SIZE", s), col("FILTRABLE_SIZE", f[0]), col("BUST_CIRCUMFERENCE_FROM", "%s cm" % n, str(float(n)))]) for i, s, f, n in F], "Corpiños Ana Grant Mujer")


def deville():
    F = [(5, "80"), (1, "90"), (8, "90C"), (2, "95"), (9, "95C"), (3, "100"), (10, "100C"), (4, "105"), (11, "105C"), (6, "110"), (12, "110C"), (7, "115"), (13, "120")]
    return chart("2309930", [(i, [col("SIZE", s), col("FILTRABLE_SIZE", s.rstrip("C")), col("BUST_CIRCUMFERENCE_FROM", "%s cm" % s.rstrip("C"), s.rstrip("C"))]) for i, s in F], "deville")


FALLAS = []
def check(nombre, got, exp):
    ok = got == exp
    print(("OK  " if ok else "FAIL") + " " + nombre + ("" if ok else "  got=%r exp=%r" % (got, exp)))
    if not ok: FALLAS.append(nombre)


def test_fila():
    g = ana_grant()
    # las filas que usa la publicacion viva MLA657733290 (90->:2, 100->:6, 110->:10, 115->:12)
    for talle, fila in (("90", "9172274:2"), ("100", "9172274:6"), ("110", "9172274:10"), ("115", "9172274:12"), ("100C", "9172274:7"), ("100c", "9172274:7")):
        check("Ana Grant talle %s -> %s" % (talle, fila), g.search_row_id(talle)[0], fila)
    # control: la busqueda anterior elegia la ULTIMA coincidencia (FILTRABLE_SIZE de :7) -> el bug medido
    check("control: legacy 100 -> :7 (bug)", g._search_row_id_legacy("100")[0], "9172274:7")
    d = deville()
    check("deville 100 -> :3", d.search_row_id("100")[0], "2309930:3")
    check("deville 95C -> :9", d.search_row_id("95C")[0], "2309930:9")
    # sin coincidencia exacta en SIZE cae a la busqueda anterior (por medida en cm)
    check("fallback numerico 103 -> :7", g.search_row_id("103")[0], "9172274:7")
    check("talle inexistente -> None", g.search_row_id("XL")[0], None)
    check("label legible", g._meli_chart_label(), "Corpiños Ana Grant Mujer")


def test_eleccion_guia():
    find = metodo(CAT, "meli_find_grid_chart")
    g1 = ana_grant(); g2 = chart("1666388", [(1, [col("SIZE", "90")])], "Peter"); g3 = chart("2129992", [(1, [col("SIZE", "90")])], "Lidia corpiños")
    def cat(charts):
        c = Obj(); c.ensure_one = lambda: None
        c.meli_import_grid_charts = lambda brand=None, gender=None, meli=None: RS(charts)
        c.env = {"mercadolibre.grid.chart": RS()}
        return c
    check("una guia con la marca -> esa", find(cat([g2, g1, g3]), brand="Ana Grant", gender="Mujer", sizes=["90", "100"]).mapped("meli_id"), ["9172274"])
    check("marca sin acentos/mayusculas", find(cat([g2, g1]), brand="ANA GRANT", gender="Mujer").mapped("meli_id"), ["9172274"])
    check("ninguna con la marca -> no elige", len(find(cat([g2, g3]), brand="Eyelit", gender="Mujer")), 0)
    e1 = chart("9517831", [(i, [col("SIZE", s)]) for i, s in enumerate(["S", "M", "L", "XL", "XXL"], 1)], "Calzoncillos Eyelit Talle Hombre")
    e2 = chart("2728610", [(i, [col("SIZE", s)]) for i, s in enumerate(["7", "8", "9", "10"], 1)], "eyelit 7-8-9-10")
    check("dos de la marca: desempata por talles", find(cat([e1, e2]), brand="Eyelit", gender="Hombre", sizes=["L", "XL"]).mapped("meli_id"), ["9517831"])
    e3 = chart("9062788", [(i, [col("SIZE", s)]) for i, s in enumerate(["S", "M", "L", "XL", "XXL"], 1)], "Calzoncillos Eyelit Hombre Talles")
    check("dos de la marca que cubren -> no adivina", len(find(cat([e1, e3]), brand="Eyelit", gender="Hombre", sizes=["L", "XL"])), 0)


def test_resolver_plantilla():
    res = metodo(PROD, "_meli_grid_chart_resolve"); vals = metodo(PROD, "_meli_line_values")
    NAMES = {"SIZE": ("TALLE", "TALLA", "SIZE"), "BRAND": ("MARCA", "_MARCA", "BRAND"), "GENDER": ("GENERO", "GENDER"), "SIZE_GRID_ID": ()}
    def linea(nombre, ml, valores): return Obj(attribute_id=Obj(name=nombre, meli_default_id_attribute=Obj(att_id=ml) if ml else None), value_ids=RS(Obj(name=v) for v in valores))
    def tmpl(lineas, chart_ml=None, found=None):
        t = Obj(meli_grid_chart_id=None, meli_brand=False, meli_gender=False, display_name="t", attribute_line_ids=RS(lineas), _MELI_GRID_LINE_NAMES=NAMES)
        t.ensure_one = lambda: None
        llamadas = []
        t.meli_category = Obj(meli_find_grid_chart=lambda **k: (llamadas.append(k) or found or RS()))
        t.env = {"mercadolibre.grid.chart": Obj(import_chart=lambda gid, meli=None: (llamadas.append(("import", gid)) or RS([Obj(meli_id=gid)])), __bool__=lambda s: False)}
        t._meli_line_values = lambda a: vals(t, a)
        t.llamadas = llamadas
        return t
    class Vacio(object):
        def __bool__(self): return False
        def import_chart(self, gid, meli=None): return RS([Obj(meli_id=gid)])
    # 1) atributo "ID de la guia de talles" (SIZE_GRID_ID, 1 valor) -> se importa esa
    t = tmpl([linea("ID de la guía de talles", "SIZE_GRID_ID", ["2309930"]), linea("Talle", "SIZE", ["100"])])
    t.env = {"mercadolibre.grid.chart": Vacio()}
    check("resolver: via atributo SIZE_GRID_ID", res(t).mapped("meli_id"), ["2309930"])
    # 2) por marca + genero de las LINEAS (meli_brand/meli_gender vacios, como en la 902)
    t = tmpl([linea("_Marca", "BRAND", ["Ana Grant"]), linea("Género", "GENDER", ["Mujer"]), linea("Talle", "SIZE", ["90", "100"])], found=RS([Obj(meli_id="9172274")]))
    t.env = {"mercadolibre.grid.chart": Vacio()}
    check("resolver: por marca de la linea", res(t).mapped("meli_id"), ["9172274"])
    check("resolver: pasa marca/genero/talles", (t.llamadas[-1]["brand"], t.llamadas[-1]["gender"], t.llamadas[-1]["sizes"]), ("Ana Grant", "Mujer", ["90", "100"]))
    # 3) sin talle no busca guia
    t = tmpl([linea("_Marca", "BRAND", ["Ana Grant"])])
    t.env = {"mercadolibre.grid.chart": Vacio()}
    res(t); check("resolver: sin Talle no llama a ML", t.llamadas, [])


if __name__ == "__main__":
    test_fila(); test_eleccion_guia(); test_resolver_plantilla()
    print("\n%d FALLAS" % len(FALLAS) if FALLAS else "\nTODO OK")
    sys.exit(1 if FALLAS else 0)
