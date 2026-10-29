# -*- coding: utf-8 -*-
"""26.338 (#696 sigue, staging 393 PetMarkt 19.0, 29-oct-2026): el GC de notificaciones
(_gc_meli_notifications, autovacuum) chocó con el cron 177 de órdenes: SerializationFailure en el
DELETE por lotes. El GC NO puede bloquear ni esperar a nadie.

Colisión real con conexiones aparte (los datos se commitean y se limpian al final):
  * conexión B tiene una notificación vieja `FOR UPDATE` (como el cron mientras procesa);
  * conexión D commitea un UPDATE de otra DESPUÉS de que el GC tomó su snapshot;
  * el GC corre en la conexión C con statement_timeout 8 s (si espera, revienta).
Esperado: el GC termina rápido, sin excepción, deja la bloqueada y la actualizada, y borra el resto.
Control (código anterior): espera el lock de B hasta el statement_timeout => ERROR.
Sin red. Correr:
  odoo-bin ... -u meli_oerp --test-enable --test-tags meli_gc_lock --stop-after-init
"""
import time
from datetime import timedelta

from odoo import SUPERUSER_ID, api, fields, sql_db
from odoo.tests import TransactionCase, tagged

PFX = 'testgclock-'


@tagged('post_install', '-at_install', 'meli', 'meli_696', 'meli_gc_lock')
class TestGcNotificacionesNoBloquea(TransactionCase):

    def _conn(self):
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
            cr.execute("DELETE FROM mercadolibre_notification WHERE notification_id LIKE %s", (PFX + '%',))
            cr.commit()
        finally:
            cr.close()

    def _seed(self, cr, names, days_ago=200, state='SUCCESS', topic='orders_v2', attempts=1):
        old = fields.Datetime.now() - timedelta(days=days_ago)
        ids = {}
        for name in names:
            cr.execute("""INSERT INTO mercadolibre_notification
                            (notification_id, topic, resource, state, attempts, received,
                             create_date, write_date, create_uid, write_uid)
                          VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, 1) RETURNING id""",
                       (PFX + name, topic, '/orders/' + PFX + name, state, attempts, old, old, old))
            ids[name] = cr.fetchone()[0]
        return ids

    def _exists(self, cr, ids):
        cr.execute("SELECT id FROM mercadolibre_notification WHERE id = ANY(%s)", (list(ids),))
        return {r[0] for r in cr.fetchall()}

    def test_gc_saltea_bloqueada_y_actualizada_y_borra_el_resto(self):
        self._purge()
        self.addCleanup(self._purge)
        a = self._conn()
        ids = self._seed(a, ['locked', 'upd', 'free1', 'free2', 'free3'])
        a.commit()

        b = self._conn()  # el "cron": tiene la fila tomada y no suelta
        b.execute("SELECT id FROM mercadolibre_notification WHERE id = %s FOR UPDATE", (ids['locked'],))

        c = self._conn()  # el autovacuum
        c.execute("SET LOCAL statement_timeout = '8s'")
        c.execute("SELECT count(*) FROM mercadolibre_notification")  # snapshot REPEATABLE READ tomado

        d = self._conn()  # alguien commitea un cambio de otra fila DESPUÉS del snapshot de C
        d.execute("UPDATE mercadolibre_notification SET processing_errors = 'post-snapshot' WHERE id = %s",
                  (ids['upd'],))
        d.commit()

        env = api.Environment(c, SUPERUSER_ID, {})
        t0 = time.time()
        error = None
        try:
            env['mercadolibre.notification']._gc_meli_notifications()
        except Exception as e:  # el control revienta acá (statement_timeout / serialización)
            error = e
        elapsed = time.time() - t0
        self.assertIsNone(error, 'el GC no puede fallar por una colisión: %r' % (error,))
        self.assertLess(elapsed, 5.0, 'el GC no puede quedarse esperando un lock (%.1f s)' % elapsed)
        vivas = self._exists(c, ids.values())
        self.assertEqual(vivas, {ids['locked'], ids['upd']},
                         'se saltean la bloqueada y la actualizada; el resto se borra')
        c.execute("SHOW lock_timeout")
        self.assertEqual(c.fetchone()[0], '0', 'lock_timeout restaurado al salir del GC')

    def test_gc_no_toca_working_set_del_cron_de_ordenes(self):
        self._purge()
        self.addCleanup(self._purge)
        a = self._conn()
        ids = self._seed(a, ['fail_reintentable'], state='FAILED', attempts=3)
        ids.update(self._seed(a, ['fail_agotada'], state='FAILED', attempts=24))
        ids.update(self._seed(a, ['fail_otro_topic'], state='FAILED', attempts=1, topic='items'))
        ids.update(self._seed(a, ['ok_con_hermana_viva']))
        # hermana RECEIVED del mismo resource (el cron la marca SUCCESS a ella y a sus duplicados)
        a.execute("""INSERT INTO mercadolibre_notification (notification_id, topic, resource, state, received,
                                                          create_date, write_date)
                     VALUES (%s, 'orders_v2', %s, 'RECEIVED', now(), now(), now())""",
                  (PFX + 'hermana', '/orders/' + PFX + 'ok_con_hermana_viva'))
        ids.update(self._seed(a, ['ok_tocada_hoy']))
        a.execute("UPDATE mercadolibre_notification SET write_date = now() at time zone 'UTC' WHERE id = %s",
                  (ids['ok_tocada_hoy'],))
        a.commit()

        c = self._conn()
        env = api.Environment(c, SUPERUSER_ID, {})
        env['mercadolibre.notification']._gc_meli_notifications()
        vivas = self._exists(c, ids.values())
        self.assertEqual(vivas, {ids['fail_reintentable'], ids['ok_con_hermana_viva'], ids['ok_tocada_hoy']})
