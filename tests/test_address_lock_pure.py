# -*- coding: utf-8 -*-
"""address_lock (#caso-K03 cliente A) — SIN Odoo.

Correr:  python3 meli_oerp/tests/test_address_lock_pure.py   (desde la raiz de addons)
NO esta en tests/__init__.py a proposito (carga models/address_lock.py por ruta).
"""
import importlib.util
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "meli_address_lock", os.path.join(_HERE, "..", "models", "address_lock.py"))
al = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(al)

BUYER, ML_DELIV, ML_DELIV_2, MANUAL_DELIV, BILLING = 10, 20, 21, 30, 40


class TestDecideOrderContact(unittest.TestCase):

    def test_pedido_nuevo_toma_ml(self):
        self.assertEqual(al.decide_order_contact(True, False, False, BUYER, ML_DELIV), al.WRITE)

    def test_campo_vacio_toma_ml(self):
        self.assertEqual(al.decide_order_contact(False, False, ML_DELIV, BUYER, ML_DELIV), al.WRITE)

    def test_ml_no_trae_contacto_no_toca(self):
        self.assertEqual(al.decide_order_contact(False, MANUAL_DELIV, ML_DELIV, BUYER, False), al.NONE)

    def test_igual_no_escribe(self):
        self.assertEqual(al.decide_order_contact(False, ML_DELIV, ML_DELIV, BUYER, ML_DELIV), al.SAME)

    def test_cambio_manual_se_respeta(self):
        # caso-K03: el usuario cambio la entrega; ML sigue diciendo la original
        self.assertEqual(al.decide_order_contact(False, MANUAL_DELIV, ML_DELIV, BUYER, ML_DELIV), al.MANUAL)

    def test_factura_manual_se_respeta(self):
        self.assertEqual(al.decide_order_contact(False, BUYER, BILLING, BUYER, BILLING), al.MANUAL)

    def test_cambio_en_ml_sin_toque_manual_entra(self):
        # el comprador cambio la direccion en ML y nadie toco el pedido
        self.assertEqual(al.decide_order_contact(False, ML_DELIV, ML_DELIV, BUYER, ML_DELIV_2), al.WRITE)

    def test_contacto_editado_a_mano_bloquea(self):
        self.assertEqual(al.decide_order_contact(False, ML_DELIV, ML_DELIV, BUYER, ML_DELIV_2,
                                                 current_edited=True), al.MANUAL)

    def test_legado_valor_por_defecto_es_del_conector(self):
        # pedido anterior al registro, entrega = el propio cliente (default de Odoo)
        self.assertEqual(al.decide_order_contact(False, BUYER, False, BUYER, ML_DELIV), al.WRITE)

    def test_legado_otro_valor_se_respeta(self):
        self.assertEqual(al.decide_order_contact(False, MANUAL_DELIV, False, BUYER, ML_DELIV), al.MANUAL)

    def test_legado_igual_se_adopta(self):
        self.assertEqual(al.decide_order_contact(False, ML_DELIV, False, BUYER, ML_DELIV), al.SAME)


class TestLocked(unittest.TestCase):

    def test_vacio_no_bloquea(self):
        self.assertFalse(al.order_contact_locked(False, ML_DELIV, BUYER))

    def test_del_conector_no_bloquea(self):
        self.assertFalse(al.order_contact_locked(ML_DELIV, ML_DELIV, BUYER))

    def test_manual_bloquea(self):
        self.assertTrue(al.order_contact_locked(MANUAL_DELIV, ML_DELIV, BUYER))


class TestFingerprint(unittest.TestCase):

    BASE = {'street': 'Cra 7 # 45-10', 'street2': 'Apto 301', 'city': 'Bogota', 'zip': '110111',
            'state_id': 5, 'country_id': 49, 'phone': '3001234567'}

    def test_estable_ante_espacios_y_mayusculas(self):
        other = dict(self.BASE, street='  CRA 7  # 45-10 ', city='bogota')
        self.assertEqual(al.address_fingerprint(self.BASE), al.address_fingerprint(other))

    def test_cambia_con_la_calle(self):
        other = dict(self.BASE, street='Calle 100 # 15-20')
        self.assertNotEqual(al.address_fingerprint(self.BASE), al.address_fingerprint(other))

    def test_vacios_equivalentes(self):
        a = dict(self.BASE, street2=False)
        b = dict(self.BASE, street2=None)
        c = dict(self.BASE)
        c.pop('street2')
        self.assertEqual(al.address_fingerprint(a), al.address_fingerprint(b))
        self.assertEqual(al.address_fingerprint(a), al.address_fingerprint(c))

    def test_sin_huella_no_es_manual(self):
        self.assertFalse(al.address_manually_edited(False, self.BASE))

    def test_huella_igual_no_es_manual(self):
        self.assertFalse(al.address_manually_edited(al.address_fingerprint(self.BASE), self.BASE))

    def test_editada_es_manual(self):
        fp = al.address_fingerprint(self.BASE)
        self.assertTrue(al.address_manually_edited(fp, dict(self.BASE, phone='3109999999')))


if __name__ == '__main__':
    unittest.main()
