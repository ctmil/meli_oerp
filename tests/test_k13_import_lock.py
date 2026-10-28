# -*- coding: utf-8 -*-
"""#caso-K13 -- la MISMA orden de ML importada por dos procesos a la vez no crea dos ventas.

Medido en produccion (Odoo 18, octubre 2026): el barrido de `Cron Meli Orders` y
`Meli Process Order Notifications` importaron la misma orden en paralelo y quedaron DOS
mercadolibre.orders, dos envios y dos sale.order. Se reproducen aca los dos mecanismos con una
SEGUNDA conexion real a Postgres (no se puede con un solo cursor de test):

* b) el otro proceso la esta importando AHORA (tiene el lock) ⇒ esta pasada la saltea.
* c) el otro proceso ya la COMMITEO despues de nuestro snapshot (REPEATABLE READ: el search no la
  ve) ⇒ esta pasada la saltea en vez de crear la segunda venta.

La carrera completa con dos imports reales que commitean esta en `shell_import_race_same_order.py`.
"""
from odoo import sql_db
from odoo.tests import tagged

from .test_import_cupon_linea import TestImportCuponLinea, _order_json
from ..models.import_lock import PARALLEL_TAG, _key64

ROUTES = [('/items/', {'id': 'MLM000TEST'})]


@tagged('post_install', '-at_install', 'meli', 'meli_K13_lock')
class TestImportLockK13(TestImportCuponLinea):

    # no re-ejecutar los tests heredados
    test_1_new_order_seller_coupon_line_is_net = None
    test_1_coupon_only_in_payments_still_fetches_discounts = None
    test_1_pack_member_coupon_only_in_payments_does_not_fetch = None
    test_6_resync_does_not_add_line_to_confirmed_sale = None

    def _sos(self, oid):
        return self.env['sale.order'].search([('meli_order_id', '=', str(oid))])

    def _mos(self, oid):
        return self.env['mercadolibre.orders'].search([('order_id', '=', str(oid))])

    def _other_connection(self):
        cr = sql_db.db_connect(self.env.cr.dbname).cursor()
        self.addCleanup(cr.close)
        return cr

    def test_a_same_transaction_twice_one_sale(self):
        """Dos pasadas en la MISMA transaccion (el lock es re-entrante): una venta, una orden."""
        oid = 2000215884134036
        oj = _order_json(oid=oid, unit=500.0, paid=500.0, coupon=0)
        res1, _m = self._run(oj, ROUTES)
        res2, _m = self._run(_order_json(oid=oid, unit=500.0, paid=500.0, coupon=0), ROUTES)
        self.assertNotIn(PARALLEL_TAG, str(res1))
        self.assertNotIn(PARALLEL_TAG, str(res2))
        self.assertEqual(len(self._sos(oid)), 1)
        self.assertEqual(len(self._mos(oid)), 1)

    def test_b_other_process_holds_the_order(self):
        """Otro proceso tiene la orden tomada: esta pasada no crea nada y devuelve SKIP."""
        oid = 2000069034869019
        other = self._other_connection()
        other.execute("SELECT pg_advisory_lock(%s)", (_key64(str(oid)),))
        self.addCleanup(other.execute, "SELECT pg_advisory_unlock_all()")
        res, _m = self._run(_order_json(oid=oid, unit=500.0, paid=500.0, coupon=0), ROUTES)
        self.assertIn(PARALLEL_TAG, str(res))
        self.assertFalse(self._sos(oid))
        self.assertFalse(self._mos(oid))

    def test_b_other_process_holds_the_cart(self):
        """Otra orden del MISMO carrito se esta importando: el carrito se serializa entero."""
        oid, pack = 2000501410124481, 2000708010532469
        other = self._other_connection()
        other.execute("SELECT pg_advisory_lock(%s)", (_key64(str(pack)),))
        self.addCleanup(other.execute, "SELECT pg_advisory_unlock_all()")
        oj = _order_json(oid=oid, unit=500.0, paid=500.0, coupon=0)
        oj['pack_id'] = pack
        res, _m = self._run(oj, ROUTES)
        self.assertIn(PARALLEL_TAG, str(res))
        self.assertFalse(self._mos(oid))

    def test_c_committed_after_our_snapshot(self):
        """El otro proceso COMMITEO la orden despues de nuestro snapshot: no se crea la segunda."""
        oid = 2000958936354088
        self.env.cr.execute("SELECT 1")  # nuestro snapshot ya esta tomado (como en el barrido)
        other = self._other_connection()
        other.execute("INSERT INTO mercadolibre_orders (order_id, name) VALUES (%s, %s) RETURNING id",
                      (str(oid), 'ML %s (otro proceso)' % oid))
        new_id = other.fetchone()[0]
        other.commit()

        def _cleanup():
            other.execute("DELETE FROM mercadolibre_orders WHERE id = %s", (new_id,))
            other.commit()
        self.addCleanup(_cleanup)

        self.assertFalse(self._mos(oid), "precondicion: nuestro snapshot no ve la fila del otro proceso")
        res, _m = self._run(_order_json(oid=oid, unit=500.0, paid=500.0, coupon=0), ROUTES)
        self.assertIn(PARALLEL_TAG, str(res))
        self.assertFalse(self._sos(oid), "se creo la segunda venta de una orden ya importada por otro proceso")
