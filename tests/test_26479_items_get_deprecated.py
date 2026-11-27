# -*- coding: utf-8 -*-
"""26.479 — ML deprecó el multiget `GET /items?ids=` (27-nov-2026, flota; medido en un cliente).

ML contesta 403 {"error": "ResourceDeprecated"} a una fracción AL AZAR de los multiget; `GET /items/<id>`
suelto sigue respondiendo. Antes cada llamador perdía el lote entero en silencio. `meli_items_get`:
  1. con el multiget deprecado igual devuelve TODO, en la misma forma [{code, body}] y en el orden pedido;
  2. tras el primer ResourceDeprecated deja de intentar multiget (no duplica tráfico);
  3. una entrada con error dentro de la lista se relee de a una; un 404 real se respeta;
  4. un 429 en el GET suelto se reintenta; un id que no se pudo leer queda como error explícito (y se loguea);
  5. meli_oerp.items_multiget = 0 => nunca multiget;
  6. el diagnóstico de stock (_meli_diag_multiget) sigue funcionando con el multiget deprecado.
Sin red: ML es un fake.
"""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.meli_oerp.models import meli_util as mu

DEPRECATED = {'error': 'ResourceDeprecated',
              'message': 'Resource deprecated - client no longer allowed to consume this resource',
              'status': 403}


class _Resp(object):
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class _FakeMeli(object):
    access_token = 'TOKEN-26479'

    def __init__(self, items, deprecated=True, entry_errors=(), flaky=None):
        self.items = items                    # {id: body}
        self.deprecated = deprecated          # el multiget contesta 403 ResourceDeprecated
        self.entry_errors = set(entry_errors) # en la lista vuelven con code 500
        self.flaky = dict(flaky or {})        # {id: n} => n veces 429 antes de responder
        self.multigets = []
        self.singles = []
        self.params = []

    def need_login(self):
        return False

    def get(self, path, params=None, *a, **k):
        params = dict(params or {})
        self.params.append((path, params))
        assert '?' not in path, "el query va en params (el cliente SDK concatena '?' a ciegas): %s" % path
        if path == '/items':
            ids = params['ids'].split(',')
            assert len(ids) <= 20
            self.multigets.append(ids)
            if self.deprecated:
                return _Resp(dict(DEPRECATED))
            out = []
            for m in ids:
                if m in self.entry_errors:
                    out.append({'code': 500, 'body': {'error': 'internal_error', 'status': 500}})
                elif m in self.items:
                    out.append({'code': 200, 'body': dict(self.items[m])})
                else:
                    out.append({'code': 404, 'body': {'error': 'not_found', 'status': 404}})
            return _Resp(out)
        mid = path.rsplit('/', 1)[-1]
        self.singles.append(mid)
        if self.flaky.get(mid):
            self.flaky[mid] -= 1
            return _Resp({'error': 'http_429', 'status': 429, 'message': 'too many requests'})
        if mid in self.items:
            return _Resp(dict(self.items[mid]))
        return _Resp({'error': 'not_found', 'status': 404, 'message': 'Item not found'})


def _items(n, prefix='MLA4790000'):
    return {'%s%02d' % (prefix, i): {'id': '%s%02d' % (prefix, i), 'status': 'active', 'price': 100 + i}
            for i in range(n)}


