# -*- coding: utf-8 -*-
"""26.367 (502, 3-nov-2026) -- pack_splitted en modo LEGACY (sin politica por motivo).

Medido en un cliente FULL: ML divide el carrito, cancela la orden original y crea otra (la gemela).
La salida FULL de las dos queda 'done' al importar; la regla E3 (26.171) dejaba la original ABIERTA
por tener "salida hecha" => venta, factura (a mano) y salida de stock DOBLES.
Ahora: gemela con salida propia hecha + original SIN factura publicada => se devuelve la salida de la
original (tambien FULL) y se cancela. Con factura publicada, sin gemela o gemela sin salida: como antes.
"""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

OID = "2000019259353996"
TWIN_OID = "2000019260000001"


class _FakeMeli:
    access_token = "TEST"
    needlogin_state = False


def _oj(oid=OID):
    return {"id": int(oid), "status": "cancelled", "pack_id": 2000015789241223,
            "cancel_detail": {"code": "pack_splitted", "requested_by": "meli"},
            "payments": [{"id": 1, "status": "refunded", "status_detail": "by_admin",
                          "transaction_amount": 200.0, "total_paid_amount": 200.0,
                          "transaction_amount_refunded": 200.0}]}


@tagged("post_install", "-at_install", "meli_26367")
class TestPackSplitGemelaLegacy(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.co = cls.env.company
        cls.wh = cls.env["stock.warehouse"].search([("company_id", "=", cls.co.id)], limit=1)
        cls.cust = cls.env["res.partner"].create({"name": "Comprador ML 502"})
        cls.co.mercadolibre_return_mode = "done"
        cls.co.mercadolibre_invoice_cancel_mode = "manual"
        cls.co.mercadolibre_cancel_mode = "legacy"
        if "mercadolibre_cancel_auto_from" in cls.co._fields:
            cls.co.mercadolibre_cancel_auto_from = False
        if "mercadolibre_notification_mode" in cls.co._fields:
            cls.co.mercadolibre_notification_mode = "internal_note"
        cls.ICP = cls.env["ir.config_parameter"].sudo()
        cls.ICP.set_param("meli_oerp.cancel_reason_policy", "")
        cls.ICP.set_param("meli_oerp.cancel_return_full", "")
        cls.ICP.set_param("meli_oerp.cancel_pack_split_twin_return", "")
        cls.SO = cls.env["sale.order"]

    def setUp(self):
        super().setUp()
        p = patch.object(type(self.SO), "_meli_cancel_fetch",
                         lambda so_self, meli, path: {"error": "not_found", "status": 404})
        p.start()
        self.addCleanup(p.stop)

    def _prod(self):
        Product = self.env["product.product"]
        pvals = {"name": "P-502", "list_price": 100.0, "invoice_policy": "order"}
        if "is_storable" in Product._fields:
            pvals.update(type="consu", is_storable=True)
        elif "detailed_type" in Product._fields:
            pvals.update(detailed_type="product")
        else:
            pvals.update(type="product")
        prod = Product.create(pvals)
        self.env["stock.quant"]._update_available_quantity(prod, self.wh.lot_stock_id, 50)
        return prod

    def _mkso(self, prod, oid, deliver=True, status="cancelled"):
        so = self.SO.create({
            "partner_id": self.cust.id, "meli_order_id": oid, "meli_status": status,
            "meli_shipment_logistic_type": "fulfillment",
            "order_line": [(0, 0, {"product_id": prod.id, "product_uom_qty": 2, "price_unit": 100})]})
        so.action_confirm()
        if deliver:
            for pk in so.picking_ids:
                so._meli_validate_picking(pk)
        return so

    def _split(self, twin=True, twin_deliver=True):
        prod = self._prod()
        so = self._mkso(prod, OID)
        MO = self.env["mercadolibre.orders"]
        buyer = self.env["mercadolibre.buyers"].create({"name": "Comprador 502", "buyer_id": "502502"})
        mo1 = MO.create({"order_id": OID, "pack_id": "2000015789241223", "status": "cancelled",
                         "buyer": buyer.id, "date_created": "2026-10-31 02:31:03", "sale_order": so.id})
        self.env["mercadolibre.order_items"].create({"order_id": mo1.id, "order_item_id": "MLA502"})
        so.meli_orders = [(6, 0, mo1.ids)]
        tw = self.SO
        if twin:
            tw = self._mkso(prod, TWIN_OID, deliver=twin_deliver, status="paid")
            mo2 = MO.create({"order_id": TWIN_OID, "pack_id": "2000015790810943", "status": "paid",
                             "buyer": buyer.id, "date_created": "2026-10-31 02:58:20", "sale_order": tw.id})
            self.env["mercadolibre.order_items"].create({"order_id": mo2.id, "order_item_id": "MLA502"})
        return so, tw, prod

    def _cancel(self, so):
        return so.with_context(meli_cancel_ctx_nocache=True).meli_cancel_with_detail(
            "Orden cancelada por MercadoLibre. Motivo: pack_splitted", order_json=_oj(), meli=_FakeMeli())

    def _qty(self, prod):
        return prod.with_context(location=self.wh.lot_stock_id.id).qty_available

    def _returns(self, so):
        return self.env["stock.move"].search([
            ("origin_returned_move_id", "in", so.picking_ids.mapped("move_ids").ids)]).mapped("picking_id")

    def test_gemela_despachada_full_devuelve_y_cancela(self):
        so, tw, prod = self._split()
        self.assertEqual(self._qty(prod), 46, "doble salida antes de procesar")
        self.assertTrue(self._cancel(so))
        self.assertEqual(so.state, "cancel", "la original ya no queda como venta (ni para facturar)")
        self.assertEqual(self._returns(so).mapped("state"), ["done"], "FULL: se devuelve el duplicado")
        self.assertEqual(self._qty(prod), 48, "queda una sola salida: la de la gemela")
        self.assertIn(tw.name, so.meli_cancel_decision)
        self.assertNotEqual(tw.state, "cancel", "la gemela no se toca")

    def test_reproceso_no_duplica_devolucion(self):
        so, tw, prod = self._split()
        self.assertTrue(self._cancel(so))
        self._cancel(so)
        self.assertEqual(len(self._returns(so)), 1)
        self.assertEqual(self._qty(prod), 48)

    def test_gemela_sin_salida_queda_abierta(self):
        so, tw, prod = self._split(twin_deliver=False)
        self.assertFalse(self._cancel(so))
        self.assertNotEqual(so.state, "cancel")
        self.assertFalse(self._returns(so))
        self.assertIn("la venta queda abierta", so.meli_cancel_decision)

    def test_sin_gemela_queda_abierta(self):
        so, tw, prod = self._split(twin=False)
        self.assertFalse(self._cancel(so))
        self.assertNotEqual(so.state, "cancel")
        self.assertFalse(self._returns(so))
        self.assertIn("no se encontró la venta gemela", so.meli_cancel_decision)

    def test_con_factura_publicada_no_cancela_ni_devuelve(self):
        so, tw, prod = self._split()
        with patch.object(type(self.SO), "_meli_unresolved_posted_invoices",
                          lambda s, _c=self.cust: _c):
            self.assertFalse(self._cancel(so))
        self.assertNotEqual(so.state, "cancel", "factura publicada: decisión fiscal del vendedor")
        self.assertFalse(self._returns(so))

    def test_parametro_en_cero_comportamiento_anterior(self):
        self.ICP.set_param("meli_oerp.cancel_pack_split_twin_return", "0")
        so, tw, prod = self._split()
        self.assertFalse(self._cancel(so))
        self.assertNotEqual(so.state, "cancel")
        self.assertFalse(self._returns(so))
