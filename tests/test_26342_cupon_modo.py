# -*- coding: utf-8 -*-
"""26.342 (caso-K22 / caso-K13, 30-oct-2026) -- criterio contable del descuento del VENDEDOR, por cliente.

Valores REALES de caso-K22 tras el pase a 26.335 (ids anonimizados, importes y /discounts reales):
  - SO 181678: orden con pack_id y tag order_has_discount, items 436.99, pagado MP 436.99 (coupon 0);
    /discounts = cupon del vendedor 33.40 + oferta de precio 451 (ya en el precio). 26.330 la dejo en 403.59.
  - SO 181690: carrito de 2 ordenes 291.77 + 297.50 = 589.27 pagado; cupones 19.89 + 18.41 = 38.30.
    26.330 la dejo en 550.97 (272.81 + 278.16).
caso-K13 (#547) quiere items - cupon (default, sin cambios); caso-K22 concilia contra lo cobrado por MP.
Parametro: meli_oerp.seller_coupon_mode[.company_<id>] = 'discount' (default) | 'collected'.
"""
from unittest.mock import patch

from odoo.tests import common, tagged
from odoo.tools import mute_logger

from .test_import_cupon_linea import _FakeMeli, _MPNoDisponible, _order_json

PARAM = 'meli_oerp.seller_coupon_mode'


def _disc_real(item, cupon, oferta):
    return {'details': [
        {'type': 'coupon', 'items': [{'id': item, 'quantity': 1, 'amounts': {'total': cupon, 'seller': cupon}}]},
        {'type': 'discount', 'items': [{'id': item, 'quantity': 1, 'amounts': {'total': oferta, 'seller': oferta}}]}]}


