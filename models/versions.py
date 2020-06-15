# -*- coding: utf-8 -*-
from dateutil.parser import *
from datetime import *
import logging
_logger = logging.getLogger(__name__)

# Odoo version 13.0

# Odoo 12.0 -> Odoo 13.0
uom_model = "uom.uom"

# Odoo 12.0 -> Odoo 13.0
prod_att_line = "product.template.attribute.line"

# account
acc_inv_model  = "account.invoice"

# default_create_variant
default_no_create_variant = "no_variant"
default_create_variant = "always"

#variant mage ids
def variant_image_ids(self):
    return self.product_image_ids

#att value ids
def att_value_ids(self):
    return self.attribute_value_ids

#att line ids
def att_line_ids(self):
    return self.attribute_value_ids


def get_image_full(self):
    return self.image

def set_image_full(self, image):
    self.image = image
    return True

def prepare_attribute( product_template_id, attribute_id, attribute_value_id ):
    att_vals = { 'attribute_id': attribute_id,
                 'value_ids': [(4,attribute_value_id)],
                 'product_tmpl_id': product_template_id
               }
    return att_vals
    
def stock_inventory_action_done( self ):
    return_id = self.post_inventory()
    return_id = self.action_start()
    return_id = self.action_validate()
    return return_id

def ml_datetime(datestr):
    try:
        #return parse(datestr).isoformat().replace("T"," ")
        return parse(datestr).strftime('%Y-%m-%d %H:%M:%S')
    except:
        _logger.error(datestr)
        return None
