# -*- coding: utf-8 -*-
from odoo import models, fields, tools, api, osv
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

from odoo.exceptions import ValidationError
from odoo.addons.web_editor.tools import get_video_embed_code, get_video_thumbnail

from datetime import datetime

from .meli_oerp_config import *

#from ..melisdk.meli import Meli
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



class MeliImage(models.Model):
    _name = 'mercadolibre.image'
    _description = "MercadoLibre Image"
    _inherit = ['image.mixin']
    _order = 'sequence, id'

    name = fields.Char("Name", required=True)
    sequence = fields.Integer(default=10)

    image_1920 = fields.Image()

    #product_tmpl_id = fields.Many2one('product.template', "Product Template", index=True, ondelete='cascade')
    #product_variant_id = fields.Many2one('product.product', "Product Variant", index=True, ondelete='cascade')
    video_url = fields.Char('Video URL',
                            help='URL of a video for showcasing your product.')
    embed_code = fields.Html(compute="_compute_embed_code", sanitize=False)

    can_image_1024_be_zoomed = fields.Boolean("Can Image 1024 be zoomed", compute='_compute_can_image_1024_be_zoomed', store=True)

    @api.depends('image_1920', 'image_1024')
    def _compute_can_image_1024_be_zoomed(self):
        for image in self:
            image.can_image_1024_be_zoomed = image.image_1920 and tools.is_image_size_above(image.image_1920, image.image_1024)

    @api.onchange('video_url')
    def _onchange_video_url(self):
        if not self.image_1920:
            thumbnail = get_video_thumbnail(self.video_url)
            self.image_1920 = thumbnail and base64.b64encode(thumbnail) or False

    @api.depends('video_url')
    def _compute_embed_code(self):
        for image in self:
            image.embed_code = get_video_embed_code(image.video_url) or False

    @api.constrains('video_url')
    def _check_valid_video_url(self):
        for image in self:
            if image.video_url and not image.embed_code:
                raise ValidationError(_("Provided video URL for '%s' is not valid. Please enter a valid video URL.", image.name))

    meli_imagen_id = fields.Char(string='Imagen Id',index=True)
    meli_imagen_link = fields.Char(string='Imagen Link')
    meli_imagen_size = fields.Char(string='Size')
    meli_imagen_max_size = fields.Char(string='Max Size')
    meli_imagen_bytes = fields.Integer(string='Size bytes')
    meli_imagen_hash = fields.Char(string='File Hash Id')
    meli_pub = fields.Boolean(string='Publicar en ML',index=True)
    meli_force_pub = fields.Boolean(string='Publicar en ML y conservar en Odoo',index=True)
    meli_published = fields.Boolean(string='Publicado en ML',index=True)

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
