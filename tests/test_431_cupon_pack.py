# -*- coding: utf-8 -*-
"""26.318 (#431 B) -- cupón del VENDEDOR en un pack/carrito: se prorratea por ítem.

Valores REALES medidos en producción de 431 (27-oct-2026, instrumento meli-montos-vs-ml.py, venta por venta):
  - pack 2000015663400143 (una orden, 2000019126496014): ítems 3259.99, cupón del vendedor 163.00 (sólo en
    los pagos; la orden no trae `coupon.amount`) => ML cobró 3096.99 y la venta quedó en 3259.99.
  - pack 2000015653157451 (tres órdenes): ítems 3929.00, cupón 196.45 => esperado 3732.55. El reparto del
    bruto entre las tres órdenes no está en la medición: se usa uno sintético que suma lo real.
  - control: pack sin cupón, precio pleno.
Antes de 26.318 la orden miembro de un pack no buscaba /discounts (guarda `not order.pack_id`) y el armado
del pack aplicaba a TODAS las líneas el descuento de la orden que disparó el sync, sin prorratear
(mecanismo del incidente 26.131).
"""
from unittest.mock import patch

from odoo.tests import common, tagged
from odoo.tools import mute_logger

from .test_import_cupon_linea import _FakeMeli, _MPNoDisponible, _order_json

PACK1 = 2000015663400143
OID1 = 2000019126496014


def _disc(item, seller, tipo='coupon'):
    return {'details': [{'type': tipo, 'items': [{'id': item, 'quantity': 1,
                                                   'amounts': {'total': seller, 'seller': seller}}]}]}


