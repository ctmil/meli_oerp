# -*- coding: utf-8 -*-
"""Modo SIMULACION de ordenes de ML: una venta entra desde un bundle JSON por el camino real del
import, queda marcada SIMULADA y ninguna llamada de red sale de la maquina (se mide a nivel socket).

Casos: interruptor apagado ⇒ rehusa; no-admin ⇒ rehusa; venta nueva simulada (incluye el pago de
MercadoPago servido desde el bundle via la guarda de requests); escrituras bloqueadas (cliente,
requests y get_new_instance); re-sync de una simulada (desde su bundle, nunca contra ML); una orden
REAL con el mismo id no se pisa; el barrido de estados no toma simuladas.
"""
import json
import socket
from contextlib import contextmanager
from unittest.mock import patch

import requests

from odoo.exceptions import AccessError, UserError
from odoo.tests import common, tagged
from odoo.tools import mute_logger

from odoo.addons.meli_oerp.models.meli_sim_client import (MeliSimClient, meli_sim_activate,
                                                          meli_sim_parse_bundle)

OID = 9000000000000001
PAY = 9000000000000101


def _order_json(oid=OID, unit=1500.0, status='paid'):
    return {
        'id': oid, 'status': status, 'status_detail': None,
        'date_created': '2026-11-13T10:00:00.000-03:00', 'date_closed': '2026-11-13T10:00:01.000-03:00',
        'total_amount': unit, 'paid_amount': unit, 'currency_id': 'ARS',
        'coupon': {'id': None, 'amount': 0},
        'order_items': [{'item': {'id': 'MLA000SIM', 'title': 'Taza simulada', 'variation_id': None,
                                  'seller_sku': 'SKUSIM', 'category_id': 'MLA1'},
                         'quantity': 1, 'unit_price': unit, 'full_unit_price': unit, 'currency_id': 'ARS'}],
        'payments': [{'id': PAY, 'transaction_amount': unit, 'total_paid_amount': unit,
                      'currency_id': 'ARS', 'status': 'approved', 'coupon_amount': 0,
                      'shipping_cost': 0, 'date_created': '2026-11-13T10:00:01.000-03:00',
                      'date_last_modified': '2026-11-13T10:00:01.000-03:00'}],
        'buyer': {'id': 900001, 'nickname': 'COMPRADORSIM', 'first_name': 'Comprador', 'last_name': 'Simulado',
                  'name': 'Comprador Simulado', 'email': 'comprador@example.com',
                  'phone': {'area_code': '11', 'number': '00000000'}, 'alternative_phone': {}},
        'seller': {'id': 900999},
        'tags': ['paid'], 'context': {'channel': 'marketplace', 'site': 'MLA'},
        'shipping': {'id': None}, 'pack_id': None,
    }


def _bundle(**kw):
    return {
        'order': _order_json(**kw),
        'routes': {
            '/items/MLA000SIM': {'id': 'MLA000SIM', 'title': 'Taza simulada', 'seller_custom_field': 'SKUSIM'},
            'https://api.mercadopago.com/v1/payments/%s' % PAY: {
                'id': PAY, 'status': 'approved', 'shipping_amount': 0, 'taxes_amount': 0,
                'payment_method_id': 'account_money', 'payment_type_id': 'account_money', 'installments': 1,
                'operation_type': 'regular_payment', 'date_approved': '2026-11-13T10:00:01.000-03:00',
                'coupon_amount': 0, 'payer': {'id': 900001},
                'fee_details': [{'type': 'mercadopago_fee', 'fee_payer': 'collector', 'amount': 195.0}],
                'charges_details': [],
                'transaction_details': {'total_paid_amount': kw.get('unit', 1500.0),
                                        'net_received_amount': kw.get('unit', 1500.0) - 195.0}},
        },
        'meta': {'origen': 'test', 'anonimizado': True},
    }


@contextmanager
def _no_network(test):
    """Cualquier conexión TCP real durante el bloque se anota y falla."""
    attempts = []

    def _deny(*a, **k):
        attempts.append(a[:1])
        raise OSError("red prohibida en el test de simulación")

    with patch.object(socket, 'create_connection', _deny), patch.object(socket.socket, 'connect', _deny):
        yield attempts
    test.assertEqual(attempts, [], "la simulación intentó salir a la red: %s" % attempts)


