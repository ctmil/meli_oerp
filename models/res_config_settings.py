from odoo import models, fields, api, SUPERUSER_ID
from logging import getLogger

_log = getLogger(__name__)

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    mercadolibre_client_id = fields.Char(
        string='Client Id', 
        help='Client ID', 
        related="company_id.mercadolibre_client_id",
        readonly=False
    )
    mercadolibre_secret_key = fields.Char(
        string='Secret key', 
        help='Secret key',
        related="company_id.mercadolibre_secret_key",
        readonly=False
    )
    mercadolibre_access_token = fields.Char(
        string='Access Token', 
        help='Access Token', 
        related="company_id.mercadolibre_access_token",
        readonly=False
    )
    mercadolibre_refresh_token = fields.Char(
        string='Refresh Token', 
        help='Refresh Token',
        related="company_id.mercadolibre_refresh_token",
        readonly=False
    )
    mercadolibre_sending_message_to_customer = fields.Boolean(
        string='Activate sending message to customer',
        help='Activate sending message to customer',
        related='company_id.mercadolibre_sending_message_to_customer',
        readonly=False
    )
