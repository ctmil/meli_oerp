# -*- coding: utf-8 -*-
"""26.412 (un caso): qué pasa con el stock en Mercado Libre cuando ML cancela una venta.

POR QUÉ EXISTE. Cuando una venta se cancela, Mercado Libre REPONE SOLA la unidad en la
publicación. Odoo cancelaba la venta y no publicaba nada: la variación volvía a la venta con el
número que ML repuso, aunque no hubiera mercadería, hasta que el cron de stock volvía a pasar por
ese binding (con miles de bindings, días). Caso real del 16-nov-2026: una compradora canceló
(buyer_cancel_express) y la variante volvió a la venta con 1 unidad que no existía.

Config «Al cancelarse una venta en ML» (`mercadolibre_cancel_stock_mode`, compañía y cuenta):
  - 'republish' (default): después del commit, publicar el stock de Odoo de los productos de la venta.
  - 'hold': marcar cada variante «Stock retenido en ML» (`product.product.meli_stock_hold`) ⇒
    `_meli_available_quantity` da 0 en todo camino de publicación ⇒ ML queda en 0 para esa
    variación hasta que alguien apriete «Habilitar stock en ML». NUNCA se pausa la publicación
    (las otras variantes siguen a la venta).

Reglas que este archivo respeta:
  - NINGUNA llamada de red dentro de la transacción que procesa la orden (un incidente previo:
    alargarla produjo deadlocks). La publicación sale en UN callback post-commit por cursor, con
    cursor propio y tope de MELI_CANCEL_STOCK_POST_MAX productos; el resto queda encolado para el
    cron (`sale.order._meli_cancel_stock_enqueue`, lo implementa meli_oerp_multiple).
  - Sólo actúa en la TRANSICIÓN a cancelada (lo llama quien canceló, si quedó en 'cancel').
  - Ventas de más de MELI_CANCEL_HOLD_MAX_AGE_DAYS días no retienen (re-importes masivos).
"""
import logging
from datetime import timedelta

from odoo import fields, models

_logger = logging.getLogger(__name__)

MELI_CANCEL_STOCK_POST_MAX = 20
MELI_CANCEL_HOLD_MAX_AGE_DAYS = 30
_PENDING_ATTR = '_meli_cancel_stock_pending'


def _cr_on(cr, event, func):
    """Registra func para después del commit/rollback. Odoo 14+: cr.postcommit/postrollback;
    Odoo 13: cr.after('commit'|'rollback', func)."""
    callbacks = getattr(cr, 'post' + event, None)
    if callbacks is not None and hasattr(callbacks, 'add'):
        callbacks.add(func)
        return True
    after = getattr(cr, 'after', None)
    if after:
        after(event, func)
        return True
    return False


def meli_stock_post_now(registry, uid, context, product_ids, limit=MELI_CANCEL_STOCK_POST_MAX):
    """Publica el stock de product_ids con un cursor PROPIO (ya fuera de la transacción de la orden).
    Cada producto en su savepoint: uno que falla no voltea a los demás. Devuelve los ids publicados."""
    from odoo import api
    done = []
    with registry.cursor() as cr:
        env = api.Environment(cr, uid, dict(context or {}, meli_cancel_stock_post=True))
        products = env['product.product'].browse(list(product_ids)).exists()
        for product in products:
            if len(done) >= limit:
                _logger.warning("meli_cancel_stock: tope %s alcanzado, %s producto(s) quedan para el cron",
                                limit, len(products) - len(done))
                break
            try:
                with cr.savepoint():
                    product.product_post_stock()
                done.append(product.id)
                _logger.info("meli_cancel_stock: stock publicado tras cancelación ML: %s (retenido=%s)",
                             product.display_name, product.meli_stock_hold)
            except Exception as e:
                _logger.error("meli_cancel_stock: no se pudo publicar el stock de %s: %s",
                              product.display_name, e, exc_info=True)
    return done


