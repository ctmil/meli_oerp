# -*- coding: utf-8 -*-
##############################################################################
# 26.332 (caso-K01 cliente B, ticket id caso-K06 / portal #caso-K05) -- CAMBIOS de producto de MercadoLibre.
#
# COMO LO MODELA ML (medido el 28-oct-2026 sobre las 10 ordenes `change` de una cuenta MLM):
#   - El cambio cuelga de un reclamo (mediations/returns) del comprador:
#       GET /post-purchase/v1/claims/{id}/changes -> type replace|change, new_orders_ids,
#       new_orders_shipments, return.id, status (change_return_delivered | change_expired | ...)
#   - ML crea una ORDEN NUEVA (tag `change`, pack y shipment nuevos, mismo precio) + un return del
#     original (GET /post-purchase/v2/claims/{id}/returns).
#   - La orden nueva NO trae vinculo al original (related_orders=None, order_request.change=None):
#     se resuelve comprador -> claims/search?player_role=complainant&player_user_id=<buyer> -> /changes.
#   - PLATA: cambio exitoso => ML CANCELA y REEMBOLSA la original y la NUEVA queda paid (account_money,
#     mismo importe). Cambio vencido => la original sigue paid y la nueva se cancela. El comprador paga
#     UNA vez y ML deja UNA sola orden viva. Por eso la orden `change` se sigue importando como venta
#     normal (con precio): una venta $0 + original viva dejaria $0 facturado contra un cobro real
#     cuando ML cancela la original. Aca NO se toca ningun importe ni el camino de importacion.
#   - STOCK (lo que estaba roto): la unidad ORIGINAL vuelve (return `delivered` a `warehouse`) y nada la
#     reingresaba. Se procesa con `_meli_return_done_pickings` sobre la VENTA ORIGINAL, que ya respeta
#     FULL / meli_oerp.cancel_return_full, mercadolibre_return_mode y el guard de "ya devuelta".
#
# RED FUERA DE LA ESCRITURA (leccion caso-K07): fase 1 = solo GET, sin escribir nada (sin locks);
# fase 2 = escrituras cortas por orden, con savepoint. Idempotente: estado meli_change_state +
# mensajes once_key + guard de devolucion existente.
##############################################################################
import ast
import json
import logging
import re

from odoo import api, fields, models

from .versions import meli_message_post

_logger = logging.getLogger(__name__)

CHANGE_TAG = "change"
_TAG_RE = re.compile(r"""['"]change['"]""")
CHANGE_DELIVERED = ("change_return_delivered",)
RETURN_DELIVERED = ("delivered",)
RETURN_DEAD = ("expired", "cancelled", "canceled")


# ---------------------------------------------------------------------------
#  Funciones puras (testeadas con los JSON reales, sin Odoo)
# ---------------------------------------------------------------------------
def meli_change_has_tag(tags):
    """True si la orden tiene el tag `change` (NO `no_add_tag_change`, que traen todas).
    `tags` = lista (JSON de ML) o el Text guardado en mercadolibre.orders (repr de la lista)."""
    if not tags:
        return False
    if isinstance(tags, (list, tuple)):
        return CHANGE_TAG in tags
    tags = str(tags)
    try:
        val = ast.literal_eval(tags)
        if isinstance(val, (list, tuple)):
            return CHANGE_TAG in val
    except Exception:
        pass
    return bool(_TAG_RE.search(tags))


def _ids(rows):
    return {str(r.get("id")) for r in (rows or []) if isinstance(r, dict) and r.get("id")}


def meli_change_find_link(order_id, changes_by_claim):
    """{claim_id: json de /claims/{id}/changes} -> el cambio cuyo new_orders_ids contiene order_id.
    Devuelve dict(claim_id, orig_order_id, type, status, status_detail, return_id, raw) o None."""
    oid = str(order_id)
    for cid, cjson in (changes_by_claim or {}).items():
        rows = cjson.get("data") if isinstance(cjson, dict) else cjson
        for ch in (rows or []):
            if not isinstance(ch, dict) or oid not in _ids(ch.get("new_orders_ids")):
                continue
            ret = ch.get("return") or {}
            return {
                "claim_id": str(ch.get("claim_id") or cid),
                "orig_order_id": str(ch.get("resource_id") or ""),
                "type": ch.get("type") or "",
                "status": ch.get("status") or "",
                "status_detail": ch.get("status_detail") or "",
                "return_id": str(ret.get("id") or "") if isinstance(ret, dict) else "",
                "raw": ch,
            }
    return None


def meli_change_outcome(link):
    """'delivered' (el devuelto llego: reingresar) | 'closed' (vencido/cancelado) | 'pending'."""
    st = (link or {}).get("status") or ""
    if st in CHANGE_DELIVERED:
        return "delivered"
    if st.endswith("expired") or st.endswith("cancelled") or st.endswith("canceled"):
        return "closed"
    return "pending"


