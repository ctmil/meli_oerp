# -*- coding: utf-8 -*-
from odoo import fields, models, api
import logging

_logger = logging.getLogger(__name__)


class MeliCarrierMapping(models.Model):
    """Tabla de mapeo entre nombres de tracking method de MercadoLibre
    y delivery.carrier existentes en Odoo. Permite reutilizar carriers
    ya dados de alta (ej: desde Producteca u otro conector) sin duplicar."""

    _name = "meli_oerp.carrier.mapping"
    _description = "Mapeo de carriers MercadoLibre"
    _order = "meli_name asc"

    meli_name = fields.Char(
        string="Nombre en MercadoLibre",
        required=True,
        index=True,
        help="Nombre del tracking method tal como llega de MercadoLibre (ej: 'MEL Distribution', 'Andreani Estándar')",
    )
    carrier_id = fields.Many2one(
        "delivery.carrier",
        string="Transportista en Odoo",
        domain="[('active', '=', True)]",
        help="Carrier existente en Odoo al que se mapea este nombre de ML. "
             "Si está vacío, se creará uno automáticamente al recibir un envío con este nombre.",
    )
    carrier_active = fields.Boolean(
        related="carrier_id.active",
        string="Carrier activo",
        store=True,
    )
    logistic_type = fields.Char(
        string="Tipo logístico",
        help="Tipo logístico de ML asociado (fulfillment, drop_off, cross_docking, etc.)",
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Empresa",
        default=lambda self: self.env.company,
    )

    @api.onchange('carrier_id')
    def _onchange_carrier_id(self):
        if self.carrier_id and not self.carrier_id.active:
            return {
                'warning': {
                    'title': 'Transportista archivado',
                    'message': 'El transportista "%s" está archivado. '
                               'Seleccione uno activo o desarchívelo primero.' % self.carrier_id.name,
                }
            }

    _sql_constraints = [
        (
            "unique_meli_name_company",
            "UNIQUE(meli_name, company_id)",
            "Ya existe un mapeo para este nombre de ML en esta empresa.",
        ),
    ]

    @api.model
    def resolve_carrier(self, meli_name, company=None, product_shipping_id=None):
        """Busca un carrier en Odoo para el nombre de ML dado.

        Returns:
            delivery.carrier recordset (puede estar vacío)
        """
        if not meli_name:
            return self.env["delivery.carrier"]

        company = company or self.env.company
        domain = [
            ("meli_name", "=ilike", meli_name),
            "|",
            ("company_id", "=", company.id),
            ("company_id", "=", False),
        ]
        mapping = self.search(domain, limit=1)

        if mapping and mapping.carrier_id and mapping.carrier_id.active:
            return mapping.carrier_id

        if not mapping:
            # Crear entrada de mapeo vacía para que el usuario la asigne después
            try:
                self.sudo().create({
                    "meli_name": meli_name,
                    "company_id": company.id,
                })
            except Exception:
                pass  # unique constraint — ya existe

        return self.env["delivery.carrier"]
