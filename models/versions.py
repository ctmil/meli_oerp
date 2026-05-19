# -*- coding: utf-8 -*-
from dateutil.parser import *
from datetime import *

import unicodedata
import logging
_logger = logging.getLogger(__name__)
import json
import re
from markupsafe import Markup
# Odoo version 19.0

# Odoo 18.0 -> type='json', Odoo 19.0 -> type='jsonrpc'
route_typejson = "jsonrpc"

# Odoo < 17.0 -> 'tree', Odoo 17.0+ -> 'list'
view_mode_tree = 'list'

# ---------------------------------------------------------------------------
# UniqueIndex vs _sql_constraints  (Odoo < 17  vs  Odoo 17+)
# ---------------------------------------------------------------------------
# Odoo 17+ introduced models.UniqueIndex as the new way to declare unique
# constraints. _sql_constraints still works in all versions but UniqueIndex
# is preferred in newer ones.
#
# Usage in models (retrocompatible, write once):
#
#   from . import versions
#
#   class MyModel(models.Model):
#       _unique_buyer_id = versions.UniqueIndex('buyer_id')
#       _sql_constraints = versions.sql_constraints_if_no_unique_index([
#           ('unique_buyer_id', 'buyer_id', 'Buyer ID must be unique'),
#       ])
#
# ---------------------------------------------------------------------------
HAS_UNIQUE_INDEX = False
_OdooUniqueIndex = None
try:
    from odoo.models import UniqueIndex as _OdooUniqueIndex
    HAS_UNIQUE_INDEX = True
    _logger.info("versions: models.UniqueIndex disponible (Odoo 17+)")
except (ImportError, AttributeError):
    _logger.info("versions: models.UniqueIndex no disponible - usando _sql_constraints")


def UniqueIndex(fields_expr, message=None):
    """
    Retrocompatible unique index declaration.
    - Odoo 17+  : returns models.UniqueIndex(fields_expr, message=message)
    - Odoo < 17 : returns None (silently ignored by Odoo ORM)
    Pair with sql_constraints_if_no_unique_index() for full coverage.
    """
    if _OdooUniqueIndex is not None:
        if message is not None:
            return _OdooUniqueIndex('(%s)' % fields_expr, message=message)
        return _OdooUniqueIndex('(%s)' % fields_expr)
    return None

def sql_constraints_if_no_unique_index(constraints):
    """
    Returns _sql_constraints list only when UniqueIndex is NOT available.
    constraints: list of (name, fields_expr, message)
    - Odoo 17+  : returns []          (UniqueIndex handles the constraint)
    - Odoo < 17 : returns the list    (classic _sql_constraints fallback)
    """
    if HAS_UNIQUE_INDEX:
        return []
    return [
        (name, 'unique(%s)' % fields, msg)
        for name, fields, msg in constraints
    ]

# ---------------------------------------------------------------------------
# Constraint (arbitrary SQL CHECK constraints)  —  Odoo 19+
# ---------------------------------------------------------------------------
_OdooConstraint = None
try:
    from odoo.models import Constraint as _OdooConstraint
except (ImportError, AttributeError):
    pass

def Constraint(sql_expr, message=None):
    """
    Retrocompatible arbitrary SQL constraint declaration.
    - Odoo 19+  : returns models.Constraint(sql_expr, message=message)
    - Odoo < 19 : returns None (silently ignored by Odoo ORM)
    Pair with sql_constraints_if_no_constraint() for full coverage.
    """
    if _OdooConstraint is not None:
        if message is not None:
            return _OdooConstraint(sql_expr, message=message)
        return _OdooConstraint(sql_expr)
    return None

def sql_constraints_if_no_constraint(constraints):
    """
    Returns _sql_constraints list only when Constraint is NOT available.
    constraints: list of (name, sql_expr, message)
    - Odoo 19+  : returns []     (Constraint handles it)
    - Odoo < 19 : returns the list (classic _sql_constraints fallback)
    """
    if _OdooConstraint is not None:
        return []
    return [
        (name, sql_expr, msg)
        for name, sql_expr, msg in constraints
    ]

# ---------------------------------------------------------------------------

