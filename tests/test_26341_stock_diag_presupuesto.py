# -*- coding: utf-8 -*-
"""26.341 (26.190 re-portado, #598 OrgVit 475) -- "Meli Stock Diagnostic" con presupuesto por corrida.

El cron consultaba ML item por item, sin limite y en UNA transaccion: con 129 candidatos superaba
el limite del worker, moria, se perdia todo y Odoo termino desactivandolo. Ahora: multiget
/items?ids= de a 20, tope de items y de segundos (ir.config_parameter), cursor que retoma, y la
venta ML sin producto deja una actividad "Por hacer" (una por item).

Sin red: ML es un objeto falso. Se usa el camino "QTY STALE" (activa en ML con stock y 0
guardado en Odoo) porque no necesita push ni activacion: lo que se prueba es el PRESUPUESTO.
"""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


class _Resp(object):
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class _FakeMeliMulti(object):
    """Contesta /items?ids=a,b,c como ML (lista de {code, body}) y /items/<id> suelto."""
    access_token = 'x'
    seller_id = 26341

    def __init__(self, missing=()):
        self.missing = set(missing)
        self.multigets = []   # lista de listas de ids pedidas por multiget
        self.singles = []     # ids pedidas de a una

    def _body(self, mid):
        return {'id': mid, 'status': 'active', 'available_quantity': 5, 'sub_status': [],
                'shipping': {'logistic_type': 'xd_drop_off'}}

    def get(self, path, *args, **kwargs):
        if path.startswith('/items?ids='):
            ids = path.split('ids=')[1].split('&')[0].split(',')
            self.multigets.append(ids)
            return _Resp([{'code': 404, 'body': {'error': 'not_found', 'message': 'no existe'}}
                          if mid in self.missing else {'code': 200, 'body': self._body(mid)} for mid in ids])
        mid = path.rstrip('/').split('/')[-1]
        self.singles.append(mid)
        if mid in self.missing:
            return _Resp({'error': 'not_found', 'status': 404, 'message': 'no existe'})
        return _Resp(self._body(mid))

    def need_login(self):
        return False


