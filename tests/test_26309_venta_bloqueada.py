# -*- coding: utf-8 -*-
"""26.309 (caso-K02 cliente H) -- venta BLOQUEADA para actualizar desde ML (`meli_update_forbidden`).

El freno es correcto (no escribe nada) pero:
  - logueaba ERROR "Forbidden to upate by meli_oerp" en CADA llamada, y
  - devolvia un error indistinguible de un fallo real => la notificacion quedaba FAILED y el cron
    de notificaciones (que toma RECEIVED + FAILED) la reintentaba para siempre.
Ahora: WARNING una vez por venta (despues DEBUG) y el retorno trae `meli_update_forbidden` para
que quien llama cierre la notificacion sin reintento. El pedido sigue SIN tocarse.

Camino real orders_update_order_json con ML simulado (sin red), mismo armado que test_K03.
Control (origin sin el fix): test_1 y test_2 FALLAN.
"""
from unittest.mock import patch

from odoo.tests import common, tagged
from odoo.tools import mute_logger

from odoo.addons.meli_oerp.models import versions as meli_versions
from .test_k03_direcciones_manuales import _FakeMeli, _MPNoDisponible, _order_json, OID

LOGGER = "odoo.addons.meli_oerp.models.orders"


@tagged('post_install', '-at_install', 'meli', 'meli_26309')
class TestMeli26309VentaBloqueada(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        pricelist = cls.env['product.pricelist'].search([], limit=1) or \
            cls.env['product.pricelist'].create({'name': 'Lista ML'})
        cls.company.mercadolibre_pricelist = pricelist
        if 'mercadolibre_cron_get_orders_shipment_client' in cls.company._fields:
            cls.company.mercadolibre_cron_get_orders_shipment_client = True
        cls.product = cls.env['product.product'].create({
            'name': 'Prueba K03', 'taxes_id': [(5, 0, 0)], 'meli_id': 'MLA554523', 'default_code': 'SKU554523'})

    def setUp(self):
        super().setUp()
        getattr(meli_versions, '_MELI_UPDATE_FORBIDDEN_WARNED', set()).clear()

    def _sync(self, street='Calle Falsa 123'):
        oj = _order_json(street)
        routes = [('/orders/%s/billing_info' % OID, {}), ('/orders/%s/discounts' % OID, {}),
                  ('/orders/%s' % OID, oj), ('/items/', {'id': 'MLA554523', 'title': 'Prueba K03'})]
        with patch('odoo.addons.meli_oerp.models.orders.requests.get', return_value=_MPNoDisponible()), \
                mute_logger('odoo.addons.meli_oerp_multiple.models.sale'):
            return self.env['mercadolibre.orders'].orders_update_order_json(
                {'id': False, 'order_json': oj}, meli=_FakeMeli(routes), config=self.company)

    def _bloqueada(self):
        self._sync()
        so = self.env['sale.order'].search([('meli_order_id', '=', str(OID))], limit=1)
        self.assertTrue(so)
        so.meli_update_forbidden = True
        return so

    def test_1_retorno_marcado_y_sin_escritura(self):
        so = self._bloqueada()
        street = so.partner_shipping_id.street
        res = self._sync('Otra Calle 999')
        self.assertTrue(isinstance(res, dict) and res.get('error'), res)
        self.assertTrue(res.get('meli_update_forbidden'), "el retorno tiene que marcar el freno: %s" % res)
        self.assertTrue(meli_versions.meli_is_update_forbidden_error(res))
        so.invalidate_recordset()
        self.assertEqual(so.partner_shipping_id.street, street, "la venta bloqueada no se toca")

    def test_2_warning_una_vez_sin_error(self):
        self._bloqueada()
        with self.assertLogs(LOGGER, level="DEBUG") as cm:
            self._sync()
        hits = [l for l in cm.output if 'MELI_UPDATE_FORBIDDEN' in l or 'Forbidden to upate' in l]
        self.assertEqual(len([l for l in hits if l.startswith('WARNING')]), 1, hits)
        self.assertFalse([l for l in hits if l.startswith('ERROR')], hits)
        with self.assertLogs(LOGGER, level="DEBUG") as cm2:
            self._sync()
            self._sync()
        hits2 = [l for l in cm2.output if 'MELI_UPDATE_FORBIDDEN' in l or 'Forbidden to upate' in l]
        self.assertTrue(hits2, "sigue frenando (a DEBUG)")
        self.assertFalse([l for l in hits2 if l.startswith(('WARNING', 'ERROR'))], hits2)

    def test_3_helper_reconoce_los_dos_textos(self):
        f = meli_versions.meli_is_update_forbidden_error
        self.assertTrue(f({'error': 'Forbidden to upate by meli_oerp'}))
        self.assertTrue(f('Forbidden to update sale order by meli_oerp'))
        self.assertFalse(f({'error': 'orden filtrada por fecha START'}))
        self.assertFalse(f(None))
