# -*- coding: utf-8 -*-
from dateutil.parser import *
from datetime import *

import unicodedata
import logging
_logger = logging.getLogger(__name__)
import json
import re
from markupsafe import Markup, escape as markup_escape
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

def meli_once_marker(once_key):
    """Marca HTML invisible que identifica un mensaje "postear una sola vez"."""
    return "<!-- meli-once:%s -->" % once_key


def meli_message_already_posted(record, once_key):
    """True si el chatter de `record` ya tiene el mensaje marcado con `once_key`."""
    if not record or not once_key:
        return False
    try:
        # sudo: el cron corre con un usuario de permisos acotados y esto es sólo lectura.
        return bool(record.env['mail.message'].sudo().search_count([
            ('model', '=', record._name),
            ('res_id', '=', record.id),
            ('body', 'like', meli_once_marker(once_key)),
        ]))
    except Exception as e:
        # Ante cualquier problema leyendo el chatter preferimos postear de más
        # (perder un aviso es peor que repetirlo).
        _logger.warning("meli_message_already_posted failed on %s(%s): %s", record._name, record.id, e)
        return False


# ---------------------------------------------------------------------------
# 26.309 (caso-K02): venta BLOQUEADA para actualizar desde ML (`sale.order.meli_update_forbidden`).
# El freno es correcto (no escribe nada), pero se logueaba ERROR en CADA llamada y la notificacion
# quedaba FAILED => el cron de notificaciones (RECEIVED + FAILED) la reintentaba en cada corrida,
# para siempre. Ahora: WARNING una vez por venta y por proceso (despues DEBUG) y el retorno trae la
# marca `meli_update_forbidden` para que la notificacion se cierre como SUCCESS sin reintento.
MELI_UPDATE_FORBIDDEN_ERRORS = ('Forbidden to upate by meli_oerp', 'Forbidden to update sale order by meli_oerp')
_MELI_UPDATE_FORBIDDEN_WARNED = set()


def meli_is_update_forbidden_error(err):
    """True si `err` (str o dict de retorno) es el freno de venta bloqueada."""
    if isinstance(err, dict):
        if err.get('meli_update_forbidden'):
            return True
        err = err.get('error')
    return any(m in str(err or '') for m in MELI_UPDATE_FORBIDDEN_ERRORS)


def meli_log_update_forbidden(logger, sorder, where=''):
    """WARNING la primera vez por venta en este proceso; las siguientes DEBUG."""
    key = (getattr(sorder, '_name', ''), getattr(sorder, 'id', None))
    if key in _MELI_UPDATE_FORBIDDEN_WARNED:
        logger.debug("MELI_UPDATE_FORBIDDEN: venta %s bloqueada (ya avisado)%s",
                     getattr(sorder, 'name', key[1]), where)
        return False
    if len(_MELI_UPDATE_FORBIDDEN_WARNED) > 50000:
        _MELI_UPDATE_FORBIDDEN_WARNED.clear()
    _MELI_UPDATE_FORBIDDEN_WARNED.add(key)
    logger.warning("MELI_UPDATE_FORBIDDEN: venta %s bloqueada para actualizar desde ML "
                   "(No actualizar desde ML = activo): no se escribe nada%s",
                   getattr(sorder, 'name', key[1]), where)
    return True


def meli_message_body_with_marker(body, once_key):
    """Devuelve `body` con la marca `once_key` pegada al final, invisible en el chatter.

    Ojo con la diferencia entre versiones de Odoo (verificada en el core):
      - 16.0: `message_post` NO escapa el body → un str plano se guarda como HTML.
      - 17.0/18.0/19.0: `message_post` hace `escape(body)` salvo que sea `Markup`
        (mail_thread.py: "escape if text, keep if markup") → un comentario HTML
        en un str plano se vería literal, `<!-- meli-once:... -->`, en el chatter.
    Por eso devolvemos un `Markup` con el body YA escapado + la marca cruda: el texto
    se ve igual que siempre en las 4 versiones y la marca queda invisible.
    Sólo se usa en los avisos con `once_key` (los demás callers no cambian).
    """
    return markup_escape(body) + Markup(meli_once_marker(once_key))


