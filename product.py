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

from openerp.osv import fields, osv
import logging

class product_product(osv.osv):
    
    _inherit = "product.template"
    
    _columns = {
	'meli_id': fields.char(string='Id del item asignado por Meli', size=256),
	'meli_title': fields.char(string='Nombre del producto en Mercado Libre',size=256), 
	'meli_description': fields.html(string='Description'),
	'meli_category': fields.many2one("mercadolibre.category","Categoría de MercadoLibre"),
	'meli_listing_type': fields.selection([("free","Libre"),("bronze","Bronce"),("silver","Plata"),("gold","Oro"),("premium","Premium")], string='Tipo de lista'),
	'meli_buying_mode': fields.selection( [("buy_it_now","Compre ahora"),("classified","Clasificado")], string='Método de compra'),
	'meli_price': fields.char(string='Precio de venta', size=128),
	'meli_currency': fields.selection([("ARS","Peso Argetino (ARS)")],string='Moneda (ARS)'),
	'meli_condition': fields.selection([ ("new", "Nuevo"), ("used", "Usado"), ("not_specified","No especificado")],'Condición del producto'),
	'meli_available_quantity': fields.integer(string='Cantidad disponible', size=128),
	'meli_warranty': fields.char(string='Garantía', size=256),
	'meli_imagen': fields.char(string='Imagen', size=256),
	'meli_video': fields.char(string='Video (id de youtube)', size=256),
	### Agregar imagen/archivo uno o mas, y la descripcion en HTML...
	# TODO Agregar el banner
    }

product_product()
