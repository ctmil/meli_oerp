# -*- coding: utf-8 -*-
"""26.403 (un caso): el modo de notificaciones de la compañía se ignoraba con multi-cuenta.

`mercadolibre_notification_mode` vive sólo en res.company. Con meli_oerp_multiple, `_get_config`
devuelve un `mercadolibre.configuration` (sin ese campo) y `meli_message_post` dejaba el modo en
'notification' por defecto: con la compañía en 'important' los avisos de RUTINA seguían saliendo
en el chatter de cada venta. Ahora el modo se resuelve desde config.company_id / record.company_id.

Control: en la rama de versión SIN el fix, los tests *_rutina_* FALLAN (la rutina se postea).

    odoo-bin -d <db> -i meli_oerp --test-enable --test-tags meli_26403 --stop-after-init
"""
from unittest.mock import patch

from odoo.addons.meli_oerp.models.versions import meli_message_post
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

OK_NOTE = "Companias Coinciden OK, Carrier, Servicio de envio y Pedido"
ROUTINE = "Monto correcto 26403"
ACTION = "ACCION REQUERIDA 26403: gestionar a mano"


@tagged('post_install', '-at_install', 'meli', 'meli_26403')
class TestMeli26403ModoConfigSinCampo(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        gfield = 'group_ids' if 'group_ids' in cls.env.user._fields else 'groups_id'
        cls.env.user.write({gfield: [(4, cls.env.ref('sales_team.group_sale_manager').id)]})
        cls.co = cls.env.company
        cls.co.mercadolibre_notification_mode = 'important'
        cls.partner = cls.env['res.partner'].create({'name': 'Cliente 26403'})
        P = cls.env['product.product']
        cls.prod = P.create({'name': 'Prod 26403', 'type': 'service', 'invoice_policy': 'order',
                             'taxes_id': [(5, 0, 0)]})
        cls.ship = P.create({'name': 'Envio 26403', 'default_code': 'Envio 26403', 'type': 'service',
                             'invoice_policy': 'order', 'taxes_id': [(5, 0, 0)], 'company_id': cls.co.id})
        cls.carrier = cls.env['delivery.carrier'].create({'name': 'Envio 26403', 'product_id': cls.ship.id,
                                                          'company_id': cls.co.id})
        for f, v in (('mercadolibre_order_total_config', 'paid_amount'),
                     ('mercadolibre_including_shipping_cost', 'always')):
            if f in cls.co._fields:
                cls.co[f] = v

    def _config_sin_campo(self):
        """Lo que devuelve _get_config con multiple: un mercadolibre.configuration (sin el campo
        del modo) de la compañía. Sin multiple instalado, cualquier registro con company_id y sin
        el campo reproduce lo mismo."""
        model = 'mercadolibre.configuration' if 'mercadolibre.configuration' in self.env else 'res.partner'
        conf = self.env[model].new({'company_id': self.co.id})
        self.assertNotIn('mercadolibre_notification_mode', conf._fields, "precondición: config SIN el campo")
        self.assertEqual(conf.company_id, self.co)
        return conf

    def _venta(self):
        tf = 'tax_ids' if 'tax_ids' in self.env['sale.order.line']._fields else 'tax_id'
        return self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {'product_id': self.prod.id, 'product_uom_qty': 1, 'price_unit': 100.0,
                                   tf: [(5, 0, 0)]})]})

    def _count(self, rec, text):
        return self.env['mail.message'].search_count([
            ('model', '=', rec._name), ('res_id', '=', rec.id), ('body', 'like', text)])

    def test_rutina_no_se_postea_con_config_sin_campo(self):
        so = self._venta()
        meli_message_post(so, ROUTINE, config=self._config_sin_campo(), routine=True)
        self.assertEqual(self._count(so, ROUTINE), 0,
                         "compañía en 'important' + config sin el campo => la rutina va sólo al log")

    def test_accionable_si_se_postea_como_nota(self):
        so = self._venta()
        meli_message_post(so, ACTION, config=self._config_sin_campo(), once_key="t26403-acc-%s" % so.id)
        msg = self.env['mail.message'].search([('model', '=', so._name), ('res_id', '=', so.id),
                                                ('body', 'like', ACTION)])
        self.assertEqual(len(msg), 1, "lo accionable sigue en el chatter")
        self.assertEqual(msg.subtype_id, self.env.ref('mail.mt_note'), "como nota interna (sin inbox)")

    def test_rutina_config_sin_campo_ni_compania_cae_a_la_venta(self):
        so = self._venta()
        meli_message_post(so, ROUTINE, config=self.env['res.currency'].search([], limit=1), routine=True)
        self.assertEqual(self._count(so, ROUTINE), 0, "sin compañía en config => modo de la compañía de la venta")

    def test_rutina_camino_real_sync_envio(self):
        """Camino real: _update_sale_order_shipping_info con la config de multi-cuenta."""
        so = self._venta()
        mo = self.env['mercadolibre.orders'].create({'order_id': '2000052403%06d' % so.id,
                                                     'name': '2000052403%06d' % so.id, 'sale_order': so.id})
        so.meli_orders = [(6, 0, [mo.id])]
        sh = self.env['mercadolibre.shipment'].create({
            'sale_order': so.id, 'tracking_method': 'Envio 26403', 'mode': 'me2',
            'shipping_cost': 0.0, 'shipping_seller_cost': 0.0, 'shipping_list_cost': 0.0})
        conf = self._config_sin_campo()
        with patch.object(type(sh), '_meli_sync_picking_tracking', lambda self, sorder: None, create=True), \
             patch.object(type(so), 'meli_amount_to_invoice', lambda self, meli=None, config=None: 100.0, create=True), \
             patch.object(type(mo), '_ensure_payment_shipping_amounts', lambda self, meli=None, config=None: None,
                          create=True):
            sh._update_sale_order_shipping_info(mo, meli=None, config=conf)
        self.assertEqual(so.carrier_id, self.carrier, "precondición: la sincronización corrió")
        self.assertEqual(self._count(so, OK_NOTE), 0, "«Coinciden OK» es rutina => no va al chatter")

    def test_config_con_campo_sigue_mandando(self):
        """Sin regresión: si config ES la compañía (tiene el campo), manda su valor."""
        so = self._venta()
        self.co.mercadolibre_notification_mode = 'internal_note'
        meli_message_post(so, ROUTINE, config=self.co, routine=True)
        self.assertEqual(self._count(so, ROUTINE), 1)
