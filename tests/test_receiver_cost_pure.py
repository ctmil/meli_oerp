# -*- coding: utf-8 -*-
"""receiver_buyer_cost — SIN Odoo.

Correr:  python3 meli_oerp/tests/test_receiver_cost_pure.py   (desde la raiz de addons)
NO esta en tests/__init__.py a proposito (carga models/receiver_cost.py por ruta).
"""
import importlib.util
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "meli_receiver_cost", os.path.join(_HERE, "..", "models", "receiver_cost.py"))
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)

SELLER, BUYER = 570653807, 437148007


class TestReceiverBuyerCost(unittest.TestCase):

    def test_envio_gratis_pagado_por_vendedor(self):
        # /shipments/<shipment_id>/costs real (un cliente, orden <order_id>)
        rcosts = {"receiver": {"cost": 2335.09, "user_id": BUYER,
                               "cost_details": [{"sender_id": SELLER, "amount": 2335.09}]},
                  "senders": [{"user_id": SELLER, "cost": 0}]}
        self.assertEqual(rc.receiver_buyer_cost(rcosts), 0.0)

    def test_comprador_paga_todo(self):
        rcosts = {"receiver": {"cost": 3990.0, "user_id": BUYER, "cost_details": []}}
        self.assertEqual(rc.receiver_buyer_cost(rcosts), 3990.0)

    def test_sin_cost_details(self):
        self.assertEqual(rc.receiver_buyer_cost({"receiver": {"cost": 1500}}), 1500.0)

    def test_subsidio_parcial(self):
        rcosts = {"receiver": {"cost": 3000.0, "user_id": BUYER,
                               "cost_details": [{"sender_id": SELLER, "amount": 1000.0}]}}
        self.assertAlmostEqual(rc.receiver_buyer_cost(rcosts), 2000.0)

    def test_detalle_del_propio_comprador_no_descuenta(self):
        rcosts = {"receiver": {"cost": 3000.0, "user_id": BUYER,
                               "cost_details": [{"sender_id": BUYER, "amount": 3000.0}]}}
        self.assertEqual(rc.receiver_buyer_cost(rcosts), 3000.0)

    def test_nunca_negativo_y_entradas_raras(self):
        rcosts = {"receiver": {"cost": 100.0, "cost_details": [{"sender_id": SELLER, "amount": 500.0}]}}
        self.assertEqual(rc.receiver_buyer_cost(rcosts), 0.0)
        for bad in (None, {}, {"receiver": None}, {"receiver": "x"}, []):
            self.assertEqual(rc.receiver_buyer_cost(bad), 0.0)



class TestShippingMissingInPaid(unittest.TestCase):
    f = staticmethod(rc.shipping_missing_in_paid)

    def test_me1_pago_con_envio_paid_sin_envio(self):
        # ML <order_id> (un cliente): total == paid == 3.138.200, pago con envio 205.570
        self.assertEqual(self.f(205570, 3138200, 3138200, 0, 205570, 1), 205570)

    def test_pago_con_envio_y_paid_que_ya_lo_trae_no_suma(self):
        self.assertEqual(self.f(205570, 3343770, 3138200, 0, 205570, 1), 0.0)

    def test_pago_con_envio_en_pack_no_mezcla_niveles(self):
        self.assertEqual(self.f(205570, 3138200, 3138200, 0, 205570, 2), 0.0)

    def test_pago_con_envio_y_paid_ambiguo_no_suma(self):
        # paid por encima de los items pero no por el flete entero (financiacion, etc.)
        self.assertEqual(self.f(205570, 3150000, 3138200, 0, 205570, 1), 0.0)

    def test_pago_con_envio_con_cupon(self):
        # paid = total - cupon, sin envio
        self.assertEqual(self.f(5000, 95000, 100000, 5000, 5000, 1), 5000)

    def test_k25_pago_sin_envio_paid_sin_envio_suma(self):
        self.assertEqual(self.f(8000, 100000, 100000, 0, 0, 1), 8000)

    def test_k25_pago_sin_envio_paid_con_envio_no_suma(self):
        self.assertEqual(self.f(8000, 108000, 100000, 0, 0, 1), 0.0)

    def test_comprador_no_paga_envio(self):
        self.assertEqual(self.f(0, 100000, 100000, 0, 0, 1), 0.0)
        self.assertEqual(self.f(0, 100000, 100000, 0, 5000, 1), 0.0)

    def test_idempotente_sobre_el_estado_de_la_linea(self):
        # El criterio no mira amount_total ni la linea: mismo resultado en cada pasada.
        a = self.f(205570, 3138200, 3138200, 0, 205570, 1)
        b = self.f(205570, 3138200, 3138200, 0, 205570, 1)
        self.assertEqual(a, b)


def _costs(cost, buyer, seller, seller_cost=0.0, gross=None):
    return {"receiver": {"cost": cost, "user_id": buyer, "cost_details": [{"sender_id": seller, "amount": cost}]},
            "gross_amount": gross if gross is not None else cost + seller_cost,
            "senders": [{"user_id": seller, "cost": seller_cost}]}


def _ship_pay(pid, amount, ship_id, status="approved", desc="marketplace_shipment"):
    return {"id": pid, "status": status, "transaction_amount": amount, "description": desc,
            "external_reference": str(ship_id)}


