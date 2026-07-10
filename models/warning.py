from odoo import fields, models
from odoo.tools.translate import _
import pdb
import json
import re


from . import versions
from .versions import *

#CHANGE WARNING_MODULE with your module name
WARNING_MODULE = 'meli_oerp'
WARNING_TYPES = [('warning','Warning'),('info','Information'),('error','Error')]
import logging
_logger = logging.getLogger(__name__)

meli_errors = {
    "validation_error": "Hemos encontrado errores de validación",
    "item.category_id.invalid": "Categoría de MercadoLibre inválida, seleccione una categoría en la plantilla de MercadoLibre",
    #"item.category_id.invalid": "Categoría de MercadoLibre inválida, seleccione una categoría en la plantilla de MercadoLibre",
    "item.attributes.missing_required": "Un atributo faltante es requerido.",
    "item.price.invalid": "El precio no es válido, requiere un mínimo.",
    "item.description.ignored": "La descripción fue ignorada",
    "shipping.free_shipping.cost_exceeded": "El costo del envío supera al precio de venta.",
    "no image to upload": "Falta cargar una imagen en el producto",
    "item.image.required": "Imagen requerida para publicar el producto",
    "body.invalid_field_types": "Tipo de valor de propiedad de campo inválido (revisar términos de venta, garantia, etc...)"
}


