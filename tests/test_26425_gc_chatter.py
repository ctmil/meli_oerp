# -*- coding: utf-8 -*-
"""26.425 (un caso): limpieza automática del CHATTER de los modelos meli.

`mercadolibre.notification._gc_meli_chatter` (@api.autovacuum) borra mail.message 'notification' de
mercadolibre.orders / .shipment / .account más viejos que ICP meli_oerp.chatter_days (default 0 =
apagado; 1..6 => 7) y conserva lo que tiene valor: comentarios, otros modelos, adjuntos, destacados,
tracking, mail.mail, hijos, inbox sin leer y la marca meli-once. Tope por corrida meli_oerp.gc_max_rows
(también para _gc_meli_notifications, que antes tenía 10.000 fijos).
Los datos van en la transacción del test (rollback), salvo el de bloqueo, que usa conexiones aparte y
limpia al final. Sin red. Correr:
  odoo-bin ... -u meli_oerp --test-enable --test-tags meli_gc_chatter --stop-after-init
"""
import time
from datetime import timedelta

from odoo import fields, sql_db
from odoo.tests import TransactionCase, tagged

PFX = 'test26425-'


@tagged('post_install', '-at_install', 'meli', 'meli_gc_chatter')
class TestGcChatter(TransactionCase):

    def _icp(self, key, value):
        ICP = self.env['ir.config_parameter'].sudo()
        setter = getattr(ICP, 'set_str', None) or ICP.set_param  # 20.0: set_str ; 16-19: set_param
        setter(key, value)

    def setUp(self):
        super().setUp()
        self.Noti = self.env['mercadolibre.notification']
        self.order = self.env['mercadolibre.orders'].create({'name': PFX + 'order'})
        self.ship = self.env['mercadolibre.shipment'].create({'name': PFX + 'ship'})
        self.partner = self.env['res.partner'].create({'name': PFX + 'partner'})
        self._icp('meli_oerp.gc_max_rows', '')

    def _msg(self, rec, days_ago, message_type='notification', body='Sale order created (pack)!', **extra):
        vals = {
            'model': rec._name, 'res_id': rec.id, 'message_type': message_type,
            'body': body, 'date': fields.Datetime.now() - timedelta(days=days_ago),
        }
        vals.update(extra)
        return self.env['mail.message'].sudo().create(vals)

    def _vivos(self, recs):
        ids = [r.id for r in recs.values()]
        exist = set(self.env['mail.message'].sudo().browse(ids).exists().ids)
        return {k for k, r in recs.items() if r.id in exist}

    def _setup(self):
        Msg = self.env['mail.message'].sudo()
        r = {
            'ord_viejo': self._msg(self.order, 40),
            'ship_viejo': self._msg(self.ship, 40),
            'ord_nuevo': self._msg(self.order, 10),
            'ord_comment_viejo': self._msg(self.order, 40, message_type='comment', body='nota de una persona'),
            'partner_viejo': self._msg(self.partner, 40),  # otro modelo: nunca
            'ord_once_viejo': self._msg(self.order, 40, body='aviso <!-- meli-once:x-1 -->'),
        }
        att = self.env['ir.attachment'].sudo().create({'name': PFX + 'a.txt', 'raw': b'x',
                                                       'res_model': 'mercadolibre.orders', 'res_id': self.order.id})
        r['ord_adjunto_viejo'] = self._msg(self.order, 40, attachment_ids=[(6, 0, att.ids)])
        star = 'starred_partner_ids' if 'starred_partner_ids' in Msg._fields else 'bookmarked_partner_ids'
        r['ord_destacado_viejo'] = self._msg(self.order, 40, **{star: [(6, 0, self.partner.ids)]})
        r['ord_padre_viejo'] = self._msg(self.order, 40)
        r['ord_hijo_nuevo'] = self._msg(self.order, 1, parent_id=r['ord_padre_viejo'].id)
        r['ord_inbox_sin_leer_viejo'] = self._msg(self.order, 40)
        r['ord_inbox_leido_viejo'] = self._msg(self.order, 40)
        Notif = self.env['mail.notification'].sudo()
        Notif.create({'mail_message_id': r['ord_inbox_sin_leer_viejo'].id, 'res_partner_id': self.partner.id,
                      'notification_type': 'inbox', 'is_read': False})
        Notif.create({'mail_message_id': r['ord_inbox_leido_viejo'].id, 'res_partner_id': self.partner.id,
                      'notification_type': 'inbox', 'is_read': True})
        r['ord_mail_viejo'] = self._msg(self.order, 40)
        self.env['mail.mail'].sudo().create({'mail_message_id': r['ord_mail_viejo'].id, 'state': 'exception'})
        if 'mail.tracking.value' in self.env:
            TV = self.env['mail.tracking.value'].sudo()
            fref = 'field_id' if 'field_id' in TV._fields else 'field'
            fld = self.env['ir.model.fields']._get('res.partner', 'name')
            r['ord_tracking_viejo'] = self._msg(self.order, 40)
            tv = {fref: fld.id, 'mail_message_id': r['ord_tracking_viejo'].id,
                  'old_value_char': 'a', 'new_value_char': 'b'}
            for k, v in (('field_desc', 'Name'), ('field_type', 'char')):  # 16.0 los pide (NOT NULL)
                if k in TV._fields:
                    tv[k] = v
            TV.create(tv)
        return r

    BORRABLES = {'ord_viejo', 'ship_viejo', 'ord_inbox_leido_viejo'}

    def test_apagado_por_defecto(self):
        self._icp('meli_oerp.chatter_days', '')
        r = self._setup()
        self.assertEqual(self.Noti._gc_meli_chatter(), 0)
        self.assertEqual(self._vivos(r), set(r))
        self._icp('meli_oerp.chatter_days', '0')
        self.assertEqual(self.Noti._gc_meli_chatter(), 0)
        self._icp('meli_oerp.chatter_days', 'abc')  # inválido => default 0 => apagado
        self.assertEqual(self.Noti._gc_meli_chatter(), 0)
        self.assertEqual(self._vivos(r), set(r))

    def test_30_dias_borra_solo_avisos_automaticos_viejos(self):
        self._icp('meli_oerp.chatter_days', '30')
        r = self._setup()
        n = self.Noti._gc_meli_chatter()
        self.assertEqual(self._vivos(r), set(r) - self.BORRABLES)
        self.assertGreaterEqual(n, len(self.BORRABLES))
        # el hijo de un padre conservado sigue colgando de él
        self.assertEqual(r['ord_hijo_nuevo'].parent_id, r['ord_padre_viejo'])
        # la notificación de bandeja leída se fue con su mensaje (cascade)
        self.assertFalse(self.env['mail.notification'].sudo().search(
            [('mail_message_id', '=', r['ord_inbox_leido_viejo'].id)]))
        # segunda corrida: nada más para borrar de lo sembrado
        before = self._vivos(r)
        self.Noti._gc_meli_chatter()
        self.assertEqual(self._vivos(r), before)

    def test_minimo_7_dias(self):
        self._icp('meli_oerp.chatter_days', '1')
        r = {'d5': self._msg(self.order, 5), 'd10': self._msg(self.order, 10)}
        self.Noti._gc_meli_chatter()
        self.assertEqual(self._vivos(r), {'d5'})

    def test_tope_por_corrida(self):
        self._icp('meli_oerp.chatter_days', '30')
        r = {i: self._msg(self.order, 40 + i) for i in range(5)}
        self.assertEqual(self.Noti._gc_meli_chatter(batch_size=2, max_rows=3), 3)
        self.assertEqual(len(self._vivos(r)), 2)
        self._icp('meli_oerp.gc_max_rows', '1')
        self.assertEqual(self.Noti._gc_meli_chatter(), 1)
        self.assertEqual(len(self._vivos(r)), 1)

    def test_notificaciones_tope_configurable(self):
        """El GC de notificaciones toma el tope de meli_oerp.gc_max_rows (antes 500x20 fijo)."""
        self._icp('meli_oerp.notification_days', '30')
        old = fields.Datetime.now() - timedelta(days=100)
        notis = self.Noti
        for i in range(4):
            n = self.Noti.create({'notification_id': PFX + 'n%s' % i, 'topic': 'items', 'state': 'SUCCESS',
                                  'resource': '/items/' + PFX + str(i), 'received': old})
            notis |= n
        notis.flush_recordset()
        self.env.cr.execute("UPDATE mercadolibre_notification SET create_date=%s, write_date=%s WHERE id = ANY(%s)",
                            (old, old, notis.ids))
        self.Noti.invalidate_model()
        self.assertEqual(self.Noti._gc_meli_max_rows(), self.Noti._GC_MAX_ROWS_DEFAULT)
        self._icp('meli_oerp.gc_max_rows', '3')
        self.assertEqual(self.Noti._gc_meli_max_rows(), 3)
        self.Noti._gc_meli_notifications()
        self.assertEqual(len(notis.exists()), 1)
        self._icp('meli_oerp.gc_max_rows', '0')  # <= 0 o inválido => default
        self.assertEqual(self.Noti._gc_meli_max_rows(), self.Noti._GC_MAX_ROWS_DEFAULT)
        self.Noti._gc_meli_notifications()
        self.assertFalse(notis.exists())