@tagged('post_install', '-at_install', 'meli', 'meli_431_cupon_pack')
class TestCuponPack431(common.TransactionCase):

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
            'name': 'Refaccion', 'taxes_id': [(5, 0, 0)], 'meli_id': 'MLM000TEST', 'default_code': 'SKU000'})
        cls.Orders = cls.env['mercadolibre.orders']

    # -- helpers ----------------------------------------------------------------------------------
    def _mo(self, oid, unit, disc=0.0, pack=PACK1, qty=1):
        mo = self.Orders.create({'order_id': str(oid), 'pack_id': str(pack), 'discount_seller_amount': disc})
        self.env['mercadolibre.order_items'].create({
            'order_id': mo.id, 'order_item_id': 'MLM000TEST', 'unit_price': str(unit), 'quantity': qty})
        return mo

    def _pack_prices(self, mos):
        disc, gross = self.Orders._meli_pack_seller_discount(mos)
        return [mo._set_product_unit_price(self.product, mo.order_items[0], config=self.company,
                                           items_total=gross or None, seller_discount=disc)['price_unit']
                for mo in mos], disc, gross

    # -- 1. import de la orden miembro (camino real orders_update_order_json, ML simulado) ---------
    def test_1_pack_member_fetches_its_discount(self):
        """Pack 2000015663400143: el cupón viene sólo en los pagos. Ahora la orden miembro consulta
        /discounts y guarda SU descuento (163.00) en su mercadolibre.orders."""
        oj = _order_json(oid=OID1, unit=3259.99, paid=3259.99, coupon=163.00)
        oj['coupon'] = {'id': None, 'amount': 0}
        oj['pack_id'] = PACK1
        meli = _FakeMeli([('/orders/%s/discounts' % OID1, _disc('MLM000TEST', 163.00)), ('/items/', {'id': 'MLM000TEST'})])
        with patch('odoo.addons.meli_oerp.models.orders.requests.get', return_value=_MPNoDisponible()), \
                mute_logger('odoo.addons.meli_oerp_multiple.models.sale'):
            self.Orders.orders_update_order_json({'id': False, 'order_json': oj}, meli=meli, config=self.company)
        self.assertIn('/orders/%s/discounts' % OID1, meli.calls)
        mo = self.Orders.search([('order_id', '=', str(OID1))], limit=1)
        self.assertAlmostEqual(mo.discount_seller_amount, 163.00, places=2)
        # venta de una sola orden: la arma el import simple, al neto que cobró ML
        so = self.env['sale.order'].search([('meli_order_id', '=', str(OID1))], limit=1)
        self.assertTrue(so)
        self.assertAlmostEqual(so.amount_total, 3096.99, places=2)

    def test_1_offer_in_price_is_not_discounted_again(self):
        """Control 26.249 en un pack: la oferta de precio (type `discount`) ya está en unit_price."""
        oj = _order_json(oid=OID1, unit=3259.99, paid=3259.99, coupon=163.00)
        oj['coupon'] = {'id': None, 'amount': 0}
        oj['pack_id'] = PACK1
        d = _disc('MLM000TEST', 163.00)
        d['details'].append({'type': 'discount', 'items': [{'id': 'MLM000TEST', 'quantity': 1,
                                                            'amounts': {'total': 300.0, 'seller': 300.0}}]})
        meli = _FakeMeli([('/orders/%s/discounts' % OID1, d), ('/items/', {'id': 'MLM000TEST'})])
        with patch('odoo.addons.meli_oerp.models.orders.requests.get', return_value=_MPNoDisponible()), \
                mute_logger('odoo.addons.meli_oerp_multiple.models.sale'):
            self.Orders.orders_update_order_json({'id': False, 'order_json': oj}, meli=meli, config=self.company)
        mo = self.Orders.search([('order_id', '=', str(OID1))], limit=1)
        self.assertAlmostEqual(mo.discount_seller_amount, 163.00, places=2)

    def test_1_venta_simple_oferta_de_precio_real(self):
        """Mecanismo A (431, real): venta simple 2000019126011950 con oferta de precio del vendedor
        (type `discount`, 238.99, ya dentro de unit_price 2033.95). La venta tiene que quedar en 2033.95;
        prod 26.250.1 la dejaba en 1794.96 (la oferta restada otra vez). Corregido en 26.249/26.287."""
        oid = 2000019126011950
        oj = _order_json(oid=oid, unit=2033.95, paid=2033.95, coupon=0)
        routes = [('/orders/%s/discounts' % oid, _disc('MLM000TEST', 238.99, tipo='discount')), ('/items/', {'id': 'MLM000TEST'})]
        # la orden trae `coupon.amount` 0: lo que dispara la consulta es el cupon en la orden o en los pagos;
        # se fuerza con el campo de la orden como en produccion (cargado tarde desde los cargos).
        oj['coupon'] = {'id': 'OF1', 'amount': 238.99}
        meli = _FakeMeli(routes)
        with patch('odoo.addons.meli_oerp.models.orders.requests.get', return_value=_MPNoDisponible()), \
                mute_logger('odoo.addons.meli_oerp_multiple.models.sale'):
            self.Orders.orders_update_order_json({'id': False, 'order_json': oj}, meli=meli, config=self.company)
        mo = self.Orders.search([('order_id', '=', str(oid))], limit=1)
        self.assertAlmostEqual(mo.discount_seller_amount, 0.0, places=2)
        so = self.env['sale.order'].search([('meli_order_id', '=', str(oid))], limit=1)
        self.assertTrue(so)
        self.assertAlmostEqual(so.amount_total, 2033.95, places=2)

    # -- 2. armado de las líneas del pack (shipment): prorrateo del total del pack ---------------
    def test_2_single_order_pack_real(self):
        mo = self._mo(OID1, 3259.99, disc=163.00)
        prices, disc, gross = self._pack_prices([mo])
        self.assertAlmostEqual(disc, 163.00, places=2)
        self.assertAlmostEqual(prices[0], 3096.99, places=2)

    def test_2_three_orders_pack_split_or_concentrated_same_result(self):
        """Pack 2000015653157451 (3929.00, cupón 196.45 => 3732.55). Da lo mismo si ML informa el
        descuento repartido por orden o todo en una: se prorratea el TOTAL del pack por bruto."""
        units = [1965.00, 1182.00, 782.00]          # suma 3929.00 (reparto sintético)
        split = [98.25, 59.10, 39.10]               # 5 % por orden, suma 196.45
        mos = [self._mo(2000019115651494 + i, u, disc=d, pack=2000015653157451) for i, (u, d) in enumerate(zip(units, split))]
        p_split, disc, gross = self._pack_prices(mos)
        self.assertAlmostEqual(disc, 196.45, places=2)
        self.assertAlmostEqual(gross, 3929.00, places=2)
        self.assertAlmostEqual(sum(p_split), 3732.55, delta=0.02)
        for mo, d in zip(mos, [196.45, 0.0, 0.0]):
            mo.discount_seller_amount = d
        p_conc, _d, _g = self._pack_prices(mos)
        for a, b in zip(p_split, p_conc):
            self.assertAlmostEqual(a, b, places=2)
        # ninguna línea lleva el cupón del pack entero (26.131)
        for u, p in zip(units, p_conc):
            self.assertGreater(p, u - 196.45 + 0.01 if u > 196.45 else 0.0)

    def test_2_pack_without_coupon_full_price(self):
        mos = [self._mo(2000019125997458, 1000.0, pack=2000015662953689), self._mo(2000019126000942, 486.0, pack=2000015662953689)]
        prices, disc, gross = self._pack_prices(mos)
        self.assertEqual(disc, 0.0)
        self.assertAlmostEqual(prices[0], 1000.0, places=2)
        self.assertAlmostEqual(prices[1], 486.0, places=2)

    def test_2_incoherent_pack_discount_is_not_applied(self):
        """Descuento del pack >= bruto del pack: precio pleno (romper el precio es peor)."""
        mos = [self._mo(2000000000000201, 100.0, disc=80.0, pack=2000000000000299),
               self._mo(2000000000000202, 50.0, disc=80.0, pack=2000000000000299)]
        prices, disc, gross = self._pack_prices(mos)
        self.assertEqual(disc, 0.0)
        self.assertAlmostEqual(sum(prices), 150.0, places=2)

    def test_2_line_guard_with_record_item_does_not_crash(self):
        """La guarda por línea con un mercadolibre.order_items (no dict) no levanta AttributeError."""
        mo = self._mo(2000000000000301, 100.0, pack=2000000000000399)
        res = mo._set_product_unit_price(self.product, mo.order_items[0], config=self.company, seller_discount=150.0)
        self.assertAlmostEqual(res['price_unit'], 100.0, places=2)


