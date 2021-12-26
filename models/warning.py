from odoo import fields, osv, models
from odoo.tools.translate import _
import pdb
#CHANGE WARNING_MODULE with your module name
WARNING_MODULE = 'meli_oerp'
WARNING_TYPES = [('warning','Warning'),('info','Information'),('error','Error')]


class warning(models.TransientModel):
    _name = 'meli.warning'
    _description = 'warning'
    type = fields.Selection(WARNING_TYPES, string='Type', readonly=True);
    title = fields.Char(string="Title", size=100, readonly=True);
    message = fields.Text(string="Message", readonly=True);
    message_html = fields.Html(string="Message HTML", readonly=True);

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
            
            status = "status" in rjson and rjson["status"]
            cause = "cause" in rjson and rjson["cause"]
            message = "message" in rjson and rjson["message"]
            error = "error" in rjson and rjson["error"]
            
            if status in ["error"]:
                title = "ERROR MELI: " + title
            
            if status in ["warning"]:
                title = "WARNING MELI: " + title
                
            if message:
                _logger.info("_format_meli_error message:"+str(message))
                _logger.info(message)
                for mess in message:
                    _logger.info("mess:"+str(mess))
        
        return title, message, message_html

    def _get_view_id(self ):
        """Get the view id
        @return: view id, or False if no view found
        """
        res = self.env['ir.model.data'].get_object_reference( WARNING_MODULE, 'warning_form')
        return res and res[1] or False

    def _message(self, id):
        #pdb.set_trace()
        message = self.browse( id)
        message_type = [t[1]for t in WARNING_TYPES if message.type == t[0]][0]
        #_logger.info( '%s: %s' % (_(message_type), _(message.title)) )
        res = {
            'name': '%s: %s' % (_(message_type), _(message.title)),
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': self._get_view_id(),
            'res_model': 'warning',
            'domain': [],
            #'context': context,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'res_id': message.id
        }
        return res

    def warning(self, title, message, message_html='', context=None):
        context = context or self.env.context
        title, message, message_html = self._format_meli_error(title=title,message=message,message_html=message_html,context=context)
        id = self.create( {'title': title, 'message': message, 'message_html': message_html, 'type': 'warning'}).id
        res = self._message( id )
        return res

    def info(self, title, message, message_html='', context=None):
        context = context or self.env.context
        title, message, message_html = self._format_meli_error(title=title,message=message,message_html=message_html,context=context)
        id = self.create( {'title': title, 'message': message, 'message_html': message_html, 'type': 'info'}).id
        res = self._message( id )
        return res

    def error(self, title, message, message_html='', context=None):
        context = context or self.env.context
        title, message, message_html = self._format_meli_error(title=title,message=message,message_html=message_html, context=context)
        id = self.create( {'title': title, 'message': message, 'message_html': message_html, 'type': 'error'}).id
        res = self._message( id)
        return res

warning()