def meli_stock_post_after_commit(env, product_ids):
    """Acumula product_ids y registra UN callback post-commit por cursor (se re-arma tras cada
    commit/rollback). Si el cursor no soporta callbacks, no publica: queda para el cron."""
    cr = env.cr
    pending = getattr(cr, _PENDING_ATTR, None)
    if pending is None:
        pending = []
        try:
            setattr(cr, _PENDING_ATTR, pending)
        except Exception:
            _logger.warning("meli_cancel_stock: el cursor no admite callbacks; queda para el cron")
            return False
        registry, uid, context = env.registry, env.uid, dict(env.context)

        def _reset():
            try:
                setattr(cr, _PENDING_ATTR, None)
            except Exception:
                pass

        def _run():
            ids = list(dict.fromkeys(pending))
            _reset()
            if not ids:
                return
            try:
                meli_stock_post_now(registry, uid, context, ids)
            except Exception as e:
                _logger.error("meli_cancel_stock: falló la publicación post-commit: %s", e, exc_info=True)

        if not _cr_on(cr, 'commit', _run):
            _reset()
            return False
        _cr_on(cr, 'rollback', _reset)
    pending.extend(product_ids)
    return True


class SaleOrderMeliCancelStock(models.Model):
    _inherit = "sale.order"

    def _meli_cancel_stock_mode(self, config=None):
        """'republish' (default) | 'hold'. Con cuenta de conexión manda la config de la CUENTA."""
        cfg = config or self.company_id or self.env.user.company_id
        mode = False
        if cfg and 'mercadolibre_cancel_stock_mode' in cfg._fields:
            mode = cfg.mercadolibre_cancel_stock_mode
        return mode if mode in ('republish', 'hold') else 'republish'

    def _meli_cancel_stock_products(self):
        products = self.env['product.product']
        for line in self.order_line:
            product = line.product_id
            if not product or product.type == 'service' or getattr(line, 'is_delivery', False):
                continue
            products |= product
        return products

    def _meli_cancel_is_recent(self):
        ref = ('meli_date_closed' in self._fields and self.meli_date_closed) or self.date_order
        if not ref:
            return True
        return ref >= fields.Datetime.now() - timedelta(days=MELI_CANCEL_HOLD_MAX_AGE_DAYS)

    def _meli_cancel_is_full(self):
        lt = 'meli_shipment_logistic_type' in self._fields and self.meli_shipment_logistic_type
        return bool(lt and 'fulfillment' in lt)

    def _meli_cancel_stock_enqueue(self, products):
        """Gancho: dejar los productos primeros en la cola del cron de stock (meli_oerp_multiple)."""
        return True

    def _meli_cancel_stock_followup(self, config=None):
        """Llamar DESPUÉS de cancelar una venta ML (sólo si quedó en 'cancel'). Sin red acá adentro."""
        for order in self:
            try:
                if order.state != 'cancel' or not order.meli_order_id or order._meli_cancel_is_full():
                    continue
                products = order._meli_cancel_stock_products()
                if not products:
                    continue
                mode = order._meli_cancel_stock_mode(config=config)
                with order.env.cr.savepoint():
                    if mode == 'hold' and order._meli_cancel_is_recent():
                        note = "venta ML %s (%s) cancelada" % (order.meli_order_id, order.name)
                        products._meli_stock_hold_set(note=note)
                        order.message_post(body="Venta cancelada en Mercado Libre: stock retenido en ML "
                                                "(se publica 0) para %s. Para volver a ofrecerlo: "
                                                "'Habilitar stock en ML' en el producto."
                                                % ", ".join(products.mapped('display_name')))
                    order._meli_cancel_stock_enqueue(products)
                meli_stock_post_after_commit(order.env, products.ids)
            except Exception as e:
                _logger.error("meli_cancel_stock: followup de %s falló: %s", order.name, e, exc_info=True)
        return True
