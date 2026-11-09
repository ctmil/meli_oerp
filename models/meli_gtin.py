# -*- coding: utf-8 -*-
"""26.389 (deuda 515 Natural Dry, #442) -- match de producto por CODIGO DE BARRAS normalizado
GTIN y reintento de ordenes de ML que quedaron SIN items.

1. GTIN: ML guarda el GTIN con el ancho que cargo el vendedor. En 515 el SKU/GTIN de la
   publicacion es `07502300970043` (GTIN-14, cero de relleno) y en Odoo el producto tiene
   barcode `7502300970043` (EAN-13). Es EL MISMO codigo, pero toda busqueda era igualdad
   exacta y la linea de la venta quedaba sin producto (191 lineas medidas el 21-ago).
   Un GTIN-8/12/13/14 es un numero: los ceros a la izquierda son relleno. `meli_gtin_keys`
   devuelve las formas equivalentes y la busqueda vincula SOLO si hay exactamente UN
   producto (un barcode repetido nunca decide).
2. Reintento: una `mercadolibre.orders` que quedo sin `order_items` (importacion cortada a
   mitad, producto que no estaba, etc.) no la volvia a mirar nadie: el barrido del cron solo
   trae ordenes que NO existen en Odoo. `_meli_retry_orders_without_items` reprocesa unas
   pocas por corrida, las que menos intentos tienen primero, con un tope de intentos para
   que una orden que no se puede completar no ocupe la cola para siempre.
"""
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

from .gtin import meli_gtin_keys, meli_item_gtins  # noqa: F401


class ProductProductMeliGtin(models.Model):
    _inherit = "product.product"

    @api.model
    def _meli_search_by_barcode_gtin(self, codes, domain=None):
        """UN producto cuyo barcode es (una forma GTIN equivalente de) alguno de `codes`.

        Devuelve product.product de 1 registro, o vacio con 0 o con varios. Varios codigos
        (GTIN de una publicacion) cuentan juntos: si apuntan a productos distintos, no decide."""
        empty = self.env['product.product']
        if isinstance(codes, (str, int)):
            codes = [codes]
        keys = []
        for code in (codes or []):
            for k in meli_gtin_keys(code):
                if k not in keys:
                    keys.append(k)
        if not keys:
            return empty
        found = empty.search([('barcode', 'in', keys)] + list(domain or []), limit=3)
        if len(found) == 1:
            return found
        if len(found) > 1:
            _logger.warning("Barcode GTIN: %s productos para %s (%s) -> NO se vincula",
                            len(found), keys, found.mapped('default_code'))
        return empty


class MercadolibreOrdersItemsRetry(models.Model):
    _inherit = "mercadolibre.orders"

    meli_items_retry_count = fields.Integer(
        string="Reintentos (orden sin items)", default=0, copy=False,
        help="Cuantas veces el cron volvio a importar esta orden porque habia quedado sin items. "
             "Al llegar al tope deja de reintentarse sola; se puede actualizar a mano.")

    @api.model
    def _meli_orders_without_items_domain(self, account=None, company=None, max_retries=5):
        domain = [('order_items', '=', False),
                  ('meli_items_retry_count', '<', max_retries),
                  ('status', '!=', 'cancelled')]
        if account and 'connection_account' in self._fields:
            domain.append(('connection_account', '=', account.id))
        elif company and 'company_id' in self._fields:
            domain += ['|', ('company_id', '=', False), ('company_id', '=', company.id)]
        return domain

    @api.model
    def _meli_retry_orders_without_items(self, meli=None, config=None, account=None, limit=5,
                                         max_retries=5, commit=True):
        """Reimporta hasta `limit` ordenes sin items. Devuelve {'retried', 'completed'}.

        Mismo patron que el barrido de ordenes nuevas: commit por orden y, si una falla, rollback
        de SOLO lo suyo (lo anterior ya esta commiteado). El intento se suma igual: si no, la que
        falla quedaria primera en la cola en cada corrida. No se usa savepoint porque
        `orders_update_order` base hace su propio rollback al fallar y eso rompe un savepoint
        abierto. `commit=False` solo para tests (TransactionCase no admite commit/rollback)."""
        company = (config and 'company_id' in config._fields and config.company_id) or config or self.env.company
        if commit:
            self.env.cr.commit()
        orders = self.search(self._meli_orders_without_items_domain(account=account, company=company,
                                                                    max_retries=max_retries),
                             order='meli_items_retry_count asc, id asc', limit=limit)
        retried = completed = 0
        for oid in orders.ids:
            order = self.browse(oid)
            retried += 1
            try:
                order.orders_update_order(meli=meli, config=config)
            except Exception as e:
                if self.env.cr.closed:
                    raise
                _logger.error("Reintento orden sin items %s: %s", order.order_id, e)
                if commit:
                    self.env.cr.rollback()
            order = self.browse(oid)
            order.invalidate_recordset()
            order.sudo().write({'meli_items_retry_count': (order.meli_items_retry_count or 0) + 1})
            if order.order_items:
                completed += 1
                _logger.info("Reintento orden sin items %s: completada (%s items)", order.order_id, len(order.order_items))
            if commit:
                self.env.cr.commit()
        if retried:
            _logger.info("Reintento ordenes sin items: %s reintentadas, %s completadas", retried, completed)
        return {'retried': retried, 'completed': completed}