class TestFletePackCobrado(unittest.TestCase):
    """[#caso-K02/#caso-K21/#caso-K22, 27-oct-2026] Payloads REALES (GET /shipments/<id>/costs y
    /v1/payments/search?external_reference=<envio> con el token de cada vendedor).
    En los 7 casos cost_details nombra al vendedor por receiver.cost entero: no discrimina.
    Lo que discrimina es el pago MP marketplace_shipment cobrado por el vendedor."""

    CASES = [
        # (nombre, envio, rcosts, search_json, use_payment, payment_shipping, option_cost, esperado_receiver, esperado_linea)
        ("K02 pack ME1 ML 2000384899703529", 42331350052,
         _costs(102089, 3731085, 196350138),
         {"results": [_ship_pay(185004403007, 102089, 42331350052)]}, True, 0.0, 102089, 102089, 102089),
        ("K02 pack ME2 KETER ML 2000535052182916", 42457144866,
         _costs(8692, 380406917, 337163020, seller_cost=23390, gross=82060),
         {"results": [_ship_pay(185039582613, 8692, 42457144866)]}, True, 0.0, 8692, 8692, 8692),
        ("cliente F caso-K21 pack Full SO 6219", 44072759283,
         _costs(1299.8, 175181508, 570653807),
         {"results": [_ship_pay(183298296955, 1299.8, 44072759283)]}, True, 0.0, 1299.8, 1299.8, 1299.8),
        ("cliente F caso-K21 pack Full SO 6232", 44194202845,
         _costs(4999, 222948840, 570653807),
         {"results": [_ship_pay(185054666366, 4999, 44194202845)]}, True, 0.0, 4999, 4999, 4999),
        ("K22 pack Full Super SO 1106 (lo cobra ML, no el vendedor)", 45335115314,
         _costs(79, 3485303698, 573976600, seller_cost=6, gross=85),
         {"results": []}, True, 0.0, 79, 0.0, 0.0),
        ("K22 pack Full Super SO 1795", 42816333134,
         _costs(99, 1136045267, 573976600, seller_cost=6, gross=105),
         {"results": []}, True, 0.0, 99, 0.0, 0.0),
        # Control positivo: no-pack con el flete DENTRO del pago de la orden (no hay pago aparte).
        ("K02 NO-pack ME1 ML 2000754024405310 (control)", 42040239173,
         _costs(200640, 835204409, 196350138),
         {"results": []}, True, 200640.0, 200640, 0.0, 200640),
    ]

    def test_casos_reales(self):
        for name, ship, rcosts, search, use_pay, pay_ship, opt, exp_rc, exp_line in self.CASES:
            with self.subTest(name):
                collected = rc.seller_collected_shipping(search, ship)
                got_rc = rc.pack_receiver_cost(rcosts, collected, previous=None)
                self.assertAlmostEqual(got_rc, exp_rc, places=2)
                self.assertAlmostEqual(rc.buyer_shipping_amount(use_pay, pay_ship, opt, got_rc), exp_line, places=2)

    def test_cost_details_no_discrimina(self):
        # El criterio anterior (26.166..26.316) da 0 en los 7: por eso caso-K02 y cliente F perdian el flete cobrado.
        for name, ship, rcosts, *_ in self.CASES:
            with self.subTest(name):
                self.assertEqual(rc.receiver_buyer_cost(rcosts), 0.0)

    def test_ignora_pagos_que_no_son_el_flete_de_este_envio(self):
        ship = 42331350052
        search = {"results": [
            _ship_pay(1, 102089, ship, status="refunded"),
            _ship_pay(2, 102089, ship, desc="Sombrilla Jardin"),
            _ship_pay(3, 50, 99999999999),
            _ship_pay(4, 102089, ship),
        ]}
        self.assertEqual(rc.seller_collected_shipping(search, ship), 102089)

    def test_consulta_fallida_no_asume(self):
        rcosts = _costs(4999, 222948840, 570653807)
        for bad in (None, {}, {"error": "unauthorized"}, {"results": None}, "x"):
            with self.subTest(bad=bad):
                self.assertIsNone(rc.seller_collected_shipping(bad, 44194202845))
        # queda lo que habia
        self.assertEqual(rc.pack_receiver_cost(rcosts, None, previous=4999.0), 4999.0)
        self.assertEqual(rc.pack_receiver_cost(rcosts, None, previous=0.0), 0.0)
        # envio nuevo: el criterio anterior
        self.assertEqual(rc.pack_receiver_cost(rcosts, None, previous=None), rc.receiver_buyer_cost(rcosts))

    def test_sin_flete_del_comprador_no_consulta_y_da_0(self):
        # envio gratis real (caso-K13 MLM: receiver.cost 0, option.cost 0)
        rcosts = {"receiver": {"cost": 0, "user_id": 1537271697, "cost_details": []}, "senders": [{"cost": 190}]}
        self.assertEqual(rc.receiver_gross_cost(rcosts), 0.0)
        self.assertEqual(rc.pack_receiver_cost(rcosts, None, previous=123.0), 0.0)
        self.assertEqual(rc.pack_receiver_cost({"algo": True}, None, previous=None), 0.0)


if __name__ == "__main__":
    unittest.main()
