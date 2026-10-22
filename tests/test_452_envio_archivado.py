# -*- coding: utf-8 -*-
"""[26.274 #452] Servicio de envio archivado => se creaba uno nuevo por venta.

Caso real (Global Value 452, 18.0): el cliente archivo el producto "ME1 - zip" (ENVIO-ME1) y los
de los transportistas; la busqueda sólo miraba activos y creaba uno nuevo en cada pasada del cron.
Con product_sequence (OCA) la referencia nueva no era ENVIO-ME1, asi que nunca lo volvia a encontrar.
Y el producto creado no se usaba: la linea toma el producto del transportista.
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'meli_452')
class TestMeli452EnvioArchivado(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.cdom = [('company_id', '=', cls.company.id)]
        cls.Ship = cls.env['mercadolibre.shipment']
        cls.Product = cls.env['product.product'].with_context(active_test=False)

    def _prod(self, name, code, active=True):
        return self.env['product.product'].create({
            'name': name, 'default_code': code, 'type': 'service',
            'company_id': self.company.id, 'active': active})

    def _find(self, name, mode):
        return self.Ship._meli_find_shipping_product(name, mode, self.company, self.cdom)

    def test_me1_archivado_se_reutiliza(self):
        arch = self._prod('ME1 - zip', 'ENVIO-ME1', active=False)
        self.assertEqual(self._find('ME1 - zip', 'me1'), arch,
                         "el ENVIO-ME1 archivado se reutiliza en vez de crear otro")

    def test_me1_referencia_pisada_por_secuencia(self):
        prod = self._prod('ME1 - zip', '001300')
        self.assertEqual(self._find('ME1 - zip', 'me1'), prod,
                         "con la referencia pisada (product_sequence) se encuentra por nombre")

    def test_activo_tiene_prioridad_sobre_archivado(self):
        self._prod('ME1 - zip', 'ENVIO-ME1-OLD', active=False)
        act = self._prod('ME1 - zip', 'ENVIO-ME1')
        self.assertEqual(self._find('ME1 - zip', 'me1'), act)

    def test_producto_del_transportista(self):
        prod = self._prod('Transporte 452', 'X452', active=False)
        self.env['delivery.carrier'].create({
            'name': 'MEL Distribution 452', 'product_id': prod.id, 'company_id': self.company.id})
        self.assertEqual(self._find('MEL Distribution 452', 'me2'), prod,
                         "sin producto propio, se usa el del transportista (el que va a la linea)")

    def test_no_me1_archivado_por_nombre(self):
        arch = self._prod('Places Pickup 452', 'Places Pickup 452', active=False)
        self.assertEqual(self._find('Places Pickup 452', 'me2'), arch)

    def test_sin_nada_devuelve_vacio(self):
        self.assertFalse(self._find('Inexistente 452', 'me2'))