@tagged('post_install', '-at_install', 'meli', 'meli_431_cupon_pack')
class TestCuponPackArmado431(common.TransactionCase):
    """Armado REAL de la venta del carrito (mercadolibre.shipment.fetch_shipment, modo PASIVA: sin red)."""

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
            cls.company.mercadolibre_cron_get_orders_shipment_client = False
        cls.products = [cls.env['product.product'].create({
            'name': 'Refaccion %s' % i, 'taxes_id': [(5, 0, 0)], 'default_code': 'SKU43%s' % i}) for i in range(3)]

    def _pack(self, pack, units, discs, ship='4590000000001'):
        Orders = self.env['mercadolibre.orders']
        mos = []
        for i, (u, d) in enumerate(zip(units, discs)):
            oid = str(int(pack) + 1000 + i)
            vals = {'order_id': oid, 'name': 'MO %s' % oid, 'pack_id': str(pack), 'pack_order': True,
                    'shipping_id': ship, 'status': 'paid', 'total_amount': u, 'paid_amount': u,
                    'coupon_amount': d, 'discount_seller_amount': d,
                    'date_created': '2026-10-22 13:05:00', 'date_closed': '2026-10-22 13:05:36'}
            vals = {k: v for k, v in vals.items() if k in Orders._fields}
            mo = Orders.create(vals)
            self.env['mercadolibre.order_items'].create({
                'order_id': mo.id, 'order_item_id': 'MLM43%s' % i, 'unit_price': str(u), 'quantity': 1,
                'product_id': self.products[i].id})
            mos.append(mo)
        return mos

    class _Pasiva:
        access_token = 'PASIVA'

        def get(self, *a, **k):
            raise AssertionError('sin red en el modo PASIVA')

        def need_login(self):
            return False

    def _armar(self, mos):
        self.env['mercadolibre.shipment'].fetch_shipment(order=mos[0], meli=self._Pasiva(), config=self.company)
        so = mos[0].sale_order or self.env['sale.order'].search([('meli_orders', 'in', [m.id for m in mos])], limit=1)
        self.assertTrue(so, 'no se armo la venta del carrito')
        return so, so.order_line.filtered(lambda l: not l.is_delivery and not l.display_type)

    def test_3_pack_tres_ordenes_cupon_prorrateado(self):
        """Pack 2000015653157451: 3929.00 con cupón 196.45 => 3732.55. Hasta 26.316 cada línea llevaba
        el descuento de la orden que disparó el sync (98.25 x 3 = 294.75) o ninguno."""
        mos = self._pack(2000015653157451, [1965.00, 1182.00, 782.00], [98.25, 59.10, 39.10])
        so, lines = self._armar(mos)
        self.assertEqual(len(lines), 3)
        self.assertAlmostEqual(sum(l.price_unit * l.product_uom_qty for l in lines), 3732.55, delta=0.02)
        self.assertAlmostEqual(so.meli_discount_seller_amount, 196.45, places=2)

    def test_3_pack_una_orden_real(self):
        """Pack 2000015663400143 (una orden): 3259.99, cupón 163.00 => 3096.99."""
        mos = self._pack(2000015663400143, [3259.99], [163.00], ship='4590000000002')
        so, lines = self._armar(mos)
        self.assertAlmostEqual(sum(l.price_unit * l.product_uom_qty for l in lines), 3096.99, places=2)

    def test_3_pack_sin_cupon_control(self):
        mos = self._pack(2000015662953689, [1000.00, 486.00], [0.0, 0.0], ship='4590000000003')
        so, lines = self._armar(mos)
        self.assertAlmostEqual(sum(l.price_unit * l.product_uom_qty for l in lines), 1486.00, places=2)
        self.assertEqual(so.meli_discount_seller_amount or 0.0, 0.0)
