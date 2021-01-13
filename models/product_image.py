# -*- coding: utf-8 -*-
from odoo import models, fields, api, osv
from odoo.tools.translate import _

import pdb
import logging
_logger = logging.getLogger(__name__)

import hashlib
import math
import requests
import base64
import mimetypes
from urllib.request import urlopen

from datetime import datetime

from .meli_oerp_config import *

from ..melisdk.meli import Meli
import string
if (not ('replace' in string.__dict__)):
    string = str

from . import versions
from .versions import *

class ProductImage(models.Model):

    _inherit = "product.image"

    #meli_id = fields.Char(u'ID MELI')
    #product_attribute_id = fields.Many2one('product.attribute.value', u'Atributo asociado')

    #website_sale.product_template_form_view
    meli_imagen_id = fields.Char(string='Imagen Id',index=True)
    meli_imagen_link = fields.Char(string='Imagen Link')
    meli_imagen_size = fields.Char(string='Size')
    meli_imagen_max_size = fields.Char(string='Max Size')
    meli_imagen_bytes = fields.Integer(string='Size bytes')
    meli_imagen_hash = fields.Char(string='File Hash Id')
    meli_pub = fields.Boolean(string='Publicar en ML',index=True)
    meli_force_pub = fields.Boolean(string='Publicar en ML y conservar en Odoo',index=True)
    meli_published = fields.Boolean(string='Publicado en ML',index=True)

    _sql_constraints = [
        ('unique_meli_imagen_id', unique_meli_imagen_id_fields, 'Meli Imagen Id already exists!')
    ]

    def calculate_hash(self):
        hexhash = ''
        for pimage in self:
            image = get_image_full( pimage )
            if not image:
                continue;
            imagebin = base64.b64decode( image )
            hash = hashlib.blake2b()
            hash.update(imagebin)
            hexhash = hash.hexdigest()
            pimage.meli_imagen_hash = hexhash
        return hexhash
