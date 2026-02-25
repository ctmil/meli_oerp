
from odoo import fields, models, api
from odoo.tools.translate import _
import logging
_logger = logging.getLogger(__name__)

import pdb
import threading

from .meli_oerp_config import *
from .warning import warning
from . import versions
from .versions import *

import requests

from typing import Dict, List

import babel.dates
import base64
import copy
import itertools
import json
import pytz

from odoo import _, _lt, api, fields, models
from odoo.fields import Command
from odoo.models import BaseModel, NewId
# Odoo 19: odoo.osv.expression moved to odoo.domain
try:
    from odoo.domain import AND, TRUE_DOMAIN, normalize_domain
except ImportError:
    from odoo.osv.expression import AND, TRUE_DOMAIN, normalize_domain
from odoo.tools import date_utils, unique
from odoo.tools.misc import OrderedSet, get_lang
from odoo.exceptions import UserError
from collections import defaultdict

SEARCH_PANEL_ERROR_MESSAGE = _lt("Too many items to display.")

class Base(models.AbstractModel):
    _inherit = 'base'


    def Xweb_read(self, specification: Dict[str, Dict]) -> List[Dict]:

        fields_to_read = list(specification) or ['id']

        modelo = self.env.context and "params" in self.env.context and "model" in self.env.context["params"] and self.env.context["params"]["model"]

        #_logger.info("web_read : context: " +str(self.env.context))
        #_logger.info("web_read : fields_to_read: " +str(fields_to_read))

        if fields_to_read == ['id']:
            # if we request to read only the ids, we have them already so we can build the return dictionaries immediately
            # this also avoid a call to read on the co-model that might have different access rules
            values_list = [{'id': id_} for id_ in self._ids]
        else:
            #_logger.info("web_read : values_list self._ids: "+str(self._ids)+" self.read: " +str(fields_to_read))
            if ((modelo=="mercadolibre.product" or (modelo=="mercadolibre.product_template")) and self._ids and len(self._ids)==1):
                for id in self._ids:
                    record_data = self.sudo().search_read([('id','=',id)],fields_to_read)
                    #_logger.info("record_data:"+str(record_data))
                    values_list = [{}]
                    if not record_data:
                        record_object = self.sudo().browse(id)
                        #_logger.info("record_object:"+str(record_object))
                    if record_data:
                        for f in fields_to_read:
                            #_logger.info("web_read : f: " +str(f)+" => " + str(record_data[0][f]))
                            if (type(record_data[0][f])==tuple):
                                values_list[0][f] = record_data[0][f][0]
                            else:
                                values_list[0][f] = record_data[0][f]
                        #_logger.info("web_read : values_list: " +str(values_list))
                    else:

                        values_list: List[Dict] = self.read(fields_to_read, load=None)
            else:
                values_list: List[Dict] = self.read(fields_to_read, load=None)

        if not values_list:
            return values_list

        #for f in values_list[0]:
        #    _logger.info("web_read values_list : f: " +str(f)+" => " + str(values_list[0][f]))

        def cleanup(vals: Dict) -> Dict:
            """ Fixup vals['id'] of a new record. """
            if not vals['id']:
                vals['id'] = vals['id'].origin or False
            return vals

        for field_name, field_spec in specification.items():
            #_logger.info("web_read : field_name: " +str(field_name))
            field = self._fields.get(field_name)
            if field is None:
                continue

            if field.type == 'many2one':
                if 'fields' not in field_spec:
                    for values in values_list:
                        if isinstance(values[field_name], NewId):
                            values[field_name] = values[field_name].origin
                    continue

                co_records = self[field_name]
                if 'context' in field_spec:
                    co_records = co_records.with_context(**field_spec['context'])
                    #_logger.info("co_records: "+str(co_records))

                extra_fields = dict(field_spec['fields'])
                #_logger.info("extra_fields: "+str(extra_fields))
                extra_fields.pop('display_name', None)
                #_logger.info("extra_fields: "+str(extra_fields))
                many2one_data = {
                    vals['id']: cleanup(vals)
                    for vals in co_records.web_read(extra_fields)
                }
                #_logger.info("many2one_data: "+str(many2one_data))
                #_logger.info("field_spec['fields']: "+str(field_spec['fields']))

                if 'display_name' in field_spec['fields']:
                    for rec in co_records.sudo():
                        many2one_data[rec.id]['display_name'] = rec.display_name

                for values in values_list:
                    if values[field_name] is False:
                        continue
                    #_logger.info("field_name: "+str(field_name))
                    #_logger.info("values[field_name]: "+str(values[field_name]))
                    vals = many2one_data[values[field_name]]
                    values[field_name] = vals['id'] and vals

            elif field.type in ('one2many', 'many2many'):
                if not field_spec:
                    continue

                co_records = self[field_name]

                if 'order' in field_spec and field_spec['order']:
                    co_records = co_records.search([('id', 'in', co_records.ids)], order=field_spec['order'])
                    order_key = {
                        co_record.id: index
                        for index, co_record in enumerate(co_records)
                    }
                    for values in values_list:
                        # filter out inaccessible corecords in case of "cache pollution"
                        values[field_name] = [id_ for id_ in values[field_name] if id_ in order_key]
                        values[field_name] = sorted(values[field_name], key=order_key.__getitem__)

                if 'context' in field_spec:
                    co_records = co_records.with_context(**field_spec['context'])

                if 'fields' in field_spec:
                    if field_spec.get('limit') is not None:
                        limit = field_spec['limit']
                        ids_to_read = OrderedSet(
                            id_
                            for values in values_list
                            for id_ in values[field_name][:limit]
                        )
                        co_records = co_records.browse(ids_to_read)

                    x2many_data = {
                        vals['id']: vals
                        for vals in co_records.web_read(field_spec['fields'])
                    }

                    for values in values_list:
                        values[field_name] = [x2many_data.get(id_) or {'id': id_} for id_ in values[field_name]]

            elif field.type in ('reference', 'many2one_reference'):
                if not field_spec:
                    continue

                values_by_id = {
                    vals['id']: vals
                    for vals in values_list
                }
                for record in self:
                    if not record[field_name]:
                        continue

                    if field.type == 'reference':
                        co_record = record[field_name]
                    else:  # field.type == 'many2one_reference'
                        co_record = self.env[record[field.model_field]].browse(record[field_name])

                    if 'context' in field_spec:
                        co_record = co_record.with_context(**field_spec['context'])

                    if 'fields' in field_spec:
                        reference_read = co_record.web_read(field_spec['fields'])
                        if any(fname != 'id' for fname in field_spec['fields']):
                            # we can infer that if we can read fields for the co-record, it exists
                            co_record_exists = bool(reference_read)
                        else:
                            co_record_exists = co_record.exists()
                    else:
                        # If there are no fields to read (field_spec.get('fields') --> None) and we web_read ids, it will
                        # not actually read the records so we do not know if they exist.
                        # This ensures the record actually exists
                        co_record_exists = co_record.exists()

                    record_values = values_by_id[record.id]

                    if not co_record_exists:
                        record_values[field_name] = False
                        if field.type == 'many2one_reference':
                            record_values[field.model_field] = False
                        continue

                    if 'fields' in field_spec:
                        record_values[field_name] = reference_read[0]
                        if field.type == 'reference':
                            record_values[field_name]['id'] = {
                                'id': co_record.id,
                                'model': co_record._name
                            }

        #_logger.info("web_read : values_list FINAL: " +str(values_list))
        return values_list
