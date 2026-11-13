# -*- coding: utf-8 -*-
"""26.402 (13-nov-2026): el total de la venta importada == lo cobrado en ML aunque la venta tenga una
posicion fiscal que mapea el IVA del producto.

Hallazgo: venta SIMULADA en odoo19mint (Taza, 143.999 ARS). Producto con «15%» no incluido; la venta
cae en la posicion fiscal «Foreign Trade» (15% -> «0% Exports»). El import neteaba el unitario por el
15% del PRODUCTO (143.999/1,15 = 125.216,52) y la linea quedaba con el 0% MAPEADO => total 125.216,52
y la venta frenada en presupuesto por el control de montos. Igual con cualquier posicion que mapee
el IVA (exento, zona franca, exportacion).

Regla: se netea por los impuestos que la linea va a llevar de verdad (meli_predict_line_taxes), que
tiene que coincidir con lo que deja sale.order.line._meli_sync_line_taxes. Sin posicion fiscal: igual
que antes (control).
"""
from odoo.tests import common, tagged

from odoo.addons.meli_oerp.models.versions import meli_predict_line_taxes, ml_product_price_conversion
from .test_meli_simulacion import _bundle, _no_network

UNIT = 1150.0


@tagged('post_install', '-at_install', 'meli', 'meli_26402_neteo_fp')
class TestMeli26402NeteoPosicionFiscal(common.TransactionCase):

    @classmethod
    def _request_handler(cls, s, r, /, **kw):
        return s.get_adapter(r.url).send(r, **kw)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        country = cls.company.country_id or cls.env.ref('base.ar')
        Tax = cls.env['account.tax'].sudo()
        G = cls.env['account.tax.group'].sudo()
        gvals = {'name': 'IVA 26402'}
        if 'company_id' in G._fields:
            gvals['company_id'] = cls.company.id
        if 'country_id' in G._fields:
            gvals['country_id'] = country.id
        grp = G.create(gvals)

        def _t(name, amount):
            vals = {'name': name, 'amount': amount, 'type_tax_use': 'sale', 'company_id': cls.company.id,
                    'tax_group_id': grp.id}
            if 'country_id' in Tax._fields:
                vals['country_id'] = country.id
            if 'price_include_override' in Tax._fields:
                vals['price_include_override'] = 'tax_excluded'
            elif 'price_include' in Tax._fields:
                vals['price_include'] = False
            return Tax.create(vals)

        cls.t15 = _t('IVA 15% 26402', 15.0)
        cls.t0 = _t('0% Exports 26402', 0.0)
        cls.fp_map = cls._fp(cls.env, 'Foreign Trade 26402', cls.t15, cls.t0)
        cls.fp_vacia = cls._fp(cls.env, 'Exenta sin destino 26402', cls.t15, None)

        pricelist = cls.env['product.pricelist'].search([], limit=1) or cls.env['product.pricelist'].create({'name': 'Lista ML'})
        cls.company.mercadolibre_pricelist = pricelist
        cls.contact = cls.env['res.partner'].create({'name': 'Cliente ML 26402'})
        if 'mercadolibre_contact_partner' in cls.company._fields:
            cls.company.mercadolibre_contact_partner = cls.contact
        cls.product = cls.env['product.product'].create({
            'name': 'Taza simulada', 'taxes_id': [(6, 0, [cls.t15.id])], 'meli_id': 'MLA000SIM',
            'default_code': 'SKUSIM'})
        cls.company.sudo().meli_simulation_enabled = True

    @staticmethod
    def _fp(env, name, src, dest):
        """Posicion fiscal que mapea src -> dest (None = quita el impuesto), en cada version de Odoo."""
        FP = env['account.fiscal.position'].sudo()
        f = FP._fields.get('tax_ids')
        if f is not None and f.comodel_name == 'account.fiscal.position.tax':  # 16-18
            return FP.create({'name': name, 'auto_apply': False,
                              'tax_ids': [(0, 0, {'tax_src_id': src.id, 'tax_dest_id': dest and dest.id or False})]})
        fp = FP.create({'name': name, 'auto_apply': False})  # 19+: el impuesto destino lleva la relacion
        if dest:
            dest.write({'fiscal_position_ids': [(4, fp.id)], 'original_tax_ids': [(4, src.id)]})
        # 19+: una posicion sin impuestos quita todos (= mapeo a vacio)
        return fp

    def _so(self, fpos):
        return self.env['sale.order'].create({'partner_id': self.contact.id, 'company_id': self.company.id,
                                              'fiscal_position_id': fpos and fpos.id or False})

    def _sim_total(self, fpos):
        self.contact.with_company(self.company).property_account_position_id = fpos and fpos.id or False
        with _no_network(self):
            res = self.env['mercadolibre.orders'].meli_simulate_order(_bundle(unit=UNIT), config=self.company)
        self.assertTrue(res['ok'], res)
        so = self.env['sale.order'].browse(res['sale_order'])
        self.assertTrue(so, res)
        return so

    # --- camino real (simulacion) ----------------------------------------------------------
    def test_01_control_sin_posicion_fiscal(self):
        so = self._sim_total(None)
        self.assertFalse(so.fiscal_position_id)
        line = so.order_line.filtered(lambda l: l.product_id == self.product)
        self.assertAlmostEqual(line.price_unit, UNIT / 1.15, places=2)
        self.assertAlmostEqual(so.amount_total, UNIT, places=2)

    def test_02_posicion_que_mapea_a_0(self):
        so = self._sim_total(self.fp_map)
        self.assertEqual(so.fiscal_position_id, self.fp_map)
        line = so.order_line.filtered(lambda l: l.product_id == self.product)
        tf = 'tax_ids' if 'tax_ids' in line._fields else 'tax_id'
        self.assertEqual(line[tf], self.t0)
        # antes: 1000,00 (= 1150/1,15) con 0 % => total 1000 contra 1150 cobrado
        self.assertAlmostEqual(line.price_unit, UNIT, places=2)
        self.assertAlmostEqual(so.amount_total, UNIT, places=2)

    def test_03_posicion_que_quita_el_impuesto(self):
        # _meli_sync_line_taxes vuelve a poner el IVA del producto: el neteo tiene que seguirlo
        so = self._sim_total(self.fp_vacia)
        self.assertAlmostEqual(so.amount_total, UNIT, places=2)

    # --- la prediccion coincide con la decision real de la linea ---------------------------
    def test_04_prediccion_igual_a_sync_line_taxes(self):
        for fpos in (self.fp_map, self.fp_vacia):
            for iva_name in (None, self.t15.name):
                so = self._so(fpos)
                line = self.env['sale.order.line'].create({'order_id': so.id, 'product_id': self.product.id,
                                                           'product_uom_qty': 1, 'price_unit': 1.0,
                                                           'meli_order_item_iva': iva_name or False})
                tf = 'tax_ids' if 'tax_ids' in line._fields else 'tax_id'
                line._meli_sync_line_taxes(self.product, so, tf)
                pred = meli_predict_line_taxes(self.product, so, iva_name=iva_name)
                self.assertEqual(set(pred.ids), set(line[tf].ids), "fp=%s iva=%s" % (fpos.name, iva_name))
                price = ml_product_price_conversion(self.env['mercadolibre.orders'], self.product, UNIT,
                                                    config=self.company, taxes=pred)
                total = price * (1.0 + sum(t.amount for t in line[tf]) / 100.0)
                self.assertAlmostEqual(total, UNIT, places=2, msg="fp=%s iva=%s" % (fpos.name, iva_name))

    def test_05_sin_posicion_no_cambia_nada(self):
        so = self._so(None)
        self.assertIsNone(meli_predict_line_taxes(self.product, so))
        self.assertAlmostEqual(ml_product_price_conversion(self.env['mercadolibre.orders'], self.product, UNIT,
                                                           config=self.company, taxes=None), UNIT / 1.15, places=4)

    def test_06_envio_solo_mapeo(self):
        so = self._so(self.fp_map)
        self.assertEqual(meli_predict_line_taxes(self.product, so, ml_line=False), self.t0)
