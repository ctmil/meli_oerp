# -*- coding: utf-8 -*-
"""MLM: régimen fiscal y uso de CFDI de billing-info -> contacto fiscal / venta — SIN Odoo.

Correr:  python3 meli_oerp/tests/test_mlm_cfdi_pure.py   (NO esta en tests/__init__.py)
Carga por AST de models/orders.py: _normalize_billing_info_v2, las helpers _meli_mx_cfdi_* y
_meli_mx_apply_cfdi (no importa odoo). ORDERS_PY=<ruta> apunta a otra copia (p.ej. la previa al fix).

Gap (hasta 26.290, legacy y v2 por igual): ML informa en MLM taxes.taxpayer_type.id (601/612/616) y
taxes.cfdi.id (G01/G03/S01) y el modulo nunca los escribia en l10n_mx_edi_fiscal_regime /
l10n_mx_edi_usage. Payloads anonimizados de PLAN-2026-10-23-535-verificar-billing-v2-mlm (T3LC).
"""
import ast
import contextlib
import logging
import os
import textwrap
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PATH = os.environ.get("ORDERS_PY") or os.path.join(_HERE, "..", "models", "orders.py")
_FUNCS = ("_normalize_billing_info_v2", "_meli_mx_cfdi_codes", "_meli_mx_cfdi_partner_vals",
          "_meli_mx_cfdi_order_usage", "_meli_mx_selection_codes", "_meli_mx_apply_cfdi")
_ASSIGNS = ("_MELI_MX_REGIME_FIELD", "_MELI_MX_USAGE_FIELD", "_MELI_MX_ODOO_DEFAULTS", "_MELI_MX_OVERRIDE_FLAG")


def _load():
    src = open(_PATH, encoding="utf-8").read()
    tree = ast.parse(src)
    lines = src.splitlines()
    ns = {"_logger": logging.getLogger("test_mlm_cfdi")}
    found = set()
    for node in tree.body:  # constantes de modulo
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) in _ASSIGNS for t in node.targets):
            exec(compile(ast.Module([node], []), "orders.py", "exec"), ns)
            found.update(t.id for t in node.targets)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in _FUNCS and node.name not in found:
            found.add(node.name)
            code = textwrap.dedent("\n".join(lines[node.lineno - 1:node.end_lineno]))
            exec(compile(code, "orders.py:%s" % node.name, "exec"), ns)
    missing = set(_FUNCS + _ASSIGNS) - found
    return ns, missing, src


NS, MISSING, SRC = _load()

REGIMES = ['601', '603', '605', '606', '612', '616', '621', '625', '626']
USAGES = ['G01', 'G02', 'G03', 'I01', 'D01', 'S01', 'CP01']


def v2(cust_type, name, last, doc, regime, regime_desc, usage, usage_desc):
    """billing-info v2 MLM (anonimizado) tal como lo entrega /orders/billing-info/MLM/<id>."""
    return {
        "name": name, "last_name": last,
        "identification": {"type": "RFC", "number": doc},
        "taxes": {"taxpayer_type": {"id": regime, "description": regime_desc},
                  "cfdi": {"id": usage, "description": usage_desc}},
        "address": {"street_name": "Calle X", "street_number": "1", "city_name": "Ciudad",
                    "state": {"name": "Estado"}, "zip_code": "01000"},
        "attributes": {"cust_type": cust_type, "vat_discriminated_billing": "true"},
    }


PM = v2("BU", "EMPRESA ANON SA DE CV", "", "AAA010101KR2", "601", "General de Ley Personas Morales",
        "G01", "Adquisición de mercancías")
PF = v2("CO", "Juan", "Perez", "PEPJ800101678", "612",
        "Personas Físicas con Actividades Empresariales y Profesionales", "G03", "Gastos en general")
PUB = v2("CO", "Publico", "General", "XAXX010101000", "616", "Sin obligaciones fiscales",
         "S01", "Sin efectos fiscales")
# legacy /orders/<id>/billing_info, additional_info aplanado por get_billing_info
LEGACY_PM = {"doc_type": "RFC", "doc_number": "AAA010101KR2", "TAXPAYER_TYPE_ID": "601",
             "TAXPAYER_TYPE_DESCRIPTION": "General de Ley Personas Morales", "CFDI": "G01",
             "CFDI_DESCRIPTION": "Adquisición de mercancías"}


class FakeField(object):
    def __init__(self, values):
        self.values = values

    def get_values(self, env):
        return list(self.values)


class FakeModel(object):
    def __init__(self, fields):
        self._fields = fields


class FakeCr(object):
    @contextlib.contextmanager
    def savepoint(self):
        yield


