# -*- coding: utf-8 -*-
"""#caso-K15 / 26.316 -- el precio de la linea de producto de una venta ML lo manda ML.

Reproduce la SO 11806 de cliente E (27-oct-2026): ML 2000499184416134, 1 x 27.500, sin cupon. En prod un
campo Studio de sale.order.line (`x_studio_precio_por_medida`, depends product_id/ancho/largo) termina
su compute con `record['price_unit'] = <formula>`; la sincronizacion reescribia `product_id` en cada
write y ese compute dejaba la linea en 0 (o en un precio de formula) DENTRO del write del conector.
Aca la personalizacion se simula parcheando create/write de sale.order.line: cada vez que se escribe
`product_id`, otra escritura deja `price_unit = 0` (lo mismo que medimos en prod con la traza).
"""
from unittest.mock import patch

from odoo import api
from odoo.tests import common, tagged
from odoo.tools import mute_logger

from .test_import_cupon_linea import _FakeMeli, _MPNoDisponible, _order_json

OID = 2000055153543301
UNIT = 27500.0
MARK = 'meli-once:precio-ml-pisado-'


@tagged('post_install', '-at_install', 'meli', 'meli_K15_precio_linea')
class TestPrecioLineaMl(common.TransactionCase):

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
        # como en cliente E: la venta queda en presupuesto (no se confirma en la sincronizacion)
        cls.company.mercadolibre_order_confirmation = 'manual'
        cls.product = cls.env['product.product'].create({
            'name': 'Cuadro Decorativo', 'taxes_id': [(5, 0, 0)], 'meli_id': 'MLM000TEST', 'default_code': 'YNPQ87632'})

    def setUp(self):
        super().setUp()
        SOL = type(self.env['sale.order.line'])
        self.studio_hits = []
        orig_write, orig_create = SOL.write, SOL.create
        hits = self.studio_hits

        def studio_write(recs, vals):
            res = orig_write(recs, vals)
            if 'product_id' in vals and not recs.env.context.get('_studio_inner'):
                hits.append(('write', recs.ids))
                orig_write(recs.with_context(_studio_inner=True), {'price_unit': 0.0})
            return res

        @api.model_create_multi
        def studio_create(model, vals_list):
            recs = orig_create(model, vals_list)
            todo = recs.filtered('product_id')
            if todo and not model.env.context.get('_studio_inner'):
                hits.append(('create', todo.ids))
                orig_write(todo.with_context(_studio_inner=True), {'price_unit': 0.0})
            return recs

        p1 = patch.object(SOL, 'write', studio_write)
        p2 = patch.object(SOL, 'create', studio_create)
        p1.start(); p2.start()
        self.addCleanup(p1.stop); self.addCleanup(p2.stop)

    def _sync(self):
        meli = _FakeMeli([('/items/', {'id': 'MLM000TEST', 'title': 'Cuadro Decorativo'})])
        oj = _order_json(oid=OID, unit=UNIT, paid=UNIT, coupon=0)
        with patch('odoo.addons.meli_oerp.models.orders.requests.get', return_value=_MPNoDisponible()), \
                mute_logger('odoo.addons.meli_oerp_multiple.models.sale', 'odoo.addons.meli_oerp.models.orders'):
            self.env['mercadolibre.orders'].orders_update_order_json({'id': False, 'order_json': oj}, meli=meli, config=self.company)
        so = self.env['sale.order'].search([('meli_order_id', '=', str(OID))], limit=1)
        self.assertTrue(so, "no se creo la venta")
        return so

    def _product_line(self, so):
        line = so.order_line.filtered(lambda l: l.product_id == self.product)
        self.assertEqual(len(line), 1)
        return line

    def _marks(self, so):
        return len(so.message_ids.filtered(lambda m: MARK in (m.body or '')))

    def test_0_control_la_personalizacion_pisa_el_precio(self):
        """Control positivo: un write de la linea con product_id (lo que hacia el conector) la deja en 0."""
        so = self.env['sale.order'].create({'partner_id': self.contact.id})
        line = self.env['sale.order.line'].create({'order_id': so.id, 'product_id': self.product.id,
                                                    'product_uom_qty': 1, 'price_unit': UNIT})
        self.assertEqual(line.price_unit, 0.0)
        line.write({'product_id': self.product.id, 'price_unit': UNIT})
        self.assertEqual(line.price_unit, 0.0)

    def test_1_import_13151_queda_con_el_precio_de_ml(self):
        so = self._sync()
        self.assertTrue(self.studio_hits, "la personalizacion simulada no corrio: el test no prueba nada")
        self.assertEqual(so.state, 'draft')
        self.assertAlmostEqual(self._product_line(so).price_unit, UNIT, places=2)
        self.assertAlmostEqual(so.amount_total, UNIT, places=2)

    def test_2_resync_no_reescribe_product_id_ni_pisa_el_precio(self):
        so = self._sync()
        n = len(self.studio_hits)
        so2 = self._sync()
        self.assertEqual(so2, so)
        self.assertEqual(len(self.studio_hits), n, "el re-sync volvio a escribir product_id: %s" % self.studio_hits[n:])
        self.assertAlmostEqual(self._product_line(so).price_unit, UNIT, places=2)

    def test_3_resync_con_precio_cambiado_vuelve_al_de_ml_no_a_cero(self):
        """12529: el operador cambia el precio en el presupuesto y el re-sync lo llevaba a 0."""
        so = self._sync()
        line = self._product_line(so)
        line.with_context(_studio_inner=True).write({'price_unit': 16725.84})
        self._sync()
        self.assertAlmostEqual(line.price_unit, UNIT, places=2)

    def test_4_venta_confirmada_no_se_toca(self):
        so = self._sync()
        line = self._product_line(so)
        so.action_confirm()
        line.with_context(_studio_inner=True).write({'price_unit': 100.0})
        self.assertFalse(line._meli_enforce_ml_price(UNIT))
        self.assertEqual(line.price_unit, 100.0)

    def test_5_producto_cambiado_la_personalizacion_pisa_y_se_restituye_con_aviso(self):
        """Si el write SI lleva product_id (cambio el producto en ML) la personalizacion corre igual:
        el precio de ML se restituye y queda UN aviso en la venta."""
        so = self._sync()
        line = self._product_line(so)
        other = self.env['product.product'].create({'name': 'Cuadro Otro', 'taxes_id': [(5, 0, 0)]})
        n = len(self.studio_hits)
        with mute_logger('odoo.addons.meli_oerp.models.orders'):
            line._meli_write_ml_line({'product_id': other.id, 'price_unit': UNIT, 'product_uom_qty': 1})
        self.assertGreater(len(self.studio_hits), n, "la personalizacion simulada no corrio")
        self.assertAlmostEqual(line.price_unit, UNIT, places=2)
        self.assertEqual(self._marks(so), 1)
        with mute_logger('odoo.addons.meli_oerp.models.orders'):
            line._meli_write_ml_line({'product_id': self.product.id, 'price_unit': UNIT, 'product_uom_qty': 1})
        self.assertAlmostEqual(line.price_unit, UNIT, places=2)
        self.assertEqual(self._marks(so), 1, "el aviso se repitio")
