# -*- coding: utf-8 -*-
"""[26.348 #543] Transportista de OTRA compania en una venta ML multiempresa.

Caso de produccion (cliente 543, 19.0, 1-nov-2026): la compania 2 recibe una venta con envio
"Estándar"; el unico transportista con ese nombre era de la compania 1. El 2º fallback lo buscaba
por nombre SIN filtro de compania (``order company_id asc``) y lo asignaba al pedido ⇒ Odoo
levantaba "company inconsistencies" y la venta de ML se revertia entera (ni siquiera quedaba la
mercadolibre.orders). El fix: de la compania del pedido o compartido; si no hay, se crea en la
compania del pedido.
"""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.meli_oerp.models.shipment import meli_carrier_by_name, meli_carrier_company_ok

NAME = 'Estandar T543'


@tagged('post_install', '-at_install', 'meli_543_carrier')
class TestMeli543CarrierCompania(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.c1 = cls.env.company
        cls.c2 = cls.env['res.company'].create({'name': 'Cia 2 T543', 'currency_id': cls.c1.currency_id.id})
        cls.env.user.write({'company_ids': [(4, cls.c2.id)]})
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=[cls.c1.id, cls.c2.id]))
        cls.Carrier = cls.env['delivery.carrier']
        cls.Ship = cls.env['mercadolibre.shipment']

    def _product(self, company, name='Envio T543'):
        return self.env['product.product'].create({
            'name': name, 'type': 'service', 'company_id': company and company.id or False})

    def _carrier(self, company, name=NAME):
        return self.Carrier.create({
            'name': name, 'company_id': company and company.id or False,
            'product_id': self._product(company, 'Prod %s %s' % (name, company and company.id)).id})

    # --- busqueda por nombre
    def test_carrier_de_otra_compania_no_se_usa(self):
        self._carrier(self.c1)
        self.assertFalse(meli_carrier_by_name(self.env, NAME, self.c2),
                         "el transportista de la compania 1 no sirve para un pedido de la compania 2")

    def test_carrier_compartido_si(self):
        shared = self._carrier(False)
        self._carrier(self.c1)
        self.assertEqual(meli_carrier_by_name(self.env, NAME, self.c2), shared)

    def test_propio_antes_que_compartido(self):
        self._carrier(False)
        own = self._carrier(self.c2)
        self.assertEqual(meli_carrier_by_name(self.env, NAME, self.c2), own)

    def test_company_ok(self):
        c1 = self._carrier(self.c1)
        self.assertFalse(meli_carrier_company_ok(c1, self.c2))
        self.assertTrue(meli_carrier_company_ok(c1, self.c1))
        self.assertTrue(meli_carrier_company_ok(self._carrier(False, 'Otro T543'), self.c2))

    # --- 1er fallback: tabla de mapeo
    def test_mapeo_compartido_a_carrier_ajeno_no_se_usa(self):
        if 'meli_oerp.carrier.mapping' not in self.env:
            self.skipTest('sin tabla de mapeo')
        c1 = self._carrier(self.c1)
        self.env['meli_oerp.carrier.mapping'].create({'meli_name': NAME, 'company_id': False, 'carrier_id': c1.id})
        res = self.env['meli_oerp.carrier.mapping'].resolve_carrier(meli_name=NAME, company=self.c2)
        self.assertFalse(res, "el mapeo compartido apunta a un transportista de la compania 1")
        self.assertEqual(self.env['meli_oerp.carrier.mapping'].resolve_carrier(meli_name=NAME, company=self.c1), c1)

    def test_mapeo_propio_gana_al_compartido_ajeno(self):
        if 'meli_oerp.carrier.mapping' not in self.env:
            self.skipTest('sin tabla de mapeo')
        M = self.env['meli_oerp.carrier.mapping']
        M.create({'meli_name': NAME, 'company_id': False, 'carrier_id': self._carrier(self.c1).id})
        own = self._carrier(self.c2, 'Propio T543')
        M.create({'meli_name': NAME, 'company_id': self.c2.id, 'carrier_id': own.id})
        self.assertEqual(M.resolve_carrier(meli_name=NAME, company=self.c2), own)

    # --- producto de envio por el transportista
    def test_producto_de_envio_no_sale_del_carrier_ajeno(self):
        c1 = self._carrier(self.c1)
        found = self.Ship._meli_find_shipping_product(NAME, 'me2', self.c2, [('company_id', '=', self.c2.id)])
        self.assertNotEqual(found, c1.product_id)

    # --- flujo completo: el caso de produccion
    def test_flujo_venta_cia2_con_carrier_cia1(self):
        ajeno = self._carrier(self.c1)
        partner = self.env['res.partner'].create({'name': 'Comprador T543'})
        sorder = self.env['sale.order'].with_company(self.c2).create(
            {'partner_id': partner.id, 'company_id': self.c2.id})
        morder = self.env['mercadolibre.orders'].create({'order_id': '543%d' % sorder.id})
        ship = self.Ship.create({'sale_order': sorder.id, 'mode': 'me2', 'tracking_method': NAME,
                                 'shipping_cost': 0.0})
        # sin pago informado el flujo corta antes del transportista ("conflict"): se fija un importe
        SO = type(self.env['sale.order'])
        with mute_logger('odoo.addons.meli_oerp.models.meli_util'), \
                patch.object(SO, 'meli_amount_to_invoice', return_value=100.0, create=True):
            ship.with_company(self.c2)._update_sale_order_shipping_info(morder, config=self.c2)
        self.assertTrue(sorder.carrier_id, "la venta tiene transportista")
        self.assertNotEqual(sorder.carrier_id, ajeno)
        self.assertIn(sorder.carrier_id.company_id, (self.c2, self.env['res.company']),
                      "transportista de la compania del pedido o compartido")
        self.assertEqual(ajeno.company_id, self.c1, "el transportista de la compania 1 no se toca")