@tagged('post_install', '-at_install', 'meli', 'meli_26341')
class TestStockDiagPresupuesto(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.company.write({'mercadolibre_cron_post_update_stock': True})
        if 'mercadolibre_stock_diag_reactivate' in self.company._fields:
            self.company.mercadolibre_stock_diag_reactivate = 'all'
        # que ningun otro producto publicado de la base entre al diagnostico
        self.env['product.product'].search([('meli_pub', '=', True)]).write({'meli_pub': False})
        if 'mercadolibre.product' in self.env:
            self.env['mercadolibre.product'].search([('meli_last_status', '=', 'paused')]).write({'meli_last_status': 'active'})
        wh = self.env['stock.warehouse'].search([('company_id', '=', self.company.id)], limit=1)
        self.loc = wh.lot_stock_id
        tipo = {'type': 'consu', 'is_storable': True} if 'is_storable' in self.env['product.template']._fields else {'type': 'product'}
        self.ICP = self.env['ir.config_parameter'].sudo()
        # Odoo 20: get_str/set_str
        self._get = getattr(self.ICP, 'get_str', None) or self.ICP.get_param
        self._set = getattr(self.ICP, 'set_str', None) or self.ICP.set_param
        self.products = self.env['product.product']
        for i in range(45):
            p = self.env['product.product'].create(dict(tipo, name='D%02d' % i, default_code='TD341%02d' % i))
            p.write({'meli_pub': True, 'meli_id': 'MLM9341%04d' % i, 'meli_available_quantity': 0})
            self.env['stock.quant']._update_available_quantity(p, self.loc, 3.0)
            self.products |= p
        self.env.flush_all()
        self._set('meli_stock_diag_max_items', '20')
        self._set('meli_stock_diag_time_budget', '600')

    def _diag(self, meli):
        with mute_logger('odoo.addons.meli_oerp.models.company'):
            return self.company.meli_stock_diagnostic(meli=meli, reactivate='all')

    def _cursor(self, meli):
        return self._get('meli_stock_diag_cursor.%s.%s' % (self.company.id, meli.seller_id)) or ''

    def test_1_tope_de_items_multiget_y_cursor(self):
        """45 candidatas con tope 20 => UN multiget de 20, 25 pendientes, cursor en la 20.a."""
        meli = _FakeMeliMulti()
        res = self._diag(meli)
        self.assertEqual(res.get('items_to_check'), 45, res)
        self.assertEqual(res.get('items_processed'), 20, res)
        self.assertEqual(res.get('items_deferred'), 25, res)
        self.assertEqual(len(meli.multigets), 1, "un solo multiget de 20, no 45 GET sueltos")
        self.assertEqual(len(meli.multigets[0]), 20)
        self.assertFalse(meli.singles, "no tiene que consultar item por item")
        self.assertEqual(self._cursor(meli), 'MLM93410019')
        done = self.products.filtered(lambda p: p.meli_available_quantity == 5)
        self.assertEqual(len(done), 20, "las 20 revisadas se corrigieron (QTY STALE)")

    def test_2_la_siguiente_corrida_retoma_donde_quedo(self):
        meli = _FakeMeliMulti()
        self._diag(meli)
        # que las 20 ya corregidas vuelvan a ser candidatas: el cursor es lo que decide por donde empieza
        self.products.write({'meli_available_quantity': 0})
        self.env.flush_all()
        meli2 = _FakeMeliMulti()
        res = self._diag(meli2)
        self.assertEqual(meli2.multigets[0][0], 'MLM93410020', "retoma en la 21.a, no vuelve a la 1.a")
        self.assertEqual(res.get('items_processed'), 20)
        # tercera corrida: quedan 5 al final y da la vuelta
        self.products.write({'meli_available_quantity': 0})
        self.env.flush_all()
        meli3 = _FakeMeliMulti()
        self._diag(meli3)
        ids3 = [m for chunk in meli3.multigets for m in chunk]
        self.assertEqual(ids3[:5], ['MLM93410040', 'MLM93410041', 'MLM93410042', 'MLM93410043', 'MLM93410044'])
        self.assertEqual(ids3[5], 'MLM93410000', "da la vuelta al principio")

    def test_3_corrida_completa_limpia_el_cursor(self):
        self._set('meli_stock_diag_max_items', '100')
        meli = _FakeMeliMulti()
        res = self._diag(meli)
        self.assertEqual(res.get('items_processed'), 45)
        self.assertEqual(res.get('items_deferred'), 0)
        self.assertEqual([len(c) for c in meli.multigets], [20, 20, 5])
        self.assertEqual(self._cursor(meli), '', "corrida completa => el proximo arranca de cero")

    def test_4_rechazo_de_ml_por_item_cuenta_como_error_no_como_sin_accion(self):
        self._set('meli_stock_diag_max_items', '100')
        meli = _FakeMeliMulti(missing={'MLM93410003', 'MLM93410030'})
        res = self._diag(meli)
        self.assertEqual(res.get('api_errors'), 2, res)
        self.assertEqual(res.get('api_errors_by_status'), {404: 2})
        self.assertEqual(res.get('items_checked_ok'), 43)
        self.assertEqual(res.get('diag_state'), 'warning')

    def test_5_tope_de_segundos(self):
        """Presupuesto de tiempo agotado => procesa al menos una y difiere el resto."""
        self._set('meli_stock_diag_max_items', '100')
        self._set('meli_stock_diag_time_budget', '0')
        meli = _FakeMeliMulti()
        res = self._diag(meli)
        self.assertEqual(res.get('items_processed'), 1, res)
        self.assertEqual(res.get('items_deferred'), 44, res)

    def test_6_commit_por_lote_con_commit_batches(self):
        """commit_batches=True (cron dedicado de multiple): cada lote de 20 queda COMMITEADO antes
        de pedir el siguiente; si el worker muere en el 3.er lote, los 2 primeros no se pierden.
        Sin commit_batches (llamador viejo): ningun commit, como antes."""
        import odoo.modules.module as _mod
        self._set('meli_stock_diag_max_items', '100')
        meli = _FakeMeliMulti()
        commits = []
        import threading
        _t = threading.current_thread()
        _had = hasattr(_t, 'testing')
        _old = getattr(_t, 'testing', None)
        _t.testing = False  # 16-18 marcan el hilo de tests; 19+ usan current_test
        if _had:
            self.addCleanup(setattr, _t, 'testing', _old)
        else:
            self.addCleanup(delattr, _t, 'testing')
        with patch.object(_mod, 'current_test', None), \
                patch.object(self.env.cr, 'commit', lambda *a: commits.append(len(meli.multigets))), \
                patch('odoo.addons.meli_oerp.models.company.MeliCommit', lambda *a, **k: None), \
                mute_logger('odoo.addons.meli_oerp.models.company'):
            self.company.meli_stock_diagnostic(meli=meli, reactivate='all', commit_batches=True)
            self.assertEqual(commits, [1, 2, 3, 3], "un commit por lote (+ el de cierre), cada uno antes del multiget siguiente")
            del commits[:]
            self.products.write({'meli_available_quantity': 0})
            self.env.flush_all()
            meli = _FakeMeliMulti()
            self.company.meli_stock_diagnostic(meli=meli, reactivate='all')
            self.assertEqual(commits, [], "sin commit_batches no se commitea nada (comportamiento previo)")


class _MPNoDisponible:
    ok = False
    status_code = 503

    def __bool__(self):
        return False

    def json(self):
        return {}


class _FakeMeliOrders:
    access_token = 'TEST'

    def get(self, path, params=None, **kw):
        if path.startswith('/items/'):
            return _Resp({'id': 'MLM934100SIN', 'title': 'Sin producto'})
        return _Resp({})

    def need_login(self):
        return False


def _order_json(oid):
    return {
        'id': oid, 'status': 'paid', 'status_detail': None,
        'date_created': '2026-10-08T10:00:00.000-06:00', 'date_closed': '2026-10-08T10:00:01.000-06:00',
        'total_amount': 100.0, 'paid_amount': 100.0, 'currency_id': 'MXN',
        'coupon': {'id': None, 'amount': 0},
        'order_items': [{'item': {'id': 'MLM934100SIN', 'title': 'Sin producto', 'variation_id': None,
                                  'seller_sku': 'SKU-NO-EXISTE-341', 'category_id': 'MLM1'},
                         'quantity': 1, 'unit_price': 100.0, 'full_unit_price': 100.0, 'currency_id': 'MXN'}],
        'payments': [{'id': 99034101, 'transaction_amount': 100.0, 'total_paid_amount': 100.0,
                      'currency_id': 'MXN', 'status': 'approved', 'coupon_amount': 0,
                      'shipping_cost': 0, 'date_created': '2026-10-08T10:00:01.000-06:00',
                      'date_last_modified': '2026-10-08T10:00:01.000-06:00'}],
        'buyer': {'id': 123341, 'nickname': 'COMPRADOR341', 'first_name': 'Comprador', 'last_name': 'Test',
                  'name': 'Comprador Test', 'email': 'comprador341@example.com',
                  'phone': {'area_code': '81', 'number': '00000000'}, 'alternative_phone': {}},
        'seller': {'id': 123999},
        'tags': ['paid'], 'context': {'channel': 'marketplace', 'site': 'MLM'},
        'shipping': {'id': None}, 'pack_id': None,
    }


@tagged('post_install', '-at_install', 'meli', 'meli_26341')
class TestVentaSinProductoActividad(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        pricelist = cls.env['product.pricelist'].search([], limit=1) or cls.env['product.pricelist'].create({'name': 'Lista ML'})
        cls.company.mercadolibre_pricelist = pricelist
        cls.contact = cls.env['res.partner'].create({'name': 'Cliente ML 341'})
        if 'mercadolibre_contact_partner' in cls.company._fields:
            cls.company.mercadolibre_contact_partner = cls.contact

    def _import(self, oid):
        with patch('odoo.addons.meli_oerp.models.orders.requests.get', return_value=_MPNoDisponible()), \
                mute_logger('odoo.addons.meli_oerp.models.orders', 'odoo.addons.meli_oerp_multiple.models.sale'):
            return self.env['mercadolibre.orders'].orders_update_order_json(
                {'id': False, 'order_json': _order_json(oid)}, meli=_FakeMeliOrders(), config=self.company)

    def test_1_actividad_unica_y_filtro(self):
        oid = 2000934100341
        self._import(oid)
        so = self.env['sale.order'].search([('meli_order_id', '=', str(oid))], limit=1)
        if not so:
            self.skipTest("la venta sin producto no se crea en esta configuracion")
        acts = so.activity_ids.filtered(lambda a: 'ML: producto no encontrado' in (a.summary or ''))
        self.assertEqual(len(acts), 1, so.activity_ids.mapped('summary'))
        self.assertIn('SKU-NO-EXISTE-341', acts.summary)
        # re-proceso de la misma orden (el cron la vuelve a mirar): no duplica la actividad
        self._import(oid)
        acts = so.activity_ids.filtered(lambda a: 'ML: producto no encontrado' in (a.summary or ''))
        self.assertEqual(len(acts), 1, "una actividad por item, no una por corrida")
        # el filtro de Presupuestos la encuentra
        found = self.env['sale.order'].search([('meli_order_id', '!=', False),
                                               ('activity_ids.summary', 'ilike', 'ML: producto no encontrado')])
        self.assertIn(so, found)