@tagged('post_install', '-at_install', 'meli', 'meli_gc_chatter')
class TestGcChatterNoBloquea(TransactionCase):
    """Un mensaje bloqueado por otra transacción (p.ej. el cron escribiendo en esa orden) se saltea
    sin esperar; el resto se borra. Datos commiteados en conexiones aparte, limpiados al final."""

    def _cursor(self):
        cr = sql_db.db_connect(self.env.cr.dbname).cursor()
        self.addCleanup(self._close, cr)
        return cr

    @staticmethod
    def _close(cr):
        try:
            if not cr.closed:
                cr.rollback()
                cr.close()
        except Exception:
            pass

    def _purge(self):
        cr = sql_db.db_connect(self.env.cr.dbname).cursor()
        try:
            cr.execute("DELETE FROM mail_message WHERE body LIKE %s", (PFX + 'lock%',))
            cr.commit()
        finally:
            cr.close()

    def test_bloqueado_se_saltea_sin_esperar(self):
        self._purge()
        self.addCleanup(self._purge)
        old = fields.Datetime.now() - timedelta(days=60)
        seed = self._cursor()
        ids = []
        for i in range(4):
            seed.execute("""INSERT INTO mail_message (model, res_id, message_type, body, date,
                                                      create_date, write_date, create_uid, write_uid)
                            VALUES ('mercadolibre.orders', 0, 'notification', %s, %s, %s, %s, 1, 1)
                            RETURNING id""", (PFX + 'lock%s' % i, old, old, old))
            ids.append(seed.fetchone()[0])
        seed.commit()
        locker = self._cursor()
        locker.execute("SELECT id FROM mail_message WHERE id = %s FOR UPDATE", (ids[0],))
        gc = self._cursor()
        gc.execute("SET statement_timeout = '8s'")
        from odoo import api, SUPERUSER_ID
        env = api.Environment(gc, SUPERUSER_ID, {})
        ICP = env['ir.config_parameter'].sudo()
        (getattr(ICP, 'set_str', None) or ICP.set_param)('meli_oerp.chatter_days', '30')
        t0 = time.monotonic()
        env['mercadolibre.notification']._gc_meli_chatter()
        elapsed = time.monotonic() - t0
        gc.execute("SELECT id FROM mail_message WHERE id = ANY(%s)", (ids,))
        left = {r[0] for r in gc.fetchall()}
        gc.rollback()  # no dejar el ICP ni los borrados: la limpieza es _purge
        self.assertEqual(left, {ids[0]})
        self.assertLess(elapsed, 8)
