# -*- coding: utf-8 -*-
from odoo import models, fields, api, osv
from odoo.tools.translate import _
import pdb
import logging
_logger = logging.getLogger(__name__)


class ProductTemplateAttributeLine(models.Model):
    _inherit = "product.template.attribute.line"

    meli_att_id = fields.Char(string=u'Id Attribute ML', related='attribute_id.meli_att_id')
