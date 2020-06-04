# -*- coding: utf-8 -*-

# Odoo version 13.0

# Odoo 12.0 -> Odoo 13.0
uom_model = "uom.uom"

# Odoo 12.0 -> Odoo 13.0
prod_att_line = "product.template.attribute.line"

# account
acc_inv_model  = "account.move"

# default_create_variant
default_no_create_variant = "no_variant"
default_create_variant = "always"

#variant mage ids
def variant_image_ids(self):
    return self.product_variant_image_ids

#att value ids
def att_value_ids(self):
    return self.product_template_attribute_value_ids

#att line ids
def att_line_ids(self):
    return self.attribute_line_ids

def get_image_full(self):
    return self.image_1920

def set_image_full(self, image):
    return (self.image_1920 = image)
    
    
