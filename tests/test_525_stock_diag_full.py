# -*- coding: utf-8 -*-
"""#611 (ROEN 525, 21-oct-2026): "Meli Stock Diagnostic" anotaba "REACTIVADA" cada 30 min
sobre las mismas publicaciones, que seguian pausadas.

(1) El SQL del diagnostico suma la existencia de TODAS las ubicaciones internas (Full incluida),
    pero el push publica solo las de la configuracion: con stock solo en Full (MLF) el binding
    publica 0, ML la vuelve a pausar, y el diagnostico la "reactivaba" otra vez.
(2) "REACTIVADA" se anotaba sin mirar si ML la habia activado.

Sin red: ML es un objeto falso con respuestas por publicacion; el push y la activacion se
reemplazan por mocks (lo que se prueba es la DECISION del diagnostico).
"""

from unittest.mock import MagicMock, patch

from odoo.tests import TransactionCase, tagged


class _Resp(object):
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class _FakeMeli(object):
    access_token = 'x'

    def __init__(self, script):
        self.script = {k: list(v) for k, v in script.items()}
        self.calls = []

    def get(self, path, *args, **kwargs):
        meli_id = path.rstrip('/').split('/')[-1]
        self.calls.append(meli_id)
        seq = self.script.get(meli_id)
        if not seq:
            return _Resp({'error': 'not_found', 'status': 404, 'message': 'test'})
        return _Resp(seq.pop(0) if len(seq) > 1 else seq[0])


def _item(meli_id, status):
    return {'id': meli_id, 'status': status, 'available_quantity': 0,
            'sub_status': ['out_of_stock'] if status == 'paused' else [],
            'shipping': {'logistic_type': 'xd_drop_off'}}


@tagged('post_install', '-at_install', 'meli_525')
class TestStockDiagFull(TransactionCase):

    def setUp(self):
        super().setUp()
        company = self.env.company
        if 'mercadolibre_stock_location_to_post' not in company._fields:
            self.skipTest("requiere meli_oerp_stock (ubicacion de publicacion)")
        PP = type(self.env['product.product'])
        if hasattr(PP, '_clear_logistic_type_cache'):
            PP._clear_logistic_type_cache()
            self.addCleanup(PP._clear_logistic_type_cache)
        wh = self.env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
        self.loc_wh = wh.lot_stock_id
        parent = self.env.ref('stock.stock_location_locations', raise_if_not_found=False) or wh.view_location_id.location_id
        self.loc_full = self.env['stock.location'].create({
            'name': 'MLF525D', 'usage': 'internal', 'location_id': parent.id, 'company_id': company.id,
            'mercadolibre_logistic_type': 'fulfillment'})
        vals = {'mercadolibre_cron_post_update_stock': True,
                'mercadolibre_stock_location_to_post': self.loc_wh.id}
        if 'mercadolibre_stock_location_to_post_full' in company._fields:
            vals['mercadolibre_stock_location_to_post_full'] = self.loc_full.id
        if 'publish_stock' in company._fields:
            vals['publish_stock'] = False
        if 'mercadolibre_stock_diag_reactivate' in company._fields:
            vals['mercadolibre_stock_diag_reactivate'] = 'all'
        company.write(vals)
        # que ningun otro producto publicado de la base entre al diagnostico
        self.env['product.product'].search([('meli_pub', '=', True)]).write({'meli_pub': False})
        tipo = {'type': 'consu', 'is_storable': True} if 'is_storable' in self.env['product.template']._fields else {'type': 'product'}
        self.tipo = tipo
        self.post = MagicMock(return_value={})
        self.activate = MagicMock(return_value={})
        for name, mock in (('product_post_stock', self.post), ('product_meli_status_active', self.activate)):
            p = patch.object(PP, name, mock)
            p.start()
            self.addCleanup(p.stop)

    def _producto(self, code, meli_id, loc, qty):
        p = self.env['product.product'].create(dict(self.tipo, name=code, default_code=code))
        p.write({'meli_pub': True, 'meli_id': meli_id, 'meli_available_quantity': 0})
        self.env['stock.quant']._update_available_quantity(p, loc, qty)
        # el diagnostico lee por SQL: en el cron real esto ya esta commiteado
        self.env.flush_all()
        return p

    def test_1_stock_solo_en_full_no_reactiva(self):
        """PMG9378/PMG8009/PMG5630_10: existencia solo en MLF => no se pide activar (publicaria 0)."""
        self._producto('T525F', 'MLM525100001', self.loc_full, 3.0)
        meli = _FakeMeli({'MLM525100001': [_item('MLM525100001', 'paused')]})
        res = self.env.company.meli_stock_diagnostic(meli=meli, reactivate='all')
        self.assertIn('MLM525100001', meli.calls, "control: la publicacion tiene que haber entrado al diagnostico")
        self.assertFalse(self.activate.called, "con stock solo en Full no hay nada publicable que reactivar")
        self.assertEqual(res.get('actions_taken'), 0)

    def test_2_no_anota_reactivada_si_ml_sigue_pausada(self):
        """Stock publicable > 0, se pide activar, ML sigue pausada => 'NO QUEDO ACTIVA', no 'REACTIVADA'."""
        self._producto('T525W', 'MLM525100002', self.loc_wh, 2.0)
        meli = _FakeMeli({'MLM525100002': [_item('MLM525100002', 'paused')]})
        with self.assertLogs('odoo.addons.meli_oerp.models.company', level='WARNING') as cm:
            self.env.company.meli_stock_diagnostic(meli=meli, reactivate='all')
        self.assertEqual(self.activate.call_count, 1)
        self.assertTrue(any('NO QUEDO ACTIVA' in m for m in cm.output), cm.output)

    def test_3_reactiva_cuando_ml_la_activa(self):
        """Control positivo: stock publicable y ML queda activa => se reactiva como siempre."""
        self._producto('T525A', 'MLM525100003', self.loc_wh, 2.0)
        meli = _FakeMeli({'MLM525100003': [_item('MLM525100003', 'paused'), _item('MLM525100003', 'active')]})
        with self.assertLogs('odoo.addons.meli_oerp.models.company', level='WARNING') as cm:
            res = self.env.company.meli_stock_diagnostic(meli=meli, reactivate='all')
        self.assertEqual(self.activate.call_count, 1)
        self.assertEqual(res.get('actions_taken'), 1)
        self.assertFalse(any('NO QUEDO ACTIVA' in m for m in cm.output), cm.output)
