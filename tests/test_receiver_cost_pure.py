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


if __name__ == "__main__":
    unittest.main()
