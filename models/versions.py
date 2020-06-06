# -*- coding: utf-8 -*-

# Odoo version 13.0

# Odoo 12.0 -> Odoo 13.0
uom_model = "product.uom"

# Odoo 12.0 -> Odoo 13.0
prod_att_line = "product.attribute.line"

# account
acc_inv_model  = "account.invoice"

# default_create_variant
default_no_create_variant = False
default_create_variant = True

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

def _prepare_attribute(_prepare_attribute( product_template_id, attribute_id, attribute_value_id ):
    att_vals = { 'attribute_id': attribute_id,
                 'product_tmpl_id': product_template_id
               }
    return att_vals
    
def _stock_inventory_action_done( self )
    return self.action_done()


    
    