@tagged('post_install', '-at_install', 'meli', 'meli_simulacion')
class TestMeliSimulacion(common.TransactionCase):

    @classmethod
    def _request_handler(cls, s, r, /, **kw):
        """Odoo (17+) bloquea requests en Session.send, ARRIBA de la guarda de la simulación (que vive
        en HTTPAdapter.send). Se deja bajar al adapter: si la guarda no actuara, el patch de socket
        de _no_network lo atrapa y el test falla."""
        return s.get_adapter(r.url).send(r, **kw)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        pricelist = cls.env['product.pricelist'].search([], limit=1) or cls.env['product.pricelist'].create({'name': 'Lista ML'})
        cls.company.mercadolibre_pricelist = pricelist
        cls.contact = cls.env['res.partner'].create({'name': 'Cliente ML'})
        if 'mercadolibre_contact_partner' in cls.company._fields:
            cls.company.mercadolibre_contact_partner = cls.contact
        cls.product = cls.env['product.product'].create({
            'name': 'Taza simulada', 'taxes_id': [(5, 0, 0)], 'meli_id': 'MLA000SIM', 'default_code': 'SKUSIM'})
        cls.company.sudo().meli_simulation_enabled = True

    def _simulate(self, bundle, **kw):
        with mute_logger('odoo.addons.meli_oerp_multiple.models.sale'):
            return self.env['mercadolibre.orders'].meli_simulate_order(bundle, config=self.company, **kw)

    # ------------------------------------------------------------------------------------------
    def test_01_interruptor_apagado_rehusa(self):
        self.company.sudo().meli_simulation_enabled = False
        with self.assertRaises(UserError):
            self._simulate(_bundle())
        self.assertFalse(self.env['mercadolibre.orders'].search([('order_id', '=', str(OID))]))

    def test_02_no_admin_rehusa(self):
        user = self.env['res.users'].create({'name': 'Vendedor', 'login': 'vend_sim_test',
                                             'email': 'vend_sim@example.com'})
        with self.assertRaises(AccessError):
            self.env['mercadolibre.orders'].with_user(user).meli_simulate_order(_bundle(), config=self.company)

    def test_03_venta_nueva_simulada_sin_red(self):
        with _no_network(self):
            res = self._simulate(_bundle())
        self.assertTrue(res['ok'], res)
        self.assertFalse(res['resync'])
        mo = self.env['mercadolibre.orders'].browse(res['meli_order'])
        self.assertTrue(mo.meli_simulated)
        self.assertTrue(mo.sudo().meli_sim_bundle)
        so = self.env['sale.order'].browse(res['sale_order'])
        self.assertTrue(so, res)
        self.assertTrue(so.meli_simulated)
        self.assertAlmostEqual(so.amount_total, 1500.0, places=2)
        # el pago de MercadoPago (requests directo) salio del bundle por la guarda
        self.assertIn('https://api.mercadopago.com/v1/payments/%s' % PAY, res['calls'])
        pay = mo.payments.filtered(lambda p: str(p.payment_id) == str(PAY))
        self.assertTrue(pay and pay.full_payment, "el pago no tomó el detalle de MP del bundle")

    def test_04_escrituras_bloqueadas(self):
        client = MeliSimClient(_bundle())
        with _no_network(self), meli_sim_activate(client, self.env.cr.dbname):
            # cliente nuevo dentro de la simulación = el simulado
            self.assertIs(self.env['meli.util'].get_new_instance(self.company), client)
            r = client.post('/messages/action_guide/packs/%s/option' % OID, body={'option_id': 'X'})
            self.assertEqual(r.json().get('error'), 'meli_simulation')
            client.put_mini('/items/MLA000SIM', {'available_quantity': 0})
            client.uploadfiles('/packs/%s/fiscal_documents' % OID, files=[])
            rr = requests.put('https://api.mercadolibre.com/items/MLA000SIM', json={'status': 'paused'})
            self.assertEqual(rr.status_code, 403)
            rg = requests.get('https://api.mercadolibre.com/users/me')
            self.assertEqual(rg.status_code, 404)  # GET no cubierto: no sale, queda en missing
        self.assertEqual(len(client.blocked), 4, client.blocked)
        self.assertIn('/users/me', client.missing)
        # fuera de la simulación get_new_instance vuelve a ser el real
        self.assertNotIsInstance(self.env['meli.util'].get_new_instance(self.company), MeliSimClient)

    def test_05_resync_desde_el_bundle(self):
        res1 = self._simulate(_bundle())
        mo = self.env['mercadolibre.orders'].browse(res1['meli_order'])
        # el bundle cambia (cancelación): re-simular actualiza la MISMA orden
        with _no_network(self):
            res2 = self._simulate(_bundle(status='cancelled'))
        self.assertTrue(res2['resync'])
        self.assertEqual(res2['meli_order'], mo.id)
        self.assertEqual(mo.status, 'cancelled')
        # «Actualizar» de una simulada: sale del bundle guardado, nunca de ML
        with _no_network(self):
            mo.orders_update_order()
        self.assertEqual(mo.status, 'cancelled')
        self.assertEqual(json.loads(mo.sudo().meli_sim_bundle)['order']['status'], 'cancelled')

    def test_06_orden_real_no_se_pisa(self):
        real = self.env['mercadolibre.orders'].create({'order_id': str(OID), 'name': 'real'})
        with self.assertRaises(UserError):
            self._simulate(_bundle())
        self.assertFalse(real.meli_simulated)

    def test_07_bundle_invalido_y_json_pelado(self):
        with self.assertRaises(UserError):
            self._simulate('{"routes": {}}')
        b = meli_sim_parse_bundle(json.dumps(_order_json()))
        self.assertEqual(str(b['order']['id']), str(OID))