class FakeEnv(dict):
    cr = FakeCr()


class FakePartner(object):
    def __init__(self, fields, **vals):
        self._fields = dict.fromkeys(fields, True)
        self.vals = dict.fromkeys(fields, False)
        self.vals.update(vals)
        self.id = 7
        self.writes = []

    def __len__(self):
        return 1

    def __bool__(self):
        return True

    def __getitem__(self, k):
        return self.vals[k]

    def __getattr__(self, k):
        if k in ("vals", "_fields"):
            raise AttributeError(k)
        if k in self.vals:
            return self.vals[k]
        raise AttributeError(k)

    def write(self, vals):
        self.writes.append(dict(vals))
        self.vals.update(vals)


MX_FIELDS = ("l10n_mx_edi_fiscal_regime", "l10n_mx_edi_usage")


def make_self(partner_fields=MX_FIELDS):
    env = FakeEnv()
    env["res.partner"] = FakeModel({f: FakeField(REGIMES if "regime" in f else USAGES) for f in partner_fields})
    env["sale.order"] = FakeModel({"l10n_mx_edi_usage": FakeField(USAGES)})

    class S(object):
        _normalize_billing_info_v2 = NS.get("_normalize_billing_info_v2")
        _meli_mx_selection_codes = NS.get("_meli_mx_selection_codes")
        _meli_mx_apply_cfdi = NS.get("_meli_mx_apply_cfdi")
    s = S()
    s.env = env
    return s


class TestMlmCfdi(unittest.TestCase):

    def test_00_helpers_presentes(self):
        self.assertFalse(MISSING, "faltan en orders.py: %s" % sorted(MISSING))

    def _apply(self, payload, partner, is_new=False, v2_shape=True):
        s = make_self()
        bi = s._normalize_billing_info_v2(payload, site_id="MLM") if v2_shape else payload
        return s._meli_mx_apply_cfdi(partner, bi, is_new=is_new)

    def test_01_pm_601_g01_contacto_nuevo(self):
        # Odoo pone 601 por default al crear el partner MX: el creado en esta importacion toma lo de ML
        p = FakePartner(MX_FIELDS, l10n_mx_edi_fiscal_regime="601")
        self._apply(PM, p, is_new=True)
        self.assertEqual(p.l10n_mx_edi_fiscal_regime, "601")
        self.assertEqual(p.l10n_mx_edi_usage, "G01")

    def test_02_pf_612_g03_contacto_nuevo_corrige_default(self):
        p = FakePartner(MX_FIELDS, l10n_mx_edi_fiscal_regime="601")
        vals = self._apply(PF, p, is_new=True)
        self.assertEqual(vals, {"l10n_mx_edi_fiscal_regime": "612", "l10n_mx_edi_usage": "G03"})
        self.assertEqual(p.l10n_mx_edi_fiscal_regime, "612")

    def test_03_publico_general_616_s01_vacios(self):
        p = FakePartner(MX_FIELDS)
        self._apply(PUB, p, is_new=False)
        self.assertEqual(p.l10n_mx_edi_fiscal_regime, "616")
        self.assertEqual(p.l10n_mx_edi_usage, "S01")

    def test_04_legacy_endpoint(self):
        p = FakePartner(MX_FIELDS)
        self._apply(LEGACY_PM, p, v2_shape=False)
        self.assertEqual((p.l10n_mx_edi_fiscal_regime, p.l10n_mx_edi_usage), ("601", "G01"))

    def test_05_valor_manual_no_se_pisa(self):
        p = FakePartner(MX_FIELDS, l10n_mx_edi_fiscal_regime="626", l10n_mx_edi_usage="I01")
        with self.assertLogs("test_mlm_cfdi", level="INFO") as cm:
            vals = self._apply(PF, p, is_new=False)
        self.assertEqual(vals, {})
        self.assertEqual(p.writes, [])
        self.assertEqual((p.l10n_mx_edi_fiscal_regime, p.l10n_mx_edi_usage), ("626", "I01"))
        self.assertTrue(any("no se pisa" in m for m in cm.output), cm.output)

    def test_06_manual_parcial_completa_solo_el_vacio(self):
        p = FakePartner(MX_FIELDS, l10n_mx_edi_fiscal_regime="626")
        vals = self._apply(PF, p, is_new=False)
        self.assertEqual(vals, {"l10n_mx_edi_usage": "G03"})
        self.assertEqual(p.l10n_mx_edi_fiscal_regime, "626")

    def test_07_sin_l10n_mx_edi_noop(self):
        s = make_self(partner_fields=())
        p = FakePartner(())
        bi = s._normalize_billing_info_v2(PF, site_id="MLM")
        self.assertEqual(s._meli_mx_apply_cfdi(p, bi, is_new=True), {})
        self.assertEqual(p.writes, [])

    def test_08_16_0_solo_regimen(self):
        # 16.0: l10n_mx_edi_40 tiene regimen en el partner pero el uso vive solo en account.move
        s = make_self(partner_fields=("l10n_mx_edi_fiscal_regime",))
        p = FakePartner(("l10n_mx_edi_fiscal_regime",), l10n_mx_edi_fiscal_regime="601")
        bi = s._normalize_billing_info_v2(PF, site_id="MLM")
        self.assertEqual(s._meli_mx_apply_cfdi(p, bi, is_new=True), {"l10n_mx_edi_fiscal_regime": "612"})

    def test_09_codigo_fuera_de_seleccion_noop(self):
        p = FakePartner(MX_FIELDS)
        bad = v2("CO", "A", "B", "PEPJ800101678", "999", "x", "ZZZ", "y")
        self.assertEqual(self._apply(bad, p, is_new=True), {})

    def test_10_contacto_bloqueado_noop(self):
        p = FakePartner(MX_FIELDS + ("meli_update_forbidden",), meli_update_forbidden=True)
        self.assertEqual(self._apply(PF, p, is_new=True), {})

    def test_11_mla_no_trae_codigos_mx(self):
        mla = {"identification": {"type": "CUIT", "number": "20111111112"},
               "taxes": {"taxpayer_type": {"description": "IVA Responsable Inscripto"}}}
        self.assertEqual(NS["_meli_mx_cfdi_codes"](make_self()._normalize_billing_info_v2(mla, "MLA")),
                         (None, None))

    def test_12_uso_en_la_venta(self):
        f = NS["_meli_mx_cfdi_order_usage"]
        self.assertEqual(f("G01", USAGES, True, False, False), "G01")      # venta nueva
        self.assertEqual(f("G01", USAGES, False, "G03", False), "G01")     # default, sin factura
        self.assertIsNone(f("G01", USAGES, False, "I01", False))           # cambiado a mano
        self.assertIsNone(f("G01", USAGES, False, "G03", True))            # ya facturada
        self.assertIsNone(f("G01", USAGES, False, "G01", False))           # sin cambio
        self.assertIsNone(f("ZZZ", USAGES, True, False, False))            # fuera de seleccion

    def test_13_cableado_en_la_importacion(self):
        body = SRC[SRC.index("def orders_update_order_json"):]
        body = body[:body.index("\n    def ", 10)]
        self.assertTrue("self._meli_mx_apply_cfdi(" in body, "orders_update_order_json no llama _meli_mx_apply_cfdi")
        self.assertTrue("_meli_mx_cfdi_order_usage(" in body, "orders_update_order_json no fija el uso en la venta")
        self.assertEqual(body.count("_mx_cfdi_new_partner_ids.add("), 3)


