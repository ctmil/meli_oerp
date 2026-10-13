# Prueba con Postgres REAL del filtro de motivos (26.221, #638). NO es un TestCase de Odoo: se corre con
#   odoo-bin shell -c <conf> -d <db efimera con meli_oerp> < meli_oerp/tests/shell_cancel_return_reasons.py
# Todo va en una transaccion que se revierte. Sin red (meli simulado). Esperado: RESUMEN 17 OK / 0 FAIL.
# 26.221 (T3LC #638) - filtro de motivos de la devolucion automatica. Corre en `odoo-bin shell`
# sobre Postgres REAL (db efimera t_motivos, suite 19.0 de las ramas sello-19.0). SIN red: el
# `meli` del resync es un doble que responde /orders/<id>; por_estado_ml con la foto simulada.
# Todo dentro de UNA transaccion que se revierte al final.
import json
from unittest.mock import patch
from odoo import fields
from odoo.addons.meli_oerp.models import cancel_decision as cd

E = env
co = E.company
OUT = []
ICP = E['ir.config_parameter'].sudo()
print("PARAM instalado:", repr(ICP.get_param(cd.CANCEL_RETURN_REASONS_PARAM)))
for f in ('mercadolibre_cancel_mode', 'mercadolibre_return_mode'):
    print("company.%s =" % f, f in co._fields and co[f])
co.mercadolibre_cancel_mode = 'legacy'
if 'mercadolibre_return_mode' in co._fields:
    co.mercadolibre_return_mode = 'done'

wh = E['stock.warehouse'].search([('company_id', '=', co.id)], limit=1)
stock_loc = wh.lot_stock_id
partner = E['res.partner'].create({'name': 'Comprador ML test'})
seq = [9100000]

def mk_so(code, tag):
    seq[0] += 1
    pv = {'name': 'Motivo %s' % tag, 'list_price': 100.0}
    if 'is_storable' in E['product.product']._fields:
        pv.update(type='consu', is_storable=True)
    else:
        pv.update(type='product')
    p = E['product.product'].create(pv)
    E['stock.quant']._update_available_quantity(p, stock_loc, 10.0)
    so = E['sale.order'].create({'partner_id': partner.id, 'meli_order_id': str(seq[0]),
                                 'order_line': [(0, 0, {'product_id': p.id, 'product_uom_qty': 2, 'price_unit': 100.0})]})
    so.action_confirm()
    out = so.picking_ids.filtered(lambda x: x.picking_type_code == 'outgoing')
    for m in out.move_ids:
        if 'quantity_done' in m._fields:      # 16.0
            m.quantity_done = m.product_uom_qty
        else:
            m.quantity = m.product_uom_qty
            m.picked = True
    out._action_done()
    so.meli_status = 'cancelled'
    so.meli_cancel_reason_code = code or ''
    return so, p, out

def state(so, p, out):
    E.flush_all(); E.invalidate_all()
    rets = E['stock.move'].search([('origin_returned_move_id', 'in', out.move_ids.ids), ('state', '!=', 'cancel')])
    return {'so': so.state, 'out': out.state, 'ret': sorted(set(rets.mapped('state'))),
            'qty': p.with_context(location=stock_loc.id).qty_available,
            'flag': so.meli_cancel_return_skipped,
            'chatter_skip': bool(so.message_ids.filtered(lambda m: 'meli-once:cancel-return-skip-' in (m.body or '')))}

def check(name, got, exp):
    ok = all(got[k] == v for k, v in exp.items())
    OUT.append((name, ok, got))
    print("%-4s %-58s %s" % ("OK" if ok else "FAIL", name, got))

RET = {'so': 'cancel', 'ret': ['done'], 'qty': 10.0, 'flag': False, 'chatter_skip': False}
NORET = {'so': 'cancel', 'ret': [], 'qty': 8.0, 'flag': True, 'chatter_skip': True}

