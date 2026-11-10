# -*- coding: utf-8 -*-
"""26.391 -- orden de ML PAGADA con unit_price / total_amount / paid_amount = null.

ML puede devolver una orden pagada con esos tres campos en null mientras el pago aprobado
si trae transaction_amount. Antes: _set_product_unit_price hacia float(None) => TypeError
=> la importacion de la orden fallaba, la venta quedaba en presupuesto, total 0 y SIN
lineas, y cada reimportacion repetia el error. Ademas el motivo de meli_confirm_ready
decia "producto no encontrado (SKU sin vincular)" aunque el SKU si matcheaba.

Sin red: ML simulado con _FakeMeli (como test_import_cupon_linea).
Control: en la rama de version SIN el fix, test_1/test_2/test_4/test_5 dan ERROR.
"""
from unittest.mock import patch

from odoo.tests import common, tagged
from odoo.tools import mute_logger

from .test_import_cupon_linea import _FakeMeli, _MPNoDisponible, _order_json

OID = 2000052391000001
OID_MULTI = 2000052391000002
ITEM_A = 'MLM26391A'
ITEM_B = 'MLM26391B'
_MUTE = ('odoo.addons.meli_oerp_multiple.models.sale', 'odoo.addons.meli_oerp.models.orders',
         'odoo.addons.meli_oerp.models.shipment')