# Odoo 12.0 -> Odoo 13.0
uom_model = "uom.uom"
cl_vat_sep_million = "."

#message types
order_message_type = "notification"
product_message_type = "notification"

def meli_message_post(record, body, config=None):
    """Post a message respecting the MeLi notification mode setting.

    config: res.company or connection_account record with mercadolibre_notification_mode field.
           If None, falls back to the record's company.

    Modes:
      - 'notification': standard notification (appears in user inbox)
      - 'internal_note': logged in chatter as internal note (no inbox notification)
      - 'none': only server log, no chatter message at all
    """
    if not record:
        return
    if not config:
        config = getattr(record, 'company_id', None) or record.env.user.company_id
    mode = 'notification'
    if config and 'mercadolibre_notification_mode' in config._fields:
        mode = config.mercadolibre_notification_mode or 'notification'

    if mode == 'none':
        _logger.info("MELI [%s] %s: %s", record._name, getattr(record, 'name', record.id), body)
        return

    body_val = body
    if isinstance(body_val, str) and '<' in body_val and '>' in body_val:
        body_val = Markup(body_val)
    else:
        body_val = str(body_val)
    kwargs = {'body': body_val}
    if mode == 'internal_note':
        kwargs['message_type'] = 'comment'
        kwargs['subtype_xmlid'] = 'mail.mt_note'
    else:
        kwargs['message_type'] = order_message_type

    try:
        record.message_post(**kwargs)
    except Exception as e:
        _logger.warning("meli_message_post failed on %s(%s): %s", record._name, record.id, e)
disable_cancel_warning_enabled = False
price_list_apply_tax = True
search_partner_vat_match = False
mercadolibre_shipment_print_guide_mode = "pdf"

# ---------------------------------------------------------------------------
# Detectar si el SDK de MercadoLibre (paquete "meli") está disponible
# USE_MELI_SDK controla qué backend usa MeliApi:
#   True  → usa meli.RestClientApi + meli.OAuth20Api  (SDK oficial)
#   False → usa requests directo (sin dependencias externas)
#
# Se puede forzar manualmente:
#   from odoo.addons.meli_oerp.models import versions
#   versions.USE_MELI_SDK = True   # forzar SDK
#   versions.USE_MELI_SDK = False  # forzar requests
# ---------------------------------------------------------------------------
MELI_SDK_AVAILABLE = False
try:
    import meli as _meli_sdk_probe
    MELI_SDK_AVAILABLE = True
    _logger.info("meli SDK disponible")
except ImportError:
    _logger.info("meli SDK no disponible - Usando requests directo")

# Por defecto: usar SDK solo si está instalado
USE_MELI_SDK = MELI_SDK_AVAILABLE

#forzar NO SDK: comentar siguiente linea
#USE_MELI_SDK = False

# Detectar si unidecode está disponible
UNIDECODE_AVAILABLE = False
try:
    import unidecode as unidecode_lib
    UNIDECODE_AVAILABLE = True
    _logger.info("✓ unidecode disponible - Usando normalización avanzada")
except ImportError:
    _logger.info("⚠ unidecode no disponible - Usando unicodedata (estándar Python)")


def normalize_text(text):
    """
    Normaliza texto removiendo acentos y caracteres especiales
    
    Usa unidecode si está disponible (mejor calidad)
    Sino usa unicodedata (estándar Python)
    
    Args:
        text (str): Texto a normalizar
        
    Returns:
        str: Texto normalizado
    """
    if not text:
        return ''
    
    text = str(text)
    
    if UNIDECODE_AVAILABLE:
        # Versión premium: unidecode
        # Convierte: "Niño" → "Nino", "北京" → "Bei Jing", etc.
        return unidecode_lib.unidecode(text)
    else:
        # Fallback: unicodedata (solo remueve acentos latinos)
        # Convierte: "Niño" → "Nino"
        # Pero: "北京" → "北京" (no transliterar caracteres no-latinos)
        normalized = unicodedata.normalize('NFD', text)
        return ''.join(
            char for char in normalized
            if unicodedata.category(char) != 'Mn'
        )


