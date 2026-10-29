# -*- coding: utf-8 -*-
"""#696 (535, 29-oct-2026): el import de ordenes no reescribe contactos si nada cambio.

En 535 hubo 62.022 mensajes de seguimiento de direccion (res.partner contact_address_inline) en un mes.
Causa: en la MISMA vuelta de import, el contacto de ENTREGA se escribia dos veces con datos distintos:
  1) orders.py arma el receiver desde el envio ya guardado y no llevaba `zip_code` => CP vacio;
  2) el camino de packs de shipment.py usa el JSON de ML => CP de vuelta.
Dos cambios reales por import => dos trackings por resync. Ademas el precio de lista del comprador se
escribia en cada import aunque fuera el mismo.

Criterio: un 2do import con los mismos datos da 0 writes y 0 mail.tracking.value en los contactos.
Sin red. Correr:
  odoo-bin ... -u meli_oerp --test-enable --test-tags meli_696_partner --stop-after-init
"""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'meli_696_partner')
class TestContactoSinWritesRedundantes696(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.company.mercadolibre_cron_get_orders_shipment_client = True
        self.Partner = self.env['res.partner']
        self.Orders = self.env['mercadolibre.orders']
        self.Shipment = self.env['mercadolibre.shipment']
        self.mx = self.env.ref('base.mx')
        self.jal = self.env['res.country.state'].search(
            [('country_id', '=', self.mx.id), ('code', '=', 'JAL')], limit=1)
        self.principal = self.Partner.create({'name': 'Comprador ML 696', 'meli_buyer_id': '69600001'})
        # receiver_address tal como llega en el JSON del envio de ML
        self.receiver_json = {
            'id': 69600001,
            'receiver_name': 'Receptor 696',
            'receiver_phone': 'XXXXXXX',
            'address_line': 'Av. Siempre Viva 742',
            'street_name': 'Av. Siempre Viva',
            'street_number': '742',
            'comment': '',
            'zip_code': '44100',
            'city': {'id': 'TUxNQ0dVQTUxNzY', 'name': 'Guadalajara'},
            'state': {'id': 'MX-JAL', 'name': 'Jalisco'},
            'country': {'id': 'MX', 'name': 'Mexico'},
        }
        # el envio ya guardado (lo que usa orders.py en los imports siguientes)
        self.ship = self.Shipment.create({
            'shipping_id': '69600000001',
            'receiver_address_line': 'Av. Siempre Viva 742',
            'receiver_address_name': 'Receptor 696',
            'receiver_address_phone': 'XXXXXXX',
            'receiver_street_name': 'Av. Siempre Viva',
            'receiver_street_number': '742',
            'receiver_zip_code': '44100',
            'receiver_city': 'Guadalajara',
            'receiver_city_code': 'TUxNQ0dVQTUxNzY',
            'receiver_state': 'Jalisco',
            'receiver_state_code': 'MX-JAL',
            'receiver_country': 'Mexico',
            'receiver_country_code': 'MX',
        })

    # --- utilidades -------------------------------------------------------------------------------
    def _flush_tracking(self):
        self.env.flush_all()
        self.env.cr.precommit.run()

    def _trackings(self, partners):
        if 'mail.tracking.value' not in self.env:
            return 0  # sin mail instalado no hay seguimiento (los writes se cuentan igual)
        return self.env['mail.tracking.value'].sudo().search_count([
            ('mail_message_id.model', '=', 'res.partner'),
            ('mail_message_id.res_id', 'in', partners.ids),
        ])

    def _recv_guardado(self):
        """receiver armado desde el envio guardado, como lo hace orders.py en los imports siguientes.
        Sin el helper (codigo anterior a #696) se arma igual que el bloque viejo, que no llevaba zip_code:
        asi el control sobre el codigo viejo falla por writes/trackings y no por un nombre faltante."""
        if hasattr(self.Orders, '_meli_receiver_from_shipment'):
            return self.Orders._meli_receiver_from_shipment(self.ship)
        s = self.ship
        return {
            'receiver_address': s.receiver_address_line, 'address_line': s.receiver_address_line,
            'receiver_name': s.receiver_address_name, 'receiver_phone': s.receiver_address_phone,
            'country': {'id': s.receiver_country_code, 'name': s.receiver_country},
            'state': {'name': s.receiver_state, 'id': s.receiver_state_code},
            'city': {'name': s.receiver_city, 'id': s.receiver_city_code},
        }

    def _una_vuelta_de_import(self):
        """Lo que hace UN import de una orden de pack sobre el contacto de entrega:
        orders.py (receiver desde el envio guardado) y luego shipment.py (receiver del JSON)."""
        recv_guardado = self._recv_guardado()
        d1 = self.Shipment.partner_delivery_id(
            partner_id=self.principal, Receiver=recv_guardado, config=self.company)
        # en produccion hay commits entre los dos caminos (MeliCommit): el seguimiento se cierra en
        # cada uno. Sin este flush Odoo compara inicio vs final de la vuelta y no ve la alternancia.
        self._flush_tracking()
        d2 = self.Shipment.partner_delivery_id(
            partner_id=self.principal, Receiver=dict(self.receiver_json), config=self.company)
        self._flush_tracking()
        return d1, d2

    # --- casos ------------------------------------------------------------------------------------
    def test_receiver_desde_envio_lleva_cp(self):
        recv = self._recv_guardado()
        self.assertEqual(recv.get('zip_code'), '44100')
        self.assertEqual(recv['address_line'], self.receiver_json['address_line'])
        self.assertEqual(recv['state']['id'], 'MX-JAL')

    def test_segundo_import_igual_cero_writes_cero_tracking(self):
        d1, d2 = self._una_vuelta_de_import()
        self.assertTrue(d2, 'el contacto de entrega se crea en el primer import')
        self.assertEqual(d1, d2, 'mismo contacto de entrega en los dos caminos')
        self.assertEqual(d2.zip, '44100')
        antes = self._trackings(self.principal | d2)

        Partner = type(self.Partner)
        orig_write = Partner.write
        writes = []

        def _spy(recs, vals):
            if recs & (self.principal | d2):
                writes.append((recs.ids, sorted(vals)))
            return orig_write(recs, vals)

        with patch.object(Partner, 'write', _spy):
            self._una_vuelta_de_import()
            self._una_vuelta_de_import()

        nuevos = self._trackings(self.principal | d2) - antes
        self.assertEqual((len(writes), nuevos), (0, 0),
                         'un import con los mismos datos no escribe el contacto ni genera seguimiento: '
                         'writes=%s trackings_nuevos=%s' % (writes, nuevos))
        self.assertEqual(d2.zip, '44100')

    def test_dato_ausente_no_borra_lo_guardado(self):
        _d1, d2 = self._una_vuelta_de_import()
        incompleto = dict(self.receiver_json)
        incompleto.pop('zip_code')
        self.Shipment.partner_delivery_id(partner_id=self.principal, Receiver=incompleto, config=self.company)
        self.assertEqual(d2.zip, '44100')

    def test_cambio_real_si_se_escribe(self):
        _d1, d2 = self._una_vuelta_de_import()
        nuevo = dict(self.receiver_json, zip_code='44110')
        self.Shipment.partner_delivery_id(partner_id=self.principal, Receiver=nuevo, config=self.company)
        self.assertEqual(d2.zip, '44110')

    def test_contacto_de_facturacion_mismos_valores_no_se_escribe(self):
        from odoo.addons.meli_oerp.models.orders import _meli_partner_vals_changed
        fact = self.Partner.create({'name': 'Razon Social 696', 'type': 'invoice', 'vat': 'XIA190128J61',
                                    'street': 'Calle 1', 'zip': '44100', 'country_id': self.mx.id,
                                    'state_id': self.jal.id or False})
        same = {'name': 'Razon Social 696', 'vat': 'XIA190128J61', 'street': 'Calle 1', 'zip': '44100',
                'country_id': self.mx.id, 'state_id': self.jal.id or False}
        self.assertEqual(_meli_partner_vals_changed(fact, same), {})
        self.assertEqual(_meli_partner_vals_changed(fact, dict(same, zip='44110')), {'zip': '44110'})
