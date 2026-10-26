# -*- coding: utf-8 -*-
# 26.313 — compat de stock.move._action_assign con overrides AJENOS sin `force_qty`.
# Caso real (158 Elvimarta, 26-oct-2026): MRO meli_oerp_multiple -> shopify_ept._action_assign(self) -> meli_oerp -> mrp -> stock.
# Desde 26.302 el suite pasaba force_qty=... SIEMPRE a super() => TypeError en cada reserva => ventas sin confirmar.
# El test pone, justo debajo de la clase de meli_oerp en el MRO, un _action_assign(self) SIN el parametro.
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'meli_26313')
class TestActionAssignCompatTerceros(TransactionCase):

    def _clase_debajo(self):
        """Primera clase del MRO de stock.move que define _action_assign DEBAJO de la de meli_oerp."""
        mro = type(self.env['stock.move']).__mro__
        idx = [i for i, c in enumerate(mro)
               if c.__module__.startswith('odoo.addons.meli_oerp.') and '_action_assign' in c.__dict__]
        self.assertTrue(idx, "meli_oerp no sobreescribe stock.move._action_assign")
        for c in mro[idx[0] + 1:]:
            if '_action_assign' in c.__dict__:
                return c
        self.fail("no hay _action_assign debajo de meli_oerp en el MRO")

    def test_override_ajeno_sin_force_qty_no_revienta(self):
        llamadas = []

        def ajeno_sin_force_qty(self_moves):  # firma de shopify_ept / producteca
            llamadas.append(len(self_moves))
            return True

        with patch.object(self._clase_debajo(), '_action_assign', ajeno_sin_force_qty):
            # sin force_qty (camino normal: confirmar venta, reservar)
            self.env['stock.move']._action_assign()
            # y por el camino con contexto que salta el update ML
            self.env['stock.move'].with_context(meli_skip_stock_update=True)._action_assign()
        self.assertEqual(len(llamadas), 2, "el override ajeno tiene que recibir la llamada (sin TypeError)")

    def test_force_qty_con_valor_se_sigue_reenviando(self):
        recibido = []

        def core_con_force_qty(self_moves, force_qty=False):  # firma del core / mrp
            recibido.append(force_qty)
            return True

        with patch.object(self._clase_debajo(), '_action_assign', core_con_force_qty):
            self.env['stock.move']._action_assign(force_qty=3.0)
            self.env['stock.move']._action_assign()
        self.assertEqual(recibido, [3.0, False], "force_qty con valor debe llegar a super(); sin valor, el default")
