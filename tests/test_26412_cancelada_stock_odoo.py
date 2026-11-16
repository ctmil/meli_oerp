# -*- coding: utf-8 -*-
"""26.412 (un caso) — «Al cancelarse una venta en ML» en Odoo 13, por el camino real de la
cancelación (`sale.order.confirm_ml` con meli_status 'cancelled' => action_cancel + followup).

  - default 'republish': no retiene; el producto queda pendiente de publicar después del commit
    (cr.after('commit')), sin red dentro de la transacción.
  - 'hold': la variante queda «Stock retenido en ML», `_meli_available_quantity` da 0, y con
    meli_oerp_multiple los bindings quedan con stock_update NULL (primeros en el cron).
  - sólo la transición dispara; FULL y ventas de más de 30 días no retienen.
  - «Habilitar stock en ML» saca la retención y publica.
Sin red: product_post_stock se reemplaza por un mock.
"""
import contextlib
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import SavepointCase  # Odoo 13: TransactionCase no tiene env de clase

from odoo.addons.meli_oerp.models import meli_cancel_stock as MCS


class _Registry(object):
    def __init__(self, cr):
        self.cr = cr

    def cursor(self):
        return contextlib.nullcontext(self.cr)


@tagged("post_install", "-at_install", "meli", "meli_cancel", "meli_26412_cancel_stock")
class TestCancelStockHold13(SavepointCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Comprador 26412"})
        Product = cls.env["product.product"]
        cls.product = Product.create({"name": "Corpiño 26412", "type": "product", "list_price": 100.0})
        cls.product2 = Product.create({"name": "Corpiño 26412 b", "type": "product", "list_price": 100.0})
        cls.company = cls.env.user.company_id
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

    def _cancel_por_ml(self, so):
        """El camino real 13.0: meli_oerp confirm_ml con meli_status 'cancelled'."""
        self.env["sale.order"].browse(so.id)
        from odoo.addons.meli_oerp.models.orders import sale_order as base_so
        return base_so.confirm_ml(so, meli=None, config=self.company)

    def _pending(self):
        return list(getattr(self.env.cr, MCS._PENDING_ATTR, None) or [])

    def test_default_es_republish(self):
        self.assertEqual(self.env["res.company"].new({}).mercadolibre_cancel_stock_mode, "republish")
        so = self._so()
        self._cancel_por_ml(so)
        self.assertEqual(so.state, "cancel")
        self.assertFalse(self.product.meli_stock_hold)
        self.assertIn(self.product.id, self._pending())

    def test_hold_retiene_y_da_cero(self):
        self.company.mercadolibre_cancel_stock_mode = "hold"
        so = self._so()
        self._cancel_por_ml(so)
        self.assertEqual(so.state, "cancel")
        self.assertTrue(self.product.meli_stock_hold, "la variante no quedó retenida")
        self.assertIn(so.meli_order_id, self.product.meli_stock_hold_note or "")
        self.assertEqual(self.product._meli_available_quantity(), 0)
        self.assertEqual(self.product.product_tmpl_id.meli_stock_hold_count, 1)
        self.assertIn(self.product.id, self._pending())

    def test_solo_la_transicion(self):
        self.company.mercadolibre_cancel_stock_mode = "hold"
        so = self._so()
        so.action_cancel()
        setattr(self.env.cr, MCS._PENDING_ATTR, None)
        self._cancel_por_ml(so)
        self.assertFalse(self.product.meli_stock_hold)
        self.assertFalse(self._pending())

    def test_full_y_vieja_no_retienen(self):
        self.company.mercadolibre_cancel_stock_mode = "hold"
        self._cancel_por_ml(self._so(meli_shipment_logistic_type="fulfillment"))
        self.assertFalse(self.product.meli_stock_hold)
        self._cancel_por_ml(self._so(meli_date_closed=fields.Datetime.now() - timedelta(days=40)))
        self.assertFalse(self.product.meli_stock_hold)
        self.assertIn(self.product.id, self._pending())

    def test_habilitar(self):
        self.product._meli_stock_hold_set(note="test")
        with patch.object(type(self.env["product.product"]), "product_post_stock", autospec=True) as post:
            self.product.product_tmpl_id.action_meli_stock_hold_release()
        self.assertFalse(self.product.meli_stock_hold)
        self.assertEqual(post.call_count, 1)

    def test_post_now_tope(self):
        with patch.object(type(self.env["product.product"]), "product_post_stock", autospec=True) as post:
            done = MCS.meli_stock_post_now(_Registry(self.env.cr), self.env.uid, {},
                                           [self.product.id, self.product2.id], limit=1)
        self.assertEqual(done, [self.product.id])
        self.assertEqual(post.call_count, 1)
