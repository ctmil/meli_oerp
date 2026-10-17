# -*- coding: utf-8 -*-
"""[#603 / #595 Shoppy 502] Reparto de importes agregados entre lineas.

Corre dentro de Odoo (tag `meli_prorate`) y tambien suelto, sin Odoo:
    python3 meli_oerp/tests/test_meli_prorate.py
Los numeros son de la base de 502 (lectura 5-oct-2026), no inventados.
"""
import os
import unittest

try:
    from odoo.tests import tagged
    from odoo.tests.common import BaseCase as _Base
    from odoo.addons.meli_oerp.models import meli_prorate as mp
except Exception:  # fuera de Odoo
    import importlib.util
    _Base = unittest.TestCase

    def tagged(*_a):
        return lambda cls: cls
    _p = os.path.join(os.path.dirname(__file__), '..', 'models', 'meli_prorate.py')
    _s = importlib.util.spec_from_file_location('meli_prorate', _p)
    mp = importlib.util.module_from_spec(_s)
    _s.loader.exec_module(mp)


# carrito -> (importe de cada sub-orden, cupon del carrito, cupon que ML asigno a cada sub-orden)
CARRITOS_502 = {
    'ML 2000014810505643': ([12012.00, 30901.20], 4291.32, [1201.21, 3090.11]),
    'ML 2000014926971999': ([25300.00, 3799.00], 2909.90, [2529.98, 379.92]),
    'ML 2000014809450849': ([31660.90, 11653.60, 7907.25, 3600.63, 3829.00], 4692.11,
                            [2532.87, 932.28, 632.60, 288.05, 306.31]),
    'ML 2000014963729457': ([3699.00, 66499.00], 7019.80, [369.90, 6649.90]),
}


def _c(x):
    return int(round(x * 100))


@tagged('post_install', '-at_install', 'meli', 'meli_prorate')
class TestMeliProrate(_Base):

    def test_carritos_reales_cuadran_al_centavo_y_sin_negativos(self):
        for name, (lineas, cupon, _ml) in CARRITOS_502.items():
            partes = mp.prorate_cents(lineas, cupon)
            self.assertEqual(sum(_c(p) for p in partes), _c(cupon), name)
            netas = [l - p for l, p in zip(lineas, partes)]
            self.assertTrue(all(n >= 0 for n in netas), name)
            # suma de lineas = lo que pago el comprador por los productos (bruto - cupon)
            self.assertEqual(sum(_c(n) for n in netas), _c(sum(lineas)) - _c(cupon), name)

    def test_reparto_proporcional_reproduce_el_de_mercadolibre(self):
        # ML ya reparte el cupon del carrito entre sus sub-ordenes en proporcion al importe:
        # el reparto propio no se aparta mas de 3 centavos por linea del que informa ML.
        for name, (lineas, cupon, ml) in CARRITOS_502.items():
            partes = mp.prorate_cents(lineas, cupon)
            self.assertLessEqual(max(abs(_c(p) - _c(m)) for p, m in zip(partes, ml)), 3, name)

    def test_orden_suelta_con_cupon_de_ml_cuadra_con_lo_cobrado(self):
        # ML 2000018227850006: 1 linea 69.862,44; cupones pagados por ML 11.099,64;
        # total_paid_amount de sus 2 pagos = 25.000,00 + 33.762,80 = 58.762,80.
        partes = mp.prorate_cents([69862.44], 11099.64)
        self.assertEqual(_c(69862.44 - partes[0]), _c(25000.00 + 33762.80))

    def test_descuento_mayor_que_la_orden_no_deja_negativos(self):
        # 01-oct, ML 2000018696820692: discount_seller_amount 132.462,50 sobre 73.499 =>
        # el codigo viejo dejo la linea en -48.730,17. Acotado al cupon (7.349,90) no pasa.
        tope = mp.bounded_order_discount(132462.50, 7349.90)
        self.assertEqual(tope, 7349.90)
        partes = mp.prorate_cents([73499.00], tope)
        self.assertEqual(_c(73499.00 - partes[0]), _c(66149.10))  # = total_paid_amount del pago
        # y aunque se pidiera repartir mas que el total, ninguna parte supera su linea
        partes = mp.prorate_cents([100.0, 0.01, 50.0], 1e9)
        self.assertEqual([_c(p) for p in partes], [10000, 1, 5000])

    def test_sin_cupon_no_se_descuenta_nada(self):
        self.assertEqual(mp.bounded_order_discount(113030.01, 0.0), 0.0)
        self.assertEqual(mp.prorate_cents([10.0, 20.0], 0), [0.0, 0.0])
        self.assertEqual(mp.prorate_cents([], 5), [])
        self.assertEqual(mp.prorate_cents([0.0, 0.0], 5), [0.0, 0.0])

    def test_595_la_linea_barata_del_carrito_ya_no_queda_afuera(self):
        # ML 2000014963729457: pagado 70.198, cupon 7.019,80. Orden de alta por order_id:
        # COMBO0002 66.499 y despues el cepillo C04538LI 3.699.
        pagado, cupon = 70198.00, 7019.80
        viejo = lambda total, linea: total < (pagado - cupon)
        self.assertTrue(viejo(0.0, 66499.00))
        self.assertFalse(viejo(66499.00, 3699.00))          # el bug: el cepillo no entraba
        self.assertTrue(mp.pack_line_fits(0.0, pagado, 66499.00))
        self.assertTrue(mp.pack_line_fits(66499.00, pagado, 3699.00))
        # una linea que ya no cabe (p.ej. producto reemplazado a mano) no se re-crea
        self.assertFalse(mp.pack_line_fits(70198.00, pagado, 3699.00))

    def test_595_carritos_del_ticket(self):
        # (pagado, cupon, sub-ordenes en orden de order_id) -> la ultima faltaba
        casos = {
            'ML 2000014973022159': (33696.00, 3369.60, [10699.00, 19998.00, 2999.00]),
            'ML 2000014809450849': (58651.38, 4692.11, [3600.63, 7907.25, 11653.60, 31660.90, 3829.00]),
        }
        for name, (pagado, cupon, subs) in casos.items():
            total_viejo = total_nuevo = 0.0
            for s in subs:
                if total_viejo < pagado - cupon:
                    total_viejo += s
                if mp.pack_line_fits(total_nuevo, pagado, s):
                    total_nuevo += s
            self.assertLess(total_viejo, pagado - 1, name)
            self.assertEqual(_c(total_nuevo), _c(pagado), name)

    def test_propiedades_en_20000_casos_aleatorios(self):
        import random
        rnd = random.Random(502)
        for _ in range(20000):
            n = rnd.randint(1, 8)
            lineas = [round(rnd.uniform(0, 200000), 2) for _ in range(n)]
            monto = round(rnd.uniform(0, sum(lineas) * 1.5), 2)
            partes = mp.prorate_cents(lineas, monto)
            esperado = min(_c(monto), sum(_c(l) for l in lineas))
            self.assertEqual(sum(_c(x) for x in partes), esperado)
            for l, x in zip(lineas, partes):
                self.assertTrue(0 <= _c(x) <= _c(l))


if __name__ == '__main__':
    unittest.main()
