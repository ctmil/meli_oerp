# -*- coding: utf-8 -*-
"""26.371 (#462 Matices/Olpa, B1 armonización 18.0): lo que corría sólo en el cliente.

  T4 (P1, 30de2f8) Odoo 17.2+/18: una línea creada con price_unit en los vals queda con
     technical_price_unit == price_unit y Odoo la lee como "precio NO fijado a mano": un write posterior
     de product_uom_qty recomputa el precio a la tarifa (SO 6212: 133.881 -> 183.912). El precio de ML
     se marca como fijado (technical_price_unit = -1).
  T5 (P2, b53781b) diagnóstico de stock: el UPDATE de meli_last_status va en un SAVEPOINT. Un error de
     Postgres ahí (40001 contra el cron de stock) dejaba la transacción ABORTADA y se perdía la corrida.
Control (origin/18.0 26.370) ⇒ ROJO las dos.
Correr: odoo-bin ... --test-enable --test-tags meli_b462 --stop-after-init
"""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install', 'meli_b462')
class TestMatices462MeliOerp(TransactionCase):

    def test_t4_price_unit_de_ml_no_se_recomputa(self):
        SOL = self.env['sale.order.line']
        if 'technical_price_unit' not in SOL._fields:
            self.skipTest("Odoo sin technical_price_unit (16.0): no hay recompute que proteger")
        product = self.env['product.product'].create({'name': 'Agenda T4 462', 'list_price': 183912.0,
                                                      'taxes_id': [(5, 0, 0)]})
        upd = self.env['mercadolibre.orders'].new({})._set_product_unit_price(
            product, {'unit_price': 133881.0, 'quantity': 1}, config=self.env.company)
        self.assertEqual(upd.get('technical_price_unit'), -1.0, upd)
        partner = self.env['res.partner'].create({'name': 'Comprador T4 462'})
        so = self.env['sale.order'].create({'partner_id': partner.id})
        vals = dict(upd, order_id=so.id, product_id=product.id, product_uom_qty=1.0)
        line = SOL.create(vals)
        self.assertAlmostEqual(line.price_unit, 133881.0, places=2)
        line.write({'product_uom_qty': 2.0})
        self.assertAlmostEqual(line.price_unit, 133881.0, places=2, msg="el precio de ML no se recomputa a la tarifa")
        line.write({'product_id': product.id})
        self.assertAlmostEqual(line.price_unit, 133881.0, places=2)

    def test_t5_diagnostico_savepoint_no_aborta_la_transaccion(self):
        if 'mercadolibre.product' not in self.env:
            self.skipTest("sin meli_oerp_multiple el UPDATE no corre")
        cr = self.env.cr
        orig = cr.execute
        hits = []

        def boom(query, params=None, log_exceptions=True):
            if 'UPDATE mercadolibre_product' in str(query):
                hits.append(1)
                return orig("SELECT 1/0")   # error REAL de Postgres, como el 40001
            return orig(query, params, log_exceptions)

        product = self.env['product.product'].create({'name': 'Diag T5 462'})
        with patch.object(cr, 'execute', boom), mute_logger('odoo.sql_db'):
            self.env.company._meli_diag_persist_ml_status(product.id, 'MLA4625001', 'active', 3)
        self.assertEqual(hits, [1], "el UPDATE se intentó")
        cr.execute("SELECT 1")
        self.assertEqual(cr.fetchone()[0], 1, "la transacción sigue viva: el diagnóstico sigue con el próximo ítem")
