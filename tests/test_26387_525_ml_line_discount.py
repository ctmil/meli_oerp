# -*- coding: utf-8 -*-
"""26.387 (#525 ROEN, SO 8152 / 7578) -- una regla % de la tarifa no rebaja la linea de ML.

ROEN tiene en su tarifa de ML ("LP MELI") una regla `percentage 15` para dos variantes. Odoo
(_compute_discount, store + precompute) volcaba ese 15 % a `discount` de la linea que crea el
conector con el precio de ML: la venta quedaba 15 % por debajo de lo cobrado (700,11 contra
823,65), "Condition not met" y la venta en presupuesto. Re-sincronizar no lo corregia.

Sin red: ML simulado con _FakeMeli (como test_k15_precio_linea_ml / test_import_cupon_linea).
Control: en la rama de version SIN el fix, test_1/test_2/test_4 fallan (discount 15).
"""
from unittest.mock import patch

from odoo.tests import common, tagged
from odoo.tools import mute_logger

from .test_import_cupon_linea import _FakeMeli, _MPNoDisponible, _order_json

OID = 2000052552552501
UNIT = 823.65
PCT = 15.0
_MUTE = ('odoo.addons.meli_oerp_multiple.models.sale', 'odoo.addons.meli_oerp.models.orders',
         'odoo.addons.meli_oerp.models.shipment')


