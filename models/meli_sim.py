# -*- coding: utf-8 -*-
"""Modo SIMULACION de ordenes de Mercado Libre (demo / test / soporte).

Importa una venta desde un bundle JSON por el camino real del import, sin que exista en ML y sin
que ML reciba ninguna escritura. Ver `meli_sim_client.py` para las garantias de red.

Interruptor por compañía `meli_simulation_enabled` (default APAGADO, sólo Administración).
"""
import base64
import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .meli_sim_client import (MeliSimClient, meli_sim_activate, meli_sim_active,
                              meli_sim_parse_bundle)

_logger = logging.getLogger(__name__)


def meli_sim_config_company(config, env):
    if config is not None and config:
        if config._name == 'res.company':
            return config
        if 'company_id' in config._fields and config.company_id:
            return config.company_id
    return env.company


class ResCompanyMeliSim(models.Model):
    _inherit = 'res.company'

    meli_simulation_enabled = fields.Boolean(
        string="Simular ventas de Mercado Libre (demo/test)", default=False, copy=False,
        groups="base.group_system",
        help="Permite importar ventas SIMULADAS desde un JSON (asistente y OCAPI). Las ventas quedan "
             "marcadas «SIMULADA» y Mercado Libre no recibe ninguna escritura. Sólo para bases de "
             "demostración o de prueba: dejarlo apagado en producción.")
    meli_simulation_fallback_real_reads = fields.Boolean(
        string="Simulación: completar lecturas con ML real", default=False, copy=False,
        groups="base.group_system",
        help="Si el JSON de la simulación no trae una consulta que el import necesita, se LEE de "
             "Mercado Libre con el token de la cuenta. Nunca se escribe. Apagado: la consulta "
             "faltante devuelve vacío y queda anotada.")

    def action_meli_simulate_wizard(self):
        self.ensure_one()
        return self.env['mercadolibre.orders.simulate'].meli_sim_open_action(company=self)


class SaleOrderMeliSim(models.Model):
    _inherit = 'sale.order'

    meli_simulated = fields.Boolean(string="Venta ML SIMULADA", readonly=True, copy=False,
                                    help="Venta importada en modo simulación: no existe en Mercado Libre.")

    def meli_sim_guard(self, what=''):
        """True (y deja constancia) si alguna venta es simulada: el llamador NO escribe en ML."""
        sims = self.filtered('meli_simulated')
        if sims:
            _logger.info("meli simulacion: %s omitido para ventas simuladas %s", what or 'escritura a ML', sims.ids)
        return bool(sims)


