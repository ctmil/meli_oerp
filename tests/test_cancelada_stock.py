# -*- coding: utf-8 -*-
"""Test (26.412): «Al cancelarse una venta en ML» = republish (default) | hold.

Sin Odoo: carga models/meli_cancel_stock.py con un paquete `odoo` falso, y extrae de
models/product.py el guard de _meli_available_quantity. Mide:
  1. modo: default/ausente/invalido => republish; config de la CUENTA manda.
  2. hold: marca la variante, encola los bindings, NO hay red dentro de la transacción,
     la publicación sale recién en el commit (cursor propio), una vez por producto.
  3. republish: no marca, publica en el commit.
  4. no-cancelada / FULL / sin meli_order_id => nada. Venta > 30 días en hold => no retiene, publica.
  5. rollback descarta y re-arma; tope MELI_CANCEL_STOCK_POST_MAX; Odoo 13 (cr.after) y 14+ (postcommit).
  6. guard: _meli_available_quantity da 0 con la variante retenida (y el valor real sin retener).
  7. orders.py llama al followup después de CADA action_cancel() de cancelación ML.
Control negativo: PRODUCT_SRC=<product.py viejo> u ORDERS_SRC=<orders.py viejo> => FALLA.
Uso: python3 tests/test_cancelada_stock.py
"""
import os, re, sys, types, unittest, importlib.util
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
PRODUCT_SRC = os.environ.get("PRODUCT_SRC") or os.path.join(ROOT, "models", "product.py")
ORDERS_SRC = os.environ.get("ORDERS_SRC") or os.path.join(ROOT, "models", "orders.py")
NOW = datetime(2026, 11, 16, 15, 0, 0)

# ---------------------------------------------------------------- odoo falso
LOG = []  # eventos en orden: ('net', id, cursor) | ('commit', cursor) ...


class Callbacks(object):
    def __init__(self): self._f = []
    def add(self, f): self._f.append(f)
    def run(self):
        f, self._f = self._f, []
        for x in f: x()


class Cursor14(object):
    """Odoo 14+: postcommit/postrollback."""
    n = 0
    def __init__(self):
        Cursor14.n += 1; self.name = "cr%d" % Cursor14.n
        self.postcommit = Callbacks(); self.postrollback = Callbacks(); self.in_tx = True
    # = odoo/sql_db.py 16-20: commit limpia postrollback y corre postcommit; rollback limpia postcommit
    def commit(self):
        LOG.append(('commit', self.name)); self.in_tx = False
        self.postrollback = Callbacks(); self.postcommit.run(); self.in_tx = True
    def rollback(self): LOG.append(('rollback', self.name)); self.postcommit = Callbacks(); self.postrollback.run()
    def savepoint(self):
        class SP(object):
            def __enter__(s): return s
            def __exit__(s, *a): return False
        return SP()
    def __enter__(self): return self
    def __exit__(self, et, ev, tb):
        if et is None: self.commit()
        return False


class Cursor13(Cursor14):
    """Odoo 13: cr.after('commit'|'rollback', f), sin postcommit; commit/rollback vacían AMBAS listas
    (= odoo/sql_db.py 13.0 _pop_event_handlers)."""
    def __init__(self):
        Cursor14.__init__(self); del self.postcommit; del self.postrollback; self._h = {'commit': [], 'rollback': []}
    def after(self, ev, f): self._h[ev].append(f)
    def _pop(self, ev):
        h, self._h = self._h, {'commit': [], 'rollback': []}
        return h[ev]
    def commit(self):
        LOG.append(('commit', self.name)); self.in_tx = False
        for f in self._pop('commit'): f()
        self.in_tx = True
    def rollback(self):
        LOG.append(('rollback', self.name))
        for f in self._pop('rollback'): f()


DB = {}  # id -> FakeProduct


class Registry(object):
    def __init__(self, cls): self.cls = cls; self.cursors = []
    def cursor(self):
        c = self.cls(); self.cursors.append(c); return c


class FakeProduct(object):
    def __init__(self, pid, ptype='product', hold=False, qty=1):
        self.id = pid; self.type = ptype; self.meli_stock_hold = hold; self.display_name = "P%d" % pid
        self.virtual_available = qty; self.cr = None
        DB[pid] = self


class Recs(object):
    """recordset mínimo de product.product."""
    def __init__(self, env, ids): self.env = env; self.ids = list(dict.fromkeys(ids))
    def __iter__(self):
        for i in self.ids:
            r = Recs(self.env, [i]); yield r
    def __len__(self): return len(self.ids)
    def __bool__(self): return bool(self.ids)
    def __or__(self, o): return Recs(self.env, self.ids + o.ids)
    def __getattr__(self, k):
        if k in ('id',): return self.ids[0]
        return getattr(DB[self.ids[0]], k)
    def browse(self, ids): return Recs(self.env, ids)
    def exists(self): return Recs(self.env, [i for i in self.ids if i in DB])
    def mapped(self, k): return [getattr(DB[i], k) for i in self.ids]
    def product_post_stock(self):
        cr = self.env.cr
        LOG.append(('net', self.ids[0], cr.name, cr.in_tx))
    def _meli_stock_hold_set(self, note=None):
        LOG.append(('hold', tuple(self.ids), note))
        for i in self.ids: DB[i].meli_stock_hold = True


