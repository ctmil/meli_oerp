# -*- coding: utf-8 -*-
from dateutil.parser import *
from datetime import *

import unidecode
import logging
_logger = logging.getLogger(__name__)
import json

# Odoo version 18.0

# Odoo 12.0 -> Odoo 13.0
uom_model = "uom.uom"
cl_vat_sep_million = "."

#message types
order_message_type = "notification"
product_message_type = "notification"

def pretty_json( data ):
    return json.dumps( data, sort_keys=False, indent=4 )

def really_compare( a, b, sensitive=False ):

    a = str(a).capitalize()
    b = str(b).capitalize()

    if (sensitive):
        return (a==b)

    a = unidecode.unidecode(a)
    b = unidecode.unidecode(b)

    return (a==b)



#price from pricelist
def get_price_from_pl( pricelist, product, quantity ):
    pl = pricelist
    return_val = {}
    return_val[pl.id] = pl._get_product_price(product=product,quantity=quantity)
    return return_val

#Autocommit
def Autocommit( self, act=False ):
    return False

def UpdateProductType( product ):
    if not product:
        return
    for prod in product:
        if (prod and "detailed_type" in prod._fields and prod.detailed_type not in ['product']):
            failed = False
            try:
                prod.write( { 'detailed_type': 'consu' } )
            except Exception as e:
                _logger.info("Set detailed_type almacenable ('consu') not possible:")
                _logger.error(e, exc_info=True)
                failed = True
                pass;

        if (prod and "type" in prod._fields and prod.type not in ['product']):
            failed = False
            try:
                prod.write( { 'type': 'consu' } )
            except Exception as e:
                _logger.info("Set type almacenable ('consu') not possible:")
                _logger.error(e, exc_info=True)
                failed = True
                pass;

        if (prod and "is_storable" in prod._fields and prod.is_storable):
            failed = False
            try:
                prod.write( { 'is_storable': True } )
            except Exception as e:
                _logger.info("Set type is_storable ('is_storable') not possible:")
                _logger.error(e, exc_info=True)
                failed = True
                pass;

            query = """UPDATE product_template SET type='consu', is_storable=True WHERE id=%i""" % (prod.id)
            cr = prod._cr
            respquery = cr.execute(query)

def ProductType():
    return {
        "type": "consu",
        "is_storable": True
        #"detailed_type": "consu"
    }

# Odoo 12.0 -> Odoo 13.0
prod_att_line = "product.template.attribute.line"

# account
acc_inv_model  = "account.move"

#stock inventory to quant: 14.0 -> 15.0
stock_inv_model = "stock.quant"

# default_create_variant
default_no_create_variant = "no_variant"
default_create_variant = "always"

#'unique(product_tmpl_id,meli_imagen_id)'
unique_meli_imagen_id_fields = 'unique(product_tmpl_id,product_variant_id,meli_imagen_id)'


def get_ref_view( self, module_name, view_name ):

    refview = self.env['ir.model.data'].check_object_reference( module_name, view_name )

    return refview

#TODO: get_company_selected, user with allowed companies
def get_company_selected( self, context=None, company=None, company_id=None, user=None, user_id=None ):
    context = context or self.env.context
    company = company or self.env.user.company_id
    #_logger.info("context:"+str(context)+" company:"+str(company))
    company_id = company_id or (context and 'allowed_company_ids' in context and context['allowed_company_ids'] and context['allowed_company_ids'][0]) or company.id
    company = self.env['res.company'].browse(company_id) or company
    return company

#variant mage ids
def variant_image_ids(self):
    if "product_variant_image_ids" in self._fields:
        return self.product_variant_image_ids
    return None

#template image ids
def template_image_ids(self):
    if "product_template_image_ids" in self._fields:
        return self.product_template_image_ids
    return None


#att value ids
def att_value_ids(self):
    return self.product_template_attribute_value_ids

#att line ids
def att_line_ids(self):
    return self.attribute_line_ids

def get_image_full(self):
    return ("variant_image" in self._fields and self.variant_image) or self.image_1920

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

