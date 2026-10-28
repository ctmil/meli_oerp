# -*- coding: utf-8 -*-
"""[caso-K02, 26.307] Linea de envio ML en $0 que quedaba "A facturar" en una venta ya facturada.

Caso de produccion (caso-K02 cliente H, SO ML 2000402644338137, 25-oct-2026): factura del producto
posteada; ML informa despues un envio de 51.222,31 y el guard de venta facturada frena el cambio
de precio (la linea sigue en $0), pero la rama "envio con precio" de shipment.py escribia igual
qty_to_invoice=1 directo sobre el campo calculado => linea $0 "A facturar" y pedido "A facturar".
Un "Crear factura" manual habria armado una factura con UNA linea de envio de $0.
"""
import importlib.util
import os
from unittest.mock import patch

from odoo import release
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.modules.module import get_module_path
from odoo.tests import tagged


@tagged('post_install', '-at_install', 'meli_K02_envio')
class TestMeliK02EnvioAFacturar(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        gfield = 'group_ids' if 'group_ids' in cls.env.user._fields else 'groups_id'
        cls.env.user.write({gfield: [(4, cls.env.ref('sales_team.group_sale_manager').id)]})
        P = cls.env['product.product']
        cls.prod = P.create({'name': 'Deposito K02', 'type': 'service', 'invoice_policy': 'order',
                             'taxes_id': [(5, 0, 0)]})
        cls.ship = P.create({'name': 'ME1 - zip K02', 'default_code': 'ENVIO-ME1-K02', 'type': 'service',
                             'invoice_policy': 'delivery', 'taxes_id': [(5, 0, 0)]})
        cls.carrier = cls.env['delivery.carrier'].create({'name': 'ME1 - zip K02', 'product_id': cls.ship.id})
        co = cls.env.company
        if 'mercadolibre_protect_invoiced_orders' in co._fields:
            co.mercadolibre_protect_invoiced_orders = True
        if 'mercadolibre_including_shipping_cost' in co._fields:
            co.mercadolibre_including_shipping_cost = 'always'

    def _venta_facturada(self, ref, ship_price=0.0):
        tf = 'tax_ids' if 'tax_ids' in self.env['sale.order.line']._fields else 'tax_id'
        so = self.env['sale.order'].create({
            'partner_id': self.partner_a.id, 'meli_order_id': ref, 'carrier_id': self.carrier.id,
            'order_line': [
                (0, 0, {'product_id': self.prod.id, 'product_uom_qty': 1, 'price_unit': 738677.69, tf: [(5, 0, 0)]}),
                (0, 0, {'product_id': self.ship.id, 'product_uom_qty': 1, 'price_unit': ship_price,
                        'is_delivery': True, tf: [(5, 0, 0)]}),
            ]})
        so.action_confirm()
        inv = so._create_invoices()
        inv.action_post()
        sl = so.order_line.filtered('is_delivery')
        self.assertTrue(sl._meli_is_ml_shipping_line())
        return so, sl, inv

    def _assert_facturada(self, so, sl):
        self.env.flush_all()
        self.assertEqual(sl.qty_to_invoice, 0.0, "envio $0: nada para facturar")
        self.assertEqual(sl.invoice_status, 'invoiced')
        self.assertEqual(so.invoice_status, 'invoiced', "la venta facturada no puede figurar 'A facturar'")

    def test_01_refresh_corrige_valor_escrito_a_mano(self):
        so, sl, inv = self._venta_facturada('2000424231350253')
        self._assert_facturada(so, sl)
        sl.qty_to_invoice = 1.0          # lo que escribia shipment.py hasta 26.306
        self.env.flush_all()
        # control: reproduce el estado medido en caso-K02 ('to invoice' en 17+; en 16 el delivery del core
        # lo baja a 'no' porque solo queda el envio) => nunca 'invoiced'
        self.assertNotEqual(so.invoice_status, 'invoiced', "control: reproduce el estado medido en K02")
        self.assertEqual(sl.qty_to_invoice, 1.0)
        sl._meli_refresh_shipping_invoice_qty()
        self._assert_facturada(so, sl)

    def test_02_resync_real_de_venta_facturada_no_deja_envio_a_facturar(self):
        so, sl, inv = self._venta_facturada('2000050515033242')
        mo = self.env['mercadolibre.orders'].create({'order_id': '2000050515033242', 'name': '2000050515033242',
                                                     'sale_order': so.id})
        self.env['mercadolibre.payments'].create({
            'order_id': mo.id, 'payment_id': '158000001', 'status': 'approved',
            'currency_id': self.env.company.currency_id.name,
            'transaction_amount': 738677.69, 'total_paid_amount': 789900.0, 'shipping_amount': 51222.31})
        so.meli_orders = [(6, 0, [mo.id])]
        sh = self.env['mercadolibre.shipment'].create({
            'sale_order': so.id, 'tracking_method': 'ME1 - zip K02', 'mode': 'me1',
            'shipping_cost': 51222.31, 'shipping_list_cost': 51222.31})
        SO = type(so)
        with patch.object(SO, 'meli_amount_to_invoice', lambda self, meli=None, config=None: 789900.0, create=True), \
             patch.object(type(mo), '_ensure_payment_shipping_amounts', lambda self, meli=None, config=None: None,
                          create=True):
            sh._update_sale_order_shipping_info(mo, meli=None, config=self.env.company)
        sl = so.order_line.filtered('is_delivery')
        self.assertEqual(len(sl), 1)
        self.assertAlmostEqual(sl.price_unit, 0.0, places=2, msg="el guard frena el precio de la venta facturada")
        self._assert_facturada(so, sl)
        self.assertFalse(so._get_invoiceable_lines(), "Crear factura no tiene nada para facturar")

    def _migrate(self):
        path = os.path.join(get_module_path('meli_oerp'), 'migrations',
                            '%s.26.307' % release.series, 'post-migrate.py')
        spec = importlib.util.spec_from_file_location('meli_K02_mig', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.migrate(self.env.cr, '%s.26.306' % release.series)
        self.env.invalidate_all()

    def test_03_migracion_repara_solo_envios_en_cero(self):
        so0, sl0, _i0 = self._venta_facturada('2000272434239135', 0.0)
        so1, sl1, _i1 = self._venta_facturada('2000101489836809', 0.0)
        # envio con precio sin facturar (como las 16 producto 2 de caso-K02): NO se toca
        sl1.price_unit = 900.0
        self.env.flush_all()
        before_priced = (sl1.qty_to_invoice, sl1.invoice_status)
        self.assertEqual(before_priced[0], 1.0)
        sl0.qty_to_invoice = 1.0
        self.env.flush_all()
        self.assertNotEqual(so0.invoice_status, 'invoiced')
        self._migrate()
        self._assert_facturada(so0, sl0)
        self.assertEqual((sl1.qty_to_invoice, sl1.invoice_status), before_priced)