class Env(object):
    def __init__(self, cr, uid=2, context=None, registry=None):
        self.cr = cr; self.uid = uid; self.context = context or {}; self.registry = registry
    def __getitem__(self, model):
        assert model == 'product.product'
        return Recs(self, [])


def _install_fake_odoo():
    odoo = types.ModuleType("odoo")
    fields = types.ModuleType("odoo.fields")
    class Datetime(object):
        @staticmethod
        def now(): return NOW
    fields.Datetime = Datetime
    models = types.ModuleType("odoo.models")
    class Model(object):
        pass
    models.Model = Model
    api = types.ModuleType("odoo.api")
    api.Environment = lambda cr, uid, ctx: Env(cr, uid, ctx)
    odoo.fields, odoo.models, odoo.api = fields, models, api
    sys.modules.update({"odoo": odoo, "odoo.fields": fields, "odoo.models": models, "odoo.api": api})


_install_fake_odoo()
_spec = importlib.util.spec_from_file_location("meli_cancel_stock", os.path.join(ROOT, "models", "meli_cancel_stock.py"))
MCS = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(MCS)
SaleMixin = MCS.SaleOrderMeliCancelStock


class Line(object):
    def __init__(self, product, is_delivery=False): self.product_id = product; self.is_delivery = is_delivery


class Cfg(object):
    def __init__(self, mode=None, has=True):
        self._fields = {'mercadolibre_cancel_stock_mode': 1} if has else {}
        self.mercadolibre_cancel_stock_mode = mode


class Order(SaleMixin):
    _fields = {'meli_date_closed': 1, 'meli_shipment_logistic_type': 1}
    def __init__(self, env, lines, state='cancel', meli_order_id='<order_id>', closed=NOW, lt='xd_drop_off', company=None):
        self.env = env; self.state = state; self.meli_order_id = meli_order_id; self.name = 'S29015'
        self.meli_date_closed = closed; self.date_order = closed; self.meli_shipment_logistic_type = lt
        self.company_id = company; self.order_line = lines; self.msgs = []; self.enqueued = []
    def __iter__(self): yield self
    def message_post(self, body=None, **kw): self.msgs.append(body)
    def _meli_cancel_stock_enqueue(self, products):
        self.enqueued.append(tuple(products.ids)); LOG.append(('enqueue', tuple(products.ids)))


def mk(cls=Cursor14):
    reg = Registry(cls); cr = cls(); env = Env(cr, registry=reg)
    return reg, cr, env


def prod_recs(env, *pids): return Recs(env, list(pids))


