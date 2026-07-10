# -*- coding: utf-8 -*-
import json
import tempfile
import binascii
import requests
import base64
import certifi
import urllib3
import xlrd
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import date, datetime
from collections import defaultdict
import logging
_logger = logging.getLogger(__name__)


class MeliConsultCategoryWizard(models.TransientModel):
    _name = 'meli.consult.category.wizard'
    _description = 'Mercado Libre >> Consultar categorías'

    company_id = fields.Many2one('res.company', string=u'Compañia', default=lambda self: self.env.user.company_id)
    product_tmpl_id = fields.Many2one('product.template', string='Producto')
    categories_meli = fields.Many2many('mercadolibre.category')
    category_selected_id = fields.Many2one('mercadolibre.category', string='Categoría')

    def apply_category(self):
        self.ensure_one()
        if not self.category_selected_id:
            raise ValidationError(_("Seleccione al menos una categoría"))
        # FIX #532: la predicción trajo la categoría en modo liviano (id+nombre). Al SELECCIONARLA
        # la hidratamos con un import completo (atributos, grid charts, catalog_domain) para que
        # quede lista para publicar. Es 1 sola categoría, no las N sugeridas → sigue siendo rápido.
        try:
            self.env['mercadolibre.category'].import_category(
                self.category_selected_id.meli_category_id, create_missing_website=False)
        except Exception:
            _logger.exception("apply_category: no se pudo hidratar la categoría %s",
                              self.category_selected_id.meli_category_id)
        self.product_tmpl_id.meli_category = self.category_selected_id
