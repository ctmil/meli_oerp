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


class res_company(osv.osv):
    _name = "res.company"
    _inherit = "res.company"
    
    _columns = {
	'mercadolibre_client_id': fields.char(string='Client ID para ingresar a MercadoLibre',size=128), 
	'mercadolibre_secret_key': fields.char(string='Secret Key para ingresar a MercadoLibre',size=128), 
	# TODO Agregar el banner
    }

res_company()

