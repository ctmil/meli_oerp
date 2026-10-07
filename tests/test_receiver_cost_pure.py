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

    def test_olpa_envio_gratis_pagado_por_vendedor(self):
        # /shipments/48148291803/costs real (Olpa 462, orden 2000018743707872)
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

    def test_158_elvimarta_me1_pago_con_envio_paid_sin_envio(self):
        # ML 2000015003762179 (158, IHSA): total == paid == 3.138.200, pago con envio 205.570
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

    def test_620_pago_sin_envio_paid_sin_envio_suma(self):
        self.assertEqual(self.f(8000, 100000, 100000, 0, 0, 1), 8000)

    def test_620_pago_sin_envio_paid_con_envio_no_suma(self):
        self.assertEqual(self.f(8000, 108000, 100000, 0, 0, 1), 0.0)

    def test_comprador_no_paga_envio(self):
        self.assertEqual(self.f(0, 100000, 100000, 0, 0, 1), 0.0)
        self.assertEqual(self.f(0, 100000, 100000, 0, 5000, 1), 0.0)

    def test_idempotente_sobre_el_estado_de_la_linea(self):
        # El criterio no mira amount_total ni la linea: mismo resultado en cada pasada.
        a = self.f(205570, 3138200, 3138200, 0, 205570, 1)
        b = self.f(205570, 3138200, 3138200, 0, 205570, 1)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