@tagged('post_install', '-at_install', 'meli', 'meli_26479')
class TestItemsGetDeprecated(TransactionCase):

    def setUp(self):
        super().setUp()
        mu._MELI_ITEMS_MULTIGET_STATE['off_until'] = 0.0
        self.addCleanup(mu._MELI_ITEMS_MULTIGET_STATE.__setitem__, 'off_until', 0.0)
        sleep = patch.object(mu._meli_time, 'sleep', lambda *a: None)
        sleep.start()
        self.addCleanup(sleep.stop)

    def test_1_deprecado_devuelve_todo_en_orden(self):
        items = _items(45)
        ids = list(items)
        fake = _FakeMeli(items, deprecated=True)
        with self.assertLogs('odoo.addons.meli_oerp.models.meli_util', level='WARNING') as logs:
            res = self.env['meli.util'].meli_items_get(fake, ids, attributes='id,status,price')
        self.assertEqual(len(res), 45)
        self.assertEqual([r['body']['id'] for r in res], ids, "misma forma y mismo orden que lo pedido")
        self.assertTrue(all(r['code'] == 200 for r in res))
        self.assertEqual(len(fake.multigets), 1, "tras el 1er ResourceDeprecated no se insiste con multiget")
        self.assertEqual(sorted(fake.singles), sorted(ids))
        self.assertTrue(any('ResourceDeprecated' in m for m in logs.output))
        single_params = [p for path, p in fake.params if path != '/items']
        self.assertTrue(all(p.get('attributes') == 'id,status,price' for p in single_params),
                        "el GET suelto pide los mismos attributes")
        # proxima corrida en el mismo proceso: directo de a uno
        fake2 = _FakeMeli(items, deprecated=True)
        self.env['meli.util'].meli_items_get(fake2, ids[:3])
        self.assertEqual(fake2.multigets, [])

    def test_2_multiget_vivo_entrada_con_error_y_404(self):
        items = _items(5)
        ids = list(items) + ['MLA479NOEXISTE']
        fake = _FakeMeli(items, deprecated=False, entry_errors={ids[2]})
        res = self.env['meli.util'].meli_items_get(fake, ids)
        self.assertEqual(len(fake.multigets), 1)
        self.assertEqual(fake.singles, [ids[2]], "solo se relee la entrada con error (el 404 real no)")
        self.assertEqual([r['code'] for r in res], [200, 200, 200, 200, 200, 404])

    def test_3_429_se_reintenta_y_lo_ilegible_queda_explicito(self):
        items = _items(2)
        ids = list(items)
        fake = _FakeMeli(items, deprecated=True, flaky={ids[0]: 1, ids[1]: 10})
        with self.assertLogs('odoo.addons.meli_oerp.models.meli_util', level='WARNING') as logs:
            res = self.env['meli.util'].meli_items_get(fake, ids)
        self.assertEqual(res[0]['code'], 200, "un 429 se reintenta")
        self.assertEqual(res[1]['code'], 429)
        self.assertEqual(res[1]['body']['error'], 'http_429')
        self.assertTrue(any(ids[1] in m for m in logs.output), "el id perdido queda en el log")

    def test_4_parametro_apaga_multiget(self):
        ICP = self.env['ir.config_parameter'].sudo()
        (getattr(ICP, 'set_str', None) or ICP.set_param)('meli_oerp.items_multiget', '0')
        items = _items(3)
        fake = _FakeMeli(items, deprecated=False)
        res = self.env['meli.util'].meli_items_get(fake, list(items))
        self.assertEqual(fake.multigets, [])
        self.assertEqual(len(res), 3)

    def test_5_ids_repetidos_y_vacios(self):
        items = _items(2)
        a, b = list(items)
        fake = _FakeMeli(items, deprecated=True)
        res = self.env['meli.util'].meli_items_get(fake, [a, False, b, a])
        self.assertEqual(len(res), 4, "alineada con lo pedido: los llamadores hacen zip(ids, res)")
        self.assertEqual(res[1]['code'], 0)
        self.assertEqual([res[0]['body']['id'], res[2]['body']['id'], res[3]['body']['id']], [a, b, a])
        self.assertEqual(sorted(fake.singles), sorted([a, b]), "cada id se lee una sola vez")

    def test_6_diagnostico_de_stock_con_multiget_deprecado(self):
        items = {k: dict(v, available_quantity=3, sub_status=[], shipping={'logistic_type': 'xd_drop_off'})
                 for k, v in _items(3).items()}
        fake = _FakeMeli(items, deprecated=True)
        out = self.env.company._meli_diag_multiget(fake, list(items) + ['MLA479NOEXISTE'])
        for mid in items:
            self.assertEqual(out[mid].get('status'), 'active')
        self.assertEqual(out['MLA479NOEXISTE'].get('status'), 404)

    def test_7_filter_meli_ids_con_multiget_deprecado(self):
        items = {k: dict(v, official_store_id=(77 if i % 2 == 0 else 88))
                 for i, (k, v) in enumerate(_items(4).items())}
        fake = _FakeMeli(items, deprecated=True)
        Util = type(self.env['meli.util'])
        with patch.object(Util, 'get_new_instance', lambda *a, **k: fake):
            res = self.env.company.filter_meli_ids(list(items), store_id=77)
        self.assertEqual(res, [k for i, k in enumerate(items) if i % 2 == 0])
