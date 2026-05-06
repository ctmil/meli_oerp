# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools
from odoo.tools.translate import _
from difflib import SequenceMatcher
import logging
import re
from . import versions

_logger = logging.getLogger(__name__)


class MergePartnerAutomatic(models.TransientModel):
    _inherit = 'base.partner.merge.automatic.wizard'

    def _merge(self, partner_ids, dst_partner=None, extra_checks=True):
        """Clear meli_buyer_id on source partners before merge to avoid unique constraint violation."""
        if dst_partner and partner_ids:
            src_partners = self.env['res.partner'].browse(partner_ids) - dst_partner
            if src_partners:
                src_partners.write({'meli_buyer_id': False})
        return super()._merge(partner_ids, dst_partner=dst_partner, extra_checks=extra_checks)


class ResPartner(models.Model):

    _inherit = "res.partner"

    meli_buyer_id = fields.Char('Meli Buyer Id',index=True)
    meli_buyer = fields.Many2one('mercadolibre.buyers',string='Meli Buyer')
    meli_update_forbidden = fields.Boolean(string='Meli Update Forbiden')
    meli_order_id = fields.Char('Meli Order Id',index=True)

    # Modo 3: contacto de facturación independiente (sin parent_id).
    # meli_buyer_partner_id vincula al buyer que creó/usó este contacto fiscal.
    # Un mismo contacto fiscal (CUIT) puede ser usado por varios buyers.
    meli_buyer_partner_id = fields.Many2one(
        'res.partner', string='MeLi Buyer (Origin)',
        index=True, ondelete='set null',
        help='Buyer de MercadoLibre que originó este contacto de facturación')
    meli_billing_partner_ids = fields.One2many(
        'res.partner', 'meli_buyer_partner_id',
        string='MeLi Billing Contacts',
        help='Contactos de facturación creados desde este buyer de MeLi')

    _unique_partner_meli_buyer_id = versions.UniqueIndex('meli_buyer_id, active, company_id', message='Meli Partner Buyer id already exists in this company!')

    # --- Protección de datos fiscales en billing children de MeLi ---
    # En MeLi, un mismo buyer puede facturar con diferentes entidades fiscales
    # por compra (DNI personal, CUIT empresa A, CUIT empresa B, etc.).
    # Cada billing child (type=invoice, meli_order_id) tiene datos fiscales propios.
    # El mecanismo commercial_fields de Odoo sincroniza datos fiscales del parent
    # a todos los children, lo que BORRA los datos del billing child cuando se
    # toca cualquier commercial_field en el parent (ej: country_id).
    # Este override protege los billing children de MeLi: deja que el sync
    # normal corra, pero restaura los datos fiscales que tenía el child.

    _MELI_FISCAL_FIELDS = ['vat', 'partner_document_type_id',
                           'l10n_latam_identification_type_id',
                           'property_account_position_id',
                           'l10n_ar_afip_responsibility_type_id']

    def _commercial_sync_from_company(self):
        # Solo proteger billing children de MeLi (type=invoice con meli_order_id)
        if self.type == 'invoice' and self.meli_order_id:
            # Guardar datos fiscales antes del sync
            fiscal_backup = {}
            for fname in self._MELI_FISCAL_FIELDS:
                if fname in self._fields:
                    val = getattr(self, fname)
                    if val:
                        fiscal_backup[fname] = val.id if hasattr(val, 'id') else val

            # Ejecutar sync normal (puede pisar datos fiscales con los del parent)
            super()._commercial_sync_from_company()

            # Restaurar datos fiscales si el sync los borró
            if fiscal_backup:
                restore = {}
                for fname, backed_val in fiscal_backup.items():
                    current = getattr(self, fname)
                    current_val = current.id if hasattr(current, 'id') else current
                    if not current_val and backed_val:
                        restore[fname] = backed_val
                if restore:
                    # Usar super().write() para evitar re-triggear commercial_fields
                    super(ResPartner, self).write(restore)
                    _logger.info("MELI_FISCAL_PROTECT: restaurados datos fiscales en billing child id:%s (%s)",
                                 self.id, list(restore.keys()))
        else:
            super()._commercial_sync_from_company()

    @api.model
    def find_similar_delivery_address(
        self,
        parent_partner,
        address_vals,
        similarity_threshold=0.82,
    ):
        """
        Try to find an existing delivery address for given parent_partner that
        is "similar enough" to address_vals to avoid creating duplicates.

        :param parent_partner: res.partner record (commercial partner)
        :param address_vals: dict with address fields (street, street2, zip, city,
                             state_id, country_id, name, phone, mobile, etc.)
        :param similarity_threshold: float between 0 and 1
        :return: res.partner record or False
        """
        #self.ensure_one()  # we just use env on this model

        if not parent_partner:
            return False

        # 1) Build a normalized string for the incoming address
        incoming_addr_str = self._build_normalized_address_string(address_vals)

        # Basic hard filters: zip, country, maybe city if present
        zip_code = address_vals.get('zip') or False
        country_id = address_vals.get('country_id') or False
        city = (address_vals.get('city') or '').strip()

        domain = [
            ('commercial_partner_id', '=', parent_partner.id),
            '|', ('type', '=', 'delivery'), ('is_company', '=', False),
            ('id', '!=', parent_partner.id),  # never match the buyer/parent itself
        ]

        if country_id:
            domain.append(('country_id', '=', country_id))
        if zip_code:
            domain.append(('zip', '=', zip_code))
        # You can decide if city should be a hard or soft filter
        # here we keep it soft (used in score), not in domain

        candidates = self.search(domain)

        if not candidates:
            return False

        best_partner = False
        best_score = 0.0

        for partner in candidates:
            candidate_vals = {
                'name': partner.name,
                'street': partner.street,
                'street2': partner.street2,
                'zip': partner.zip,
                'city': partner.city,
                'phone': partner.phone,
                'mobile': getattr(partner, 'mobile', False) or False,
            }
            candidate_str = self._build_normalized_address_string(candidate_vals)

            if not candidate_str:
                continue

            score = SequenceMatcher(None, incoming_addr_str, candidate_str).ratio()

            # Bonus points if city matches exactly (when provided)
            if city and partner.city and city.lower() == (partner.city or '').lower():
                score += 0.05

            # Bonus points if phone matches (when provided)
            in_phone = self._normalize_phone(address_vals.get('phone') or address_vals.get('mobile') or '')
            p_phone = self._normalize_phone(partner.phone or getattr(partner, 'mobile', '') or '')
            if in_phone and p_phone and in_phone == p_phone:
                score += 0.1

            if score > best_score:
                best_score = score
                best_partner = partner

        if best_partner and best_score >= similarity_threshold:
            return best_partner

        return False

    # -------------------------------------------------------------------------
    # Internal normalizers
    # -------------------------------------------------------------------------
    @api.model
    def _build_normalized_address_string(self, vals):
        """
        Create a single normalized string from address components.
        """
        parts = [
            vals.get('name') or '',
            vals.get('street') or '',
            vals.get('street2') or '',
            vals.get('zip') or '',
            vals.get('city') or '',
        ]
        raw = ' '.join(p for p in parts if p)

        # Lowercase, remove accents, remove non-alphanumeric except spaces
        # Note: ustr() is deprecated in Odoo 18, raw is already a string
        raw = str(raw).lower()
        raw = tools.remove_accents(raw)
        raw = re.sub(r'[^a-z0-9\s]', ' ', raw)
        raw = re.sub(r'\s+', ' ', raw).strip()

        return raw

    @api.model
    def _normalize_phone(self, phone):
        """
        Very simple phone normalizer: keep only digits, drop leading zeros if many.
        """
        if not phone:
            return ''
        phone = re.sub(r'\D', '', phone)
        # Remove leading 00 or single 0 if long
        phone = re.sub(r'^00', '', phone)
        if len(phone) > 8:
            phone = re.sub(r'^0', '', phone)
        return phone
