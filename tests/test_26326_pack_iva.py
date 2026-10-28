# -*- coding: utf-8 -*-
"""26.326 (28-oct-2026): la linea de un PACK NUEVO no queda sin IVA — regresion destapada en 26.316.

Fix de referencia: fork Deco #526 d3b7b4a (SO 13275, pack nuevo de DELTA, producto con VAT 21 % de 3 companias).
El bloque de impuestos comparaba contra la compania de `sorder`, vacio en un pack nuevo => quitaba el IVA y no
agregaba ninguno; hasta 26.315 lo tapaba el write completo de la linea, 26.316 (`_meli_write_ml_line`) lo destapo.
En el sync siguiente `tid` sin asignar => UnboundLocalError. `_old_block` = copia literal del bloque de
shipment.py hasta 26.325 (control: tiene que reproducir el pack sin IVA).
"""
from odoo.tests import common, tagged
from odoo.addons.meli_oerp.models.versions import tax_names_equivalent


def _old_block(line, product, sorder, tax_field):
    """Copia literal del bloque de impuestos de shipment.py (pack) hasta 26.325."""
    saleorderline_item_ids = line; product_related_obj = product
    tax_iva_name = saleorderline_item_ids.meli_order_item_iva
    tax_iva_name = tax_iva_name
    tax_iva_id = None
    if tax_iva_name and product_related_obj.taxes_id:
        for txid in product_related_obj.taxes_id:
            if ( tax_names_equivalent(txid.name,tax_iva_name) ):
                tax_iva_id = txid

    for tid in saleorderline_item_ids[tax_field]:

        if (tid.company_id.id!=sorder.company_id.id 
            or (tax_iva_id and tax_iva_id!=tid) ):
            #remove
            saleorderline_item_ids[tax_field] = [(3, tid.id)]

    if not saleorderline_item_ids[tax_field] and product_related_obj.taxes_id:
        for txid in product_related_obj.taxes_id:
            if (txid.company_id.id==sorder.company_id.id):
                if (tax_iva_id):
                    if (tax_iva_id!=tid):
                        #add
                        saleorderline_item_ids[tax_field] = [(4, txid.id)]
                else:
                    #add
                    saleorderline_item_ids[tax_field] = [(4, txid.id)]


@tagged('post_install', '-at_install', 'meli_26326_pack_iva')
class TestMeli26326PackIva(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.c1 = cls.env.company
        ar = cls.env.ref('base.ar')
        cls.c3 = cls.env['res.company'].create({'name': 'DELTA test', 'currency_id': cls.c1.currency_id.id, 'country_id': ar.id})
        cls.env.user.company_ids |= cls.c3
        Tax = cls.env['account.tax'].sudo(); G = cls.env['account.tax.group'].sudo()

        def _g(company):
            vals = {'name': 'IVA'}
            if 'company_id' in G._fields:
                vals['company_id'] = company.id
            if 'country_id' in G._fields:
                vals['country_id'] = ar.id
            return G.create(vals)

        def _t(name, amount, company, group):
            vals = {'name': name, 'amount': amount, 'type_tax_use': 'sale', 'company_id': company.id, 'tax_group_id': group.id}
            if 'country_id' in Tax._fields:
                vals['country_id'] = ar.id
            return Tax.create(vals)

        g1 = _g(cls.c1); g3 = _g(cls.c3)
        cls.t1 = _t('VAT 21%', 21, cls.c1, g1)
        cls.t3 = _t('VAT 21%', 21, cls.c3, g3)
        cls.t3b = _t('Perc IIBB', 3, cls.c3, g3)
        cls.product = cls.env['product.product'].sudo().create({'name': 'Cortina Roller', 'default_code': 'BSNE180125', 'company_id': False,
                                                                'taxes_id': [(6, 0, [cls.t1.id, cls.t3.id])]})
        cls.partner = cls.env['res.partner'].create({'name': 'Cliente ML', 'company_id': False})
        cls.tf = 'tax_ids' if 'tax_ids' in cls.env['sale.order.line']._fields else 'tax_id'

    def setUp(self):
        super().setUp()
        env3 = self.env(context=dict(self.env.context, allowed_company_ids=[self.c3.id, self.c1.id]))
        self.so = env3['sale.order'].create({'partner_id': self.partner.id, 'company_id': self.c3.id})
        self.line = env3['sale.order.line'].create({'order_id': self.so.id, 'product_id': self.product.id, 'product_uom_qty': 1,
                                                     'price_unit': 62190.082645, 'meli_order_item_iva': '21 %'})
        self.empty = self.env['sale.order']  # = `sorder` de un pack NUEVO

    def test_creada_toma_iva_de_su_compania(self):
        self.assertEqual(self.line[self.tf], self.t3)

    def test_control_pack_nuevo_viejo_queda_sin_iva(self):
        _old_block(self.line, self.product, self.empty, self.tf)
        self.assertFalse(self.line[self.tf], "control: el bloque viejo deberia dejar la linea sin impuestos")
        with self.assertRaises(UnboundLocalError):
            _old_block(self.line, self.product, self.so, self.tf)   # el sync siguiente

    def test_fix_pack_nuevo_conserva_iva(self):
        self.line._meli_sync_line_taxes(self.product, self.so, self.tf)
        self.assertEqual(self.line[self.tf], self.t3)
        self.assertAlmostEqual(self.so.amount_total, 75250.0, places=1)

    def test_fix_sorder_vacio_usa_compania_de_la_linea(self):
        self.line._meli_sync_line_taxes(self.product, self.empty, self.tf)
        self.assertEqual(self.line[self.tf], self.t3)

    def test_fix_linea_sin_impuestos_se_repara(self):
        self.line[self.tf] = [(5, 0, 0)]
        self.assertAlmostEqual(self.so.amount_total, 62190.08, places=1)
        self.line._meli_sync_line_taxes(self.product, self.so, self.tf)
        self.assertEqual(self.line[self.tf], self.t3)
        self.assertAlmostEqual(self.so.amount_total, 75250.0, places=1)

    def test_fix_iva_ml_elige_entre_los_de_la_compania(self):
        self.product.sudo().taxes_id = [(6, 0, [self.t1.id, self.t3.id, self.t3b.id])]
        self.line[self.tf] = [(6, 0, [self.t3.id, self.t3b.id])]
        self.line._meli_sync_line_taxes(self.product, self.so, self.tf)
        self.assertEqual(self.line[self.tf], self.t3)

    def test_fix_sin_iva_ml_conserva_los_de_la_compania(self):
        self.line.meli_order_item_iva = False
        self.product.sudo().taxes_id = [(6, 0, [self.t1.id, self.t3.id, self.t3b.id])]
        self.line[self.tf] = [(5, 0, 0)]
        self.line._meli_sync_line_taxes(self.product, self.so, self.tf)
        self.assertEqual(self.line[self.tf], self.t3 | self.t3b)

    def test_fix_idempotente_no_escribe(self):
        w = []
        orig = type(self.line).write
        def spy(recs, vals):
            if self.tf in vals: w.append(vals)
            return orig(recs, vals)
        type(self.line).write = spy
        try:
            self.line._meli_sync_line_taxes(self.product, self.so, self.tf)
        finally:
            type(self.line).write = orig
        self.assertFalse(w)
