# -*- coding: utf-8 -*-
"""26.329 (bus 2026-09-25T14:30:56Z): el JSON de error de ML que se persiste en meli_stock_error /
meli_price_error / notificacion NO puede guardar el access_token. Sin red."""
from odoo.tests import TransactionCase, tagged

from ..models.meli_secrets import meli_scrub_secrets

TOKEN = 'APP_USR-1234567890123456-102811-0123456789abcdef0123456789abcdef-123456789'
REFRESH = 'TG-0123456789abcdef01234567-123456789'
RESJSON = {
    'error': 'field_not_updatable', 'code': 'field_not_updatable', 'status': 400,
    'message': 'seller_custom_field is not modifiable.',
    'access_token': TOKEN,
    'cause': [{'code': 'item.id.invalid', 'url': '/items/MLA1?access_token=' + TOKEN}],
}


@tagged('post_install', '-at_install', 'meli', 'meli_26329')
class TestSecretosEnErrores(TransactionCase):

    def _assert_limpio(self, txt):
        self.assertTrue(txt)
        self.assertNotIn(TOKEN, txt)
        self.assertNotIn('1234567890123456-102811', txt)
        self.assertNotIn(REFRESH, txt)
        # lo util para diagnosticar se conserva
        self.assertIn('field_not_updatable', txt)
        self.assertIn('item.id.invalid', txt)

    def test_scrub_puro(self):
        limpio = meli_scrub_secrets(RESJSON)
        self.assertEqual(limpio['access_token'], '***')
        self.assertEqual(limpio['code'], 'field_not_updatable', "'code' es el codigo de error: no se toca")
        self._assert_limpio(str(limpio))
        self._assert_limpio(meli_scrub_secrets(str(RESJSON)))
        self.assertNotIn(REFRESH, meli_scrub_secrets('refresh_token=%s&x=1 field_not_updatable item.id.invalid' % REFRESH))
        self.assertEqual(meli_scrub_secrets('{}'), '{}')
        self.assertEqual(meli_scrub_secrets('fulfillment'), 'fulfillment')
        self.assertIsNone(meli_scrub_secrets(None))

    def test_stock_error_producto_y_plantilla(self):
        tmpl = self.env['product.template'].create({'name': 'Prod 26329'})
        prod = tmpl.product_variant_id
        # el mismo patron que company.py: obj.meli_stock_error = str(resjson)
        prod.meli_stock_error = str(RESJSON)
        prod.meli_price_error = str(RESJSON)
        tmpl.meli_stock_error = prod.meli_stock_error
        for txt in (prod.meli_stock_error, prod.meli_price_error, tmpl.meli_stock_error):
            self._assert_limpio(txt)
        tmpl2 = self.env['product.template'].create({'name': 'Prod 26329 b', 'meli_stock_error': str(RESJSON)})
        self._assert_limpio(tmpl2.meli_stock_error)
        # sin secretos: se guarda igual que antes
        prod.meli_stock_error = str({})
        self.assertEqual(prod.meli_stock_error, '{}')

    def test_notificacion(self):
        noti = self.env['mercadolibre.notification'].create({
            'notification_id': 'test-26329',
            'processing_errors': 'SKU1 MLA1 >> %s' % RESJSON,
        })
        noti.write({'processing_logs': str(RESJSON), 'last_json_response': str(RESJSON)})
        for txt in (noti.processing_errors, noti.processing_logs, noti.last_json_response):
            self._assert_limpio(txt)
