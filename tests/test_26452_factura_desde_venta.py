# -*- coding: utf-8 -*-
"""26.452: Ventas › Imprimir › «Factura» = factura publicada de la venta.

1. La accion aparece en el menu Imprimir de sale.order (binding 'report').
2. Desde 2 ventas con factura publicada devuelve el reporte de facturas de Contabilidad
   (`account.account_invoices`) sobre ESAS facturas (no sobre las ventas), y el HTML sale.
3. Venta sin factura publicada (sin factura o con borrador) => UserError con su nombre.
"""
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError
from odoo.tests import tagged


@tagged('post_install', '-at_install', 'meli_26452')
class TestMeli26452FacturaDesdeVenta(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product_a.invoice_policy = 'order'
        # Quien imprime desde Ventas: un vendedor (en 19+ el usuario de test no trae permisos de Ventas).
        gfield = 'group_ids' if 'group_ids' in cls.env.user._fields else 'groups_id'
        cls.env.user.write({gfield: [(4, cls.env.ref('sales_team.group_sale_salesman').id)]})
        cls.action = cls.env.ref('meli_oerp.action_sale_order_print_invoices')

    def _so(self, invoice=None):
        so = self.env['sale.order'].create({
            'partner_id': self.partner_a.id,
            'order_line': [(0, 0, {'product_id': self.product_a.id, 'product_uom_qty': 1, 'price_unit': 100.0})],
        })
        so.action_confirm()
        if invoice:
            inv = so._create_invoices()
            if invoice == 'posted':
                inv.action_post()
        return so

    def _run(self, orders):
        return self.action.with_context(active_model='sale.order', active_ids=orders.ids,
                                        active_id=orders[:1].id).run()

    def test_binding_in_print_menu(self):
        bindings = self.env['ir.actions.actions'].get_bindings('sale.order')
        self.assertIn(self.action.id, [a['id'] for a in bindings.get('report', [])])

    def test_prints_posted_invoices_with_accounting_report(self):
        so1, so2 = self._so('posted'), self._so('posted')
        invoices = (so1 | so2).invoice_ids
        res = self._run(so1 | so2)
        report = self.env.ref('account.account_invoices')
        self.assertEqual(res['type'], 'ir.actions.report')
        self.assertEqual(res['report_name'], report.report_name)
        self.assertEqual(sorted(res['context']['active_ids']), sorted(invoices.ids))
        self.assertEqual(res['context']['active_model'], 'account.move')
        html = self.env['ir.actions.report']._render_qweb_html(report.report_name, invoices.ids)[0]
        for inv in invoices:
            self.assertIn(inv.name, html.decode())

    def test_order_without_posted_invoice_raises(self):
        so_ok, so_none, so_draft = self._so('posted'), self._so(), self._so('draft')
        with self.assertRaisesRegex(UserError, so_none.name):
            self._run(so_ok | so_none)
        with self.assertRaisesRegex(UserError, so_draft.name):
            self._run(so_draft)
