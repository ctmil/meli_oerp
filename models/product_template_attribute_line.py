# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.fields import Command
from odoo.tools.translate import _
import pdb
import logging
_logger = logging.getLogger(__name__)


#: Unico value_type de MercadoLibre que es una enumeracion cerrada de opciones
#: predefinidas. Para el resto (string, number, number_unit, boolean, picture_id)
#: el valor es propio de CADA producto, no una lista compartida.
MELI_ENUMERATED_VALUE_TYPES = ('list',)


class ProductTemplateAttributeLine(models.Model):
    _inherit = "product.template.attribute.line"

    meli_att_id = fields.Char(string=u'Id Attribute ML', related='attribute_id.meli_att_id')

    @api.onchange('attribute_id')
    def _onchange_attribute_id(self):
        """Evitar que al elegir un atributo de ML de texto libre se precarguen TODOS sus valores.

        El core (product/models/product_template_attribute_line.py) hace, para cualquier
        atributo con create_variant == 'no_variant', un `search` de todos sus valores y los
        deja seleccionados. Con atributos que son "un valor por producto" eso es inmanejable:
        en Koreautos (521) el atributo "Numero de pieza" (ML `PART_NUMBER`) acumula 158 valores
        y el usuario tiene que borrar 157 a mano cada vez que carga un producto.

        Solo se corrige cuando el atributo esta mapeado a un atributo de MercadoLibre que NO es
        una lista de opciones. Si no hay mapeo a ML, o si el tipo es `list`, se respeta el
        comportamiento del core: ahi precargar tiene sentido y es lo que el usuario espera.
        """
        res = super()._onchange_attribute_id()
        meli_attribute = self.attribute_id.meli_default_id_attribute
        if (
            self.attribute_id.create_variant == 'no_variant'
            and meli_attribute
            and meli_attribute.value_type not in MELI_ENUMERATED_VALUE_TYPES
        ):
            self.value_ids = [Command.clear()]
        return res
