# -*- coding: utf-8 -*-
from dateutil.parser import *
from datetime import *
import logging
_logger = logging.getLogger(__name__)

# Odoo version 14.0

# Odoo 12.0 -> Odoo 13.0
uom_model = "uom.uom"

# Odoo 12.0 -> Odoo 13.0
prod_att_line = "product.template.attribute.line"

# account
acc_inv_model  = "account.move"

# default_create_variant
default_no_create_variant = "no_variant"
default_create_variant = "always"

#'unique(product_tmpl_id,meli_imagen_id)'
unique_meli_imagen_id_fields = 'unique(product_tmpl_id,product_variant_id,meli_imagen_id)'

#TODO: get_company_selected, user with allowed companies
def get_company_selected( self, context=None, company=None, company_id=None, user=None, user_id=None):
    context = context or self.env.context
    company = company or self.env.user.company_id
    #_logger.info("context:"+str(context)+" company:"+str(company))
    company_id = company_id or (context and 'allowed_company_ids' in context and context['allowed_company_ids'] and context['allowed_company_ids'][0]) or company.id
    company = self.env['res.company'].browse(company_id) or company    
    return company

#variant mage ids
def variant_image_ids(self):
    return self.product_variant_image_ids

#template image ids
def template_image_ids(self):
    return self.product_template_image_ids


#att value ids
def att_value_ids(self):
    return self.product_template_attribute_value_ids

#att line ids
def att_line_ids(self):
    return self.attribute_line_ids

def get_image_full(self):
    return self.image_1920

def set_image_full(self, image):
    self.image_1920 = image
    return True

def get_first_image_to_publish(self):
    company = self.env.user.company_id
    product = self
    first_image_to_publish = None

    if (company.mercadolibre_do_not_use_first_image):
        image_ids = variant_image_ids(product)
        if (len(image_ids)):
            #Use first image of variant image ids: product.image
            first_image_to_publish = get_image_full(image_ids[0])
    else:
        first_image_to_publish = get_image_full(product)

    return first_image_to_publish

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
        datestr = str(datestr)
        return parse(datestr).strftime('%Y-%m-%d %H:%M:%S')
    except:
        _logger.error(type(datestr))
        _logger.error(datestr)
        return None

def ml_tax_excluded(self, config=None ):
    #11.0
    #tax_excluded = self.env.user.has_group('sale.group_show_price_subtotal')
    #12.0 and 13.0
    tax_excluded = self.env.user.has_group('account.group_show_line_subtotals_tax_excluded')
        
    company = (config and "company_id" in config._fields and config.company_id) or self.env.user.company_id
    config = config or company
    if (config and config.mercadolibre_tax_included not in ['auto']):
        tax_excluded = (config.mercadolibre_tax_included in ['tax_excluded'])
    return tax_excluded

def ml_product_price_conversion( self, product_related_obj, price, config=None):
    product_template = product_related_obj.product_tmpl_id
    ml_price_converted = float(price)
    tax_excluded = ml_tax_excluded( self, config=config )
    if ( tax_excluded and product_template.taxes_id ):
        txfixed = 0
        txpercent = 0
        #_logger.info("Adjust taxes")
        for txid in product_template.taxes_id:
            if (txid.type_tax_use=="sale" and not txid.price_include):
                if (txid.amount_type=="percent"):
                    txpercent = txpercent + txid.amount
                if (txid.amount_type=="fixed"):
                    txfixed = txfixed + txid.amount
                #_logger.info(txid.amount)
        if (txfixed>0 or txpercent>0):
            #_logger.info("Tx Total:"+str(txtotal)+" to Price:"+str(ml_price_converted))
            ml_price_converted = txfixed + ml_price_converted / (1.0 + txpercent*0.01)
            _logger.info("Price adjusted with taxes:"+str(ml_price_converted))

    ml_price_converted = round(ml_price_converted,2)
    return ml_price_converted


def get_inventory_fields( product, warehouse ):
    return {
            "product_ids": [(4,product.id)],
            #"product_id": product.id,
            #"filter": "product",
            #"location_id": warehouse,
            "name": "INV: "+ product.name
            }

def set_delivery_line( sorder, delivery_price, delivery_message ):
    oline = sorder.set_delivery_line(sorder.carrier_id, delivery_price)
    sorder.write({
    	'recompute_delivery_price': False,
    	'delivery_message': delivery_message,
    })
    return oline