@tagged('post_install', '-at_install', 'meli', 'meli_26387_525')
class TestLineaMlSinDescuentoDeTarifa(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        # la regla % solo se muestra como descuento con el grupo de descuentos en lineas activo
        for xmlid in ('sale.group_discount_per_so_line', 'product.group_discount_per_so_line'):
            grp = cls.env.ref(xmlid, raise_if_not_found=False)
            if grp:
                gfield = 'group_ids' if 'group_ids' in cls.env.user._fields else 'groups_id'
                cls.env.user.write({gfield: [(4, grp.id)]})
                cls.env.ref('base.group_user').write({'implied_ids': [(4, grp.id)]})
        pricelist = cls.env['product.pricelist'].search([], limit=1) or cls.env['product.pricelist'].create({'name': 'LP MELI'})
        if 'discount_policy' in pricelist._fields:
            pricelist.discount_policy = 'without_discount'
        cls.pricelist = pricelist
        cls.company.mercadolibre_pricelist = pricelist
        cls.contact = cls.env['res.partner'].create({'name': 'Cliente ML'})
        if 'mercadolibre_contact_partner' in cls.company._fields:
            cls.company.mercadolibre_contact_partner = cls.contact
        if 'mercadolibre_cron_get_orders_shipment_client' in cls.company._fields:
            cls.company.mercadolibre_cron_get_orders_shipment_client = True
        cls.company.mercadolibre_order_confirmation = 'manual'
        cls.product = cls.env['product.product'].create({
            'name': 'Refaccion PMG4967', 'taxes_id': [(5, 0, 0)], 'list_price': UNIT,
            'meli_id': 'MLM000TEST', 'default_code': 'PMG4967_BK'})
        Item = cls.env['product.pricelist.item']
        # 16-19: compute_price 'percentage' + percent_price; 20: 'discount' + price_discount
        rule = ({'compute_price': 'percentage', 'percent_price': PCT} if 'percent_price' in Item._fields
                else {'compute_price': 'discount', 'price_discount': PCT})
        Item.create(dict(rule, pricelist_id=pricelist.id, applied_on='0_product_variant', product_id=cls.product.id))

    def _sync(self, unit=UNIT, paid=UNIT, coupon=0.0):
        routes = [('/orders/%s/discounts' % OID, {'details': []}),
                  ('/items/', {'id': 'MLM000TEST', 'title': 'Refaccion PMG4967'})]
        oj = _order_json(oid=OID, unit=unit, paid=paid, coupon=coupon)
        with patch('odoo.addons.meli_oerp.models.orders.requests.get', return_value=_MPNoDisponible()), \
                mute_logger(*_MUTE):
            self.env['mercadolibre.orders'].orders_update_order_json(
                {'id': False, 'order_json': oj}, meli=_FakeMeli(routes), config=self.company)
        so = self.env['sale.order'].search([('meli_order_id', '=', str(OID))], limit=1)
        self.assertTrue(so, "no se creo la venta")
        return so

    def _line(self, so):
        line = so.order_line.filtered(lambda l: l.product_id == self.product)
        self.assertEqual(len(line), 1)
        return line

    def _manual_line(self):
        """Linea creada a mano con la tarifa: la regla SI se vuelca a discount (control positivo)."""
        so = self.env['sale.order'].create({'partner_id': self.contact.id, 'pricelist_id': self.pricelist.id})
        return self.env['sale.order.line'].create({'order_id': so.id, 'product_id': self.product.id,
                                                    'product_uom_qty': 1})

    def test_0_control_la_tarifa_vuelca_el_descuento(self):
        """Sin este control el resto no prueba nada: la regla % de la tarifa tiene que llegar a discount."""
        self.assertAlmostEqual(self._manual_line().discount, PCT, places=2)

    def test_1_linea_ml_nace_sin_descuento_y_total_igual_a_cobrado(self):
        self.company.mercadolibre_order_confirmation = 'paid_confirm'
        so = self._sync()
        line = self._line(so)
        self.assertEqual(so.pricelist_id, self.pricelist, "la venta ML no usa la tarifa con la regla")
        self.assertAlmostEqual(line.discount, 0.0, places=4)
        self.assertAlmostEqual(line.price_unit, UNIT, places=2)
        self.assertAlmostEqual(so.amount_total, UNIT, places=2)
        self.assertFalse(so.message_ids.filtered(lambda m: 'meli_paid_amount and amount_total' in (m.body or '')),
                         "quedo el 'Condition not met' de importes")

    def test_2_resync_no_reintroduce_el_descuento(self):
        so = self._sync()
        line = self._line(so)
        line.discount = 0.0  # aisla del create: lo que se mide aca es el write del re-sync
        # cambio de cantidad en ML: el write de product/qty recomputa discount desde la tarifa
        line._meli_write_ml_line({'product_id': self.product.id, 'product_uom_qty': 2, 'price_unit': UNIT})
        self.assertAlmostEqual(line.discount, 0.0, places=4)
        line._meli_write_ml_line({'product_id': self.product.id, 'product_uom_qty': 1, 'price_unit': UNIT})
        self.assertAlmostEqual(line.discount, 0.0, places=4)
        so2 = self._sync()
        self.assertEqual(so2, so)
        self.assertAlmostEqual(line.discount, 0.0, places=4)
        self.assertAlmostEqual(so.amount_total, UNIT, places=2)

    def test_3_cupon_ml_modo_product_discount_sigue_imputando(self):
        """Cupon financiado por ML (100 de 1000) en modo product_discount: la linea lleva 10 %, no 15 ni 0."""
        with patch('odoo.addons.meli_oerp.models.orders.meli_resolve_coupon_invoice_mode',
                   return_value='product_discount'):
            so = self._sync(unit=1000.0, paid=900.0, coupon=100.0)
        line = self._line(so)
        self.assertAlmostEqual(line.price_unit, 1000.0, places=2)
        self.assertAlmostEqual(line.discount, 10.0, places=4)
        self.assertAlmostEqual(so.amount_total, 900.0, places=2)

    def test_4_descuento_manual_se_conserva(self):
        so = self._sync()
        line = self._line(so)
        line.discount = 5.0  # el operador pone un descuento a mano en el presupuesto
        line._meli_write_ml_line({'product_id': self.product.id, 'product_uom_qty': 2, 'price_unit': UNIT})
        self.assertAlmostEqual(line.discount, 5.0, places=4)
