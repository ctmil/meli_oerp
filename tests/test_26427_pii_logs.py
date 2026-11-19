# -*- coding: utf-8 -*-
"""Privacidad en los logs del servidor.

Una venta simulada (MeliSimClient: sin red) con comprador y datos fiscales INVENTADOS entra por el
camino real del import (orders_update_order_json). Se captura TODO lo que loguea el addon, a nivel
DEBUG, y se verifica que no aparezcan el nombre/apellido del comprador ni el de facturación, el
nickname, el email, el teléfono ni el documento (CUIT). Los ids siguen apareciendo (el log sirve
para diagnosticar). Además: el filtro de logging tapa tokens de ML (mensaje y traceback) y los
helpers puros enmascaran como se espera.
"""
import logging

from odoo.tests import common, tagged
from odoo.tools import mute_logger

from odoo.addons.meli_oerp.models.log_privacy import (meli_mask_doc, meli_redact_text,
                                                       meli_install_log_filter, meli_pii_err,
                                                       meli_redact_pii_text, MELI_PII_EXTRA)

OID = 9000000000004271
PAY = 9000000000004272
# Datos inventados, elegidos para que no aparezcan por casualidad en ningún otro texto del log.
BUYER_FIRST, BUYER_LAST = 'Zoraida', 'Quiquenberg'
BILL_FIRST, BILL_LAST = 'Eustaquio', 'Wolkenstrand'
NICK = 'ZORAQUIQPII'
EMAIL = 'zoraida.quiquenberg@example.com'
PHONE = '47153926'
CUIT = '27415926370'
SECRETS = (BUYER_FIRST, BUYER_LAST, BILL_FIRST, BILL_LAST, NICK, EMAIL, PHONE, CUIT,
           # también en mayúsculas / title-case, como los normaliza el import
           BUYER_FIRST.upper(), BUYER_LAST.upper(), BILL_FIRST.upper(), BILL_LAST.upper(),
           # y las partes del documento (por si se loguea con guiones)
           '41592637')


def _order_json():
    unit = 1000.0
    return {
        'id': OID, 'status': 'paid', 'status_detail': None,
        'date_created': '2026-11-19T10:00:00.000-03:00', 'date_closed': '2026-11-19T10:00:01.000-03:00',
        'total_amount': unit, 'paid_amount': unit, 'currency_id': 'ARS',
        'coupon': {'id': None, 'amount': 0},
        'order_items': [{'item': {'id': 'MLA000PII', 'title': 'Taza privacidad', 'variation_id': None,
                                  'seller_sku': 'SKUPII', 'category_id': 'MLA1'},
                         'quantity': 1, 'unit_price': unit, 'full_unit_price': unit, 'currency_id': 'ARS'}],
        'payments': [{'id': PAY, 'transaction_amount': unit, 'total_paid_amount': unit,
                      'currency_id': 'ARS', 'status': 'approved', 'coupon_amount': 0,
                      'shipping_cost': 0, 'date_created': '2026-11-19T10:00:01.000-03:00',
                      'date_last_modified': '2026-11-19T10:00:01.000-03:00'}],
        'buyer': {'id': 904271, 'nickname': NICK, 'first_name': BUYER_FIRST, 'last_name': BUYER_LAST,
                  'email': EMAIL, 'phone': {'area_code': '11', 'number': PHONE}, 'alternative_phone': {},
                  'billing_info': {'doc_type': 'CUIT', 'doc_number': CUIT}},
        'seller': {'id': 904999},
        'tags': ['paid'], 'context': {'channel': 'marketplace', 'site': 'MLA'},
        'shipping': {'id': None}, 'pack_id': None,
    }


def _bundle():
    billing = {'billing_info': {
        'doc_type': 'CUIT', 'doc_number': CUIT,
        'additional_info': [
            {'type': 'FIRST_NAME', 'value': BILL_FIRST},
            {'type': 'LAST_NAME', 'value': BILL_LAST},
            {'type': 'TAXPAYER_TYPE_ID', 'value': 'IVA Responsable Inscripto'},
            {'type': 'DOC_TYPE', 'value': 'CUIT'},
            {'type': 'DOC_NUMBER', 'value': CUIT},
        ]}}
    return {
        'order': _order_json(),
        'routes': {
            '/items/MLA000PII': {'id': 'MLA000PII', 'title': 'Taza privacidad', 'seller_custom_field': 'SKUPII'},
            '/orders/%s/billing_info' % OID: billing,
            '/users/904271': {'id': 904271, 'nickname': NICK, 'first_name': BUYER_FIRST,
                              'last_name': BUYER_LAST, 'email': EMAIL},
            'https://api.mercadopago.com/v1/payments/%s' % PAY: {
                'id': PAY, 'status': 'approved', 'shipping_amount': 0, 'taxes_amount': 0,
                'payment_method_id': 'account_money', 'payment_type_id': 'account_money', 'installments': 1,
                'operation_type': 'regular_payment', 'date_approved': '2026-11-19T10:00:01.000-03:00',
                'coupon_amount': 0, 'payer': {'id': 904271, 'email': EMAIL,
                                              'identification': {'type': 'CUIT', 'number': CUIT}},
                'fee_details': [], 'charges_details': [],
                'transaction_details': {'total_paid_amount': 1000.0, 'net_received_amount': 1000.0}},
        },
        'meta': {'origen': 'test_26427', 'anonimizado': True},
    }