# ----------------------------------------------------------------------------------------------
# 26.294: override OPT-IN del default de Odoo (601 regimen / G03 uso) en contactos EXISTENTES.
# res.company (y la configuracion de cuenta de meli_oerp_multiple) mercadolibre_mx_cfdi_override_default.
# Apagada (default) = comportamiento 26.292. Nunca pisa otro valor (carga manual) ni contactos bloqueados.
# ----------------------------------------------------------------------------------------------
_OVR = "mercadolibre_mx_cfdi_override_default"


class FakeConfig(object):
    def __init__(self, value=None, declared=True):
        self._fields = {_OVR: True} if declared else {}
        if declared:
            setattr(self, _OVR, value)


ON, OFF = FakeConfig(True), FakeConfig(False)


class TestMlmCfdiOverrideDefault(unittest.TestCase):

    def _apply(self, payload, partner, config, partner_fields=MX_FIELDS):
        s = make_self(partner_fields=partner_fields)
        bi = s._normalize_billing_info_v2(payload, site_id="MLM")
        return s._meli_mx_apply_cfdi(partner, bi, is_new=False, config=config)

    def test_20_apagada_es_26292(self):
        for cfg in (OFF, None, FakeConfig(declared=False)):
            p = FakePartner(MX_FIELDS, l10n_mx_edi_fiscal_regime="601", l10n_mx_edi_usage="G03")
            self.assertEqual(self._apply(PUB, p, cfg), {}, cfg)
            self.assertEqual((p.l10n_mx_edi_fiscal_regime, p.l10n_mx_edi_usage), ("601", "G03"))
            p = FakePartner(MX_FIELDS, l10n_mx_edi_fiscal_regime="601")
            self.assertEqual(self._apply(PF, p, cfg), {"l10n_mx_edi_usage": "G03"}, cfg)

    def test_21_prendida_601_a_612(self):
        p = FakePartner(MX_FIELDS, l10n_mx_edi_fiscal_regime="601", l10n_mx_edi_usage="G03")
        with self.assertLogs("test_mlm_cfdi", level="INFO") as cm:
            vals = self._apply(PF, p, ON)
        self.assertEqual(vals, {"l10n_mx_edi_fiscal_regime": "612"})
        self.assertEqual((p.l10n_mx_edi_fiscal_regime, p.l10n_mx_edi_usage), ("612", "G03"))
        self.assertTrue(any("MX_CFDI override 601\u2192612" in m for m in cm.output), cm.output)

    def test_22_prendida_601_a_616_y_g03_a_s01(self):
        p = FakePartner(MX_FIELDS, l10n_mx_edi_fiscal_regime="601", l10n_mx_edi_usage="G03")
        with self.assertLogs("test_mlm_cfdi", level="INFO") as cm:
            vals = self._apply(PUB, p, ON)
        self.assertEqual(vals, {"l10n_mx_edi_fiscal_regime": "616", "l10n_mx_edi_usage": "S01"})
        self.assertTrue(any("MX_CFDI override 601\u2192616" in m for m in cm.output), cm.output)
        self.assertTrue(any("MX_CFDI override G03\u2192S01" in m for m in cm.output), cm.output)

    def test_23_prendida_no_pisa_manual(self):
        p = FakePartner(MX_FIELDS, l10n_mx_edi_fiscal_regime="603", l10n_mx_edi_usage="I01")
        with self.assertLogs("test_mlm_cfdi", level="INFO") as cm:
            vals = self._apply(PUB, p, ON)
        self.assertEqual(vals, {})
        self.assertEqual(p.writes, [])
        self.assertEqual((p.l10n_mx_edi_fiscal_regime, p.l10n_mx_edi_usage), ("603", "I01"))
        self.assertTrue(any("no se pisa" in m for m in cm.output), cm.output)
        # manual en uno, default en el otro: solo se corrige el default
        p = FakePartner(MX_FIELDS, l10n_mx_edi_fiscal_regime="603", l10n_mx_edi_usage="G03")
        self.assertEqual(self._apply(PUB, p, ON), {"l10n_mx_edi_usage": "S01"})

    def test_24_prendida_contacto_bloqueado(self):
        p = FakePartner(MX_FIELDS + ("meli_update_forbidden",), meli_update_forbidden=True,
                        l10n_mx_edi_fiscal_regime="601", l10n_mx_edi_usage="G03")
        self.assertEqual(self._apply(PUB, p, ON), {})
        self.assertEqual(p.writes, [])

    def test_25_prendida_sin_l10n_mx_edi_noop(self):
        p = FakePartner(())
        self.assertEqual(self._apply(PUB, p, ON, partner_fields=()), {})
        self.assertEqual(p.writes, [])

    def test_26_prendida_16_0_solo_regimen(self):
        f = ("l10n_mx_edi_fiscal_regime",)
        p = FakePartner(f, l10n_mx_edi_fiscal_regime="601")
        self.assertEqual(self._apply(PUB, p, ON, partner_fields=f), {"l10n_mx_edi_fiscal_regime": "616"})

    def test_27_prendida_ml_manda_601_no_toca(self):
        p = FakePartner(MX_FIELDS, l10n_mx_edi_fiscal_regime="601", l10n_mx_edi_usage="G03")
        self.assertEqual(self._apply(v2("BU", "E", "", "AAA010101KR2", "601", "x", "G03", "y"), p, ON), {})

    def test_28_cableado_opcion(self):
        body = SRC[SRC.index("def orders_update_order_json"):]
        body = body[:body.index("\n    def ", 10)]
        call = body[body.index("self._meli_mx_apply_cfdi("):]
        call = call[:call.index(")\n")]
        self.assertIn("config=config", call, "la importacion no le pasa la config a _meli_mx_apply_cfdi")
        root = os.path.join(_HERE, "..")
        comp = open(os.path.join(root, "models", "company.py"), encoding="utf-8").read()
        self.assertIn("%s = fields.Boolean(" % _OVR, comp)
        decl = comp[comp.index("%s = fields.Boolean(" % _OVR):]
        self.assertIn("default=False", decl[:decl.index("\n    )")])
        view = open(os.path.join(root, "views", "company_view.xml"), encoding="utf-8").read()
        self.assertIn('<field name="%s"' % _OVR, view)


if __name__ == "__main__":
    unittest.main(verbosity=2)
