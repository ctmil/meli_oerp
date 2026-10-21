# -*- coding: utf-8 -*-
"""#615 (ROEN 525, 21-oct-2026): el enlace del reclamo abria www.<dominio>/reclamos/<id>.

Para una MEDIACION el enlace correcto (confirmado por la cliente) es la mediacion en el
panel del vendedor, por pack (o la orden si no hay pack):
  https://vendedores.<dominio>/ventas/nueva/mensajeria/<pack|orden>/mediacion/<claim_id>
Los otros tipos conservan el enlace anterior (formato del panel no confirmado).
Caso real medido: claim 5597226476, orden 2000019037387544, pack 2000015578976049.
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'meli_525')
class TestClaimLink615(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Order = self.env['mercadolibre.orders']
        self.Claim = self.env['mercadolibre.claim']

    def _order(self, order_id, pack_id=False):
        return self.Order.create({'name': 'Orden %s' % order_id, 'order_id': order_id, 'pack_id': pack_id})

    def _claim(self, claim_id, ctype, order=False, resource='order', resource_id=False):
        return self.Claim.create({'name': 'Reclamo %s' % claim_id, 'claim_id': claim_id, 'type': ctype,
                                  'site_id': 'MLM', 'order_id': order and order.id or False,
                                  'resource': resource, 'resource_id': resource_id or ''})

    def test_mediacion_con_pack(self):
        o = self._order('2000019037387544', '2000015578976049')
        c = self._claim('5597226476', 'mediations', o, resource_id='2000019037387544')
        self.assertEqual(c.claim_link, 'https://vendedores.mercadolibre.com.mx/ventas/nueva/mensajeria/'
                                       '2000015578976049/mediacion/5597226476')

    def test_mediacion_sin_pack_usa_orden(self):
        o = self._order('2000019037387544')
        c = self._claim('5597226476', 'mediations', o)
        self.assertEqual(c.claim_link, 'https://vendedores.mercadolibre.com.mx/ventas/nueva/mensajeria/'
                                       '2000019037387544/mediacion/5597226476')

    def test_mediacion_sin_orden_vinculada_usa_recurso(self):
        c = self._claim('5597226476', 'mediations', resource_id='2000019037387544')
        self.assertEqual(c.claim_link, 'https://vendedores.mercadolibre.com.mx/ventas/nueva/mensajeria/'
                                       '2000019037387544/mediacion/5597226476')

    def test_control_otros_tipos_enlace_anterior(self):
        # Control: devolucion y cancelacion conservan el enlace de siempre (pasa con y sin fix).
        o = self._order('2000019037387544', '2000015578976049')
        for ctype in ('returns', 'cancel_purchase'):
            c = self._claim('55972264%s' % len(ctype), ctype, o)
            self.assertEqual(c.claim_link, 'https://www.mercadolibre.com.mx/reclamos/%s' % c.claim_id)
        c = self._claim('5597226499', 'mediations', resource='shipment', resource_id='44')
        self.assertEqual(c.claim_link, 'https://www.mercadolibre.com.mx/reclamos/5597226499')