def really_compare(a, b, sensitive=False):
    """
    Compara dos strings con normalización inteligente
    
    Args:
        a: Primer string
        b: Segundo string  
        sensitive: Si True, mantiene case y acentos
        
    Returns:
        bool: True si son iguales
    """
    a = str(a)
    b = str(b)
    
    if sensitive:
        return a == b
    
    # Convertir a minúsculas y normalizar
    a = normalize_text(a.lower())
    b = normalize_text(b.lower())
    
    return a == b

def pretty_json( data ):
    return json.dumps( data, sort_keys=False, indent=4 )

#price from pricelist
def get_price_from_pl( pricelist, product, quantity ):
    pl = pricelist
    return_val = {}
    return_val[pl.id] = pl._get_product_price(product=product,quantity=quantity)
    return return_val

import inspect

def map_tax_compat(fiscal_position, taxes, product=None, partner=None):
    """Llama a map_tax con la firma correcta según la versión de Odoo."""
    if not fiscal_position:
        return taxes

    method = fiscal_position.map_tax
    try:
        params = inspect.signature(method).parameters
        # incluye self; si hay 2 parámetros => (self, taxes)
        if len(params) == 2:
            return method(taxes)
        else:
            return method(taxes, product, partner)
    except TypeError:
        # fallback defensivo
        try:
            return method(taxes, product, partner)
        except TypeError:
            return method(taxes)


#Autocommit
def Autocommit( self, act=False ):
    return False

def MeliCr( self ):    
    return self.env.cr
    #or return self._cr

def MeliCommit( self ):
    # flush_all() en vez de cr.commit(): fuerza writes ORM al DB dentro de la
    # transacción actual sin hacer COMMIT. Un cr.commit() destruiría savepoints
    # activos (ej: wizard batch usa 'with env.cr.savepoint()') causando
    # "savepoint does not exist" y aborto de la transacción en cascada.
    return self.env.flush_all();

def MeliRollback( self ):
    return self.env.cr.rollback();


def SaleOrderLineTaxField( self ):
    """
    Devuelve el nombre correcto del campo de impuestos de sale.order.line
    según la versión de Odoo: 'tax_id' (<=18) o 'tax_ids' (19+).
    """
    so_line_fields = self.env['sale.order.line']._fields
    if 'tax_ids' in so_line_fields:
        return 'tax_ids'
    return 'tax_id'

def SaleOrderLineUomField(self):
    """
    Devuelve el nombre correcto del campo de UoM de sale.order.line
    según la versión de Odoo: 'product_uom' (<=18) o 'product_uom_id' (19+).
    """
    so_line_fields = self.env['sale.order.line']._fields
    if 'product_uom' in so_line_fields:
        return 'product_uom'
    return 'product_uom_id'


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
            cr = prod.env.cr
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
                #old reserved_uom_qty
                if "quantity" in pop._fields:
                    if pop.quantity>=0.0:
                        pop.qty_done = pop.quantity
                    else:
                        _logger.error("picking "+str(picking and picking.name)+" en la linea "+str(pop)+" tiene el quantity en 0")
                else:
                    _logger.error("picking "+str(picking and picking.name)+" en la linea "+str(pop)+" no contiene el campo quantity")

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

    # Use higher precision (6 decimals) to avoid rounding errors in tax calculations
    # Odoo will round to the configured decimal precision when saving
    ml_price_converted = round(ml_price_converted, 6)
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
    
def normalize_tax_name(tax_name: str):
    """
    Normaliza un nombre de impuesto.
    Ejemplo: "21 %" -> (21, ""), "21% EPS" -> (21, "EPS")
    """
    # quitar espacios extras
    tax_name = tax_name.strip()
    # buscar número con regex
    match = re.search(r"(\d+)\s*%?\s*(.*)", tax_name)
    if match:
        rate = int(match.group(1))
        extra = match.group(2).strip()
        return rate, extra.upper()
    return None, None

def tax_names_equivalent(name1: str, name2: str) -> bool:
    r1, e1 = normalize_tax_name(name1)
    r2, e2 = normalize_tax_name(name2)
    if r1 is None or r2 is None:
        return False
    # reconocemos equivalencia si las tasas son iguales
    return r1 == r2
