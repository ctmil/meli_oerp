# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2009 Tiny SPRL (<http://tiny.be>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from odoo import fields, osv, models, api

class MercadolibreBanner(models.Model):
    _name = "mercadolibre.banner"
    _description = "Plantillas descriptivas para MercadoLibre"

    name = fields.Char('Titulo plantilla')
    description = fields.Text(string='Plantilla descriptiva')
    header = fields.Text(string='Encabezado')
    footer = fields.Text(string='Pie')
    images = fields.Text(string='Imagenes (links)')
    images_id = fields.Many2many("mercadolibre.image",string="Imagenes Meli")

    def get_description( self, product ):
        if not product:
            return ""
        des = self.header or ""
        if product.meli_description:
            des+= "\n"+product.meli_description
        if self.footer:
            des+= "\n"+self.footer

        return des


    def get_from_ml_description( self, meli_description ):
        if not meli_description:
            return ""
        if self.header:
            meli_description = meli_description.replace(self.header, "").strip()
        if self.footer:
            meli_description = meli_description.replace(self.footer, "").strip()

        return meli_description.strip()
