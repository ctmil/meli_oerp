# -*- coding: utf-8 -*-
"""[26.230] Filtros de facturacion de ventas ML.

1. `meli_invoice_state` (no almacenado, busqueda por SQL) clasifica igual al computar y al
   buscar: sin factura / borrador / publicada / con nota de credito.
2. TODOS los filtros de las dos busquedas de Ventas (Pedidos y Cotizaciones) se pueden
   ejecutar: se arma la vista combinada y se corre cada dominio (sirve de control de que la
   vista carga y de que ningun dominio apunta a un campo inexistente en esta serie).
"""
from lxml import etree

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged
from odoo.tools.safe_eval import safe_eval


@tagged('post_install', '-at_install', 'meli_K21')
class TestMeliK21FiltrosFacturacion(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product_a.invoice_policy = 'order'
        # Quien usa estos filtros: vendedor + lector de MercadoLibre (no admin): se prueba con ese permiso.
        gfield = 'group_ids' if 'group_ids' in cls.env.user._fields else 'groups_id'
        cls.env.user.write({gfield: [(4, cls.env.ref('sales_team.group_sale_salesman').id),
                                     (4, cls.env.ref('meli_oerp.group_mercadolibre_reader').id)]})
        cls.SO = cls.env['sale.order']

    def _ml_order(self, ref, confirm=True, logistic='fulfillment'):
        morder = self.env['mercadolibre.orders'].sudo().create({'name': 'ML %s' % ref, 'order_id': ref})
        so = self.SO.create({
            'partner_id': self.partner_a.id,
            'meli_order_id': ref,
            'meli_orders': [(6, 0, morder.ids)],
            'meli_shipment_logistic_type': logistic,
            'order_line': [(0, 0, {'product_id': self.product_a.id, 'product_uom_qty': 1, 'price_unit': 100.0})],
        })
        if confirm:
            so.action_confirm()
        return so

    def _ids(self, domain):
        return set(self.SO.search(domain).ids)

    def test_invoice_state_compute_and_search(self):
        so_none = self._ml_order('462001')
        so_draft = self._ml_order('462002')
        so_draft._create_invoices()
        so_posted = self._ml_order('462003')
        so_posted._create_invoices().action_post()
        so_ref = self._ml_order('462004')
        inv = so_ref._create_invoices()
        inv.action_post()
        rev = self.env['account.move.reversal'].with_context(
            active_model='account.move', active_ids=inv.ids).create({
                'reason': 'devolucion', 'journal_id': inv.journal_id.id,
                **({'date': inv.date} if 'date' in self.env['account.move.reversal']._fields else {}),
            })
        res = rev.refund_moves() if hasattr(rev, 'refund_moves') else rev.reverse_moves()
        refund = self.env['account.move'].browse(res.get('res_id')) if res.get('res_id') else \
            inv.reversal_move_ids if 'reversal_move_ids' in inv._fields else inv.reversal_move_id
        refund.action_post()

        mine = so_none | so_draft | so_posted | so_ref
        mine.invalidate_recordset(['meli_invoice_state'])
        self.assertEqual(
            [so.meli_invoice_state for so in (so_none, so_draft, so_posted, so_ref)],
            ['none', 'draft', 'posted', 'refunded'])

        base = [('id', 'in', mine.ids)]
        self.assertEqual(self._ids(base + [('meli_invoice_state', '=', 'none')]), {so_none.id})
        self.assertEqual(self._ids(base + [('meli_invoice_state', '=', 'draft')]), {so_draft.id})
        self.assertEqual(self._ids(base + [('meli_invoice_state', '=', 'posted')]), {so_posted.id})
        self.assertEqual(self._ids(base + [('meli_invoice_state', '=', 'refunded')]), {so_ref.id})
        self.assertEqual(self._ids(base + [('meli_invoice_state', 'in', ['none', 'draft'])]),
                         {so_none.id, so_draft.id})
        self.assertEqual(self._ids(base + [('meli_invoice_state', '!=', 'none')]),
                         {so_draft.id, so_posted.id, so_ref.id})
        self.assertEqual(self._ids(base + [('meli_invoice_state', 'not in', ['posted', 'refunded'])]),
                         {so_none.id, so_draft.id})

    def _search_filters(self, view_xmlid):
        view = self.env.ref(view_xmlid)
        arch = self.SO.get_view(view.id, 'search')['arch']
        return etree.fromstring(arch).xpath("//filter[starts-with(@name,'meli_462_')]")

    def test_filters_load_and_run(self):
        so_full = self._ml_order('462010', logistic='fulfillment')
        so_flex = self._ml_order('462011', logistic='self_service')
        so_q = self._ml_order('462012', confirm=False, logistic='xd_drop_off')
        mine = so_full | so_flex | so_q
        ctx = {'uid': self.env.uid, 'context_today': __import__('datetime').date.today}
        for xmlid in ('sale.sale_order_view_search_inherit_sale',
                      'sale.sale_order_view_search_inherit_quotation'):
            filters = self._search_filters(xmlid)
            names = {f.get('name') for f in filters}
            self.assertIn('meli_462_posted_invoice', names, xmlid)
            self.assertIn('meli_462_claim_return', names, xmlid)
            for f in filters:
                domain = safe_eval(f.get('domain') or '[]', ctx)
                self.SO.search_count(domain)  # no debe fallar
        by_name = {f.get('name'): safe_eval(f.get('domain'), ctx)
                   for f in self._search_filters('sale.sale_order_view_search_inherit_sale')}
        base = [('id', 'in', mine.ids)]
        self.assertEqual(self._ids(base + by_name['meli_462_full']), {so_full.id})
        self.assertEqual(self._ids(base + by_name['meli_462_flex']), {so_flex.id})
        self.assertEqual(self._ids(base + by_name['meli_462_drop_off']), {so_q.id})
        self.assertEqual(self._ids(base + by_name['meli_462_draft']), {so_q.id})
        self.assertEqual(self._ids(base + by_name['meli_462_no_posted_invoice']), {so_full.id, so_flex.id})
        # reclamo de devolucion abierto sobre la orden Full
        self.env['mercadolibre.claim'].sudo().create({
            'name': 'R1', 'claim_id': 'CK21', 'order_id': so_full.meli_orders.id,
            'type': 'returns', 'status': 'opened'})
        self.assertEqual(self._ids(base + by_name['meli_462_claim_return']), {so_full.id})
        self.assertEqual(self._ids(base + by_name['meli_462_claim_open']), {so_full.id})