sp = E.cr.savepoint(flush=False); sp.__enter__()
try:
    # --- 1. modo legacy, default del parametro, motivo de la foto (order_json) -------------
    for code in ('buyer_cancel_express', 'fraud'):
        so, p, out = mk_so(code, code)
        so.meli_cancel_with_detail("Orden cancelada por MercadoLibre. Motivo: %s" % code,
                                   order_json={'id': int(so.meli_order_id), 'cancel_detail': {'code': code}})
        check("legacy default %s -> devuelve" % code, state(so, p, out), RET)
    for code in ('pack_splitted', 'shipment_not_delivered', 'mediations', ''):
        so, p, out = mk_so(code, code or 'vacio')
        so.meli_cancel_with_detail("Orden cancelada por MercadoLibre.", order_json=None)
        check("legacy default %s -> NO devuelve, cancela, marca" % (code or '(sin motivo)'), state(so, p, out), NORET)
        if code == 'pack_splitted':
            keep = (so, p, out)
            # reproceso (confirm_ml de la proxima pasada): no duplica chatter ni cambia nada
            n = len(so.message_ids); max_id = max(so.message_ids.ids)
            so.meli_cancel_with_detail("Orden cancelada por MercadoLibre.")
            E.flush_all(); E.invalidate_all()
            new_msgs = so.message_ids.sorted('id')[n:] if False else so.message_ids.filtered(lambda m: m.id > max_id)
            print("  reproceso, mensajes nuevos:", [(m.body or '')[:90] for m in new_msgs])
            skip_new = new_msgs.filtered(lambda m: 'cancel-return-skip' in (m.body or '') or 'NO se devolvió' in (m.body or ''))
            check("legacy reproceso pack_splitted: sin aviso de skip duplicado", dict(state(so, p, out), skip_dup=len(skip_new)),
                  dict(NORET, skip_dup=0))
    # --- 2. escape: decision humana -> devuelve y apaga la marca ----------------------------
    so, p, out = keep
    so.with_context(meli_cancel_return_any_reason=True)._meli_cancel_goods_return()
    check("escape any_reason sobre pack_splitted marcado", state(so, p, out),
          {'so': 'cancel', 'ret': ['done'], 'qty': 10.0, 'flag': False})
    # --- 3. parametro '*' = comportamiento anterior -----------------------------------------
    ICP.set_param(cd.CANCEL_RETURN_REASONS_PARAM, '*')
    so, p, out = mk_so('pack_splitted', 'star')
    so.meli_cancel_with_detail("x")
    check("param '*' pack_splitted -> devuelve", state(so, p, out), RET)
    # --- 4. lista configurada distinta --------------------------------------------------------
    ICP.set_param(cd.CANCEL_RETURN_REASONS_PARAM, 'mediations')
    so, p, out = mk_so('mediations', 'cfg-med'); so.meli_cancel_with_detail("x")
    check("param 'mediations' mediations -> devuelve", state(so, p, out), RET)
    so, p, out = mk_so('fraud', 'cfg-fraud'); so.meli_cancel_with_detail("x")
    check("param 'mediations' fraud -> NO devuelve", state(so, p, out), NORET)
    ICP.set_param(cd.CANCEL_RETURN_REASONS_PARAM, 'buyer_cancel_express,fraud')
    # --- 5. return_mode none: no se marca nada (igual que antes) ------------------------------
    co.mercadolibre_return_mode = 'none'
    so, p, out = mk_so('pack_splitted', 'none'); so.meli_cancel_with_detail("x")
    check("return_mode none + pack_splitted -> sin marca", state(so, p, out),
          {'so': 'cancel', 'ret': [], 'qty': 8.0, 'flag': False, 'chatter_skip': False})
    co.mercadolibre_return_mode = 'done'
    # --- 6. EL CAMINO REAL DEL #638: orders_resync_status con meli simulado -------------------
    Orders = E['mercadolibre.orders']
    class Resp:
        def __init__(self, j): self._j = j
        def json(self): return self._j
    class FakeMeli:
        needlogin_state = False
        access_token = 'x'
        def __init__(self, codes): self.codes = codes; self.calls = []
        def get(self, path, params=None):
            self.calls.append(path)
            oid = path.rsplit('/', 1)[-1]
            if path.startswith('/orders/') and oid in self.codes:
                return Resp({'id': int(oid), 'status': 'cancelled', 'status_detail': None,
                             'cancel_detail': {'code': self.codes[oid], 'description': 'd', 'requested_by': 'buyer', 'date': '2026-10-12'}})
            return Resp({'error': 'not_found'})
    codes = {}; trio = {}; mo_ids = []
    for code in ('buyer_cancel_express', 'pack_splitted', 'shipment_not_delivered'):
        so, p, out = mk_so('', 'resync-' + code)
        so.meli_status = 'paid'
        mo = Orders.create({'order_id': so.meli_order_id, 'status': 'paid', 'sale_order': so.id,
                            'date_created': fields.Datetime.now()})
        so.meli_order = mo.id if 'meli_order' in so._fields else False
        codes[so.meli_order_id] = code; trio[code] = (so, p, out); mo_ids.append(mo.id)
    E.flush_all()
    others = Orders.search([('id', 'not in', mo_ids)])
    others.write({'status': 'cancelled'})  # que el barrido tome solo las 3 del test
    fm = FakeMeli(codes)
    with patch.object(type(Orders), '_meli_mark_status_checked', lambda self, ids: 0):
        res = Orders.orders_resync_status(meli=fm, config=co)
    print("resync:", res, "GETs:", len(fm.calls))
    check("resync #638 buyer_cancel_express -> devuelve", state(*trio['buyer_cancel_express']), RET)
    check("resync #638 pack_splitted -> NO devuelve, marca", state(*trio['pack_splitted']), NORET)
    check("resync #638 shipment_not_delivered -> NO devuelve, marca", state(*trio['shipment_not_delivered']), NORET)
    print("  motivo guardado:", {c: t[0].meli_cancel_reason_code for c, t in trio.items()})
    # --- 7. modo por_estado_ml (foto simulada: no enviado + reintegrado => GOODS_RETURN) -------
    co.mercadolibre_cancel_mode = 'por_estado_ml'
    SO = type(E['sale.order'])
    for code, exp in (('fraud', RET), ('pack_splitted', NORET)):
        so, p, out = mk_so(code, 'pem-' + code)
        oj = {'id': int(so.meli_order_id), 'status': 'cancelled', 'cancel_detail': {'code': code},
              'payments': [{'id': 1, 'status': 'refunded', 'transaction_amount': 200.0, 'total_paid_amount': 200.0,
                            'transaction_amount_refunded': 200.0}], 'shipping': {'id': 4000001}}
        ctx = cd.build_cancel_context([oj], {'id': 4000001, 'status': 'ready_to_ship', 'logistic_type': 'cross_docking',
                                              'status_history': {}}, '4000001')
        with patch.object(SO, '_meli_cancel_context', lambda self, **kw: ctx):
            r = so.meli_cancel_with_detail("x", order_json=oj)
        check("por_estado_ml %s (goods=return)" % code, state(so, p, out), exp)
finally:
    sp.__exit__(Exception, Exception("rollback"), None)
    E.cr.rollback()
print("RESUMEN: %d OK / %d FAIL" % (sum(1 for o in OUT if o[1]), sum(1 for o in OUT if not o[1])))
