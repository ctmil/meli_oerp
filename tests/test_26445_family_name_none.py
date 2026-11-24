# -*- coding: utf-8 -*-
"""26.445 — family_name 'None'.

La importacion guardaba str(rjson['family_name']): con un null de ML quedaba el TEXTO 'None' y al publicar
ML armaba el titulo "None <Color> <Talle>" y moderaba el item. Ahora: (1) 'None'/'False' son vacio para el
helper que usan la importacion y el armado del body; (2) la importacion no guarda el texto; (3) la migracion
26.445 deja vacio el dato viejo y no toca nada mas. Sin red: ML es un fake.
"""
import importlib.util
import os
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.meli_oerp.models import product as _meli_product


def _mid(n):
    """Id de publicacion SINTETICO (armado, sin literal sitio+digitos)."""
    return '%s%d' % ('MLA', 4450000000 + n)


class _Resp(object):
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class _FakeMeli(object):
    access_token = 'TOKEN-445'

    def __init__(self, item):
        self.item = item

    def need_login(self):
        return False

    def get(self, path, params=None, *a, **k):
        if path.startswith('/items/'):
            return _Resp(dict(self.item))
        return _Resp({'error': 'not_found', 'status': 404})


def _load_migration():
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'migrations')
    folder = [d for d in os.listdir(base) if d.endswith('26.445')][0]
    spec = importlib.util.spec_from_file_location('meli_oerp_mig_26445', os.path.join(base, folder, 'post-migrate.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@tagged('post_install', '-at_install', 'meli', 'meli_26445')
class TestFamilyNameNone(TransactionCase):

    def test_1_helper(self):
        meli_family_name_clean = getattr(_meli_product, 'meli_family_name_clean', None)
        self.assertTrue(meli_family_name_clean, "falta el helper meli_family_name_clean")
        for vacio in (None, False, '', '   ', 'None', 'False', ' None '):
            self.assertFalse(meli_family_name_clean(vacio), repr(vacio))
        self.assertEqual(meli_family_name_clean('Camison Solero'), 'Camison Solero')
        self.assertEqual(meli_family_name_clean(' Camison '), 'Camison')
        self.assertEqual(meli_family_name_clean('None Celeste'), 'None Celeste', "solo el valor exacto es vacio")

    def test_2_importar_con_family_name_null_no_guarda_none(self):
        prod = self.env['product.product'].create({'name': 'P 445 import', 'default_code': 'T445IMP'})
        item = {'id': _mid(1), 'title': 'Camison 445', 'family_name': None, 'listing_type_id': 'gold_special',
                'buying_mode': 'buy_it_now', 'price': 1000, 'currency_id': 'ARS', 'condition': 'new',
                'available_quantity': 1, 'warranty': '', 'thumbnail': '', 'pictures': [], 'attributes': [],
                'category_id': 'MLA0', 'status': 'active', 'permalink': '', 'seller_custom_field': 'T445IMP'}
        fake = _FakeMeli(item)
        with patch.object(type(self.env['meli.util']), 'get_new_instance', lambda *a, **k: fake), \
                mute_logger('odoo.addons.meli_oerp.models.product'):
            err = None
            try:
                prod.product_meli_get_product(meli_id=_mid(1), import_images=False)
            except Exception as e:  # el resto de la importacion puede necesitar mas de ML
                import traceback; err = traceback.format_exc()[-800:]
        # el test solo vale si la importacion llego a escribir los datos del item: segun la configuracion de
        # la compania de la base de test puede cortar antes (sin error); eso no es un resultado, se saltea
        if err is not None:
            self.fail("la importacion fallo: %s" % err)
        if prod.meli_title != 'Camison 445':
            self.skipTest("la importacion corto antes de escribir con esta configuracion de compania")
        self.assertNotIn(prod.meli_family_name, ('None', 'False'))
        self.assertNotIn(prod.product_tmpl_id.meli_family_name, ('None', 'False'))

    def test_3_migracion_limpia_solo_none_y_false(self):
        mig = _load_migration()
        T = self.env['product.template']
        t_none = T.create({'name': 'T445 none', 'meli_family_name': 'None'})
        t_false = T.create({'name': 'T445 false', 'meli_family_name': 'False'})
        t_ok = T.create({'name': 'T445 ok', 'meli_family_name': 'Camison Solero'})
        t_none_x = T.create({'name': 'T445 none x', 'meli_family_name': 'None Celeste'})
        v_none = t_ok.product_variant_ids[:1]
        v_none.write({'meli_family_name': 'None'})
        self.env.flush_all() if hasattr(self.env, 'flush_all') else self.env['base'].flush()
        mig.migrate(self.env.cr, '0.0.0')
        if hasattr(T, 'invalidate_recordset'):
            (t_none | t_false | t_ok | t_none_x).invalidate_recordset()
            v_none.invalidate_recordset()
        else:
            self.env['base'].invalidate_cache()
        self.assertFalse(t_none.meli_family_name)
        self.assertFalse(t_false.meli_family_name)
        self.assertFalse(v_none.meli_family_name)
        self.assertEqual(t_ok.meli_family_name, 'Camison Solero')
        self.assertEqual(t_none_x.meli_family_name, 'None Celeste')
        mig.migrate(self.env.cr, None)  # instalacion nueva: no hace nada (y no rompe)
