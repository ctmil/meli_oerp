# -*- coding: utf-8 -*-
"""[#661 fase 3] Rastro de uso de una URL de la API de Mercado Libre distinta de la oficial.

Cada request al host alternativo (reverse proxy de rescate), cada vez que el Nivel de seguridad Alto
lo ignora, y cada cambio de la URL quedan acá (y en el logger `meli_oerp.proxy_audit` como línea JSON).
Nunca se guardan tokens, headers, body ni parámetros de la URL.

Sólo lectura para el Administrador. Las filas las escribe el sistema en un cursor propio
(ver meli_util.meli_proxy_audit). Sin claves foráneas a propósito: la inserción no puede quedar
esperando un lock que tenga tomado la transacción que hizo la llamada.
"""
from datetime import timedelta

from odoo import api, fields, models


class MeliProxyAudit(models.Model):
    _name = 'meli.proxy.audit'
    _description = 'Registro de uso de la URL de la API de Mercado Libre'
    _order = 'id desc'
    _rec_name = 'host'

    event = fields.Selection([
        ('request', 'Uso'),
        ('blocked', 'Ignorado por Nivel de seguridad'),
        ('config', 'Cambio de URL'),
    ], string='Evento', readonly=True, index=True)
    company_ref = fields.Integer(string='Id compañía', readonly=True, index=True)
    company_name = fields.Char(string='Compañía', readonly=True)
    account_label = fields.Char(string='Cuenta', readonly=True)
    host = fields.Char(string='Host', readonly=True, index=True)
    method = fields.Char(string='Método', readonly=True)
    path = fields.Char(string='Ruta (sin parámetros)', readonly=True)
    status_code = fields.Integer(string='Respuesta HTTP', readonly=True)
    user_login = fields.Char(string='Usuario', readonly=True)
    note = fields.Char(string='Nota', readonly=True)

    @api.autovacuum
    def _gc_meli_proxy_audit(self):
        """Retención: ICP meli_oerp.proxy_audit_days (default 90; 0 = no borrar)."""
        try:
            days = int(self.env['ir.config_parameter'].sudo().get_param('meli_oerp.proxy_audit_days', 90))
        except (TypeError, ValueError):
            days = 90
        if days <= 0:
            return
        limit = fields.Datetime.now() - timedelta(days=days)
        self.sudo().search([('create_date', '<', limit)]).unlink()
