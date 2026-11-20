# -*- coding: utf-8 -*-
"""[un caso] Venta BLOQUEADA sin «Metodo de entrega».

Caso de produccion (un cliente, 16.0): la compania activo «Bloquear pedidos
confirmados». El modulo confirma la venta apenas el monto cierra; si en ese momento ML todavia no
asigno el servicio del envio (``pending``: sin ``tracking_method``), el alta no tiene con que elegir
el transportista y lo dejaba para la pasada siguiente. Con la venta ya en ``done`` esa pasada
salteaba todo cambio estructural: venta y albaranes quedaban SIN transportista (logistica lo
completaba a mano). Ahora el transportista se completa igual en venta y albaranes pendientes, sin
tocar lineas ni importes y sin crear transportistas.

Control: en la rama de version SIN el fix, test_1 y test_2 FALLAN; el resto pasa (no regresion).

    odoo-bin -d <db> -i meli_oerp --test-enable --test-tags meli_carrier_bloqueada --stop-after-init
"""
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

SHIP_NAME = 'MEL Distribution TCB'


@tagged('post_install', '-at_install', 'meli', 'meli_carrier_bloqueada')
class TestMeliCarrierVentaBloqueada(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        gfield = 'group_ids' if 'group_ids' in cls.env.user._fields else 'groups_id'
        cls.env.user.write({gfield: [(4, cls.env.ref('sales_team.group_sale_manager').id),
                                     (4, cls.env.ref('stock.group_stock_manager').id)]})
        cls.co = cls.env.company
        cls.partner = cls.env['res.partner'].create({'name': 'Cliente TCB'})
        P = cls.env['product.product']
        cls.prod = P.create({'name': 'Prod TCB', 'type': 'product', 'invoice_policy': 'order',
                             'taxes_id': [(5, 0, 0)]})
        cls.ship_prod = P.create({'name': 'Envio TCB', 'type': 'service', 'invoice_policy': 'order',
                                  'taxes_id': [(5, 0, 0)], 'company_id': cls.co.id})
        cls.carrier = cls.env['delivery.carrier'].create({
            'name': 'MercadoEnvios TCB', 'product_id': cls.ship_prod.id, 'company_id': cls.co.id})
        cls.env['meli_oerp.carrier.mapping'].create({
            'meli_name': SHIP_NAME, 'carrier_id': cls.carrier.id, 'company_id': cls.co.id})
        if 'mercadolibre_including_shipping_cost' in cls.co._fields:
            cls.co.mercadolibre_including_shipping_cost = 'always'

    def _venta(self):
        tf = 'tax_ids' if 'tax_ids' in self.env['sale.order.line']._fields else 'tax_id'
        so = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {'product_id': self.prod.id, 'product_uom_qty': 1, 'price_unit': 100.0,
                                   tf: [(5, 0, 0)]})]})
        mo = self.env['mercadolibre.orders'].create({'order_id': '2000099900%06d' % so.id,
                                                     'name': '2000099900%06d' % so.id, 'sale_order': so.id})
        so.meli_orders = [(6, 0, [mo.id])]
        sh = self.env['mercadolibre.shipment'].create({
            'sale_order': so.id, 'tracking_method': False, 'mode': 'me2', 'logistic_type': 'cross_docking',
            'shipping_cost': 0.0, 'shipping_seller_cost': 0.0, 'shipping_list_cost': 0.0})
        return so, mo, sh

    def _sync(self, sh, mo, so):
        with patch.object(type(so), 'meli_amount_to_invoice', lambda self, meli=None, config=None: 100.0,
                          create=True), \
             patch.object(type(mo), '_ensure_payment_shipping_amounts', lambda self, meli=None, config=None: None,
                          create=True):
            sh._update_sale_order_shipping_info(mo, meli=None, config=self.co)

    def _confirmar_y_bloquear(self, so):
        so.action_confirm()
        if so.state != 'done':
            so.action_done()
        self.assertEqual(so.state, 'done', "precondicion: venta bloqueada")
        self.assertTrue(so.picking_ids, "precondicion: la venta tiene albaranes")

    def test_1_camino_real_pending_confirmada_bloqueada(self):
        """Alta con envio pending (sin servicio) -> confirmada y bloqueada -> ML asigna el servicio."""
        so, mo, sh = self._venta()
        self._sync(sh, mo, so)
        self.assertFalse(so.carrier_id, "precondicion: sin servicio de ML no hay transportista en el alta")
        self._confirmar_y_bloquear(so)
        self.assertFalse(so.picking_ids.carrier_id, "precondicion: albaranes nacen sin transportista")
        total, nlines = so.amount_total, len(so.order_line)
        sh.tracking_method = SHIP_NAME
        self._sync(sh, mo, so)
        self.assertEqual(so.carrier_id, self.carrier, "la venta bloqueada recibe el transportista")
        for p in so.picking_ids:
            self.assertEqual(p.carrier_id, self.carrier, "albaran %s sin transportista" % p.name)
        self.assertEqual(len(so.order_line), nlines, "venta bloqueada: no se agregan lineas")
        self.assertEqual(so.amount_total, total, "venta bloqueada: el total no cambia")

    def test_2_por_nombre_sin_mapeo(self):
        so, mo, sh = self._venta()
        self._confirmar_y_bloquear(so)
        other = self.env['delivery.carrier'].create({
            'name': 'Pickit TCB', 'product_id': self.ship_prod.id, 'company_id': self.co.id})
        sh.tracking_method = 'Pickit TCB'
        self._sync(sh, mo, so)
        self.assertEqual(so.carrier_id, other)
        self.assertEqual(set(so.picking_ids.mapped('carrier_id').ids), {other.id})

    def test_3_no_pisa_transportista_cargado(self):
        so, mo, sh = self._venta()
        manual = self.env['delivery.carrier'].create({
            'name': 'A mano TCB', 'product_id': self.ship_prod.id, 'company_id': self.co.id})
        so.carrier_id = manual
        self._confirmar_y_bloquear(so)
        sh.tracking_method = SHIP_NAME
        self._sync(sh, mo, so)
        self.assertEqual(so.carrier_id, manual, "el transportista cargado (a mano o antes) no se pisa")

    def test_4_sin_transportista_existente_no_crea(self):
        so, mo, sh = self._venta()
        self._confirmar_y_bloquear(so)
        n = self.env['delivery.carrier'].with_context(active_test=False).search_count([])
        sh.tracking_method = 'Servicio Inexistente TCB'
        self._sync(sh, mo, so)
        self.assertFalse(so.carrier_id)
        self.assertEqual(self.env['delivery.carrier'].with_context(active_test=False).search_count([]), n,
                         "en venta bloqueada no se crean transportistas")

    def test_5_update_forbidden_no_se_toca(self):
        so, mo, sh = self._venta()
        self._confirmar_y_bloquear(so)
        so.meli_update_forbidden = True
        sh.tracking_method = SHIP_NAME
        self._sync(sh, mo, so)
        self.assertFalse(so.carrier_id, "venta marcada 'no actualizar desde ML': no se toca")

    def test_6_cross_docking_sin_servicio_no_hace_nada(self):
        so, mo, sh = self._venta()
        self._confirmar_y_bloquear(so)
        self._sync(sh, mo, so)
        self.assertFalse(so.carrier_id)