class _Capture(logging.Handler):
    """Junta el mensaje FINAL de cada registro (ya formateado, después de los filtros), con traceback."""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.lines = []

    def emit(self, record):
        msg = record.getMessage()
        if record.exc_info or getattr(record, 'exc_text', None):
            msg += '\n' + (record.exc_text or logging.Formatter().formatException(record.exc_info))
        self.lines.append('%s %s: %s' % (record.levelname, record.name, msg))


@tagged('post_install', '-at_install', 'meli', 'meli_pii_logs')
class TestMeliPiiLogs(common.TransactionCase):

    @classmethod
    def _request_handler(cls, s, r, /, **kw):
        return s.get_adapter(r.url).send(r, **kw)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        pricelist = cls.env['product.pricelist'].search([], limit=1) or cls.env['product.pricelist'].create({'name': 'Lista ML'})
        cls.company.mercadolibre_pricelist = pricelist
        # sin contacto genérico: el import crea el contacto del comprador (el camino reportado)
        if 'mercadolibre_contact_partner' in cls.company._fields:
            cls.company.mercadolibre_contact_partner = False
        if 'mercadolibre_cron_get_orders_shipment_client' in cls.company._fields:
            cls.company.mercadolibre_cron_get_orders_shipment_client = True
        # entidad fiscal separada del comprador (nombre de facturación distinto): es el camino del
        # reporte ("Entidad fiscal creada ... VAT ... buyer", POST-CHECK)
        for fname in ('mercadolibre_billing_force_on_main', 'mercadolibre_skip_same_name_billing_contact'):
            if fname in cls.company._fields:
                cls.company[fname] = False
        cls.product = cls.env['product.product'].create({
            'name': 'Taza privacidad', 'taxes_id': [(5, 0, 0)], 'meli_id': 'MLA000PII', 'default_code': 'SKUPII'})
        cls.company.sudo().meli_simulation_enabled = True

    def _capture(self, names=('odoo.addons.meli_oerp', 'odoo.addons.meli_oerp_multiple',
                              'odoo.addons.meli_oerp_accounting', 'odoo.addons.meli_oerp_stock')):
        cap = _Capture()
        saved = []
        for n in names:
            lg = logging.getLogger(n)
            saved.append((lg, lg.level))
            lg.setLevel(logging.DEBUG)
            lg.addHandler(cap)

        def _restore():
            for lg, lvl in saved:
                lg.removeHandler(cap)
                lg.setLevel(lvl)
        self.addCleanup(_restore)
        return cap

    # ------------------------------------------------------------------------------------------
    def test_01_import_no_loguea_datos_personales(self):
        cap = self._capture()
        with mute_logger('odoo.addons.meli_oerp_multiple.models.sale'):
            res = self.env['mercadolibre.orders'].meli_simulate_order(_bundle(), config=self.company)
        self.assertTrue(res.get('ok'), res)
        buyer = self.env['res.partner'].with_context(active_test=False).search(
            [('meli_buyer_id', '=', '904271')], limit=1)
        # la venta entró de verdad y con los datos (el fix sólo cambia lo que se LOGUEA)
        self.assertTrue(buyer, "no se creó el contacto del comprador")
        self.assertTrue(any(x.lower() in (buyer.name or '').lower() for x in (BUYER_LAST, BILL_LAST)), buyer.name)
        log = '\n'.join(cap.lines)
        self.assertTrue(cap.lines, "no se capturó ningún log: el test no mide nada")
        leaks = sorted({s for s in SECRETS if s in log})
        if leaks:
            offending = [l for l in cap.lines if any(s in l for s in leaks)]
            self.fail("el log expone datos personales %s en:\n%s" % (leaks, '\n'.join(offending[:10])))
        # el camino del contacto pasó y quedó logueado por id
        self.assertIn('Contacto principal creado: id:%s' % buyer.id, log)
        # Con la localización Latam (l10n_latam_base) el import guarda el CUIT y crea la entidad
        # fiscal: son exactamente las líneas del reporte. Ahí el documento sale enmascarado.
        if 'l10n_latam_identification_type_id' in self.env['res.partner']._fields:
            self.assertTrue(self.env['res.partner'].with_context(active_test=False).search(
                [('vat', '=', CUIT)], limit=1), "el CUIT no se guardó: el caso no ejercita el camino fiscal")
            self.assertIn('***6370', log)
            self.assertRegex(log, r'Entidad fiscal creada: id:\d+ \(VAT: \*\*\*6370\) vinculada a buyer id:%s' % buyer.id)
            self.assertRegex(log, r'POST-CHECK contacto facturación id:\d+ - vat:\*\*\*6370')

    def test_02_filtro_tapa_tokens_en_mensaje_y_traceback(self):
        meli_install_log_filter('odoo.addons.meli_oerp')
        cap = self._capture()
        lg = logging.getLogger('odoo.addons.meli_oerp.models.orders')
        tok = 'APP_USR-1234567890123456-111917-0123456789abcdef0123456789abcdef-904999'
        lg.warning("PUT /items/MLA1 falló: %s", "HTTPSConnectionPool: Max retries exceeded with url: "
                   "/items/MLA1?access_token=%s" % tok)
        try:
            raise ValueError("url /items/MLA1?access_token=%s refresh_token=TG-0123456789abcdef0123" % tok)
        except ValueError:
            lg.exception("stock error")
        log = '\n'.join(cap.lines)
        self.assertIn('access_token=***', log)
        self.assertNotIn(tok, log)
        self.assertNotIn('0123456789abcdef0123456789abcdef', log)
        self.assertNotIn('TG-0123456789abcdef0123', log)
        self.assertIn('stock error', log)  # el registro no se pierde

    def test_03_helpers_puros(self):
        self.assertEqual(meli_mask_doc('20-41592637-0'), '***6370')
        self.assertEqual(meli_mask_doc(''), 'FALTA')
        self.assertEqual(meli_mask_doc(None), 'FALTA')
        self.assertEqual(meli_mask_doc(0), '0')
        self.assertEqual(meli_mask_doc('123'), '***')
        self.assertEqual(meli_redact_text('sin secretos'), 'sin secretos')
        self.assertEqual(meli_redact_text('Authorization: Bearer APP_USR-99999999999999-x'),
                         'Authorization: Bearer ***')
        self.assertEqual(meli_redact_text('%2Fitems%3Faccess_token%3DAPP_USR-abc'),
                         '%2Fitems%3Faccess_token%3D***')
        self.assertIsNone(meli_redact_text(None))

    def test_04_error_de_contacto_sin_datos_personales(self):
        """Un ValidationError de base_vat trae el documento y el nombre entre corchetes; los handlers
        de alta/edición de contactos lo loguean con meli_pii_err + extra=MELI_PII_EXTRA (traceback
        incluido)."""
        msg = ("The VAT number [%s] for partner [%s %s] does not seem to be valid. "
               "Note: the expected format is AR200-5536168-2 or 20055361682") % (CUIT, BUYER_FIRST, BUYER_LAST)
        red = meli_redact_pii_text(msg)
        for s in (CUIT, BUYER_FIRST, BUYER_LAST):
            self.assertNotIn(s, red)
        self.assertIn('does not seem to be valid', red)  # el motivo se sigue leyendo
        self.assertNotIn(EMAIL, meli_redact_pii_text('contacto %s' % EMAIL))
        # un id de orden de ML (16 dígitos) y un MLA… no se tapan: hacen falta para diagnosticar
        self.assertIn('2000000000000001', meli_redact_pii_text('orden 2000000000000001 item MLA9000000001'))
        self.assertIn('MLA9000000001', meli_redact_pii_text('orden 2000000000000001 item MLA9000000001'))
        meli_install_log_filter('odoo.addons.meli_oerp')
        cap = self._capture()
        lg = logging.getLogger('odoo.addons.meli_oerp.models.orders')
        try:
            raise ValueError(msg)
        except ValueError as e:
            lg.info("orders_update_order > Error creando Partner: " + meli_pii_err(e))
            lg.error(meli_pii_err(e), exc_info=True, extra=MELI_PII_EXTRA)
        log = '\n'.join(cap.lines)
        self.assertIn('Traceback', log)
        for s in (CUIT, BUYER_FIRST, BUYER_LAST):
            self.assertNotIn(s, log)
