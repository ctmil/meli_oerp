from odoo import fields, osv, models
from odoo.tools.translate import _
import pdb
import json

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




class warning1(models.TransientModel):
    _name = 'warning'
    _description = 'warning'
    type = fields.Selection(WARNING_TYPES, string='Type', readonly=True)
    title = fields.Char(string="Title", size=100, readonly=True)
    message = fields.Text(string="Message", readonly=True)
    message_html = fields.Html(string="Message HTML", readonly=True)
warning1()

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
            
            if rstatus in ["error",403]:
                title = "ERROR MELI: " + title
                alertstatus = 'error'                
            
            if rstatus in ["warning"]:
                title = "WARNING MELI: " + title
                alertstatus = 'warning'
                
            alertstatus = (alertstatus in ["error"] and "danger" ) or  ( str(alertstatus) in ["400"] and "danger" ) or alertstatus
            alertstatusico = (rstatus in ["error"] and "times-circle" ) or ( str(rstatus) in ["400"] and "times-circle" ) or rstatus

                
            if rmessage and type(rmessage)==dict:
                _logger.info("_format_meli_error message:"+str(rmessage))
                _logger.info(rmessage)
                for rmess in rmessage:
                    _logger.info("rmess:"+str(rmess))
                    if rmess == "error":
                        ecode = rmessage[rmess]
                        ecodemess = (ecode in meli_errors and meli_errors[ecode]) or ecode
                        message_html = '<div role="alert" class="alert alert-'+str(alertstatus)+'" title="Meli Message"><i class="fa fa-'+str(alertstatusico)+'" role="img" aria-label="Meli Message"/> %s </div>' % (str(ecodemess))
                    if rmess == "message":
                        message = rmessage[rmess]
                        #message_html+= "<br/>"+str(rmessage[rmess])
                    if rmess == "status":
                        estatus = rmessage[rmess]
                        #message_html+= "<br/>Estado: "+str(estatus)
                    if rmess == "cause":
                        ecause = rmessage[rmess]
                        if len(ecause):
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


                                ecacodemess = "<strong>"+str(ecacodemess)+"</strong><br/>"
                                ecacodemess+= str(ecamess)
                                message_html+= '<div role="alert" class="alert alert-'+str(ecaalertstatus)+'" title="Meli Message, Code: '+str(ecacode)+'"><i class="fa fa-'+str(ecatypeicon)+'" role="img" aria-label="Meli Message"/> %s </div>' % (str(ecacodemess))
            elif type(rmessage)==str:
                ecode = rmessage
                ecodemess = (ecode in meli_errors and meli_errors[ecode]) or ecode

                message_html = '<div role="alert" class="alert alert-'+str(alertstatus)+'" title="Meli Message"><i class="fa fa-warning" role="img" aria-label="Meli Message"/> %s </div>' % (ecodemess)
                
                
                                
                        #message_html+= "<br/>Causa: "+str(ecause)
                        
                #message_html+= '<br/><button click="alert(%s)"><i class="fa fa-copy"></i>Copy Error</button>'
            
                    
        
        return title, message, message_html

    def _get_view_id(self ):
        """Get the view id
        @return: view id, or False if no view found
        """
        res = self.env['ir.model.data'].check_object_reference( WARNING_MODULE, 'warning_form')
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

warning()
