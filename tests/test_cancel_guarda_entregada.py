# -*- coding: utf-8 -*-
"""26.335 (29-oct-2026) — el modo legacy NO cancela sola una venta cuyo envío de ML figura
ENTREGADO o cuyo pago sigue ACREDITADO al vendedor.

Caso de producción: tras el deploy, el barrido de cancelaciones a medio aplicar
(`_orders_redrain_pending_cancels`, sin red) recorrió el backlog de pedidos que ML marca
`cancelled` y canceló en Odoo, entre otras, una venta con el envío ENTREGADO. En legacy la
única condición era `status == cancelled`. Ahora queda retenida (meli_cancel_held + nota) y
la acción manual "procesar cancelación" la fuerza.
"""
from datetime import timedelta

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

LOGGER = "odoo.addons.meli_oerp.models.orders"


@tagged("post_install", "-at_install", "meli", "meli_cancel", "meli_cancel_guarda_entregada")
class TestCancelGuardaEntregada(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        co = cls.env.company
        for fname, val in (("mercadolibre_cancel_mode", "legacy"),
                           ("mercadolibre_cancel_auto_from", False),
                           ("mercadolibre_notification_mode", "internal_note"),
                           ("mercadolibre_return_mode", "done"),
                           ("mercadolibre_invoice_cancel_mode", "manual")):
            if fname in co._fields:
                co[fname] = val
        cls.env["ir.config_parameter"].sudo().set_param("meli_oerp.cancel_reason_policy", "")
        cls.partner = cls.env["res.partner"].create({"name": "Comprador guarda entregada"})
        Product = cls.env["product.product"]
        vals = {"name": "Producto guarda entregada", "type": "consu", "list_price": 100.0}
        if "is_storable" not in Product._fields:
            vals["type"] = "product"
        cls.product = Product.create(vals)
        cls._n = 0

    def _sale(self, ship_status=None, ship_substatus=None):
        type(self)._n += 1
        oid = "20000386670%05d" % self._n
        so = self.env["sale.order"].create({
            "partner_id": self.partner.id, "meli_order_id": oid, "meli_status": "cancelled",
            "meli_cancel_date": fields.Datetime.now(),
            "order_line": [(0, 0, {"product_id": self.product.id, "product_uom_qty": 1.0,
                                   "price_unit": 100.0})],
        })
        so.action_confirm()
        mo = self.env["mercadolibre.orders"].create({
            "order_id": oid, "status": "cancelled", "sale_order": so.id,
            "date_created": fields.Datetime.now(),
        })
        if ship_status:
            sh = self.env["mercadolibre.shipment"].create({
                "sale_order": so.id, "shipping_id": "4824%07d" % self._n,
                "status": ship_status, "substatus": ship_substatus or False,
            })
            so.meli_shipment = sh
            mo.shipment = sh
        return so, mo

    def _redrain(self):
        return self.env["mercadolibre.orders"]._orders_redrain_pending_cancels()

    # ------------------------------------------------------------- el caso
    def test_01_redrain_no_cancela_envio_entregado(self):
        so, _mo = self._sale("delivered")
        with self.assertLogs(LOGGER, level="WARNING") as cm:
            res = self._redrain()
        self.assertNotEqual(so.state, "cancel", "una venta con el envío ENTREGADO no se cancela sola")
        self.assertTrue(so.meli_cancel_held, "queda retenida para decisión manual")
        self.assertTrue(any("MELI_CANCEL_HOLD_DELIVERED" in m for m in cm.output), cm.output)
        self.assertGreaterEqual(res.get("pending", 0), 1)
        # idempotente: la segunda pasada tampoco la cancela
        self._redrain()
        self.assertNotEqual(so.state, "cancel")

    def test_02_control_envio_cancelado_si_se_cancela(self):
        so, _mo = self._sale("cancelled")
        self._redrain()
        self.assertEqual(so.state, "cancel", "control positivo: envío que nunca salió => se cancela")
        self.assertFalse(so.meli_cancel_held)

    def test_03_entregado_y_vuelto_si_se_cancela(self):
        so, _mo = self._sale("delivered", "returned_to_sender")
        self._redrain()
        self.assertEqual(so.state, "cancel", "la mercadería volvió: la guarda no retiene")

    def test_04_pago_acreditado_fresco_retiene(self):
        so, _mo = self._sale("cancelled")
        oj = {"id": int(so.meli_order_id), "status": "cancelled",
              "cancel_detail": {"code": "buyer_regretted"},
              "payments": [{"id": 9, "status": "approved", "status_detail": "accredited",
                            "transaction_amount": 100.0, "total_paid_amount": 100.0,
                            "transaction_amount_refunded": 0.0}]}
        with self.assertLogs(LOGGER, level="WARNING"):
            self.assertFalse(so.meli_cancel_with_detail("Orden cancelada por MercadoLibre.", order_json=oj))
        self.assertNotEqual(so.state, "cancel")
        oj["payments"][0].update(status="refunded", transaction_amount_refunded=100.0)
        self.assertTrue(so.meli_cancel_with_detail("Orden cancelada por MercadoLibre.", order_json=oj))
        self.assertEqual(so.state, "cancel", "reintegrado: se cancela como siempre")

    def test_05_pago_local_viejo_no_retiene(self):
        """Un pago local `approved` modificado ANTES de la cancelación puede estar viejo
        (el barrido no lo refresca): no retiene por sí solo."""
        so, mo = self._sale("cancelled")
        self.env["mercadolibre.payments"].create({
            "order_id": mo.id, "payment_id": "77", "status": "approved",
            "date_last_modified": so.meli_cancel_date - timedelta(days=2),
        })
        self._redrain()
        self.assertEqual(so.state, "cancel")

    def test_06_accion_manual_fuerza(self):
        so, _mo = self._sale("delivered")
        with self.assertLogs(LOGGER, level="WARNING"):
            self._redrain()
        self.assertTrue(so.meli_cancel_held)
        so.action_meli_cancel_process_held()
        self.assertEqual(so.state, "cancel", "la acción manual es la decisión humana: cancela")
        self.assertFalse(so.meli_cancel_held)
