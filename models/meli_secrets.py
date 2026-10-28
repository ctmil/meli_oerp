# -*- coding: utf-8 -*-
"""26.329 (bus 2026-09-25T14:30:56Z, medido en caso-K11): los campos de error que se PERSISTEN (meli_stock_error,
meli_price_error, processing_errors/logs de la notificacion) guardaban el JSON crudo de ML con
"access_token": "APP_USR-...". Quedaba en la base y visible en la ficha.

Punto unico de control: se limpia al ESCRIBIR (create/write), no en cada sitio que arma el texto,
asi cualquier camino nuevo que haga `campo = str(resjson)` queda cubierto.
"""
import re

from odoo import api, models

# 'code' NO va: en los errores de ML `code` es el codigo del error (field_not_updatable) y hay que verlo.
_MELI_SCRUB_KEYS = ('access_token', 'refresh_token', 'client_secret', 'secret_key')
_MELI_SCRUB_KV_RE = re.compile(
    r"""(?i)(["']?(?:access_token|refresh_token|client_secret|secret_key)["']?\s*[:=]\s*["']?)([^"'&,\s}\])]+)""")
_MELI_SCRUB_TOKEN_RE = re.compile(r'\b(APP_USR|TG)-[0-9A-Za-z][0-9A-Za-z\-]{10,}')


def meli_scrub_secrets(value):
    """Copia de `value` (dict/list/str) sin secretos de ML. Otros tipos se devuelven tal cual."""
    if isinstance(value, dict):
        return {k: ('***' if (k in _MELI_SCRUB_KEYS and v) else meli_scrub_secrets(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(meli_scrub_secrets(v) for v in value)
    if isinstance(value, str) and value:
        value = _MELI_SCRUB_KV_RE.sub(lambda m: m.group(1) + '***', value)
        return _MELI_SCRUB_TOKEN_RE.sub(lambda m: m.group(1) + '-***', value)
    return value


def _meli_scrub_vals(vals, fnames):
    if not isinstance(vals, dict) or not any(f in vals for f in fnames):
        return vals
    vals = dict(vals)
    for f in fnames:
        if isinstance(vals.get(f), str):
            vals[f] = meli_scrub_secrets(vals[f])
    return vals


_PRODUCT_FIELDS = ('meli_stock_error', 'meli_price_error')
_NOTI_FIELDS = ('processing_errors', 'processing_logs', 'last_json_response')


class ProductProductMeliSecretGuard(models.Model):
    _inherit = 'product.product'

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([_meli_scrub_vals(v, _PRODUCT_FIELDS) for v in vals_list])

    def write(self, vals):
        return super().write(_meli_scrub_vals(vals, _PRODUCT_FIELDS))


class ProductTemplateMeliSecretGuard(models.Model):
    _inherit = 'product.template'

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([_meli_scrub_vals(v, _PRODUCT_FIELDS) for v in vals_list])

    def write(self, vals):
        return super().write(_meli_scrub_vals(vals, _PRODUCT_FIELDS))


class MeliNotificationSecretGuard(models.Model):
    _inherit = 'mercadolibre.notification'

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([_meli_scrub_vals(v, _NOTI_FIELDS) for v in vals_list])

    def write(self, vals):
        return super().write(_meli_scrub_vals(vals, _NOTI_FIELDS))
