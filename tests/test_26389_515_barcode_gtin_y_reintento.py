# -*- coding: utf-8 -*-
"""26.389 (deuda 515 Natural Dry, #442) -- match por codigo de barras GTIN normalizado y
reintento de ordenes de ML que quedaron sin items.

Caso real: la publicacion trae SKU `07502300970043` (GTIN-14 con cero de relleno) y en Odoo
el producto tiene barcode `7502300970043` (EAN-13), sin ese SKU como referencia interna.
La linea de la venta quedaba SIN producto. Y una mercadolibre.orders sin items no la
reintentaba nadie (el cron solo trae ordenes que no existen en Odoo).

Sin red: ML simulado con _FakeMeli (como test_import_cupon_linea / test_26387).
Control: en la rama de version SIN el fix, test_1/test_2/test_5/test_6/test_7 fallan.
"""
from unittest.mock import patch

from odoo.tests import common, tagged
from odoo.tools import mute_logger

from .test_import_cupon_linea import _FakeMeli, _MPNoDisponible, _order_json

OID = 2000051551551501
OID_RETRY = 2000051551551502
ITEM = 'MLM515TEST'
GTIN14 = '07502300970043'
EAN13 = '7502300970043'
_MUTE = ('odoo.addons.meli_oerp_multiple.models.sale', 'odoo.addons.meli_oerp.models.orders',
         'odoo.addons.meli_oerp.models.shipment', 'odoo.addons.meli_oerp.models.meli_gtin')