@tagged('post_install', '-at_install', 'meli', 'meli_26391')
class TestUnitPriceNulo(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        pricelist = cls.env['product.pricelist'].search([], limit=1) or cls.env['product.pricelist'].create({'name': 'Lista ML'})
        cls.company.mercadolibre_pricelist = pricelist
        cls.contact = cls.env['res.partner'].create({'name': 'Cliente ML'})
        if 'mercadolibre_contact_partner' in cls.company._fields:
            cls.company.mercadolibre_contact_partner = cls.contact
        if 'mercadolibre_cron_get_orders_shipment_client' in cls.company._fields:
            cls.company.mercadolibre_cron_get_orders_shipment_client = True
        if 'mercadolibre_create_product_from_order' in cls.company._fields:
            cls.company.mercadolibre_create_product_from_order = False
        if 'mercadolibre_notification_mode' in cls.company._fields:
            cls.company.mercadolibre_notification_mode = 'internal_note'
        cls.company.mercadolibre_order_confirmation = 'manual'
        cls.prod_a = cls.env['product.product'].create({
            'name': 'Producto A', 'taxes_id': [(5, 0, 0)], 'meli_id': ITEM_A, 'default_code': 'SKU-26391-A'})
        cls.prod_b = cls.env['product.product'].create({
            'name': 'Producto B', 'taxes_id': [(5, 0, 0)], 'meli_id': ITEM_B, 'default_code': 'SKU-26391-B'})

    # -- helpers ---------------------------------------------------------------------------
    def _item(self, item_id, sku, qty=1, unit=None):
        return {'item': {'id': item_id, 'title': 'Producto %s' % item_id[-1], 'variation_id': None,
                         'seller_sku': sku, 'category_id': 'MLM1'},
                'quantity': qty, 'unit_price': unit, 'full_unit_price': unit, 'currency_id': 'MXN'}

    def _oj_null(self, oid=OID, paid=205.90, items=None):
        """La forma medida en ML: total_amount, paid_amount y unit_price en null; pago aprobado."""
        oj = _order_json(oid=oid, unit=paid, paid=paid, coupon=0.0, item=ITEM_A)
        oj['total_amount'] = None
        oj['paid_amount'] = None
        oj['order_items'] = items or [self._item(ITEM_A, 'SKU-26391-A')]
        oj['payments'][0]['order_id'] = oid
        return oj

    def _routes(self, oid):
        return [('/orders/%s/discounts' % oid, {'details': []}),
                ('/items/%s' % ITEM_A, {'id': ITEM_A, 'title': 'Producto A'}),
                ('/items/%s' % ITEM_B, {'id': ITEM_B, 'title': 'Producto B'})]

    def _import(self, order_json):
        with patch('odoo.addons.meli_oerp.models.orders.requests.get', return_value=_MPNoDisponible()), \
                mute_logger(*_MUTE):
            return self.env['mercadolibre.orders'].orders_update_order_json(
                {'id': False, 'order_json': order_json}, meli=_FakeMeli(self._routes(order_json['id'])),
                config=self.company)

    def _so(self, oid):
        so = self.env['sale.order'].search([('meli_order_id', '=', str(oid))], limit=1)
        self.assertTrue(so, "no se creo la venta")
        return so

    def _lines(self, so):
        return so.order_line.filtered(lambda l: not getattr(l, 'is_delivery', False) and not l.display_type)

    def _chatter(self, so):
        return " ".join(m.body or '' for m in so.message_ids)

    # -- tests -----------------------------------------------------------------------------
    def test_1_un_item_precio_del_pago(self):
        """unit_price null + pago aprobado 205.90 => venta con linea y precio = pagado."""
        res = self._import(self._oj_null())
        self.assertFalse(isinstance(res, dict) and res.get('error'), res)
        so = self._so(OID)
        lines = self._lines(so)
        self.assertEqual(len(lines), 1, "la venta quedo sin lineas")
        self.assertEqual(lines.product_id, self.prod_a)
        self.assertAlmostEqual(lines.price_unit, 205.90, places=2)
        self.assertAlmostEqual(so.meli_paid_amount, 205.90, places=2)
        self.assertIn("se tomó del pago aprobado", self._chatter(so))
        mo = self.env['mercadolibre.orders'].search([('order_id', '=', str(OID))], limit=1)
        self.assertAlmostEqual(float(mo.order_items[0].unit_price), 205.90, places=2)

    def test_2_un_item_cantidad_dos_prorratea(self):
        oj = self._oj_null(paid=300.0, items=[self._item(ITEM_A, 'SKU-26391-A', qty=2)])
        self._import(oj)
        lines = self._lines(self._so(OID))
        self.assertEqual(len(lines), 1)
        self.assertAlmostEqual(lines.price_unit, 150.0, places=2)
        self.assertAlmostEqual(lines.product_uom_qty, 2.0)

    def test_3_reimport_idempotente(self):
        """Reimportar la misma orden no duplica la linea ni cambia el precio."""
        self._import(self._oj_null())
        self._import(self._oj_null())
        lines = self._lines(self._so(OID))
        self.assertEqual(len(lines), 1)
        self.assertAlmostEqual(lines.price_unit, 205.90, places=2)

    def test_4_varios_items_sin_precio_no_inventa(self):
        """Dos items sin precio por item: no se reparte el pago. Lineas a 0 con aviso, sin excepcion,
        y la venta NO queda lista para confirmar (motivo explicito)."""
        items = [self._item(ITEM_A, 'SKU-26391-A'), self._item(ITEM_B, 'SKU-26391-B')]
        res = self._import(self._oj_null(oid=OID_MULTI, paid=500.0, items=items))
        self.assertFalse(isinstance(res, dict) and res.get('error'), res)
        so = self._so(OID_MULTI)
        lines = self._lines(so)
        self.assertEqual(set(lines.mapped('product_id').ids), {self.prod_a.id, self.prod_b.id})
        for l in lines:
            self.assertEqual(l.price_unit, 0.0)
        self.assertFalse(any(l.price_unit < 0 for l in so.order_line))
        self.assertIn("ML no informó el precio del ítem", self._chatter(so))
        ready, reason = so.meli_confirm_ready(config=self.company)
        self.assertFalse(ready)
        self.assertIn("no informó el precio", reason)
        self.assertNotIn("SKU sin vincular", reason)

    def test_5_set_product_unit_price_none(self):
        """El metodo de precio no levanta con unit_price None (precio 0, nunca negativo)."""
        mo = self.env['mercadolibre.orders'].create({'order_id': str(OID + 8), 'status': 'paid',
                                                     'name': 'MO 26391'})
        upd = mo._set_product_unit_price(product_related_obj=self.prod_a,
                                         Item={'unit_price': None, 'quantity': 1, 'item': {'id': ITEM_A}},
                                         config=self.company)
        self.assertEqual(upd['price_unit'], 0.0)

    def test_6_motivo_sin_lineas_distingue(self):
        """Venta sin lineas con SKU vinculado y sin precio de ML: el motivo NO dice "SKU sin vincular"."""
        mo = self.env['mercadolibre.orders'].create({'order_id': str(OID + 9), 'status': 'paid',
                                                     'name': 'MO 26391 b'})
        self.env['mercadolibre.order_items'].create({'order_id': mo.id, 'order_item_id': ITEM_A,
                                                     'product_id': self.prod_a.id, 'quantity': 1,
                                                     'seller_sku': 'SKU-26391-A'})
        so = self.env['sale.order'].create({'partner_id': self.contact.id, 'meli_orders': [(6, 0, mo.ids)]})
        ready, reason = so.meli_confirm_ready(config=self.company)
        self.assertFalse(ready)
        self.assertIn("no informó el precio", reason)
        self.assertNotIn("SKU sin vincular", reason)
        # y sin producto vinculado sigue diciendo SKU sin vincular
        mo.order_items.product_id = False
        ready, reason = so.meli_confirm_ready(config=self.company)
        self.assertIn("SKU sin vincular", reason)

    def test_7_fill_respeta_orden_normal_y_pagos_ajenos(self):
        Orders = self.env['mercadolibre.orders']
        normal = _order_json(oid=OID, unit=100.0, paid=100.0, coupon=0.0, item=ITEM_A)
        out = Orders._meli_fill_missing_amounts(normal)
        self.assertEqual(out['order_items'][0]['unit_price'], 100.0)
        self.assertNotIn('_meli_unit_price_from_payment', out['order_items'][0])
        ajeno = self._oj_null()
        ajeno['payments'][0]['order_id'] = OID + 99  # pago de otra orden (pack): no se usa
        out = Orders._meli_fill_missing_amounts(ajeno)
        self.assertIsNone(out['order_items'][0]['unit_price'])
        self.assertTrue(out['order_items'][0].get('_meli_unit_price_missing'))