@tagged('post_install', '-at_install', 'meli', 'meli_26342')
class TestCuponModo26342(common.TransactionCase):

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
        cls.product = cls.env['product.product'].create({
            'name': 'Suplemento', 'taxes_id': [(5, 0, 0)], 'meli_id': 'MLM000TEST', 'default_code': 'SKU000'})
        cls.Orders = cls.env['mercadolibre.orders']
        cls.ICP = cls.env['ir.config_parameter'].sudo()

    def _set(self, key, value):
        # Odoo 16-19: set_param · Odoo 20: set_str ('' = sin valor)
        if hasattr(self.ICP, 'set_param'):
            self.ICP.set_param(key, value)
        else:
            self.ICP.set_str(key, value or '')

    def _import_181678(self, oid):
        oj = _order_json(oid=oid, unit=436.99, paid=436.99, coupon=0)
        oj['coupon'] = None
        oj['payments'][0]['coupon_amount'] = 0.0
        oj['pack_id'] = 2000602281517341
        oj['tags'] = ['order_has_discount', 'paid', 'not_delivered']
        meli = _FakeMeli([('/orders/%s/discounts' % oid, _disc_real('MLM000TEST', 33.40, 451.0)),
                          ('/items/', {'id': 'MLM000TEST'})])
        with patch('odoo.addons.meli_oerp.models.orders.requests.get', return_value=_MPNoDisponible()), \
                mute_logger('odoo.addons.meli_oerp_multiple.models.sale'):
            self.Orders.orders_update_order_json({'id': False, 'order_json': oj}, meli=meli, config=self.company)
        mo = self.Orders.search([('order_id', '=', str(oid))], limit=1)
        so = self.env['sale.order'].search([('meli_order_id', '=', str(oid))], limit=1)
        self.assertTrue(so)
        return meli, mo, so

    # -- resolucion del parametro --------------------------------------------------------------
    def test_0_resolucion(self):
        self.assertEqual(self.Orders._meli_seller_coupon_mode(config=self.company), 'discount')
        self._set(PARAM, 'collected')
        self.assertEqual(self.Orders._meli_seller_coupon_mode(config=self.company), 'collected')
        self._set('%s.company_%s' % (PARAM, self.company.id), 'discount')
        self.assertEqual(self.Orders._meli_seller_coupon_mode(config=self.company), 'discount')  # la compania manda
        self._set('%s.company_%s' % (PARAM, self.company.id), 'cualquier-cosa')
        self.assertEqual(self.Orders._meli_seller_coupon_mode(config=self.company), 'discount')  # invalido = default
        self._set('%s.company_%s' % (PARAM, self.company.id), False)
        self.assertEqual(self.Orders._meli_seller_coupon_mode(config=self.company), 'collected')

    # -- venta 181678 --------------------------------------------------------------------------
    def test_1_181678_default_resta_el_cupon(self):
        """Default = comportamiento de 26.330 / caso-K13: 436.99 - 33.40 = 403.59."""
        if not hasattr(self.Orders, '_meli_pack_seller_discount'):
            self.skipTest('esta serie no busca el descuento del miembro de carrito (26.318/26.330)')
        meli, mo, so = self._import_181678(2000822964030517)
        self.assertIn('/orders/%s/discounts' % mo.order_id, meli.calls)
        self.assertAlmostEqual(mo.discount_seller_amount, 33.40, places=2)
        self.assertAlmostEqual(so.amount_total, 403.59, places=2)
        self.assertAlmostEqual(so.meli_discount_seller_amount, 33.40, places=2)

    def test_1_181678_collected_queda_en_lo_cobrado(self):
        """caso-K22 con 'collected': la venta = 436.99 = lo cobrado por MP (26.330 la dejaba en 403.59)."""
        self._set(PARAM, 'collected')
        meli, mo, so = self._import_181678(2000822964030519)
        self.assertAlmostEqual(mo.discount_seller_amount or 0.0, 0.0, places=2)
        self.assertAlmostEqual(so.meli_discount_seller_amount or 0.0, 0.0, places=2)
        self.assertAlmostEqual(so.amount_total, 436.99, places=2)
        self.assertAlmostEqual(so.amount_total, so.meli_paid_amount, places=2)

    def test_1_181678_collected_por_compania(self):
        self._set('%s.company_%s' % (PARAM, self.company.id), 'collected')
        meli, mo, so = self._import_181678(2000822964030521)
        self.assertAlmostEqual(so.amount_total, 436.99, places=2)

    # -- carrito 181690 (reparto del pack, 26.318+) -------------------------------------------
    def _mo(self, oid, unit, disc, pack=2000602281549465):
        mo = self.Orders.create({'order_id': str(oid), 'pack_id': str(pack), 'discount_seller_amount': disc})
        self.env['mercadolibre.order_items'].create({
            'order_id': mo.id, 'order_item_id': 'MLM000TEST', 'unit_price': str(unit), 'quantity': 1})
        return mo

    def _pack_prices(self, mos):
        if not hasattr(self.Orders, '_meli_pack_seller_discount'):
            self.skipTest('esta serie no reparte el descuento del carrito (26.318)')
        disc, gross = self.Orders._meli_pack_seller_discount(mos)
        return [mo._set_product_unit_price(self.product, mo.order_items[0], config=self.company,
                                           items_total=gross or None, seller_discount=disc)['price_unit']
                for mo in mos], disc

    def test_2_181690_default_550_97(self):
        mos = self.Orders.browse([self._mo(2000822964031801, 291.77, 19.89).id, self._mo(2000822964031803, 297.50, 18.41).id])
        prices, disc = self._pack_prices(mos)
        self.assertAlmostEqual(disc, 38.30, places=2)
        self.assertAlmostEqual(sum(prices), 550.97, delta=0.02)

    def test_2_181690_collected_589_27(self):
        """Aunque el descuento haya quedado guardado en los miembros (import previo al parametro), en
        'collected' el carrito no lo resta: 589.27 = lo cobrado."""
        self._set(PARAM, 'collected')
        mos = self.Orders.browse([self._mo(2000822964031805, 291.77, 19.89).id, self._mo(2000822964031807, 297.50, 18.41).id])
        prices, disc = self._pack_prices(mos)
        self.assertEqual(disc, 0.0)
        self.assertAlmostEqual(sum(prices), 589.27, places=2)
