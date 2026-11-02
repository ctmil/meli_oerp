# -*- coding: utf-8 -*-
"""26.350 (#715 Score 361, regresion del #507): el flete de ML como COSTE de la linea de envio
respeta la configuracion `mercadolibre_shipping_cost_as_purchase_price`.

El control vivia solo en el repo del cliente (27-jul, 26.86/26.82 de las ramas
claude/envio-no-imputa-coste-19.0) y el sync del source 26.116 lo borro en silencio: en octubre el
margen volvio a descontar el flete (ML 2000015409155591, 'MEL Voluminoso' precio 0 / coste 653,60).

Cubre:
- el helper: sin config / sin el campo => True (nada cambia para quien no lo usa); True/False del campo;
- el camino de orden BLOQUEADA (el flete suele llegar despues de confirmar) y el camino normal,
  con el flag en True (coste = flete) y en False (coste 0, y limpia el que hubiera quedado).
"""
from unittest.mock import patch

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.meli_oerp.models import shipment as shipment_mod
from odoo.addons.meli_oerp.models.versions import meli_shipping_cost_as_purchase_price
from odoo.tests import tagged
from odoo.tests.common import BaseCase

FIELD = 'mercadolibre_shipping_cost_as_purchase_price'


class _Cfg:
    """Config minima: solo lo que mira el helper."""
    def __init__(self, fields_):
        self._fields = dict(fields_)
        for k, v in fields_.items():
            setattr(self, k, v)


@tagged('post_install', '-at_install', 'meli_26350_envio_costo')
class TestMeli26350HelperPure(BaseCase):

    def test_sin_config_o_sin_campo_imputa(self):
        self.assertTrue(meli_shipping_cost_as_purchase_price(None))
        self.assertTrue(meli_shipping_cost_as_purchase_price(_Cfg({'mercadolibre_including_shipping_cost': 'always'})))

    def test_campo_manda(self):
        self.assertTrue(meli_shipping_cost_as_purchase_price(_Cfg({FIELD: True})))
        self.assertFalse(meli_shipping_cost_as_purchase_price(_Cfg({FIELD: False})))


@tagged('post_install', '-at_install', 'meli_26350_envio_costo')
class TestMeli26350EnvioCosto(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        gfield = 'group_ids' if 'group_ids' in cls.env.user._fields else 'groups_id'
        cls.env.user.write({gfield: [(4, cls.env.ref('sales_team.group_sale_manager').id)]})
        P = cls.env['product.product']
        cls.prod = P.create({'name': 'Mancuerna 26350', 'type': 'service', 'invoice_policy': 'order',
                             'taxes_id': [(5, 0, 0)]})
        cls.ship = P.create({'name': 'MEL Voluminoso 26350', 'default_code': 'MEL Voluminoso 26350',
                             'type': 'service', 'invoice_policy': 'order', 'taxes_id': [(5, 0, 0)]})
        cls.carrier = cls.env['delivery.carrier'].create({'name': 'MEL Voluminoso 26350', 'product_id': cls.ship.id})
        co = cls.env.company
        for f, v in (('mercadolibre_order_total_config', 'paid_amount'),
                     ('mercadolibre_including_shipping_cost', 'always')):
            if f in co._fields:
                co[f] = v

    def setUp(self):
        super().setUp()
        if 'purchase_price' not in self.env['sale.order.line']._fields:
            self.skipTest('sale_margin no instalado: no hay purchase_price')

    def _venta(self, delivery_price=0.0, pp=0.0):
        tf = 'tax_ids' if 'tax_ids' in self.env['sale.order.line']._fields else 'tax_id'
        so = self.env['sale.order'].create({
            'partner_id': self.partner_a.id, 'carrier_id': self.carrier.id,
            'order_line': [(0, 0, {'product_id': self.prod.id, 'product_uom_qty': 1, 'price_unit': 2499.0, tf: [(5, 0, 0)]}),
                           (0, 0, {'product_id': self.ship.id, 'product_uom_qty': 1, 'price_unit': delivery_price,
                                   'is_delivery': True, tf: [(5, 0, 0)]})]})
        dl = so.order_line.filtered('is_delivery')
        if pp:
            dl.purchase_price = pp
        return so, dl

    def _lock(self, so):
        so.action_confirm()
        if 'locked' in so._fields:
            so.locked = True
        elif hasattr(so, 'action_done'):
            so.action_done()

    def _shipment(self, so, cost=653.60):
        return self.env['mercadolibre.shipment'].create({
            'sale_order': so.id, 'tracking_method': 'MEL Voluminoso 26350', 'mode': 'me2',
            'shipping_cost': 0.0, 'shipping_seller_cost': cost, 'shipping_list_cost': cost})

    def _run(self, sh, so, impute, order=None):
        with patch.object(shipment_mod, 'meli_shipping_cost_as_purchase_price', lambda config: impute), \
             patch.object(type(sh), '_meli_sync_picking_tracking', lambda self, sorder: None, create=True):
            sh._update_sale_order_shipping_info(order, meli=None, config=self.env.company)

    # --- orden bloqueada: el flete llega despues de confirmar ---
    def test_bloqueada_flag_true_imputa_flete(self):
        so, dl = self._venta()
        self._lock(so)
        self._run(self._shipment(so), so, True)
        self.assertAlmostEqual(dl.purchase_price, 653.60, places=2,
                               msg="flag True (default): comportamiento historico, coste = flete")

    def test_bloqueada_flag_false_no_imputa_y_limpia(self):
        so, dl = self._venta(pp=653.60)
        self._lock(so)
        self._run(self._shipment(so), so, False)
        self.assertEqual(dl.purchase_price, 0.0,
                         "flag False: el flete NO es coste y se limpia el que habia (ML 2000015409155591)")
        self.assertEqual(dl.price_unit, 0.0, "la linea de envio no se toca en precio")

    # --- camino normal (orden no bloqueada) ---
    def _run_normal(self, impute, pp=0.0):
        so, dl = self._venta(pp=pp)
        mo = self.env['mercadolibre.orders'].create({'order_id': '2000015409155591', 'name': '2000015409155591',
                                                     'sale_order': so.id})
        so.meli_orders = [(6, 0, [mo.id])]
        sh = self._shipment(so)
        SO = type(so)
        with patch.object(SO, 'meli_amount_to_invoice', lambda self, meli=None, config=None: 2499.0, create=True), \
             patch.object(type(mo), '_ensure_payment_shipping_amounts', lambda self, meli=None, config=None: None, create=True):
            self._run(sh, so, impute, order=mo)
        return so, so.order_line.filtered('is_delivery')

    def test_normal_flag_true_imputa_flete(self):
        so, dl = self._run_normal(True)
        self.assertTrue(dl, "sigue habiendo linea de envio")
        self.assertAlmostEqual(sum(dl.mapped('purchase_price')), 653.60, places=2)

    def test_normal_flag_false_no_imputa_y_limpia(self):
        so, dl = self._run_normal(False, pp=653.60)
        self.assertTrue(dl, "la linea de envio se sigue creando (se factura igual)")
        self.assertEqual(sum(dl.mapped('purchase_price')), 0.0, "flag False: coste del envio 0")
