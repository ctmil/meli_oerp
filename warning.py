from openerp.osv import fields, osv
from openerp.tools.translate import _

#CHANGE WARNING_MODULE with your module name
WARNING_MODULE = 'meli_oerp'
WARNING_TYPES = [('warning','Warning'),('info','Information'),('error','Error')]

class warning(osv.osv_memory):
    _name = 'warning'
    _description = 'warning'
    _columns = {
        'type': fields.selection(WARNING_TYPES, string='Type', readonly=True),
        'title': fields.char(string="Title", size=100, readonly=True),
        'message': fields.text(string="Message", readonly=True),
        'message_html': fields.html(string="Message HTML", readonly=True),
    }
    _req_name = 'title'

    def _get_view_id(self, cr, uid):
        """Get the view id
        @return: view id, or False if no view found
        """
        res = self.pool.get('ir.model.data').get_object_reference(cr, uid, 
        WARNING_MODULE, 'warning_form')
        return res and res[1] or False

    def _message(self, cr, uid, id, context):
        message = self.browse(cr, uid, id)
        message_type = [t[1]for t in WARNING_TYPES if message.type == t[0]][0]
        print '%s: %s' % (_(message_type), _(message.title))
        res = {
            'name': '%s: %s' % (_(message_type), _(message.title)),
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': self._get_view_id(cr, uid),
            'res_model': 'warning',
            'domain': [],
            'context': context,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'res_id': message.id
        }
        return res

    def warning(self, cr, uid, title, message, message_html='', context=None):
        id = self.create(cr, uid, {'title': title, 'message': message, 'message_html': message_html, 'type': 'warning'})
        res = self._message(cr, uid, id, context)
        return res

    def info(self, cr, uid, title, message, message_html='', context=None):
        id = self.create(cr, uid, {'title': title, 'message': message, 'message_html': message_html, 'type': 'info'})
        res = self._message(cr, uid, id, context)
        return res

    def error(self, cr, uid, title, message, message_html='', context=None):
        id = self.create(cr, uid, {'title': title, 'message': message, 'message_html': message_html, 'type': 'error'})
        res = self._message(cr, uid, id, context)
        return res

warning()


