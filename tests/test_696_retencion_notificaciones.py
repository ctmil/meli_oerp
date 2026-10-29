# -*- coding: utf-8 -*-
"""#696 (535 T3LC, 29-oct-2026): mercadolibre.notification no tenía retención. El autovacuum
borra sólo terminadas (SUCCESS/FAILED) más viejas que meli_oerp.notification_days (default 90; 0 = nunca)
y nunca RECEIVED/PROCESSING. Sin red.
26.338: tampoco toca el working set del cron de órdenes (FAILED orders_v2 reintentable, <24 intentos)
ni lo escrito en las últimas 24 h: las notificaciones del test se fechan también en write_date."""
from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'meli', 'meli_696')
class TestRetencionNotificaciones(TransactionCase):

    def _icp(self, value):
        ICP = self.env['ir.config_parameter'].sudo()
        setter = getattr(ICP, 'set_str', None) or ICP.set_param  # 20.0: set_str ; 16-19: set_param
        setter('meli_oerp.notification_days', value)

    def _noti(self, nid, state, days_ago, received=True, attempts=24):
        when = fields.Datetime.now() - timedelta(days=days_ago)
        n = self.env['mercadolibre.notification'].create({
            'notification_id': 'test696-%s' % nid, 'topic': 'orders_v2', 'state': state,
            'received': when if received else False,
            'processing_logs': 'x' * 100, 'attempts': attempts,
        })
        n.flush_recordset()
        self.env.cr.execute("UPDATE mercadolibre_notification SET create_date=%s, write_date=%s WHERE id=%s",
                            (when, when, n.id))
        n.invalidate_recordset()
        return n

    def _setup(self):
        Noti = self.env['mercadolibre.notification']
        Noti.search([('notification_id', 'like', 'test696-%')]).unlink()
        return {
            'ok_viejo': self._noti(1, 'SUCCESS', 120),
            'fail_viejo': self._noti(2, 'FAILED', 120),  # agotada (24 intentos): se borra
            'fail_reintentable': self._noti(8, 'FAILED', 120, attempts=3),  # el cron 177 la reintenta
            'ok_nuevo': self._noti(3, 'SUCCESS', 10),
            'recv_viejo': self._noti(4, 'RECEIVED', 400),
            'proc_viejo': self._noti(5, 'PROCESSING', 400),
            'ok_sin_received_viejo': self._noti(6, 'SUCCESS', 200, received=False),
            'ok_sin_received_nuevo': self._noti(7, 'SUCCESS', 5, received=False),
        }

    def _vivas(self, recs):
        ids = [r.id for r in recs.values()]
        exist = set(self.env['mercadolibre.notification'].browse(ids).exists().ids)
        return {k for k, r in recs.items() if r.id in exist}

    def test_default_90_dias(self):
        self._icp('')
        recs = self._setup()
        self.env['mercadolibre.notification']._gc_meli_notifications()
        self.assertEqual(self._vivas(recs), {'ok_nuevo', 'recv_viejo', 'proc_viejo', 'ok_sin_received_nuevo', 'fail_reintentable'})

    def test_cero_no_borra(self):
        self._icp('0')
        recs = self._setup()
        self.assertEqual(self.env['mercadolibre.notification']._gc_meli_notifications(), 0)
        self.assertEqual(self._vivas(recs), set(recs))

    def test_parametro_configurable(self):
        self._icp('7')
        recs = self._setup()
        self.env['mercadolibre.notification']._gc_meli_notifications()
        self.assertEqual(self._vivas(recs), {'recv_viejo', 'proc_viejo', 'ok_sin_received_nuevo', 'fail_reintentable'})

    def test_valor_invalido_usa_default(self):
        self._icp('abc')
        recs = self._setup()
        self.env['mercadolibre.notification']._gc_meli_notifications()
        self.assertIn('ok_nuevo', self._vivas(recs))
        self.assertNotIn('ok_viejo', self._vivas(recs))