def stock_picking_set_quantities( picking ):
    for spick in picking:
        for pop in spick.move_line_ids:
            #_logger.info(pop)
            #_logger.info(pop.qty_done)
            if "qty_done" in pop._fields and pop.qty_done==0.0:
                if "reserved_uom_qty" in pop._fields:
                    if pop.reserved_uom_qty>=0.0:
                        pop.qty_done = pop.reserved_uom_qty
                    else:
                        _logger.error("picking "+str(picking and picking.name)+" en la linea "+str(pop)+" tiene el reserved_uom_qty en 0")
                else:
                    _logger.error("picking "+str(picking and picking.name)+" en la linea "+str(pop)+" no contiene el campo reserved_uom_qty")

def stock_inventory_action_done( self, product, stock, config ):
    return_id = False
    uomobj = self.env[uom_model]
    whid = self.env['stock.location'].search([('usage','=','internal')]).id
    product_uom_id = uomobj.search([('name','=','Unidad(es)')])
    if (product_uom_id.id==False):
        product_uom_id = 1
    else:
        product_uom_id = product_uom_id.id

    stock_inventory_fields = get_inventory_fields( product, whid, quantity=_stock )

    _logger.info("stock_inventory_fields:")
    _logger.info(stock_inventory_fields)
    StockInventory = self.env[stock_inv_model].create(stock_inventory_fields)
    if (StockInventory):
        return_id = self.with_context(inventory_mode=True)._apply_inventory()
    return return_id

def ml_datetime(datestr):
    try:
        #return parse(datestr).isoformat().replace("T"," ")
        datestr = str(datestr)
        return parse(datestr).astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    except:
        #_logger.error(type(datestr))
        #_logger.error(datestr)
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
    company_id = ("company_id" in config._fields and config.company_id) or config
    product_template = product_related_obj.product_tmpl_id
    ml_price_converted = float(price)
    tax_excluded = ml_tax_excluded( self, config=config )
    #tax_excluded = True
    #_logger.info("Taxes:"+str(product_template.taxes_id))
    if ( tax_excluded and product_template.taxes_id ):
        txfixed = 0
        txpercent = 0
        #_logger.info("Adjust taxes")
        for txid in product_template.taxes_id:
            if (txid.company_id!=company_id):
                continue;
            if (txid.type_tax_use=="sale" and not txid.price_include):
                if (txid.amount_type=="percent"):
                    txpercent = txpercent + txid.amount
                if (txid.amount_type=="fixed"):
                    txfixed = txfixed + txid.amount
                #_logger.info(txid.amount)
        if (txfixed>0 or txpercent>0):
            #_logger.info("Tx Total:"+str(txtotal)+" to Price:"+str(ml_price_converted))
            ml_price_converted = txfixed + ml_price_converted / (1.0 + txpercent*0.01)
            #_logger.info("Price adjusted with taxes:"+str(ml_price_converted))

    ml_price_converted = round(ml_price_converted,2)
    return ml_price_converted


def get_inventory_fields( product, warehouse, quantity=0 ):
    return {
            #"product_ids": [(4,product.id)],
            "product_id": product.id,
            #"filter": "product",
            "location_id": warehouse,
            "inventory_quantity": quantity
            #"name": "INV: "+ product.name
            }

def get_delivery_line(sorder):
    delivery_line = None
    try:
        carrier_product_id = sorder.carrier_id.product_id.id
        for line in sorder.order_line:
            if(line.product_id.id == carrier_product_id):
                delivery_line = line
                return delivery_line

        delivery_lines = sorder.env['sale.order.line'].search([('order_id', 'in', sorder.ids), ('is_delivery', '=', True)])
        if delivery_lines:
            delivery_line = delivery_lines[0]
            return delivery_line

    except Exception as E:
        _logger.info("Error get delivery line failed "+str(E))
        pass;

    return delivery_line



def set_delivery_line( sorder, delivery_price, delivery_message ):
    #check version
    delivery_line = get_delivery_line(sorder)
    if not delivery_line:
        sorder.set_delivery_line(sorder.carrier_id, delivery_price)
        delivery_line = get_delivery_line(sorder)
    try:
        recompute_delivery_price = False

        if (delivery_line and abs(delivery_line.price_unit - float(delivery_price)) > 1.1 ):
            recompute_delivery_price = True
            sorder.set_delivery_line(sorder.carrier_id, delivery_price)

        sorder.write({
        	'recompute_delivery_price': recompute_delivery_price,
        	'delivery_message': delivery_message,
        })
    except:
            _logger.info("Error set_delivery_line failed (order invoiced)")

    return delivery_line

def remove_delivery_line( sorder, delivery_price=0):
    sorder._remove_delivery_line()
    return