def meli_change_return_status(returns_json):
    """Estado del return de ML. None = no se pudo leer (429/error): NO es 'no entregado'."""
    if not isinstance(returns_json, dict) or returns_json.get("_http_error") or returns_json.get("error"):
        return None
    st = returns_json.get("status") or ""
    if st not in RETURN_DELIVERED:
        for sh in returns_json.get("shipments") or []:
            if isinstance(sh, dict) and sh.get("type") == "return" and sh.get("status") in RETURN_DELIVERED:
                return "delivered"
    return st or None


def meli_change_return_is_total(returns_json, orig_order_id, orig_items=None):
    """True si el return devuelve TODO lo de la orden original (no un cambio parcial de un carrito).
    `orig_items` = {item_id: qty} de la orden original (opcional, para validar contra lo vendido).
    None = no se puede saber (sin datos)."""
    if not isinstance(returns_json, dict) or not returns_json.get("orders"):
        return None
    oid = str(orig_order_id)
    rows = [r for r in returns_json["orders"] if isinstance(r, dict) and str(r.get("order_id")) == oid]
    if not rows:
        return None
    returned = {}
    for r in rows:
        try:
            tq, rq = float(r.get("total_quantity") or 0), float(r.get("return_quantity") or 0)
        except (TypeError, ValueError):
            return None
        if r.get("context_type") not in (None, "total") or rq < tq:
            return False
        returned[str(r.get("item_id"))] = returned.get(str(r.get("item_id")), 0.0) + rq
    if orig_items:
        for item, qty in orig_items.items():
            if returned.get(str(item), 0.0) < float(qty or 0):
                return False
    return True


# ---------------------------------------------------------------------------
#  Modelos
# ---------------------------------------------------------------------------
class SaleOrderMeliChange(models.Model):
    _inherit = "sale.order"

    meli_change_origin_sale_id = fields.Many2one(
        "sale.order", string="Cambio ML: venta original", index="btree_not_null", copy=False,
        help="Esta venta es el REEMPLAZO de un cambio de producto de MercadoLibre; la venta original "
             "es la de la unidad que el comprador devolvio.")
    meli_change_replacement_ids = fields.One2many(
        "sale.order", "meli_change_origin_sale_id", string="Cambio ML: ventas de reemplazo")