# ---------------------------------------------------------------------------
# Humanización de errores de publicación de la API de MercadoLibre.
#
# La API de ML devuelve, en el 400 de validación, una lista `cause` con
# mensajes CRUDOS en inglés (ej: "Product Identifier [GTIN] contains values
# with invalid format: [C6536]"). Estos llegaban tal cual al usuario, resultando
# ILEGIBLES. Acá los mapeamos a un texto claro, en español y accionable.
#
# Cada entrada = (regex, plantilla). La plantilla puede ser:
#   - str  → mensaje fijo.
#   - callable(match) → mensaje que usa los grupos capturados.
# El PRIMER patrón que matchea gana. Si NINGUNO matchea, se conserva el texto
# original de ML (defensivo: no perder información). Extensible: agregar filas.
# ---------------------------------------------------------------------------
MELI_PUBLISH_ERROR_PATTERNS = [
    # --- GTIN/EAN/UPC: los más comunes e ilegibles (koreautos, catálogo) ---
    # GTIN con formato inválido (típico: barcode = SKU interno, no un EAN real)
    (r"Product Identifier\s*\[?\s*(GTIN|EAN|UPC)\s*\]?.*?invalid format\s*:?\s*\[?\s*([^\]\.]+?)\s*\]?\s*$",
     lambda m: ("El código de barras / %s '%s' no tiene un formato válido para MercadoLibre "
                "(parece un SKU/código interno, no un EAN real). Dejá el campo GTIN/EAN vacío o "
                "cargá un EAN real; el SKU no sirve como GTIN." % (m.group(1).upper(), m.group(2).strip()))),
    # GTIN ignorado por no ser modificable (benigno: lo gestiona el catálogo de ML)
    (r"Attribute\s*\[?\s*(GTIN|EAN|UPC)\s*\]?\s+ignored because it is not modifiable",
     lambda m: ("El código %s/EAN no se puede modificar en esta publicación (lo gestiona el catálogo "
                "de MercadoLibre). No impide publicar." % m.group(1).upper())),
    # GTIN/EAN/UPC requerido o faltante (obligatorio en catálogo; distinto de "invalid format")
    (r"(?:GTIN|EAN|UPC|c[oó]digo\s+universal(?:\s+de\s+producto)?)\b.*?"
     r"(?:is\s+required|are\s+required|\brequired\b|faltante|missing|es\s+requerido|es\s+obligatorio|obligatorio)",
     "Debe definir el código de barras (GTIN/EAN) del producto de forma obligatoria. "
     "Cargá un EAN/GTIN válido en el producto para poder publicar en el catálogo de MercadoLibre."),
    # --- Catálogo: build-title (ML no pudo armar el título por faltar atributos de la categoría) ---
    # Llega como message STRING: "...resource /decorations/build-title... message:attributes are required"
    # (también cubre el "attributes are required" pelado que puede venir en `cause`).
    (r"(?:build-title.*?)?\battributes?\s+are\s+required\b",
     "Faltan atributos obligatorios de la categoría. Completá la ficha técnica del producto "
     "(marca, modelo, código universal, etc.) en la pestaña MercadoLibre para poder publicar en MercadoLibre."),
    # --- Catálogo: falta family_name (u otras propiedades del body del catálogo) ---
    (r"body\s+does\s+not\s+contains?\s+some\s+or\s+none\s+of\s+the\s+following\s+properties\s*\[?\s*family_name",
     "Falta el Nombre de la familia (Family Name) del producto, requerido para publicar en el "
     "catálogo de MercadoLibre. Completá el campo Family Name en la ficha del producto."),
    (r"body\s+does\s+not\s+contains?\s+some\s+or\s+none\s+of\s+the\s+following\s+properties\s*\[?\s*([^\]]+?)\s*\]?\s*$",
     lambda m: ("Faltan propiedades obligatorias para publicar en el catálogo de MercadoLibre: %s. "
                "Completá esos campos en la ficha del producto." % m.group(1).strip())),
    # --- SKU del vendedor requerido ---
    (r"(?:SELLER_SKU|seller_sku|seller_custom_field)\b.*?"
     r"(?:required|missing|es\s+requerido|es\s+obligatorio)",
     "Falta el SKU del vendedor (código interno del producto). Cargá la Referencia interna del "
     "producto para poder publicar en MercadoLibre."),
    # --- Categoría inválida / requerida ---
    (r"(?:category|categor[ií]a)\b.*?"
     r"(?:invalid|not\s+found|required|inv[aá]lida|no\s+encontrada|requerida)",
     "La categoría de MercadoLibre es inválida o falta seleccionarla. Elegí una categoría válida en "
     "la pestaña MercadoLibre del producto (o en la plantilla)."),
    # --- Medidas/peso del paquete requeridas (seller_package_*) ---
    (r"attributes?\s*\[[^\]]*seller_package[^\]]*\].*?(?:are|is)\s+(?:all\s+)?required",
     "Faltan las medidas y el peso del paquete (alto, ancho, largo y peso). Cargalos en el producto "
     "(pestaña Inventario/Envío, dimensiones del paquete) para poder publicar."),
    # --- Atributos obligatorios que ML ya devuelve en español (según locale) ---
    # Marca
    (r'El campo\s*"?Marca"?\s+es obligatorio',
     "Falta cargar la Marca del producto (atributo obligatorio de la categoría)."),
    # Número de pieza / Part Number
    (r'El campo\s*"?N[uú]mero de pieza"?\s+es obligatorio',
     "Falta el Número de pieza (Part Number), atributo obligatorio de la categoría."),
    # Campo obligatorio en español genérico: El campo "X" es obligatorio [y no está cargado]
    (r'El campo\s*"?([^"]+?)"?\s+es obligatorio',
     lambda m: ("Falta cargar '%s' (atributo obligatorio de la categoría en MercadoLibre)."
                % m.group(1).strip())),
    # --- Atributos en inglés (genéricos, después de los específicos) ---
    # Atributo ignorado por no ser modificable (no-GTIN)
    (r"Attribute\s*\[?\s*([^\]]+?)\s*\]?\s+ignored because it is not modifiable",
     lambda m: ("El atributo '%s' fue ignorado porque ya no se puede modificar en una publicación "
                "existente. No impide publicar." % m.group(1).strip())),
    # Atributo obligatorio faltante (genérico en inglés)
    (r"(?:The\s+)?attributes?\s*\[?\s*([^\]]+?)\s*\]?\s+(?:are|is)\s+(?:all\s+)?required",
     lambda m: ("Falta completar el/los atributo(s) obligatorio(s) '%s' en la ficha de MercadoLibre "
                "(pestaña MercadoLibre del producto)." % m.group(1).strip())),
    # --- Título demasiado largo (por si viene desde la API y no del pre-check) ---
    (r"title.*?(?:length|too long|exceed).*?(\d+)",
     lambda m: ("El título supera el máximo de 60 caracteres permitido por MercadoLibre. "
                "Acortá 'Nombre del producto en Mercado Libre' (pestaña MercadoLibre). "
                "El título se puede editar hasta que entre la primera venta.")),
    # --- Fotos / imágenes (ES que devuelve ML + EN) ---
    (r"Las fotos|La imagen|(?:picture|image)s?.*?(?:required|invalid|not.*?found|must)",
     "Problema con las fotos del producto: MercadoLibre requiere imágenes válidas (tamaño/formato "
     "correcto y al menos una imagen). Revisá que el producto tenga fotos que cumplan los requisitos."),
    # --- Precio inválido / mínimo ---
    (r"price.*?(?:invalid|minimum|not.*?valid)",
     "El precio no es válido para MercadoLibre (revisá que no sea 0 y que cumpla el mínimo de la categoría)."),
]


