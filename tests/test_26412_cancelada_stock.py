# -*- coding: utf-8 -*-
"""26.412 (un caso) — «Al cancelarse una venta en ML»: republish (default) | hold.

ML repone sola la unidad en la publicación cuando una venta se cancela. Se mide, por el camino
real de la cancelación (`_meli_cancel_finish`):
  - default 'republish': no retiene, deja el producto pendiente de publicar DESPUÉS del commit
    (callback en cr.postcommit) — nada de red dentro de la transacción.
  - 'hold': la variante queda «Stock retenido en ML» y `_meli_available_quantity` da 0; con
    meli_oerp_multiple los bindings se sellan/re-encolan (el SQL corre: si fallara, el savepoint
    deshace la retención y este test lo ve).
  - sólo la TRANSICIÓN dispara; FULL y ventas de más de 30 días no retienen.
  - «Habilitar stock en ML» saca la retención y publica; la publicación post-commit respeta el tope.
Sin red: product_post_stock se reemplaza por un mock.
"""
import contextlib
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.meli_oerp.models import meli_cancel_stock as MCS


class _Registry(object):
    """registry.cursor() que devuelve el cursor del test (el real abriría otra transacción)."""
    def __init__(self, cr):
        self.cr = cr

    def cursor(self):
        return contextlib.nullcontext(self.cr)


@tagged("post_install", "-at_install", "meli", "meli_cancel", "meli_26412_cancel_stock")
class TestCancelStockHold(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Comprador 26412"})
        Product = cls.env["product.product"]
        vals = {"name": "Corpiño 26412", "type": "consu", "list_price": 100.0}
        if "is_storable" not in Product._fields:
            vals["type"] = "product"
        else:
            vals["is_storable"] = True
        cls.product = Product.create(vals)
        cls.product2 = Product.create(dict(vals, name="Corpiño 26412 b"))
        cls.company = cls.env.company
        cls._n = 0

    def setUp(self):
        super().setUp()
        setattr(self.env.cr, MCS._PENDING_ATTR, None)
        self.company.mercadolibre_cancel_stock_mode = "republish"

    def _so(self, **kw):
        type(self)._n += 1
        vals = {
            "partner_id": self.partner.id,
            "meli_order_id": "2000041200%05d" % self._n,
            "meli_status": "cancelled",
            "order_line": [(0, 0, {"product_id": self.product.id, "product_uom_qty": 1.0, "price_unit": 100.0})],
        }
        vals.update(kw)
        so = self.env["sale.order"].create(vals)
        so.action_confirm()
        return so

    def _pending(self):
        return list(getattr(self.env.cr, MCS._PENDING_ATTR, None) or [])

    def _postcommit_runs(self):
        funcs = getattr(self.env.cr.postcommit, "_funcs", [])
        return [f for f in funcs if getattr(f, "__name__", "") == "_run"]

    def test_default_es_republish(self):
        self.assertEqual(self.env["res.company"].new({}).mercadolibre_cancel_stock_mode, "republish")
        so = self._so()
        self.assertTrue(so._meli_cancel_finish("ML canceló (test)"))
        self.assertEqual(so.state, "cancel")
        self.assertFalse(self.product.meli_stock_hold)
        self.assertIn(self.product.id, self._pending(), "no quedó pendiente de publicar")
        self.assertTrue(self._postcommit_runs(), "la publicación no quedó para después del commit")

    def test_hold_retiene_y_da_cero(self):
        self.company.mercadolibre_cancel_stock_mode = "hold"
        so = self._so()
        self.assertTrue(so._meli_cancel_finish("ML canceló (test)"))
        self.assertTrue(self.product.meli_stock_hold, "la variante no quedó retenida")
        self.assertTrue(self.product.meli_stock_hold_date)
        self.assertIn(so.meli_order_id, self.product.meli_stock_hold_note or "")
        self.assertEqual(self.product._meli_available_quantity(), 0)
        self.assertIn(self.product.id, self._pending())
        self.assertEqual(self.product.product_tmpl_id.meli_stock_hold_count, 1)
        self.assertTrue(self.env["product.product"].search([("meli_stock_hold", "=", True), ("id", "=", self.product.id)]))

    def test_solo_la_transicion(self):
        self.company.mercadolibre_cancel_stock_mode = "hold"
        so = self._so()
        so._meli_action_cancel()
        self.assertEqual(so.state, "cancel")
        setattr(self.env.cr, MCS._PENDING_ATTR, None)
        so._meli_cancel_finish("ya estaba cancelada")
        self.assertFalse(self.product.meli_stock_hold)
        self.assertFalse(self._pending())

    def test_full_y_vieja_no_retienen(self):
        self.company.mercadolibre_cancel_stock_mode = "hold"
        so = self._so(meli_shipment_logistic_type="fulfillment")
        so._meli_cancel_finish("full")
        self.assertFalse(self.product.meli_stock_hold)
        so2 = self._so(meli_date_closed=fields.Datetime.now() - timedelta(days=40))
        so2._meli_cancel_finish("vieja")
        self.assertFalse(self.product.meli_stock_hold)
        self.assertIn(self.product.id, self._pending(), "la vieja igual republica")

    def test_habilitar(self):
        self.product._meli_stock_hold_set(note="test")
        self.assertTrue(self.product.meli_stock_hold)
        with patch.object(type(self.env["product.product"]), "product_post_stock", autospec=True) as post:
            self.product.product_tmpl_id.action_meli_stock_hold_release()
        self.assertFalse(self.product.meli_stock_hold)
        self.assertEqual(post.call_count, 1)

    def test_post_now_tope_y_cursor_propio(self):
        with patch.object(type(self.env["product.product"]), "product_post_stock", autospec=True) as post:
            done = MCS.meli_stock_post_now(_Registry(self.env.cr), self.env.uid, {},
                                           [self.product.id, self.product2.id], limit=1)
        self.assertEqual(done, [self.product.id])
        self.assertEqual(post.call_count, 1)
