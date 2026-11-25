# -*- coding: utf-8 -*-
"""26.453 (un caso): el aviso de venta cancelada por ML, UNA vez.

Antes, `_meli_cancel_finish` posteaba `cancel_msg` («Orden cancelada por MercadoLibre. Motivo: …»)
siempre que la venta quedara en 'cancel' — también cuando YA estaba cancelada. Y la sincronización
(`confirm_ml`) entra a `meli_cancel_with_detail` con meli_status='cancelled' sin mirar el estado
de la venta ⇒ el mismo aviso en cada sync. Igual el hermano «No se pudo cancelar la orden
automáticamente…», que el cron repetía mientras la venta no pudiera cancelarse.

Control: en la rama de versión SIN el fix, test_dos_syncs_un_aviso, test_finish_dos_veces_un_aviso,
test_venta_vieja_sin_marca_no_repite y test_fallo_dos_veces_un_aviso FALLAN.

    odoo-bin -d <db> -i meli_oerp --test-enable --test-tags meli_26453 --stop-after-init
"""
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

MSG = "Orden cancelada por MercadoLibre. Motivo: buyer_cancel_26453"
FAIL = "No se pudo cancelar la orden automáticamente"


@tagged("post_install", "-at_install", "meli", "meli_cancel", "meli_26453")
class TestCanceladaAvisoUnaVez(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        gfield = 'group_ids' if 'group_ids' in cls.env.user._fields else 'groups_id'
        cls.env.user.write({gfield: [(4, cls.env.ref('sales_team.group_sale_manager').id)]})
        cls.partner = cls.env["res.partner"].create({"name": "Comprador 26453"})
        cls.product = cls.env["product.product"].create({
            "name": "Servicio 26453", "type": "service", "list_price": 100.0, "invoice_policy": "order"})
        cls._n = 0

    def _so(self):
        type(self)._n += 1
        so = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "meli_order_id": "2000045300%05d" % self._n,
            "meli_status": "cancelled",
            "meli_status_detail": "buyer_cancel_26453",
            "order_line": [(0, 0, {"product_id": self.product.id, "product_uom_qty": 1.0, "price_unit": 100.0})],
        })
        so.action_confirm()
        return so

    def _count(self, so, text):
        return self.env["mail.message"].search_count([
            ("model", "=", "sale.order"), ("res_id", "=", so.id), ("body", "like", text)])

    # --- camino real: la sincronización de una venta cancelada en ML, dos veces seguidas ---
    def test_dos_syncs_un_aviso(self):
        so = self._so()
        so.confirm_ml()
        self.assertEqual(so.state, "cancel", "precondición: la primera sync cancela la venta")
        self.assertEqual(self._count(so, MSG), 1, "primera sync: el aviso se escribe")
        so.confirm_ml()
        so.confirm_ml()
        self.assertEqual(self._count(so, MSG), 1, "tres syncs => UN solo aviso de cancelación")

    def test_finish_dos_veces_un_aviso(self):
        so = self._so()
        self.assertTrue(so._meli_cancel_finish(MSG))
        self.assertTrue(so._meli_cancel_finish(MSG), "sigue devolviendo True: la venta está cancelada")
        self.assertEqual(self._count(so, MSG), 1)

    def test_transicion_sigue_avisando(self):
        """La cancelación real se sigue dejando escrita (no se apagó el aviso, se des-duplicó)."""
        so = self._so()
        so._meli_cancel_finish(MSG)
        self.assertEqual(so.state, "cancel")
        self.assertEqual(self._count(so, MSG), 1)

    def test_venta_vieja_sin_marca_no_repite(self):
        """Venta cancelada antes de 26.453: el aviso ya está SIN marca => no se reabre la ronda."""
        so = self._so()
        so._meli_action_cancel()
        self.assertEqual(so.state, "cancel")
        so.message_post(body=MSG)  # como lo dejaba el código anterior
        so._meli_cancel_finish(MSG)
        so._meli_cancel_finish(MSG)
        self.assertEqual(self._count(so, MSG), 1)

    def test_ya_cancelada_sin_aviso_avisa_una_vez(self):
        """Cancelada a mano en Odoo (sin aviso de ML): el motivo de ML se deja UNA vez."""
        so = self._so()
        so._meli_action_cancel()
        so._meli_cancel_finish(MSG)
        so._meli_cancel_finish(MSG)
        self.assertEqual(self._count(so, MSG), 1)

    def test_fallo_dos_veces_un_aviso(self):
        so = self._so()
        with patch.object(type(so), "_meli_action_cancel", side_effect=UserError("bloqueo 26453")):
            self.assertFalse(so._meli_cancel_finish(MSG))
            self.assertFalse(so._meli_cancel_finish(MSG))
        self.assertEqual(so.state, "sale")
        self.assertEqual(self._count(so, FAIL), 1, "el error de cancelación se avisa UNA vez")
        self.assertEqual(self._count(so, MSG), 1, "y el «no pudo cancelarse» (once_key previo) también una vez")