@tagged('post_install', '-at_install', 'meli', 'meli_26389_515')
class TestBarcodeGtinYReintento(common.TransactionCase):

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
        # sin alta de productos desde la orden: si no matchea, la linea queda sin producto
        if 'mercadolibre_create_product_from_order' in cls.company._fields:
            cls.company.mercadolibre_create_product_from_order = False
        cls.company.mercadolibre_order_confirmation = 'manual'
        cls.product = cls.env['product.product'].create({
            'name': 'Mandarina Kids Original', 'taxes_id': [(5, 0, 0)],
            'default_code': 'MANDARINA-KIDS', 'barcode': EAN13})

    # -- helpers ---------------------------------------------------------------------------
    def _oj(self, oid=OID, sku=GTIN14):
        oj = _order_json(oid=oid, unit=139.0, paid=139.0, coupon=0.0, item=ITEM)
        oj['order_items'][0]['item']['seller_sku'] = sku
        return oj

    def _routes(self, oid=OID, item_json=None, order_json=None):
        routes = [('/orders/%s/discounts' % oid, {'details': []})]
        if order_json is not None:
            routes.append(('/orders/%s' % oid, order_json))
        routes.append(('/items/', item_json or {'id': ITEM, 'title': 'Mandarina Kids'}))
        return routes

    def _import(self, order_json, routes):
        with patch('odoo.addons.meli_oerp.models.orders.requests.get', return_value=_MPNoDisponible()), \
                mute_logger(*_MUTE):
            return self.env['mercadolibre.orders'].orders_update_order_json(
                {'id': False, 'order_json': order_json}, meli=_FakeMeli(routes), config=self.company)

    def _item_product(self, oid=OID):
        mo = self.env['mercadolibre.orders'].search([('order_id', '=', str(oid))], limit=1)
        self.assertTrue(mo, "no se creo la mercadolibre.orders")
        self.assertTrue(mo.order_items, "la orden quedo sin items")
        return mo.order_items[0].product_id

    # -- GTIN ------------------------------------------------------------------------------
    def test_1_sku_gtin14_matchea_barcode_ean13(self):
        """El caso real de 515: SKU de ML 07502300970043, barcode en Odoo 7502300970043."""
        self._import(self._oj(), self._routes())
        self.assertEqual(self._item_product(), self.product)
        so = self.env['sale.order'].search([('meli_order_id', '=', str(OID))], limit=1)
        self.assertTrue(so, "no se creo la venta")
        self.assertIn(self.product, so.order_line.mapped('product_id'))

    def test_2_sin_sku_gtin_del_aviso(self):
        """La publicacion NO trae SKU pero el aviso declara el GTIN (con cero de relleno)."""
        item = {'id': ITEM, 'title': 'Mandarina Kids',
                'attributes': [{'id': 'GTIN', 'value_name': GTIN14}]}
        self._import(self._oj(sku=None), self._routes(item_json=item))
        self.assertEqual(self._item_product(), self.product)

    def test_3_barcode_ambiguo_no_vincula(self):
        """Dos productos con el mismo GTIN en distinto ancho: el barcode no decide."""
        self.env['product.product'].create({'name': 'Clon regalo', 'default_code': 'MANDARINA-KIDS-GIFT',
                                            'barcode': GTIN14, 'taxes_id': [(5, 0, 0)]})
        self.assertFalse(self.env['product.product']._meli_search_by_barcode_gtin(GTIN14))
        self.assertFalse(self.env['product.product']._meli_search_by_barcode_gtin(EAN13))

    def test_4_sku_alfanumerico_no_se_normaliza(self):
        from odoo.addons.meli_oerp.models.gtin import meli_gtin_keys, meli_gtin_same, meli_item_gtins
        self.assertIn(EAN13, meli_gtin_keys(GTIN14))
        self.assertIn(GTIN14, meli_gtin_keys(EAN13))
        self.assertEqual(meli_gtin_keys('K002-BRB-KID-MAN'), ['K002-BRB-KID-MAN'])
        self.assertEqual(meli_gtin_keys('1234'), ['1234'])
        self.assertTrue(meli_gtin_same(GTIN14, EAN13))
        self.assertFalse(meli_gtin_same(GTIN14, '7502300970524'))
        self.assertFalse(meli_gtin_same(GTIN14, False))
        item = {'attributes': [{'id': 'GTIN', 'value_name': 'A'}],
                'variations': [{'id': 7, 'attributes': [{'id': 'GTIN', 'values': [{'name': 'B'}]}]}]}
        self.assertEqual(meli_item_gtins(item, 7), ['B'])
        self.assertEqual(meli_item_gtins(item, None), ['A'])

    def test_5_busqueda_base_por_sku_normaliza(self):
        """search_meli_product base (sin meli_oerp_multiple) tambien iguala el GTIN."""
        Orders = self.env['mercadolibre.orders']
        if 'connection_account' in Orders._fields:
            self.skipTest("meli_oerp_multiple redefine search_meli_product (se cubre en test_1)")
        found = Orders.search_meli_product(meli_item={'id': ITEM, 'seller_sku': GTIN14}, config=self.company)
        self.assertEqual(found, self.product)

    # -- reintento de ordenes sin items -----------------------------------------------------
    def _orden_sin_items(self, oid=OID_RETRY, retries=0):
        vals = {'order_id': str(oid), 'status': 'paid', 'name': 'MO %s' % oid}
        mo = self.env['mercadolibre.orders'].create(vals)
        if retries:
            mo.meli_items_retry_count = retries
        self.assertFalse(mo.order_items)
        return mo

    def test_6_reintento_completa_orden_sin_items(self):
        mo = self._orden_sin_items()
        oj = self._oj(oid=OID_RETRY)
        meli = _FakeMeli(self._routes(oid=OID_RETRY, order_json=oj))
        patches = [patch('odoo.addons.meli_oerp.models.orders.requests.get', return_value=_MPNoDisponible())]
        SaleOrder = self.env.registry['sale.order']
        if hasattr(SaleOrder, 'multi_meli_order_update'):
            # meli_oerp_multiple post-procesa la venta con la CUENTA de la orden; esta orden de
            # prueba no tiene cuenta (en produccion siempre la tiene) y ese paso no es lo que se mide.
            patches.append(patch.object(SaleOrder, 'multi_meli_order_update', lambda so, account=None: {}))
        with patches[0], (patches[1] if len(patches) > 1 else mute_logger('x.none')), mute_logger(*_MUTE):
            res = self.env['mercadolibre.orders']._meli_retry_orders_without_items(
                meli=meli, config=self.company, commit=False)
        self.assertIn('/orders/%s' % OID_RETRY, meli.calls)
        mo.invalidate_recordset()
        self.assertTrue(mo.order_items, "el reintento no completo los items")
        self.assertEqual(mo.order_items[0].product_id, self.product)
        self.assertEqual(mo.meli_items_retry_count, 1)
        self.assertGreaterEqual(res.get('completed', 0), 1)

    def test_7_reintento_respeta_tope_y_cancelada(self):
        tope = self._orden_sin_items(oid=OID_RETRY, retries=5)
        cancel = self._orden_sin_items(oid=OID_RETRY + 1)
        cancel.status = 'cancelled'
        meli = _FakeMeli([])
        with mute_logger(*_MUTE):
            self.env['mercadolibre.orders']._meli_retry_orders_without_items(
                meli=meli, config=self.company, commit=False)
        self.assertNotIn('/orders/%s' % OID_RETRY, meli.calls)
        self.assertNotIn('/orders/%s' % (OID_RETRY + 1), meli.calls)
        self.assertEqual(tope.meli_items_retry_count, 5)