class MercadolibreOrdersChange(models.Model):
    _inherit = "mercadolibre.orders"

    meli_change_state = fields.Selection([
        ("pending", "Pendiente de vincular"),
        ("linked", "Vinculado (esperando la devolucion)"),
        ("done", "Devolucion procesada"),
        ("closed", "Cambio vencido / cancelado"),
    ], string="Cambio ML: estado", index=True, copy=False)
    meli_change_claim_id = fields.Char(string="Cambio ML: reclamo", copy=False)
    meli_change_origin_order_id = fields.Char(string="Cambio ML: orden original", index=True, copy=False)
    meli_change_origin_morder_id = fields.Many2one("mercadolibre.orders", string="Cambio ML: orden original (Odoo)",
                                                   copy=False, index="btree_not_null")
    meli_change_type = fields.Char(string="Cambio ML: tipo", copy=False)
    meli_change_status = fields.Char(string="Cambio ML: estado en ML", copy=False)
    meli_change_return_id = fields.Char(string="Cambio ML: devolucion", copy=False)
    meli_change_return_status = fields.Char(string="Cambio ML: estado de la devolucion", copy=False)
    meli_change_note = fields.Char(string="Cambio ML: nota", copy=False)

    # ------------------------------------------------------------- red --
    def _meli_change_meli(self):
        """Instancia ML de la orden (cuenta de conexion con meli_oerp_multiple; si no, la compania)."""
        self.ensure_one()
        company = self.company_id or self.env.company
        util = self.env["meli.util"]
        if "connection_account" in self._fields and self.connection_account:
            return util.get_new_instance(company, self.connection_account)
        return util.get_new_instance(company)

    @staticmethod
    def _meli_change_get(meli, path):
        """GET de solo lectura. Error/429 => dict con _http_error (nunca se lee como 'no')."""
        try:
            resp = meli.get(path, {"access_token": meli.access_token})
            code = getattr(resp, "status_code", 200) or 200
            data = resp.json() if resp is not None else None
            if code >= 400:
                return {"_http_error": code, "_body": str(data)[:300]}
            return data
        except Exception as e:  # red: se reintenta en la proxima corrida
            return {"_http_error": "exc", "_body": str(e)[:300]}

    def _meli_change_fetch(self, meli=None):
        """FASE 1 -- solo GET, NO escribe nada. Devuelve {morder.id: dict} para _meli_change_apply."""
        out = {}
        for mo in self:
            data = {"ok": False}
            out[mo.id] = data
            try:
                m = meli or mo._meli_change_meli()
                if not m or (hasattr(m, "need_login") and m.need_login()):
                    data["error"] = "sin login ML"
                    continue
                claim_ids = [mo.meli_change_claim_id] if mo.meli_change_claim_id else []
                if not claim_ids:
                    buyer = mo.buyer and mo.buyer.buyer_id
                    if not buyer:
                        data["error"] = "orden sin comprador"
                        continue
                    sj = self._meli_change_get(
                        m, "/post-purchase/v1/claims/search?player_role=complainant&player_user_id=%s" % buyer)
                    if not isinstance(sj, dict) or sj.get("_http_error"):
                        data["error"] = "claims/search: %s" % (sj or {}).get("_http_error")
                        continue
                    claim_ids = [str(c.get("id")) for c in (sj.get("data") or []) if c.get("id")]
                changes = {}
                for cid in claim_ids:
                    cj = self._meli_change_get(m, "/post-purchase/v1/claims/%s/changes" % cid)
                    if isinstance(cj, dict) and not cj.get("_http_error"):
                        changes[cid] = cj
                link = meli_change_find_link(mo.order_id, changes)
                data.update(ok=True, link=link)
                if link:
                    data["returns"] = self._meli_change_get(
                        m, "/post-purchase/v2/claims/%s/returns" % link["claim_id"])
            except Exception as e:
                data["error"] = str(e)[:300]
                _logger.warning("meli change fetch %s: %s", mo.order_id, e)
        return out

    # -------------------------------------------------------- escritura --
    def _meli_change_find_sale(self, morder, ml_order_id):
        SO = self.env["sale.order"]
        so = morder and morder.sale_order
        if not so and ml_order_id:
            so = SO.search([("meli_order_id", "=", str(ml_order_id))], limit=1)
        if not so and morder:
            so = SO.search([("meli_orders", "in", morder.ids)], limit=1)
        return so

    def _meli_change_return_moves(self, so):
        return self.env["stock.move"].search_count([
            ("origin_returned_move_id", "in", so.picking_ids.mapped("move_ids").ids),
            ("state", "!=", "cancel")])

    def _meli_change_apply(self, fetched):
        """FASE 2 -- escrituras cortas por orden (sin red). Idempotente."""
        done = 0
        for mo in self:
            data = fetched.get(mo.id) or {}
            try:
                with self.env.cr.savepoint():
                    if mo._meli_change_apply_one(data):
                        done += 1
            except Exception as e:
                _logger.error("meli change apply %s: %s", mo.order_id, e, exc_info=True)
        return done

    def _meli_change_apply_one(self, data):
        self.ensure_one()
        mo = self
        if not data.get("ok"):
            if data.get("error") and mo.meli_change_note != data["error"]:
                mo.meli_change_note = data["error"]
            return False
        link = data.get("link")
        if not link:
            mo.write({"meli_change_state": "pending",
                      "meli_change_note": "Sin reclamo con este cambio (se reintenta)."})
            return False
        config = mo._get_config()
        MO = self.env["mercadolibre.orders"]
        orig_mo = MO.search([("order_id", "=", link["orig_order_id"])], limit=1)
        orig_so = self._meli_change_find_sale(orig_mo, link["orig_order_id"])
        new_so = self._meli_change_find_sale(mo, mo.order_id)
        ret_json = data.get("returns")
        ret_status = meli_change_return_status(ret_json)
        outcome = meli_change_outcome(link)
        if outcome == "pending" and ret_status in RETURN_DELIVERED:
            outcome = "delivered"
        vals = {
            "meli_change_claim_id": link["claim_id"],
            "meli_change_origin_order_id": link["orig_order_id"],
            "meli_change_origin_morder_id": orig_mo.id or False,
            "meli_change_type": link["type"],
            "meli_change_status": link["status"],
            "meli_change_return_id": link["return_id"] or False,
            "meli_change_return_status": ret_status or mo.meli_change_return_status or False,
            "meli_change_note": False,
        }
        if new_so and orig_so and new_so != orig_so and new_so.meli_change_origin_sale_id != orig_so:
            new_so.meli_change_origin_sale_id = orig_so.id
        claim, ret = link["claim_id"], link["return_id"] or "-"
        if new_so:
            meli_message_post(new_so, (
                "Cambio de producto de MercadoLibre (reclamo %s, tipo %s): esta venta es el REEMPLAZO de %s "
                "(orden ML %s). Los importes no se modifican: ML reembolsa la original y cobra esta.") % (
                claim, link["type"] or "-", orig_so.name if orig_so else "una venta que no está en Odoo",
                link["orig_order_id"]), config=config, once_key="change-link-%s" % claim)
        if orig_so:
            meli_message_post(orig_so, (
                "Cambio de producto de MercadoLibre (reclamo %s): el comprador cambió el artículo. Reemplazo: %s "
                "(orden ML %s). Devolución ML %s.") % (
                claim, new_so.name if new_so else "orden ML aún no importada", mo.order_id, ret),
                config=config, once_key="change-link-%s" % claim)

        if outcome == "closed":
            vals["meli_change_state"] = "closed"
            for so in (orig_so | new_so):
                meli_message_post(so, (
                    "Cambio de producto ML (reclamo %s) VENCIDO/cancelado en ML (%s): la venta original sigue "
                    "vigente y la orden de reemplazo la cancela ML (se procesa como cualquier cancelación).") % (
                    claim, link["status"]), config=config, once_key="change-closed-%s" % claim)
            mo.write(vals)
            return True
        if outcome != "delivered":
            vals["meli_change_state"] = "linked"
            mo.write(vals)
            return True

        # --- la unidad original volvio: reingreso por la politica de devoluciones de la ORIGINAL ---
        vals["meli_change_state"] = "done"
        if not orig_so:
            vals["meli_change_note"] = "La venta original no está en Odoo: no hay salida que revertir."
            mo.write(vals)
            return True
        orig_items = {}
        for it in (orig_mo.order_items if orig_mo else []):
            item_id = it.order_item_id
            if item_id:
                orig_items[str(item_id)] = orig_items.get(str(item_id), 0.0) + (it.quantity or 0.0)
        total = meli_change_return_is_total(ret_json, link["orig_order_id"], orig_items or None)
        if total is None:
            # El return no se pudo leer (429) o no trae detalle: no decidir a ciegas, reintentar.
            vals["meli_change_state"] = "linked"
            vals["meli_change_note"] = "Devolución entregada pero sin detalle del return: se reintenta."
            mo.write(vals)
            return True
        ml_orders = orig_so._meli_sale_ml_orders() if hasattr(orig_so, "_meli_sale_ml_orders") else orig_mo
        if not total or len(ml_orders) > 1:
            meli_message_post(orig_so, (
                "Cambio de producto ML (reclamo %s): la devolución %s está ENTREGADA pero es PARCIAL o la venta es "
                "un carrito de varias órdenes. No se genera el reingreso automático: registrar la devolución "
                "a mano por el artículo devuelto.") % (claim, ret), config=config, once_key="change-partial-%s" % claim)
            mo.write(vals)
            return True
        before = self._meli_change_return_moves(orig_so)
        orig_so.with_context(meli_change_claim=claim)._meli_return_done_pickings(config=config)
        after = self._meli_change_return_moves(orig_so)
        if after > before:
            meli_message_post(orig_so, (
                "Cambio de producto ML (reclamo %s): devolución %s ENTREGADA a %s. Reingreso del artículo "
                "registrado según la configuración de devoluciones.") % (
                claim, ret, "MercadoLibre (FULL)" if orig_so.is_meli_order_fulfillment() else "su depósito"),
                config=config, once_key="change-return-%s" % claim)
        elif not before:
            meli_message_post(orig_so, (
                "Cambio de producto ML (reclamo %s): devolución %s ENTREGADA. No se registró reingreso "
                "(envío FULL sin 'meli_oerp.cancel_return_full', 'Devolución al cancelar' = ninguna, o sin "
                "salida validada). Ver el mensaje anterior de devoluciones.") % (claim, ret),
                config=config, once_key="change-noreturn-%s" % claim)
        mo.write(vals)
        return True

    # ---------------------------------------------------------- entrada --
    def _meli_change_candidates(self, limit=50):
        dom = [("tags", "ilike", "change"), "|", ("meli_change_state", "=", False),
               ("meli_change_state", "in", ("pending", "linked"))]
        cands = self.search(dom, order="id desc", limit=limit * 4)
        return cands.filtered(lambda o: meli_change_has_tag(o.tags))[:limit]

    def meli_change_sync(self, meli=None):
        """Vincula y procesa los cambios de `self` (o de los candidatos si self esta vacio).
        Fase 1 (red, sin escribir) y fase 2 (escritura corta). Devuelve cuantas ordenes avanzaron."""
        orders = self.filtered(lambda o: meli_change_has_tag(o.tags)) if self else self._meli_change_candidates()
        if not orders:
            return 0
        fetched = orders._meli_change_fetch(meli=meli)
        return orders._meli_change_apply(fetched)

    @api.model
    def cron_meli_change_sync(self, limit=50):
        n = self._meli_change_candidates(limit=limit).meli_change_sync()
        _logger.info("cron_meli_change_sync: %s cambios de producto procesados", n)
        return n
