# -*- coding: utf-8 -*-
# Imprimir › «Factura» desde Ventas (lista o formulario de sale.order).
#
# Imprime las FACTURAS DE CLIENTE PUBLICADAS de las ventas seleccionadas con el MISMO reporte
# que usa Contabilidad (`account.account_invoices`): mismo documento, misma localizacion
# (l10n_ar: CAE / QR / letra), mismo nombre de archivo y mismo adjunto. No se duplica ningun
# template: un wrapper propio no heredaria lo que las localizaciones agregan al reporte de
# facturas (l10n_ar, por ejemplo, engancha su documento en report_invoice_with_payments).
#
# La accion es un ir.actions.server con binding_type=report (data/sale_order_print_invoice.xml):
# asi aparece en el menu «Imprimir» de sale.order y devuelve la accion del reporte de facturas.
# Venta sin factura publicada => UserError con el nombre de la venta (nada se imprime a medias).
from odoo import _, models
from odoo.exceptions import UserError

INVOICE_REPORT_XMLID = 'account.account_invoices'


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _meli_posted_customer_invoices(self):
        """Facturas y notas de credito de cliente PUBLICADAS de estas ventas."""
        return self.invoice_ids.filtered(
            lambda m: m.state == 'posted' and m.move_type in ('out_invoice', 'out_refund'))

    def meli_action_print_invoices(self):
        missing = self.filtered(lambda so: not so._meli_posted_customer_invoices())
        if missing:
            names = ', '.join(missing.mapped('name'))
            if len(missing) == 1:
                raise UserError(_("La venta %s no tiene factura publicada.") % names)
            raise UserError(_("Las ventas %s no tienen factura publicada.") % names)
        invoices = self._meli_posted_customer_invoices().sorted(lambda m: (m.invoice_date or m.date, m.id))
        report = self.env.ref(INVOICE_REPORT_XMLID)
        # active_model/active_id de la venta no deben viajar al render del reporte de facturas.
        # config=False: igual que el menu Imprimir nativo (sin el asistente de diseno de documento
        # que report_action le abre a un admin cuya compania no eligio diseno).
        return report.with_context(active_model='account.move', active_id=invoices[:1].id,
                                   active_ids=invoices.ids).report_action(invoices, config=False)
