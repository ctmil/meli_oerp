# -*- coding: utf-8 -*-
"""26.394 (un caso): avisos de sincronización de envío en el chatter UNA vez por venta.

Antes, en shipment._update_sale_order_shipping_info:
- «Companias Coinciden OK…» iba con message_post directo => saltaba `mercadolibre_notification_mode`
  (el cliente con modo 'none' lo seguía viendo), y salía aunque las compañías NO coincidieran;
- «Sin servicio de envio o carrier.» salía en CADA sincronización (sin guarda).
Ahora pasan por meli_message_post con once_key + guarda de legado (`legacy_text`).

Control: en la rama de versión SIN el fix, test_modo_none_no_postea y los tests del helper
(legacy_text) FALLAN / dan ERROR.

    odoo-bin -d <db> -i meli_oerp --test-enable --test-tags meli_26394 --stop-after-init
"""
from unittest.mock import patch

from odoo.addons.meli_oerp.models import shipment as shipment_mod
from odoo.addons.meli_oerp.models.versions import meli_message_post
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

OK_NOTE = "Companias Coinciden OK, Carrier, Servicio de envio y Pedido"
NO_CARRIER = "Sin servicio de envio o carrier."


@tagged('post_install', '-at_install', 'meli', 'meli_26394')
class TestMeli26394ChatterOnce(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        gfield = 'group_ids' if 'group_ids' in cls.env.user._fields else 'groups_id'
        cls.env.user.write({gfield: [(4, cls.env.ref('sales_team.group_sale_manager').id)]})
        co = cls.env.company
        cls.partner = cls.env['res.partner'].create({'name': 'Cliente 26394'})
        P = cls.env['product.product']
        cls.prod = P.create({'name': 'Prod 26394', 'type': 'service', 'invoice_policy': 'order',
                             'taxes_id': [(5, 0, 0)]})
        cls.ship = P.create({'name': 'Envio 26394', 'default_code': 'Envio 26394', 'type': 'service',
                             'invoice_policy': 'order', 'taxes_id': [(5, 0, 0)], 'company_id': co.id})
        cls.carrier = cls.env['delivery.carrier'].create({'name': 'Envio 26394', 'product_id': cls.ship.id,
                                                          'company_id': co.id})
        for f, v in (('mercadolibre_order_total_config', 'paid_amount'),
                     ('mercadolibre_including_shipping_cost', 'always')):
            if f in co._fields:
                co[f] = v

    def _mode(self, mode):
        self.env.company.mercadolibre_notification_mode = mode

    def _venta(self):
        tf = 'tax_ids' if 'tax_ids' in self.env['sale.order.line']._fields else 'tax_id'
        so = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {'product_id': self.prod.id, 'product_uom_qty': 1, 'price_unit': 100.0,
                                   tf: [(5, 0, 0)]})]})
        mo = self.env['mercadolibre.orders'].create({'order_id': '2000052394%06d' % so.id,
                                                     'name': '2000052394%06d' % so.id, 'sale_order': so.id})
        so.meli_orders = [(6, 0, [mo.id])]
        sh = self.env['mercadolibre.shipment'].create({
            'sale_order': so.id, 'tracking_method': 'Envio 26394', 'mode': 'me2',
            'shipping_cost': 0.0, 'shipping_seller_cost': 0.0, 'shipping_list_cost': 0.0})
        return so, mo, sh

    def _sync(self, so, mo, sh):
        """Una pasada de sincronización del envío (sin red)."""
        with patch.object(type(sh), '_meli_sync_picking_tracking', lambda self, sorder: None, create=True), \
             patch.object(type(so), 'meli_amount_to_invoice', lambda self, meli=None, config=None: 100.0, create=True), \
             patch.object(type(mo), '_ensure_payment_shipping_amounts', lambda self, meli=None, config=None: None,
                          create=True):
            sh._update_sale_order_shipping_info(mo, meli=None, config=self.env.company)

    def _count(self, rec, text):
        return self.env['mail.message'].search_count([
            ('model', '=', rec._name), ('res_id', '=', rec.id), ('body', 'like', text)])

    # --- camino real: dos sincronizaciones seguidas ---
    def test_dos_syncs_un_solo_aviso(self):
        self._mode('internal_note')
        so, mo, sh = self._venta()
        self._sync(so, mo, sh)
        self.assertEqual(so.carrier_id, self.carrier, "precondición: el carrier de la compañía quedó asignado")
        self.assertEqual(self._count(so, OK_NOTE), 1, "primera sincronización: un aviso")
        self._sync(so, mo, sh)
        self._sync(so, mo, sh)
        self.assertEqual(self._count(so, OK_NOTE), 1, "tres sincronizaciones => UN solo aviso")

    def test_modo_none_no_postea(self):
        self._mode('none')
        so, mo, sh = self._venta()
        self._sync(so, mo, sh)
        self._sync(so, mo, sh)
        self.assertEqual(self._count(so, OK_NOTE), 0,
                         "con mercadolibre_notification_mode='none' el aviso va sólo al log")

    def test_venta_vieja_con_aviso_sin_marca_no_repostea(self):
        self._mode('internal_note')
        so, mo, sh = self._venta()
        so.message_post(body=OK_NOTE)  # como lo dejaba el código anterior a 26.394 (sin marca once)
        self._sync(so, mo, sh)
        self.assertEqual(self._count(so, OK_NOTE), 1, "guarda de legado: no reabre la ronda en ventas viejas")

    # --- helper (también cubre «Sin servicio de envio o carrier.») ---
    def test_helper_once_key_y_legacy_text(self):
        self._mode('internal_note')
        so, mo, sh = self._venta()
        for _i in range(3):
            meli_message_post(so, NO_CARRIER, config=self.env.company,
                              once_key="ship-no-carrier-%s" % so.id, legacy_text=NO_CARRIER)
        self.assertEqual(self._count(so, NO_CARRIER), 1, "tres pasadas => un aviso")

    def test_helper_legacy_text_sin_marca(self):
        self._mode('internal_note')
        so, mo, sh = self._venta()
        so.message_post(body=NO_CARRIER)
        meli_message_post(so, NO_CARRIER, config=self.env.company,
                          once_key="ship-no-carrier-%s" % so.id, legacy_text=NO_CARRIER)
        self.assertEqual(self._count(so, NO_CARRIER), 1)

    def test_constantes_publicas(self):
        self.assertEqual(shipment_mod.MELI_SHIP_COMPANY_OK_NOTE, OK_NOTE)
        self.assertEqual(shipment_mod.MELI_SHIP_NO_CARRIER_NOTE, NO_CARRIER)

    # --- modo 'important' (26.394): rutina al log, lo accionable como nota interna ---
    def test_modo_important_rutina_al_log(self):
        self._mode('important')
        so, mo, sh = self._venta()
        self._sync(so, mo, sh)
        self._sync(so, mo, sh)
        self.assertEqual(so.carrier_id, self.carrier)
        self.assertEqual(self._count(so, OK_NOTE), 0, "modo important: «Coinciden OK» es rutina => sólo log")

    def test_modo_important_accionable_queda_como_nota(self):
        self._mode('important')
        so, mo, sh = self._venta()
        txt = "ACCION REQUERIDA 26394: gestionar a mano"
        meli_message_post(so, txt, config=self.env.company, once_key="t26394-acc-%s" % so.id)
        meli_message_post(so, "rutina 26394", config=self.env.company, routine=True)
        msg = self.env['mail.message'].search([('model', '=', so._name), ('res_id', '=', so.id),
                                                ('body', 'like', txt)])
        self.assertEqual(len(msg), 1, "lo accionable sigue en el chatter")
        self.assertEqual(msg.subtype_id, self.env.ref('mail.mt_note'), "como nota interna (sin inbox)")
        self.assertEqual(self._count(so, "rutina 26394"), 0)

    def test_otros_modos_ignoran_routine(self):
        self._mode('internal_note')
        so, mo, sh = self._venta()
        meli_message_post(so, "rutina 26394 b", config=self.env.company, routine=True)
        self.assertEqual(self._count(so, "rutina 26394 b"), 1, "routine sólo cambia algo con 'important'")