class T(unittest.TestCase):
    def setUp(self):
        del LOG[:]; DB.clear()

    # 1
    def test_modo(self):
        _, _, env = mk(); o = Order(env, [])
        self.assertEqual(o._meli_cancel_stock_mode(Cfg('hold')), 'hold')
        self.assertEqual(o._meli_cancel_stock_mode(Cfg(None)), 'republish')
        self.assertEqual(o._meli_cancel_stock_mode(Cfg('xx')), 'republish')
        self.assertEqual(o._meli_cancel_stock_mode(Cfg('hold', has=False)), 'republish')
        o.company_id = Cfg('hold'); self.assertEqual(o._meli_cancel_stock_mode(None), 'hold')

    def _order(self, env, *pids, **kw):
        lines = [Line(prod_recs(env, p)) for p in pids]
        return Order(env, lines, **kw)

    # 2
    def _hold(self, cls):
        reg, cr, env = mk(cls)
        FakeProduct(78322, hold=False); FakeProduct(78323)
        o = self._order(env, 78322, 78323)
        o._meli_cancel_stock_followup(config=Cfg('hold'))
        self.assertTrue(DB[78322].meli_stock_hold and DB[78323].meli_stock_hold)
        self.assertEqual(o.enqueued, [(78322, 78323)])
        self.assertFalse([e for e in LOG if e[0] == 'net'], "red DENTRO de la transacción")
        cr.commit()
        net = [e for e in LOG if e[0] == 'net']
        self.assertEqual(sorted(e[1] for e in net), [78322, 78323])
        self.assertTrue(all(e[2] != cr.name for e in net), "publicó con el cursor de la orden")
        self.assertEqual(len(reg.cursors), 1)
        self.assertTrue(any('stock retenido' in m for m in o.msgs))
        cr.commit()  # un segundo commit no re-publica
        self.assertEqual(len([e for e in LOG if e[0] == 'net']), 2)

    def test_hold_odoo14plus(self): self._hold(Cursor14)
    def test_hold_odoo13(self): self._hold(Cursor13)

    # 3
    def test_republish_default(self):
        reg, cr, env = mk(); FakeProduct(1)
        o = self._order(env, 1); o._meli_cancel_stock_followup(config=Cfg(None))
        self.assertFalse(DB[1].meli_stock_hold)
        self.assertFalse([e for e in LOG if e[0] in ('net', 'hold')])
        cr.commit()
        self.assertEqual([e[1] for e in LOG if e[0] == 'net'], [1])

    # 4
    def test_nada_si_no_corresponde(self):
        for kw in ({'state': 'sale'}, {'lt': 'fulfillment'}, {'meli_order_id': False}):
            del LOG[:]; DB.clear(); reg, cr, env = mk(); FakeProduct(1)
            o = self._order(env, 1, **kw); o._meli_cancel_stock_followup(config=Cfg('hold')); cr.commit()
            self.assertFalse(LOG[:-1], kw)
            self.assertFalse(DB[1].meli_stock_hold, kw)

    def test_servicio_y_envio_fuera(self):
        reg, cr, env = mk(); FakeProduct(1); FakeProduct(2, ptype='service'); FakeProduct(3)
        lines = [Line(prod_recs(env, 1)), Line(prod_recs(env, 2)), Line(prod_recs(env, 3), is_delivery=True)]
        o = Order(env, lines); o._meli_cancel_stock_followup(config=Cfg('hold')); cr.commit()
        self.assertEqual([e[1] for e in LOG if e[0] == 'net'], [1])
        self.assertTrue(DB[1].meli_stock_hold); self.assertFalse(DB[2].meli_stock_hold or DB[3].meli_stock_hold)

    def test_venta_vieja_no_retiene(self):
        reg, cr, env = mk(); FakeProduct(1)
        o = self._order(env, 1, closed=NOW - timedelta(days=31)); o._meli_cancel_stock_followup(config=Cfg('hold'))
        self.assertFalse(DB[1].meli_stock_hold)
        cr.commit(); self.assertEqual([e[1] for e in LOG if e[0] == 'net'], [1])

    # 5
    def test_rollback_rearma(self):
        for cls in (Cursor13, Cursor14):
            del LOG[:]; DB.clear(); reg, cr, env = mk(cls); FakeProduct(1); FakeProduct(2)
            self._order(env, 1)._meli_cancel_stock_followup(config=Cfg(None))
            cr.rollback()
            self._order(env, 2)._meli_cancel_stock_followup(config=Cfg(None))
            cr.commit()
            self.assertEqual([e[1] for e in LOG if e[0] == 'net'], [2], cls.__name__)

    def test_varias_ordenes_un_callback_y_tope(self):
        reg, cr, env = mk()
        for p in range(1, 31): FakeProduct(p)
        for p in range(1, 31):
            self._order(env, p, 1)._meli_cancel_stock_followup(config=Cfg(None))
        cr.commit()
        net = [e[1] for e in LOG if e[0] == 'net']
        self.assertEqual(len(net), MCS.MELI_CANCEL_STOCK_POST_MAX)
        self.assertEqual(len(set(net)), len(net))
        self.assertEqual(len(reg.cursors), 1)

    # 6
    def test_guard_available_quantity(self):
        src = open(PRODUCT_SRC, encoding="utf-8").read().replace("\r\n", "\n")
        m = re.search(r"^    def _meli_available_quantity\( self, meli=False, config=None \):\n(.*?)(?=^    def )", src, re.M | re.S)
        self.assertTrue(m, "no encontré _meli_available_quantity")
        code = "def f" + m.group(0)[len("    def _meli_available_quantity"):]
        code = "\n".join(l[4:] if l.startswith("    ") else l for l in code.splitlines())
        ns = {"_logger": types.SimpleNamespace(info=lambda *a: None)}
        exec(code, ns)
        class P(object):
            meli_available_quantity = 5; virtual_available = 3; route_ids = []; product_tmpl_id = None; id = 1
            def __init__(s, hold): s.meli_stock_hold = hold
            def __len__(s): return 1
            def _meli_stock_hold_active(s): return bool(s.meli_stock_hold)
        self.assertEqual(ns["f"](P(False)), 3)
        self.assertEqual(ns["f"](P(True)), 0, "variante retenida publica stock")

    # 7
    def test_orders_llama_followup_tras_cada_cancel(self):
        src = open(ORDERS_SRC, encoding="utf-8").read().replace("\r\n", "\n")
        for a in ('if (self.meli_status=="cancelled"):\n                if (self.state in ["draft","sale","sent"]):\n                    self.action_cancel()\n',
                  'if (sorder.meli_status=="cancelled" and sorder.state in ["draft","sale","sent"]):\n                sorder.action_cancel()\n'):
            i = src.find(a); self.assertGreater(i, 0, a)
            nxt = src[i + len(a):i + len(a) + 400]
            self.assertIn("_meli_cancel_stock_followup(config=config)", nxt, "sin followup tras: " + a.splitlines()[-1].strip())


if __name__ == "__main__":
    unittest.main(verbosity=2)