class MercadoLibreOrdersMeliSim(models.Model):
    _inherit = 'mercadolibre.orders'

    meli_simulated = fields.Boolean(string="SIMULADA", readonly=True, copy=False,
                                    help="Orden importada en modo simulación: no existe en Mercado Libre.")
    meli_sim_bundle = fields.Text(string="Bundle de simulación", readonly=True, copy=False,
                                  groups="base.group_system")
    meli_sim_log = fields.Text(string="Registro de la simulación", readonly=True, copy=False)

    def meli_sim_guard(self, what=''):
        sims = self.filtered('meli_simulated')
        if sims:
            _logger.info("meli simulacion: %s omitido para ordenes simuladas %s", what or 'escritura a ML', sims.ids)
        return bool(sims)

    # --- marca desde el primer write (el import arma los vals con estos dos) -------------------
    def prepare_ml_order_vals(self, meli=None, order_json=None, config=None):
        vals = super().prepare_ml_order_vals(meli=meli, order_json=order_json, config=config)
        if getattr(meli, 'is_meli_simulation', False) or meli_sim_active(self.env.cr.dbname):
            vals['meli_simulated'] = True
        return vals

    def prepare_sale_order_vals(self, meli=None, order_json=None, config=None, sale_order=None, shipment=None):
        vals = super().prepare_sale_order_vals(meli=meli, order_json=order_json, config=config,
                                               sale_order=sale_order, shipment=shipment)
        if isinstance(vals, dict) and (getattr(meli, 'is_meli_simulation', False) or meli_sim_active(self.env.cr.dbname)):
            vals['meli_simulated'] = True
        return vals

    # --- entrada única ---------------------------------------------------------------------------
    @api.model
    def _meli_sim_real_client(self, config, company):
        """Cliente REAL (sólo para lecturas de respaldo). multiple lo pisa por cuenta."""
        return self.env['meli.util'].get_new_instance(company)

    @api.model
    def meli_simulate_order(self, bundle, config=None, check_user=True):
        """Importa la venta del bundle en modo simulación. Devuelve un dict con el resultado.

        Rehúsa (UserError/AccessError): interruptor apagado en la compañía, usuario que no es
        administrador (check_user), bundle inválido, u order_id de una orden REAL ya importada."""
        if check_user and not self.env.user.has_group('base.group_system'):
            raise AccessError(_("Sólo un administrador puede simular ventas de Mercado Libre."))
        company = meli_sim_config_company(config, self.env)
        csudo = company.sudo()
        if not csudo.meli_simulation_enabled:
            raise UserError(_("La simulación de ventas de Mercado Libre está apagada en la compañía %s.") % company.name)
        try:
            bundle = meli_sim_parse_bundle(bundle)
        except ValueError as e:
            raise UserError(_("Bundle de simulación inválido: %s") % e)
        oid = str(bundle['order']['id'])
        Orders = self.env['mercadolibre.orders']
        existing = Orders.search([('order_id', '=', oid)], limit=1)
        if existing and not existing.meli_simulated:
            raise UserError(_("La orden %s ya existe en Odoo como venta REAL: no se simula encima.") % oid)
        if not config:
            config = company

        real = None
        if csudo.meli_simulation_fallback_real_reads:
            try:
                real = self._meli_sim_real_client(config, company)
            except Exception as e:
                _logger.warning("meli simulacion: sin cliente real para lecturas de respaldo: %s", e)
        seller_id = ('mercadolibre_seller_id' in company._fields and csudo.mercadolibre_seller_id) or None
        client = MeliSimClient(bundle, seller_id=seller_id, real=real, fallback_real_reads=bool(real))

        res = None
        try:
            with meli_sim_activate(client, self.env.cr.dbname):
                res = Orders.orders_update_order_json({'id': existing.id or False, 'order_json': bundle['order']},
                                                      meli=client, config=config)
        except (UserError, AccessError):
            raise
        except Exception as e:
            _logger.warning("meli simulacion: el import de la orden %s falló", oid, exc_info=True)
            raise UserError(_("El import de la venta simulada %s falló: %s: %s") % (oid, type(e).__name__, e))

        morder = Orders.search([('order_id', '=', oid)], limit=1)
        sale = morder.sale_order if morder else self.env['sale.order']
        if not sale:
            sale = self.env['sale.order'].search([('meli_order_id', 'in', [oid, str(bundle['order'].get('pack_id') or oid)])], limit=1)
        summary = client.summary()
        error = isinstance(res, dict) and res.get('error') or False
        log = json.dumps({'bundle_meta': bundle.get('meta') or {}, 'result_error': str(error) if error else None,
                          **summary}, ensure_ascii=False, indent=1, default=str)
        if morder:
            morder.sudo().write({'meli_simulated': True, 'meli_sim_bundle': json.dumps(bundle, ensure_ascii=False),
                                 'meli_sim_log': log})
            if not existing:
                morder.message_post(body=_("Venta SIMULADA: importada desde un JSON de simulación, no existe en "
                                           "Mercado Libre. Ninguna escritura sale a ML desde esta orden."))
        if sale:
            sale.sudo().write({'meli_simulated': True})
            if not existing:
                sale.message_post(body=_("Venta SIMULADA de Mercado Libre (orden %s): no existe en ML.") % oid)
        _logger.info("meli simulacion: orden %s -> mercadolibre.orders %s / sale.order %s; GET %s, faltantes %s %s, "
                     "bloqueadas %s %s", oid, morder.id, sale.id, len(summary['calls']), len(summary['missing']),
                     summary['missing'][:10], len(summary['blocked']), summary['blocked'][:10])
        return {
            'ok': bool(morder) and not error,
            'order_id': oid,
            'resync': bool(existing),
            'meli_order': morder.id or False,
            'sale_order': sale.id or False,
            'sale_order_name': sale.name or False,
            'error': str(error) if error else False,
            **summary,
        }

    def _meli_sim_resync(self, config=None):
        """Re-sync de una orden simulada: SIEMPRE desde su bundle guardado, nunca contra ML."""
        for order in self.filtered('meli_simulated'):
            company = order.company_id or self.env.company if 'company_id' in order._fields else self.env.company
            if not company.sudo().meli_simulation_enabled:
                _logger.info("meli simulacion: re-sync de %s omitido (simulación apagada en la compañía)", order.order_id)
                continue
            bundle = order.sudo().meli_sim_bundle
            if not bundle:
                continue
            order.meli_simulate_order(bundle, config=config or order._meli_sim_resync_config(), check_user=False)
        return {}

    def _meli_sim_resync_config(self):
        self.ensure_one()
        return ('company_id' in self._fields and self.company_id) or self.env.company

    def orders_update_order(self, context=None, meli=None, config=None):
        sims = self.filtered('meli_simulated')
        if sims:
            sims._meli_sim_resync(config=None)
        rest = self - sims
        if rest or not sims:
            return super(MercadoLibreOrdersMeliSim, rest).orders_update_order(context=context, meli=meli, config=config)
        return {}

    def update_order_status(self, meli=None, config=None):
        rest = self.filtered(lambda o: not o.meli_simulated)
        if not rest:
            return {}
        return super(MercadoLibreOrdersMeliSim, rest).update_order_status(meli=meli, config=config)