def _meli_humanize_publish_message(text):
    """Traduce/aclara un mensaje individual de la lista `cause` de la API de ML.

    Devuelve (texto_es, matched_bool). Si ningún patrón conocido matchea,
    devuelve el texto ORIGINAL (defensivo: nunca perder info del error crudo).
    100% defensivo: cualquier excepción cae al texto original.
    """
    if not text:
        return "", False
    stext = str(text).strip()
    try:
        for pat, tmpl in MELI_PUBLISH_ERROR_PATTERNS:
            m = re.search(pat, stext, re.IGNORECASE | re.DOTALL)
            if m:
                try:
                    return (tmpl(m) if callable(tmpl) else tmpl), True
                except Exception:
                    _logger.exception("meli humanize: fallo aplicando plantilla; uso texto original")
                    return stext, False
    except Exception:
        _logger.exception("meli humanize: fallo inesperado; uso texto original")
    return stext, False




class warning1(models.TransientModel):
    _name = 'warning'
    _description = 'warning'
    type = fields.Selection(WARNING_TYPES, string='Type', readonly=True)
    title = fields.Char(string="Title", size=100, readonly=True)
    message = fields.Text(string="Message", readonly=True)
#    message_html = fields.Html(string="Message HTML", readonly=True)

class warning(models.TransientModel):
    _name = 'meli.warning'
    _description = 'warning'
    type = fields.Selection(WARNING_TYPES, string='Type', readonly=True)
    title = fields.Char(string="Title", size=100, readonly=True)
    message = fields.Text(string="Message", readonly=True)
    message_html = fields.Html(string="Message HTML", readonly=True)
    copy_error = fields.Text(string="Copy Error")

    _req_name = 'title'

    def _format_meli_error( self, title, message, message_html='', context=None ):
        context = context or self.env.context

        #process error messages:

        #0 longitud del titulo
        #1 Debe cargar una imagen de base en el producto, si chequeo el 'Dont use first image' debe al menos poner una imagen adicional en el producto.
        #2 Problemas cargando la imagen principal
        #3 Error publicando imagenes
        #4 Debe iniciar sesión en MELI con el usuario correcto
        #5 Completar todos los campos y revise el mensaje siguiente. ("<br><br>"+error_msg)
        #6 Debe completar el campo description en la plantilla de MercadoLibre o del producto (Descripción de Ventas)
        #7 Debe iniciar sesión en MELI
        #8 Recuerde completar todos los campos y revise el mensaje siguiente

        rjson = context and "rjson" in context and context["rjson"]
        if rjson:
            _logger.info("_format_meli_error rjson:"+str(rjson))

            rstatus = "status" in rjson and rjson["status"]
            rcause = "cause" in rjson and rjson["cause"]
            rmessage = "message" in rjson and rjson["message"]
            try:
                rmessage = rmessage and json.loads(rmessage)
            except:
                pass;

            rerror = "error" in rjson and rjson["error"]
            alertstatus = 'warning'

            # El título entrante suele ser el genérico 'MELI WARNING'; para un
            # error real de publicación resulta confuso. Lo reemplazamos por un
            # título claro y accionable (el detalle va en el message itemizado).
            _generic_titles = ["MELI WARNING", "MELI ERROR", "WARNING", "ERROR", False, None, ""]
            _clean_title = "" if title in _generic_titles else str(title)

            if rstatus in ["error",403]:
                title = ("No se pudo publicar en MercadoLibre" + (" — " + _clean_title if _clean_title else ""))
                alertstatus = 'error'

            if rstatus in ["warning"]:
                title = ("Advertencia de MercadoLibre" + (" — " + _clean_title if _clean_title else ""))
                alertstatus = 'warning'

            if str(rstatus) in ["400"]:
                title = ("No se pudo publicar en MercadoLibre" + (" — " + _clean_title if _clean_title else ""))
                alertstatus = 'error'

            alertstatus = (alertstatus in ["error"] and "danger" ) or  ( str(alertstatus) in ["400"] and "danger" ) or alertstatus
            alertstatusico = (rstatus in ["error"] and "times-circle" ) or ( str(rstatus) in ["400"] and "times-circle" ) or rstatus


            if rmessage and type(rmessage)==dict:
                _logger.info("_format_meli_error message:"+str(rmessage))
                _logger.info(rmessage)
                _cause_messages = []  # acumular mensajes de causa para el message principal
                for rmess in rmessage:
                    _logger.info("rmess:"+str(rmess))
                    if rmess == "error":
                        ecode = rmessage[rmess]
                        ecodemess = (ecode in meli_errors and meli_errors[ecode]) or ecode
                        message_html = '<div role="alert" class="alert alert-'+str(alertstatus)+'" title="Meli Message"><i class="fa fa-'+str(alertstatusico)+'" role="img" aria-label="Meli Message"/> %s </div>' % (str(ecodemess))
                    if rmess == "message":
                        message = rmessage[rmess]
                    if rmess == "status":
                        estatus = rmessage[rmess]
                    if rmess == "cause":
                        ecause = rmessage[rmess]
                        if isinstance(ecause, list) and len(ecause):
                            for eca in ecause:
                                if type(eca)==dict:
                                    ecatype = "type" in eca and eca["type"]
                                    ecacode = "code" in eca and eca["code"]
                                    ecamess = "message" in eca and eca["message"]
                                else:
                                    ecatype = "error"
                                    ecacode = "Forbidden"
                                    ecamess = str(eca)

                                ecacodemess = (ecacode in meli_errors and meli_errors[ecacode]) or ecacode
                                ecaalertstatus = (ecatype in ["error"] and "danger" ) or ecatype
                                ecatypeicon = (ecatype in ["error"] and "times-circle" ) or ecatype

                                # humanizar el mensaje crudo de ML (inglés) -> español accionable
                                _hmess, _matched = _meli_humanize_publish_message(ecamess)

                                # acumular para el texto plano del mensaje principal,
                                # prefijando con "Falta:" (error) / "Advertencia:" (warning)
                                if ecamess:
                                    _prefix = "Falta:" if ecatype == "error" else "Advertencia:"
                                    _cause_messages.append("%s %s" % (_prefix, _hmess))

                                ecacodemess = "<strong>"+str(ecacodemess)+"</strong><br/>"
                                ecacodemess+= str(_hmess)
                                message_html+= '<div role="alert" class="alert alert-'+str(ecaalertstatus)+'" title="Meli Message, Code: '+str(ecacode)+'"><i class="fa fa-'+str(ecatypeicon)+'" role="img" aria-label="Meli Message"/> %s </div>' % (str(ecacodemess))

                # Si hay mensajes de causa, mostrarlos claramente como texto principal
                if _cause_messages:
                    message = "\n".join(_cause_messages)
            elif type(rmessage)==str:
                # El mensaje viene como STRING (no lista `cause`): p.ej. el error de
                # build-title ("...message:attributes are required") o un code conocido
                # (invalid_token, etc.). Antes se volcaba CRUDO y en inglés, con ícono
                # amarillo fijo. Ahora lo humanizamos y lo presentamos con el mismo estilo
                # (alert rojo/amarillo + ícono + título accionable) que la rama `cause`.
                ecode = rmessage
                if ecode in meli_errors:
                    ecodemess = meli_errors[ecode]
                else:
                    # traducir el string crudo de ML -> español accionable (defensivo)
                    ecodemess, _matched_str = _meli_humanize_publish_message(ecode)

                # severidad/ícono coherentes con el status (rojo si error/400, amarillo si warning)
                _sev = alertstatus if alertstatus in ["danger", "warning"] else "warning"
                _ico = "times-circle" if _sev == "danger" else "warning"
                _hdr = "No se pudo publicar en MercadoLibre" if _sev == "danger" else "Advertencia de MercadoLibre"
                message_html = ('<div role="alert" class="alert alert-'+str(_sev)+'" title="Meli Message">'
                                '<i class="fa fa-'+str(_ico)+'" role="img" aria-label="Meli Message"/> '
                                '<strong>'+_hdr+'</strong><br/> %s </div>') % (str(ecodemess))
                # que el texto plano del wizard también muestre el mensaje humanizado
                if ecodemess:
                    message = ("Falta: " if _sev == "danger" else "Advertencia: ") + str(ecodemess)

                # Procesar causas aunque el mensaje sea string (ej: "Validation error" con causes detalladas)
                if rcause and isinstance(rcause, list):
                    _cause_messages = []
                    for eca in rcause:
                        if type(eca) == dict:
                            ecatype = eca.get("type", "error")
                            ecacode = eca.get("code", "")
                            ecamess = eca.get("message", "")
                        else:
                            ecatype = "error"
                            ecacode = ""
                            ecamess = str(eca)
                        ecacodemess = (ecacode in meli_errors and meli_errors[ecacode]) or ecacode
                        ecaalertstatus = "danger" if ecatype == "error" else ecatype
                        ecatypeicon = "times-circle" if ecatype == "error" else ecatype
                        # humanizar el mensaje crudo de ML (inglés) -> español accionable
                        _hmess, _matched = _meli_humanize_publish_message(ecamess)
                        if ecamess:
                            _prefix = "Falta:" if ecatype == "error" else "Advertencia:"
                            _cause_messages.append("%s %s" % (_prefix, _hmess))
                        ecacodemess_html = "<strong>"+str(ecacodemess)+"</strong><br/>"+str(_hmess)
                        message_html += '<div role="alert" class="alert alert-'+str(ecaalertstatus)+'" title="Meli Message, Code: '+str(ecacode)+'"><i class="fa fa-'+str(ecatypeicon)+'" role="img" aria-label="Meli Message"/> %s </div>' % ecacodemess_html
                    if _cause_messages:
                        message = "\n".join(_cause_messages)



                        #message_html+= "<br/>Causa: "+str(ecause)

                #message_html+= '<br/><button click="alert(%s)"><i class="fa fa-copy"></i>Copy Error</button>'



        return title, message, message_html

    def _get_view_id(self ):
        """Get the view id
        @return: view id, or False if no view found
        """
        res = get_ref_view( self, WARNING_MODULE, 'warning_form')
        return res and res[1] or False

    def _message(self, id, context=None):
        #pdb.set_trace()
        context = context or self.env.context

        message = self.browse( id)

        rjson = context and "rjson" in context and context["rjson"]
        if rjson:
            message.copy_error = str(rjson)

        message_type = [t[1]for t in WARNING_TYPES if message.type == t[0]][0]
        #_logger.info( '%s: %s' % (_(message_type), _(message.title)) )
        res = {
            'name': '%s: %s' % (_(message_type), _(message.title)),
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': self._get_view_id(),
            'res_model': 'meli.warning',
            'domain': [],
            #'context': context,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'res_id': message.id
        }
        return res

    def copy(self):
        self.ensure_one()
        _logger.info("copy_error:"+str(self.copy_error))
        return {'type': 'ir.actions.act_window_close'}


    def warning(self, title, message, message_html='', context=None):
        context = context or self.env.context
        title, message, message_html = self._format_meli_error(title=title,message=message,message_html=message_html,context=context)
        id = self.create( {'title': title, 'message': message, 'message_html': message_html, 'type': 'warning'}).id
        res = self._message( id, context=context )
        return res

    def info(self, title, message, message_html='', context=None):
        context = context or self.env.context
        title, message, message_html = self._format_meli_error(title=title,message=message,message_html=message_html,context=context)
        id = self.create( {'title': title, 'message': message, 'message_html': message_html, 'type': 'info'}).id
        res = self._message( id,  context=context )
        return res

    def error(self, title, message, message_html='', context=None):
        context = context or self.env.context
        title, message, message_html = self._format_meli_error(title=title,message=message,message_html=message_html, context=context)
        id = self.create( {'title': title, 'message': message, 'message_html': message_html, 'type': 'error'}).id
        res = self._message( id,  context=context )
        return res
