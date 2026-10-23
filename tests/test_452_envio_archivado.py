# -*- coding: utf-8 -*-
"""[26.291 #452] Servicio de envio archivado => se creaba uno nuevo por venta.

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

    # --- comportamiento del flujo real (sin el helper): falla en origin <= 26.290 ---

    def _sync_envio_me1(self):
        """Una pasada de _update_sale_order_shipping_info para una venta ME1 sin transportista."""
        partner = self.env['res.partner'].create({'name': 'Comprador 452'})
        sorder = self.env['sale.order'].create({'partner_id': partner.id, 'company_id': self.company.id})
        morder = self.env['mercadolibre.orders'].create({'order_id': '452%d' % sorder.id})
        ship = self.Ship.create({'sale_order': sorder.id, 'mode': 'me1', 'shipping_cost': 0.0})
        ship._update_sale_order_shipping_info(morder, config=self.company)

    def _me1_count(self):
        # sin filtro de compania: el flujo puede reasignar la compania del servicio/transportista
        return self.Product.search_count([('name', '=', 'ME1 - zip')])

    def test_flujo_me1_archivado_no_crea_otro(self):
        """El caso real: ENVIO-ME1 archivado por el cliente => antes se creaba un 'ME1 - zip' nuevo."""
        self._prod('ME1 - zip', 'ENVIO-ME1', active=False)
        self._sync_envio_me1()
        self.assertEqual(self._me1_count(), 1, "con el ENVIO-ME1 archivado no se crea otro producto de envio")

    def test_flujo_me1_referencia_pisada_no_se_multiplica(self):
        """product_sequence pisa la referencia: cada pasada del cron creaba uno mas."""
        self._prod('ME1 - zip', '001300')
        self._sync_envio_me1()
        self._sync_envio_me1()
        self.assertEqual(self._me1_count(), 1, "dos pasadas con la referencia pisada no multiplican el producto")