class MercadoLibreOrdersSimulate(models.TransientModel):
    _name = 'mercadolibre.orders.simulate'
    _description = 'Simular venta de Mercado Libre (demo/test)'

    company_id = fields.Many2one('res.company', string="Compañía", required=True,
                                 default=lambda self: self.env.company)
    bundle_file = fields.Binary(string="Archivo JSON")
    bundle_filename = fields.Char(string="Nombre del archivo")
    bundle_text = fields.Text(string="JSON de la venta",
                              help='{"order": {...}, "routes": {"/shipments/<id>": {...}}, "meta": {...}} '
                                   'o directamente el JSON de /orders/<id>.')
    state = fields.Selection([('draft', 'Cargar'), ('done', 'Resultado')], default='draft')
    result_text = fields.Text(string="Resultado", readonly=True)
    sale_order_id = fields.Many2one('sale.order', string="Venta", readonly=True)
    meli_order_id = fields.Many2one('mercadolibre.orders', string="Orden ML", readonly=True)

    @api.model
    def meli_sim_open_action(self, company=None, extra_ctx=None):
        ctx = dict(self.env.context, default_company_id=(company or self.env.company).id, **(extra_ctx or {}))
        return {
            'type': 'ir.actions.act_window', 'name': _("Simular venta de Mercado Libre"),
            'res_model': self._name, 'view_mode': 'form', 'target': 'new', 'context': ctx,
        }

    def _meli_sim_bundle(self):
        self.ensure_one()
        if self.bundle_file:
            return base64.b64decode(self.bundle_file)
        if self.bundle_text and self.bundle_text.strip():
            return self.bundle_text
        raise UserError(_("Pegá el JSON de la venta o subí el archivo."))

    def _meli_sim_config(self):
        self.ensure_one()
        return self.company_id

    def action_simulate(self):
        self.ensure_one()
        res = self.env['mercadolibre.orders'].meli_simulate_order(self._meli_sim_bundle(), config=self._meli_sim_config())
        lines = [
            _("Orden %s %s.") % (res['order_id'], _("re-sincronizada") if res['resync'] else _("importada como SIMULADA")),
            _("Venta: %s") % (res['sale_order_name'] or '-'),
            _("Consultas servidas desde el JSON: %s") % len(res['calls']),
            _("Escrituras bloqueadas (no salieron a ML): %s") % (', '.join(res['blocked']) or '0'),
            _("Consultas que el JSON no trae: %s") % (', '.join(res['missing']) or '0'),
        ]
        if res.get('error'):
            lines.insert(1, _("Error del import: %s") % res['error'])
        self.write({'state': 'done', 'result_text': '\n'.join(lines),
                    'sale_order_id': res['sale_order'], 'meli_order_id': res['meli_order']})
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
                'view_mode': 'form', 'target': 'new', 'name': _("Simular venta de Mercado Libre")}

    def action_open_sale(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'sale.order', 'res_id': self.sale_order_id.id,
                'view_mode': 'form', 'target': 'current'}