def meli_message_post(record, body, config=None, once_key=None, force_chatter=False):
    """Post a message respecting the MeLi notification mode setting.

    config: res.company or connection_account record with mercadolibre_notification_mode field.
           If None, falls back to the record's company.

    once_key: si viene, el mensaje se postea UNA SOLA VEZ por record. El body se
           marca con `<!-- meli-once:<once_key> -->` y en las llamadas siguientes,
           si esa marca ya está en el chatter, no se repostea (sí queda en el log).
           Se usa en los avisos que nacen de un cron que reintenta indefinidamente
           (orden ML cancelada que no se puede cancelar en Odoo): sin esto el mismo
           aviso se repetía cada ~5 min para siempre — visto en prod con 1215 y 832
           mensajes en el chatter de dos órdenes.

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

    if mode == 'none' and force_chatter:
        # [26.270] Aviso de DINERO BLOQUEADO (cobro/pago que no se registro): el modo 'none'
        # existe para bajar ruido, no para esconder plata sin registrar. Va como nota interna
        # (sin inbox), una vez por pago (once_key).
        mode = 'internal_note'
    if mode == 'none':
        _logger.info("MELI [%s] %s: %s", record._name, getattr(record, 'name', record.id), body)
        return

    if once_key:
        if meli_message_already_posted(record, once_key):
            _logger.info("MELI [%s] %s (ya posteado, once_key=%s): %s",
                         record._name, getattr(record, 'name', record.id), once_key, body)
            return
        body = meli_message_body_with_marker(body, once_key)

    body_val = body
    if isinstance(body_val, Markup):
        # Ya viene armado por once_key (body escapado + marca cruda): no tocarlo.
        pass
    elif isinstance(body_val, str) and '<' in body_val and '>' in body_val:
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
# ---------------------------------------------------------------------------
# disable_cancel_warning: clave de CONTEXTO del core de Odoo (addon `sale`).
#
# LEER EL NOMBRE DESPACIO -- es un doble negativo y ya nos costo caro.
#   True  = "desactiva el aviso"  -> `_show_cancel_wizard()` corta y `action_cancel()`
#           CANCELA de verdad y devuelve un bool.
#   False = "deja el aviso"       -> `action_cancel()` NO cancela: DEVUELVE el dict del
#           wizard `sale.order.cancel` para que lo abra la interfaz. Sin excepcion y sin
#           log. Llamado desde un cron, no cancela absolutamente nada y parece que si.
#
# Historia: nacio en `True` (25.20, sep-2025). El commit "Upgraded 18.0.25.29" (nov-2025)
# reemplazo los `disable_cancel_warning=True` literales por esta constante y en el mismo
# movimiento la puso en `False`, invirtiendo el sentido de los CUATRO call sites de una
# sola vez. Desde entonces `meli_cancel_with_detail()` no cancela ninguna venta confirmada.
# `meli_oerp_multiple` nunca paso por ese refactor y sigue con el `True` literal -- o sea
# que la intencion original esta a la vista.
#
# YA NO SE USA COMO VALOR DE CONTEXTO: el valor efectivo lo fuerza
# `sale.order._meli_action_cancel()`, que ademas VERIFICA que la venta haya quedado en
# 'cancel'. Se conserva el nombre (y en `True`) porque `versions` se importa con `*` y
# porque un `False` aca vuelve a ser una bomba silenciosa.
#
# En ESTA version (Odoo 19) el core ELIMINO el wizard y la clave: `action_cancel()`
# llama siempre a `_action_cancel()`. O sea que aca NO hay bug -- la clave es inerte.
# Se alinea igual para que las 4 versiones del source digan lo mismo.
# ---------------------------------------------------------------------------
disable_cancel_warning_enabled = True
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
# el SDK oficial NO se usa. Fijo en False y sin `import meli`:
# todas las llamadas salen por requests (MeliApiNoSDK) y por el host de meli_api_url.
MELI_SDK_AVAILABLE = False
USE_MELI_SDK = False

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


def MeliInvoicePolicy( prod, config=None ):
    """Politica de facturacion a mandar JUNTO con un write de 'type'.

    ERROR-012 -- POR QUE ESTA FUNCION EXISTE.
    En Odoo 17/18/19 `product.template.invoice_policy` es un compute
    `store=True, readonly=False` que **depende de `type`**
    (`addons/sale/models/product_template.py`): cualquier write sobre `type` lo
    recalcula y lo fuerza a `'order'`. Como el conector escribia `type='consu'` en
    cada importacion de orden, le pisaba al cliente la politica que habia elegido,
    en silencio y varias veces por dia.

    Un valor EXPLICITO en el mismo write le gana al compute. Orden de precedencia:
      1. la politica configurada en la CUENTA (`mercadolibre.configuration`),
      2. si no, la configurada en la COMPANIA (`res.company`),
      3. si no, **la que el producto ya tenia** -> se preserva y nada cambia,
      4. si el campo no existe (sin modulo `sale`), no se manda nada.

    El punto 3 es lo que implementa "dejarla vacia = accion predeterminada": sobre
    un producto que ya existe, lo predeterminado es **no cambiarle nada**.
    """
    if not prod or "invoice_policy" not in prod._fields:
        return {}

    politica = False
    for origen in (config, getattr(prod, "company_id", False)):
        if not origen:
            continue
        if "mercadolibre_product_invoice_policy" in origen._fields:
            politica = origen.mercadolibre_product_invoice_policy
            if politica:
                break

    politica = politica or prod.invoice_policy
    return {"invoice_policy": politica} if politica else {}


def UpdateProductType( product, config=None ):
    """Deja el producto como almacenable, SIN pisar la politica de facturacion.

    ERROR-012: antes esta funcion escribia `type='consu'` **siempre**, porque su
    guard (`prod.type not in ['product']`) era de Odoo <=16 -- en 17/18/19 el valor
    `'product'` ya no existe, asi que la condicion daba verdadero incluso cuando
    el producto YA era `consu`. Ese write inutil disparaba el recalculo de
    `invoice_policy`. Ahora solo se escribe **si hay algo que cambiar**, y cuando
    se escribe va la politica explicita para que el compute no gane.
    """
    if not product:
        return
    for prod in product:
        vals = {}

        # Odoo <=16: detailed_type. Se mantiene por compatibilidad hacia atras.
        if "detailed_type" in prod._fields and prod.detailed_type != 'consu':
            vals['detailed_type'] = 'consu'

        if "type" in prod._fields and prod.type != 'consu':
            vals['type'] = 'consu'

        # Guard invertido (defecto historico): decia `if prod.is_storable`, o sea
        # solo escribia cuando YA era True -- un no-op -- y nunca cumplia su objetivo.
        if "is_storable" in prod._fields and not prod.is_storable:
            vals['is_storable'] = True

        # Nada que cambiar => NO se escribe. Este early-continue es el que elimina
        # la enorme mayoria de los reverts de politica.
        if not vals:
            continue

        vals.update( MeliInvoicePolicy( prod, config=config ) )

        try:
            prod.write( vals )
        except Exception as e:
            _logger.info("UpdateProductType: no se pudo actualizar el producto %s: %s",
                         getattr(prod, 'id', '?'), vals)
            _logger.error(e, exc_info=True)


def ProductType():
    """Valores de tipo para el ALTA de un producto creado por el conector.

    Para escrituras sobre productos que YA existen no usar esto directamente:
    usar `ProductTypeWrite(prod, config)`, que ademas preserva la politica.
    """
    return {
        "type": "consu",
        "is_storable": True
        #"detailed_type": "consu"
    }


def ProductTypeWrite( prod, config=None ):
    """`ProductType()` + la politica de facturacion, para writes sobre productos existentes.

    Devuelve **{}** si el producto ya esta como corresponde, para no disparar el
    recalculo de `invoice_policy` con un write que no cambia nada (ERROR-012).
    """
    vals = {}
    if not prod:
        return vals
    if "type" in prod._fields and prod.type != 'consu':
        vals["type"] = "consu"
    if "is_storable" in prod._fields and not prod.is_storable:
        vals["is_storable"] = True
    if not vals:
        return {}
    vals.update( MeliInvoicePolicy( prod, config=config ) )
    return vals

# Odoo 12.0 -> Odoo 13.0
prod_att_line = "product.template.attribute.line"

# account
acc_inv_model  = "account.move"

#stock inventory to quant: 14.0 -> 15.0
stock_inv_model = "stock.quant"

# default_create_variant
default_no_create_variant = "no_variant"
default_create_variant = "always"

# Atributos de ML que NUNCA deben generar variantes en Odoo, aunque ML los
# declare variation_attribute y no hidden.
#
# ML los marca "de variacion" porque del lado de ML cada variacion puede llevar
# su propio codigo/SKU. Pero en Odoo eso NO es una caracteristica del producto:
# el GTIN es el campo `barcode` de la variante y el SELLER_SKU su `default_code`.
# Tomarlos como generadores abre UNA VARIANTE POR CADA CODIGO, que es justo lo
# contrario de para lo que se usan las variantes.
#
# SELLER_SKU hoy se salva solo porque ML lo manda hidden=true; si ML cambiara
# ese flag rompe igual. Por eso va en la lista y no se deja librado al flag.
meli_attributes_never_variant = ("GTIN", "SELLER_SKU")


def meli_attribute_is_never_variant( att_id ):
    """True si ese att_id de ML no debe generar variantes nunca."""
    return bool(att_id) and str(att_id).strip().upper() in meli_attributes_never_variant

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
        return _meli_only_pictures(self.product_variant_image_ids)
    return None

#template image ids
def template_image_ids(self):
    if "product_template_image_ids" in self._fields:
        return _meli_only_pictures(self.product_template_image_ids)
    return None

# [un caso] Un product.image con `video_url` es un VIDEO de la multimedia del producto: su imagen es
# la miniatura de YouTube/Vimeo. No se sube como foto a ML (aparecería una miniatura de video entre
# las fotos de la publicación). ML tampoco acepta hoy el video de YouTube (`video_id` se descarta).
def _meli_only_pictures(images):
    if images and "video_url" in images._fields:
        return images.filtered(lambda i: not i.video_url)
    return images


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
    # `.id` sobre TODAS las ubicaciones internas (ValueError con mas de una): la del deposito de la compania.
    _company = (config and 'company_id' in config._fields and config.company_id) or self.env.company
    whid = self.env['stock.warehouse'].search([('company_id','=',_company.id)], limit=1).lot_stock_id.id \
        or self.env['stock.location'].search([('usage','=','internal')], limit=1).id
    product_uom_id = uomobj.search([('name','=','Unidad(es)')])
    if (product_uom_id.id==False):
        product_uom_id = 1
    else:
        product_uom_id = product_uom_id.id

    # C-1: decia `quantity=_stock` (NameError: `_stock` es local del llamador, que lo pasa como `stock`)
    # y aplicaba el inventario sobre `self` (el producto). Desde el port 15.0 (28057b33) la funcion
    # recibia el registro de inventario: se aplica sobre el quant creado. Unico llamador: product.py
    # product_update_stock, hoy detras de `1==2` (no corre).
    stock_inventory_fields = get_inventory_fields( product, whid, quantity=stock )

    _logger.info("stock_inventory_fields:")
    _logger.info(stock_inventory_fields)
    # inventory_mode en el CREATE: asi el quant existente de esa ubicacion toma inventory_quantity (y queda
    # marcado para aplicar); sin el contexto se creaba un quant aparte en 0 y el apply no movia nada.
    StockInventory = self.env[stock_inv_model].with_context(inventory_mode=True).create(stock_inventory_fields)
    if (StockInventory):
        return_id = StockInventory.with_context(inventory_mode=True)._apply_inventory()
    return return_id

def ml_datetime(datestr):
    try:
        #return parse(datestr).isoformat().replace("T"," ")
        datestr = str(datestr)
        dt = parse(datestr).astimezone(timezone.utc)
        # Fechas placeholder/nulas de ML (año 0001, p.ej. bloques de shipping_option
        # no aplicables) → vacío. Si no, strftime('%Y') en glibc no rellena ceros y
        # devuelve '1-01-01 00:00:00' (año de 1 dígito), que luego rompe el parseo de
        # Odoo (to_datetime elige el formato por longitud) con ValueError al escribir.
        if dt.year < 1970:
            return None
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        #_logger.error(type(datestr))
        #_logger.error(datestr)
        return None

def ml_tax_excluded(self, config=None ):
    """True = el precio de lista de Odoo es NETO (al publicar se suma el IVA; al importar se netea).

    [caso-K11/caso-K10] (19-oct-2026) `auto` ("Configuracion del sistema") se resolvia con el grupo
    account.group_show_line_subtotals_tax_excluded, que existe SOLO hasta Odoo 16 (17 lo movio a
    website_sale; 18/19 usan res.company.account_price_include). En 17+ has_group() de un xmlid
    inexistente da False, asi que `auto` ya era "lista con impuestos incluidos" para publicar e
    importar precios. Se deja EXPLICITO y sin depender de un xmlid que no existe; NO se cambia el
    significado: este flag gobierna el precio PUBLICADO (price_list_apply_tax=True) y atarlo a
    account_price_include (default 'tax_excluded') subiria x1,21 lo publicado de todo cliente 17+
    con `auto`. Las ORDENES no dependen de esto: ver ml_product_price_conversion [#caso-K23].
    """
    company = (config and "company_id" in config._fields and config.company_id) or self.env.user.company_id
    config = config or company
    if (config and config.mercadolibre_tax_included not in ['auto']):
        return (config.mercadolibre_tax_included in ['tax_excluded'])
    #11.0: 'sale.group_show_price_subtotal' / 12.0 a 16.0: el grupo de abajo / 17.0+: no existe
    if self.env.ref('account.group_show_line_subtotals_tax_excluded', raise_if_not_found=False):
        return self.env.user.has_group('account.group_show_line_subtotals_tax_excluded')
    return False

def ml_sale_tax_rates(taxes, company=None):
    """(porcentaje, fijo) de los impuestos de VENTA no incluidos en precio, SOLO de `company`.

    [caso-K10] (19-oct-2026) Un producto compartido entre compañias lleva en taxes_id el IVA de CADA
    una: sumarlos todos dividia/multiplicaba por 1,42 en vez de 1,21 con dos compañias. Sin
    compañia (llamador viejo) se suman todos, como antes.
    """
    txpercent = 0.0
    txfixed = 0.0
    for txid in (taxes or []):
        if company and txid.company_id and txid.company_id != company:
            continue
        if (txid.type_tax_use == "sale" and not txid.price_include):
            if (txid.amount_type == "percent"):
                txpercent = txpercent + txid.amount
            if (txid.amount_type == "fixed"):
                txfixed = txfixed + txid.amount
    return txpercent, txfixed

def ml_product_price_conversion( self, product_related_obj, price, config=None):
    """Importe que COBRA ML (unitario de una orden, o flete) -> price_unit de la linea de venta.

    [caso de un cliente] El precio de una venta de ML es SIEMPRE final, con impuestos incluidos.
    Por eso se netea siempre por los impuestos de venta NO incluidos del producto (los
    `price_include` ya lo absorben solos), de modo que total Odoo == lo cobrado en ML.

    Antes esto dependia de ml_tax_excluded(config), o sea de `mercadolibre_tax_included`,
    que es el flag de la PUBLICACION (si la lista de precios de Odoo trae IVA o no). Un mismo
    campo gobernaba dos cosas: al pasar la conf a 'tax_included' (para publicar la lista tal
    cual, que ya trae IVA), las ordenes importadas dejaron de netearse y entraron x1,16
    (impuesto de 16 % no incluido sumado encima), y el control de montos de confirm_ml las
    frenaba en presupuesto. La PUBLICACION sigue usando ml_tax_excluded() sin cambios.
    """
    company_id = ("company_id" in config._fields and config.company_id) or config
    product_template = product_related_obj.product_tmpl_id
    ml_price_converted = float(price)
    # Sin depender de ml_tax_excluded(): ver docstring [un caso].
    #_logger.info("Taxes:"+str(product_template.taxes_id))
    if ( product_template.taxes_id ):
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

COUPON_DISCOUNT_CODE = "MELI_COUPON_DISC"


def meli_resolve_coupon_invoice_mode(config):
    """Modo de facturacion del cupon ML (tri-estado). Devuelve 'full'|'product_discount'|'separate_line'.

      - full (default): factura a precio pleno; el cupon ML (reembolsado por ML, vendedor
        made-whole) NO se refleja en lineas. [caso un cliente]
      - product_discount: el cupon se imputa como descuento (%) sobre las lineas de PRODUCTO.
      - separate_line: el cupon se imputa como linea(s) de descuento separada(s), una por grupo
        de impuesto (prorrateo), sin tocar producto ni envio. OPT-IN (riesgos AFIP/CL).

    Campo nuevo: meli_coupon_invoice_mode (meli_oerp_multiple / meli_oerp_accounting).
    Compat: si solo existe el booleano obsoleto meli_coupon_discount_on_invoice,
            True -> 'product_discount', False -> 'full'.
    """
    if not config:
        return "full"
    if "meli_coupon_invoice_mode" in config._fields and config.meli_coupon_invoice_mode:
        return config.meli_coupon_invoice_mode
    if "meli_coupon_discount_on_invoice" in config._fields:
        return "product_discount" if config.meli_coupon_discount_on_invoice else "full"
    return "full"


def _meli_line_tax_field(rec):
    return "tax_ids" if "tax_ids" in rec._fields else "tax_id"


def meli_get_coupon_discount_product(env):
    Product = env["product.product"].sudo()
    prod = Product.search([("default_code", "=", COUPON_DISCOUNT_CODE)], limit=1)
    if not prod:
        try:
            prod = Product.create({
                "name": "Descuento cupon MercadoLibre",
                "default_code": COUPON_DISCOUNT_CODE,
                "type": "service",
                "sale_ok": True,
                "purchase_ok": False,
                "taxes_id": [(5, 0, 0)],
            })
        except Exception as E:
            _logger.info("MELI: could not create coupon discount product: %s", str(E))
            prod = None
    return prod


def meli_remove_coupon_separate_line(sorder):
    """Elimina la(s) linea(s) de descuento de cupon separada(s) si existieran."""
    try:
        if sorder.state in ("done",) or ("locked" in sorder._fields and sorder.locked):
            return
        prod = sorder.env["product.product"].sudo().search(
            [("default_code", "=", COUPON_DISCOUNT_CODE)], limit=1)
        if not prod:
            return
        lines = sorder.order_line.filtered(lambda l: l.product_id.id == prod.id)
        if lines:
            lines.unlink()
    except Exception as E:
        _logger.info("MELI: remove coupon separate line failed: %s", str(E))


def meli_apply_coupon_separate_line(sorder, coupon_amount):
    """OPT-IN: imputa el cupon ML como linea(s) de descuento separada(s), UNA POR GRUPO DE
    IMPUESTO (prorrateo sobre el bruto con IVA), sin tocar precio de producto ni de envio.
    RIESGOS AFIP/CL: una linea de monto negativo puede ser rechazada por validaciones de FE
    electronica; VALIDAR contra meli_oerp_accounting_afip antes de habilitar. No es el default.
    El total facturado sigue == (bruto - coupon_amount)."""
    try:
        if sorder.state in ("done",) or ("locked" in sorder._fields and sorder.locked):
            return
        coupon_amount = abs(coupon_amount or 0.0)
        meli_remove_coupon_separate_line(sorder)
        if coupon_amount <= 0.0:
            return
        prod = meli_get_coupon_discount_product(sorder.env)
        if not prod:
            return
        non_disc_lines = sorder.order_line.filtered(
            lambda l: not l.is_delivery and l.product_id.id != prod.id)
        groups = {}
        total_gross = 0.0
        for line in non_disc_lines:
            taxes = line[_meli_line_tax_field(line)]
            tax_pct = sum(t.amount for t in taxes
                          if t.amount_type == "percent" and not t.price_include)
            gross = line.price_unit * line.product_uom_qty * (1.0 + tax_pct / 100.0)
            key = tuple(sorted(taxes.ids))
            g = groups.setdefault(key, {"gross": 0.0, "taxes": taxes, "tax_pct": tax_pct})
            g["gross"] += gross
            total_gross += gross
        if total_gross <= 0.0:
            return
        SOL = sorder.env["sale.order.line"]
        tfield = "tax_ids" if "tax_ids" in SOL._fields else "tax_id"
        for key, g in groups.items():
            share_gross = coupon_amount * (g["gross"] / total_gross)
            if share_gross <= 0.0:
                continue
            price_net = -(share_gross / (1.0 + g["tax_pct"] / 100.0))
            SOL.create({
                "order_id": sorder.id,
                "product_id": prod.id,
                "name": "Descuento cupon MercadoLibre",
                "product_uom_qty": 1.0,
                "price_unit": price_net,
                "discount": 0.0,
                tfield: [(6, 0, list(g["taxes"].ids))],
            })
        _logger.info("MELI: applied coupon as %d separate discount line(s), total=%.2f on SO %s",
                     len(groups), coupon_amount, sorder.name)
    except Exception as E:
        _logger.info("MELI: apply coupon separate line failed: %s", str(E))


def meli_sync_draft_invoice_discounts(sorder):
    """Lleva el descuento (%) de las lineas de la venta a su(s) factura(s) en BORRADOR.

    [un cliente, venta ML <order_id>] ML puede actualizar el cupon DESPUES de que
    la factura borrador ya se creo (7000 -> 9352,75, 46 s despues). El bloque del cupon recalcula
    line.discount en la venta, pero la factura borrador quedaba con el % viejo y se posteaba con
    el importe anterior (saldo contra el cobro). Solo toca facturas en estado 'draft' (sin CAE ni
    numero fiscal); nunca una posteada. Solo lineas de producto con UNA linea de venta de ESTA
    orden (packs con varias ordenes en una factura: cada orden sincroniza las suyas). Sin red."""
    try:
        if not sorder or "invoice_ids" not in sorder._fields:
            return
        moves = sorder.invoice_ids.filtered(
            lambda m: m.state == "draft" and m.move_type in ("out_invoice", "out_refund"))
        for move in moves:
            cmds = []
            for aml in move.invoice_line_ids:
                sls = aml.sale_line_ids
                if len(sls) != 1 or sls.order_id.id != sorder.id or sls.is_delivery:
                    continue
                if abs((aml.discount or 0.0) - (sls.discount or 0.0)) >= 0.000001:
                    cmds.append((1, aml.id, {"discount": sls.discount}))
            if cmds:
                move.write({"invoice_line_ids": cmds})
                _logger.info("MELI: draft invoice %s: discount re-synced from SO %s on %d line(s)",
                             move.id, sorder.name, len(cmds))
    except Exception as E:
        _logger.warning("MELI: sync draft invoice discounts failed on SO %s: %s",
                        sorder and sorder.name, str(E))


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


def _meli_guard_delivery_write(sorder, delivery_line, delivery_price):
    """True -> NO se debe escribir la linea de envio (la venta ya tiene factura posteada).

    [caso de un cliente] El guard estaba SOLO dentro de set_delivery_line, con un comentario que
    afirmaba que ese era "el unico lugar por el que pasan TODAS las reescrituras de la
    linea de envio". No era cierto: shipment.py escribe `price_unit`/`qty_to_invoice`
    DIRECTO sobre la linea, y `_remove_delivery_line()` la borra entera. Por esos caminos
    la venta quedaba igual por debajo de su propia factura, y encima el chatter posteaba
    "Cambio no aplicado" — un aviso falso, que es lo que el cliente nos marco el 5/8.

    Extraido a helper para que TODO camino que toque la linea consulte lo mismo. No
    levanta: ante cualquier error deja pasar la escritura (comportamiento previo) y avisa.
    """
    try:
        if not hasattr(sorder, '_meli_guard_invoiced'):
            return False
        _current = (delivery_line and delivery_line.price_unit) or 0.0
        # sin cambio real de precio no hay nada que proteger
        if abs(float(_current) - float(delivery_price or 0.0)) <= 0.01:
            return False
        _detail = "envío %s -> %s" % (_current, delivery_price)
        return bool(sorder._meli_guard_invoiced("la línea de envío", _detail))
    except Exception as e:
        _logger.warning("MELI guard de venta facturada: fallo en %s: %s",
                        getattr(sorder, 'name', '?'), e)
    return False


def set_delivery_line( sorder, delivery_price, delivery_message ):
    """Setea el precio de la linea de envio SIN riesgo de perderla.

    El core (delivery/models/sale_order.py::set_delivery_line) ejecuta, EN ESTE ORDEN:
        _remove_delivery_line()  ->  carrier_id = carrier.id  ->  _create_delivery_line(...)
    Si el carrier viene VACIO, o si la escritura/creacion posterior falla (compania
    incompatible, orden facturada, impuestos), el BORRADO ya ocurrio: la venta queda sin
    linea de envio y sin transportista, y el flete no se factura nunca mas. Antes esa
    excepcion se tragaba con un 'except:' pelado ("order invoiced") y el borrado quedaba
    consumado.

    Por eso:
      1) sin carrier valido NO se llama al core -> se actualiza el precio de la linea existente;
      2) la llamada al core va dentro de un savepoint -> si falla despues del borrado, se
         deshace el borrado en vez de dejar la venta pelada;
      3) los fallos se loguean con la venta y el error reales.

    Caso que lo destapo (un cliente, jul-2026): 47 ordenes quedaron sin flete en 7 semanas y
    20 se facturaron por debajo de lo cobrado al comprador.
    """
    #check version
    delivery_line = get_delivery_line(sorder)

    # [caso de un cliente] No tocar ventas YA FACTURADAS. Este es el punto por el que el
    # conector dejaba el flete en 0 sobre ventas con factura posteada, y la venta
    # quedaba por debajo de su propia factura.
    if _meli_guard_delivery_write(sorder, delivery_line, delivery_price):
        return delivery_line

    carrier = sorder.carrier_id

    if not carrier:
        # Sin transportista el core borraria la linea y no podria recrearla.
        if delivery_line and abs(delivery_line.price_unit - float(delivery_price)) > 0.01:
            delivery_line.price_unit = delivery_price
        _logger.warning("MELI set_delivery_line: venta %s sin transportista; se conserva la "
                        "linea de envio (precio %s) en vez de recrearla.",
                        sorder.name, delivery_price)
        _meli_write_delivery_message(sorder, False, delivery_message)
        return delivery_line

    recompute_delivery_price = False
    if not delivery_line or abs(delivery_line.price_unit - float(delivery_price)) > 1.1:
        recompute_delivery_price = bool(delivery_line)
        try:
            with sorder.env.cr.savepoint():
                sorder.set_delivery_line(carrier, delivery_price)
        except Exception as e:
            # El savepoint deshizo el borrado: la linea previa sigue viva.
            _logger.warning("MELI set_delivery_line: no se pudo reescribir la linea de envio "
                            "de %s (%s); se conserva la existente.", sorder.name, e)
        delivery_line = get_delivery_line(sorder)

    _meli_write_delivery_message(sorder, recompute_delivery_price, delivery_message)

    return delivery_line


def _meli_write_delivery_message( sorder, recompute_delivery_price, delivery_message ):
    try:
        sorder.write({
        	'recompute_delivery_price': recompute_delivery_price,
        	'delivery_message': delivery_message,
        })
    except Exception as e:
        _logger.warning("MELI set_delivery_line: no se pudo escribir delivery_message en %s: %s",
                        sorder.name, e)

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


# ---------------------------------------------------------------------------
# [26.269] Linea de metodo de pago EXPLICITA para los cobros/pagos de ML.
#
# El modulo creaba el account.payment con journal_id + payment_method_id pero sin
# payment_method_line_id, asi que Odoo elegia la linea solo: en 18/19 la preferida
# del partner y si no la PRIMERA linea del diario; en 16/17 la primera. La "Cuenta
# de pagos pendientes" del cobro sale de esa linea (payment_account_id). En 18/19 no
# hay default de compania: si la primera linea es "Online"/"En linea" sin cuenta, el
# cobro queda SIN ASIENTO (visto en un cliente: los 3 diarios de cobro tenian "Online"
# sin cuenta). En 16/17 la linea sin cuenta cae al default de la compania
# (account_journal_payment_debit/credit_account_id) y en 18/19 Community Odoo pone la
# cuenta pendiente del plan: esos defaults se respetan. El caso roto es 18/19 con
# account_accountant (Enterprise / Odoo.sh), donde no hay default.
#
# Regla: si la linea que Odoo elegiria sola es valida, se usa ESA (sin cambio de
# comportamiento). Si no, la primera linea del diario que si tenga cuenta. Si
# ninguna es valida, devuelve una linea vacia + el motivo, y el que llama NO crea
# el pago (un pago sin asiento es peor que un pago que falta y avisa).
# ---------------------------------------------------------------------------
def meli_payment_method_line_for(journal, payment_type='inbound', partner=None):
    """Devuelve (account.payment.method.line, motivo). motivo == '' si hay linea valida."""
    from odoo import release
    env = journal.env
    Line = env['account.payment.method.line']
    if not journal:
        return Line, "no hay diario de pagos configurado"
    journal = journal[:1]
    lines = journal._get_available_payment_method_lines(payment_type)
    company = journal.company_id
    default_field = ('account_journal_payment_debit_account_id' if payment_type == 'inbound'
                     else 'account_journal_payment_credit_account_id')
    company_default = default_field in company._fields and company[default_field]
    if not company_default and release.version_info[0] >= 18:
        # 18/19 SIN contabilidad completa (Community: _get_invoice_in_payment_state != 'in_payment'):
        # al crear el pago Odoo le pone la cuenta pendiente del plan si la linea no tiene
        # (account.payment.create -> _get_outstanding_account). Ese default se respeta. Con
        # account_accountant (Enterprise / Odoo.sh) no hay default: linea sin cuenta = sin asiento.
        Move = env['account.move']
        if hasattr(Move, '_get_invoice_in_payment_state') and Move._get_invoice_in_payment_state() != 'in_payment':
            company_default = True

    def _valid(line):
        return bool(line and (line.payment_account_id or company_default))

    # Lo que Odoo elegiria solo (ver account.payment._compute_payment_method_line_id).
    odoo_pick = Line
    if partner and release.version_info[0] >= 18:
        pref_field = ('property_inbound_payment_method_line_id' if payment_type == 'inbound'
                      else 'property_outbound_payment_method_line_id')
        if pref_field in partner._fields:
            pref = partner.with_company(company)[pref_field]
            if pref and pref.id in lines.ids:
                odoo_pick = pref
    odoo_pick = odoo_pick or lines[:1]
    if _valid(odoo_pick):
        return odoo_pick, ''
    for line in lines:
        if _valid(line):
            _logger.info("MELI payment method line: diario %s, la linea por defecto '%s' no tiene "
                         "cuenta de pagos pendientes; se usa '%s'.",
                         journal.display_name, odoo_pick.name, line.name)
            return line, ''
    tipo = 'entrante' if payment_type == 'inbound' else 'saliente'
    return Line, ("el diario '%s' no tiene ningun metodo de pago %s con 'Cuenta de pagos pendientes' "
                  "configurada (Contabilidad > Configuracion > Diarios > %s > pestana de pagos). "
                  "Sin esa cuenta el pago quedaria sin asiento." % (journal.display_name, tipo, journal.display_name))


def meli_money_block_post(record, body, config=None, once_key=None):
    """[26.270] Aviso de cobro/pago NO registrado: siempre queda en el chatter (nota interna si el
    modo de notificaciones es 'none'). Si el registro no tiene chatter, queda en el log."""
    _logger.warning("MELI dinero sin registrar [%s %s]: %s", record and record._name,
                    record and record.ids, body)
    if record and hasattr(record, 'message_post'):
        meli_message_post(record, body, config=config, once_key=once_key, force_chatter=True)
