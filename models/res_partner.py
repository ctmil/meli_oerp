# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools
from odoo.tools.translate import _
from difflib import SequenceMatcher
import re

class ResPartner(models.Model):

    _inherit = "res.partner"

    meli_buyer_id = fields.Char('Meli Buyer Id',index=True)
    meli_buyer = fields.Many2one('mercadolibre.buyers',string='Meli Buyer')
    meli_update_forbidden = fields.Boolean(string='Meli Update Forbiden')
    meli_order_id = fields.Char('Meli Order Id',index=True)

    _sql_constraints = [
        ('unique_partner_meli_buyer_id', 'unique(meli_buyer_id,active,company_id)', 'Meli Partner Buyer id already exists in this company!')
    ]

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
        self.ensure_one()  # we just use env on this model

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
                'mobile': partner.mobile,
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
            p_phone = self._normalize_phone(partner.phone or partner.mobile or '')
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
        raw = tools.ustr(raw).lower()
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
