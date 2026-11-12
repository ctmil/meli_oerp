# Prueba con Postgres REAL (un caso): sufijo del nombre de venta (tracking | shipping_id) y carrito.
# NO es un TestCase (no se importa en tests/__init__). Se corre con
#   odoo-bin shell -c <conf> -d <db EFIMERA con meli_oerp_multiple> < meli_oerp/tests/shell_so_name_shipping_id.py
# Sin red (ML simulado). Hace rollback al final. Esperado con el fix: 18 OK / 0 FAIL; sin el fix el campo no existe
# (SKIP shipping_id) y el carrito en modo tracking nace sin sufijo (1 FAIL).
# camino REAL: orders_update_order_json -> fetch_shipment (ML simulado, sin red). Base descartable.
# Por modo (off / tracking / shipping_id): venta simple (alta + re-sync con tracking cambiado) y carrito de 2 ordenes.
import requests
from unittest.mock import patch
from odoo.addons.meli_oerp.tests.test_import_cupon_linea import _order_json, _Resp

OUT = []
def rec(ok, msg): OUT.append(('OK   ' if ok else 'FAIL ') + msg)
def info(msg): OUT.append('INFO ' + msg)

company = env.company
pricelist = env['product.pricelist'].search([], limit=1) or env['product.pricelist'].create({'name': 'Lista ML'})
company.mercadolibre_pricelist = pricelist
if not env['product.product'].search([('meli_id', '=', 'MLM000TEST')], limit=1):
    env['product.product'].create({'name': 'Refaccion', 'taxes_id': [(5, 0, 0)], 'meli_id': 'MLM000TEST', 'default_code': 'SKU000'})
_Conf = env['mercadolibre.configuration']
vals = {k: v for k, v in {'name': 'Banco sufijo', 'mercadolibre_pricelist': pricelist.id,
        'mercadolibre_cron_get_orders_shipment_client': True, 'company_id': company.id}.items() if k in _Conf._fields}
for fn, f in _Conf._fields.items():
    if f.required and f.type == 'many2one' and fn not in vals:
        vals[fn] = env[f.comodel_name].search([], limit=1).id
    elif f.required and f.type == 'selection' and fn not in vals:
        vals[fn] = f._description_selection(env)[0][0]
CONF = _Conf.create(vals)
HAS_LABEL = 'mercadolibre_so_name_label' in CONF._fields
info('campo mercadolibre_so_name_label presente: %s' % HAS_LABEL)
if HAS_LABEL:
    rec(CONF.mercadolibre_so_name_label == 'tracking', 'default del modo = tracking (%s)' % CONF.mercadolibre_so_name_label)

class Meli:
    access_token = 'TEST'
    def __init__(self): self.routes = []
    def get(self, path, params=None):
        for prefix, data in self.routes:
            if path.startswith(prefix): return _Resp(data)
        return _Resp({})
    def need_login(self): return False

def addr():
    return {'id': 1, 'receiver_phone': '1100000000', 'receiver_name': 'Comprador Test', 'address_line': 'Calle 123',
            'comment': '', 'street_name': 'Calle', 'street_number': '123', 'zip_code': '1000',
            'city': {'id': 'C1', 'name': 'CABA'}, 'state': {'id': 'AR-C', 'name': 'Capital Federal'},
            'country': {'id': 'AR', 'name': 'Argentina'}, 'latitude': 0, 'longitude': 0}

def ship_json(sid, oid, tracking, logistic='cross_docking', receiver=123001):
    return {'id': sid, 'logistic_type': logistic, 'order_cost': 0, 'base_cost': 0,
            'date_created': '2026-11-12T10:00:00.000-03:00', 'last_updated': '2026-11-12T10:00:00.000-03:00',
            'site_id': 'MLA', 'order_id': oid, 'mode': 'me2', 'status': 'ready_to_ship', 'substatus': 'printed',
            'shipping_option': {'name': 'Normal', 'cost': 0, 'list_cost': 0},
            'receiver_address': addr(), 'sender_address': addr(), 'status_history': {},
            'tracking_number': tracking, 'tracking_method': 'MEL Distribution', 'comments': '',
            'date_first_printed': '', 'receiver_id': receiver, 'sender_id': 123999}

CREATED = []
SO = env.registry['sale.order']
_orig_create = SO.create
def _spy_create(self, vals_list):
    for v in (vals_list if isinstance(vals_list, list) else [vals_list]):
        if v.get('name'): CREATED.append(v['name'])
    return _orig_create(self, vals_list)

def imp(meli, oj):
    with patch('odoo.addons.meli_oerp.models.orders.requests.get', side_effect=requests.exceptions.ConnectionError('sin red')), \
         patch.object(SO, 'create', _spy_create):
        return env['mercadolibre.orders'].orders_update_order_json({'id': False, 'order_json': oj}, meli=meli, config=CONF)

def set_mode(mode):
    CONF.mercadolibre_so_name_tracking = (mode != 'off')
    if HAS_LABEL and mode != 'off':
        CONF.mercadolibre_so_name_label = mode
    return HAS_LABEL or mode != 'shipping_id'

MODES = ['off', 'tracking', 'shipping_id']
for i, mode in enumerate(MODES):
    if not set_mode(mode):
        OUT.append('SKIP modo %s (sin campo: control)' % mode); continue
    # --- venta simple
    oid = 2000000000831100 + i; sid = 45000831100 + i
    trk1 = 'MEL%sFMXDF01' % sid; trk2 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[:20] + '%06d' % i
    meli = Meli()
    oj = _order_json(oid=oid, unit=500.0, paid=500.0, coupon=0); oj['buyer']['id'] = 123100 + i
    oj['shipping'] = {'id': sid}
    meli.routes = [('/shipments/%s/items' % sid, [{'order_id': str(oid)}]), ('/shipments/%s/' % sid, {}),
                   ('/shipments/%s' % sid, ship_json(sid, oid, trk1, receiver=123100 + i))]
    del CREATED[:]
    r = imp(meli, oj)
    so = env['sale.order'].search([('meli_order_id', '=', str(oid))], limit=1)
    info('[%s] simple alta: creada como %r, queda %r (ret %s)' % (mode, CREATED[:1], so.name, str(r)[:60]))
    exp = {'off': 'ML %s' % oid, 'tracking': 'ML %s | %s' % (oid, trk1), 'shipping_id': 'ML %s | %s' % (oid, sid)}[mode]
    rec(so.name == exp, '[%s] venta simple alta: %r == %r' % (mode, so.name, exp))
    # confirmar y re-sync con el tracking cambiado (colecta al despachar / Flex)
    try:
        so.action_confirm()
    except Exception as e:
        info('[%s] action_confirm: %s' % (mode, str(e)[:120]))
    origin1 = so.picking_ids[:1].origin
    meli.routes[-1] = ('/shipments/%s' % sid, ship_json(sid, oid, trk2, receiver=123100 + i))
    imp(meli, oj)
    so.invalidate_recordset(['name'])
    exp2 = {'off': 'ML %s' % oid, 'tracking': 'ML %s | %s' % (oid, trk2), 'shipping_id': 'ML %s | %s' % (oid, sid)}[mode]
    rec(so.name == exp2, '[%s] venta simple tras cambio de tracking: %r == %r (origin albaran %r)' % (mode, so.name, exp2, origin1))
    if mode == 'shipping_id':
        rec(origin1 == 'ML %s | %s' % (oid, sid), '[shipping_id] origin del albaran = etiqueta: %r' % origin1)
    # --- carrito (pack) de 2 ordenes
    pack = 2000015998831200 + i; sid2 = 45000831200 + i; trk = 'MEL%sFMXDF01' % sid2
    o1, o2 = 2000000000831201 + 10 * i, 2000000000831202 + 10 * i
    meli = Meli()
    meli.routes = [('/shipments/%s/items' % sid2, [{'order_id': str(o1)}, {'order_id': str(o2)}]),
                   ('/shipments/%s/' % sid2, {}), ('/shipments/%s' % sid2, ship_json(sid2, o1, trk, receiver=123200 + i))]
    del CREATED[:]
    for o in (o1, o2):
        oj = _order_json(oid=o, unit=300.0, paid=300.0, coupon=0); oj['buyer']['id'] = 123200 + i
        oj['shipping'] = {'id': sid2}; oj['pack_id'] = pack; oj['tags'] = ['paid', 'pack_order']
        r = imp(meli, oj)
    sos = env['sale.order'].search([('name', 'like', 'ML %s' % pack)])
    for mo in env['mercadolibre.orders'].search([('pack_id', '=', str(pack))]):
        info('[%s]   mo %s name=%r order_id=%r shipping_id=%r shipment=%s pack_order=%s' % (mode, mo.id, mo.name, mo.order_id, mo.shipping_id, mo.shipment.id, mo.pack_order))
    for sh in env['mercadolibre.shipment'].search([('shipping_id', '=', str(sid2))]):
        info('[%s]   ship %s pack_order=%s orders=%s sale_order=%s' % (mode, sh.id, sh.pack_order, sh.orders.ids, sh.sale_order.id))
    info('[%s]   ret %s' % (mode, str(r)[:200]))
    info('[%s] carrito: create con nombres %r; quedan %r' % (mode, CREATED, sos.mapped('name')))
    exp = {'off': 'ML %s' % pack, 'tracking': 'ML %s | %s' % (pack, trk), 'shipping_id': 'ML %s | %s' % (pack, sid2)}[mode]
    rec(len(sos) == 1 and sos.name == exp, '[%s] carrito final: %r == %r' % (mode, sos.mapped('name'), exp))
    rec(bool(CREATED) and CREATED[-1] == exp, '[%s] carrito NACE con %r (create: %r)' % (mode, exp, CREATED[-1:]))
    # re-sync del carrito (borrador) con el tracking cambiado
    trk3 = 'ZYXWVUTSRQPONMLKJIHGFE%04d' % i
    meli.routes[-1] = ('/shipments/%s' % sid2, ship_json(sid2, o1, trk3, receiver=123200 + i))
    oj = _order_json(oid=o1, unit=300.0, paid=300.0, coupon=0); oj['buyer']['id'] = 123200 + i
    oj['shipping'] = {'id': sid2}; oj['pack_id'] = pack; oj['tags'] = ['paid', 'pack_order']
    imp(meli, oj); sos.invalidate_recordset(['name'])
    exp3 = {'off': 'ML %s' % pack, 'tracking': 'ML %s | %s' % (pack, trk3), 'shipping_id': 'ML %s | %s' % (pack, sid2)}[mode]
    rec(sos.name == exp3, '[%s] carrito tras cambio de tracking: %r == %r' % (mode, sos.name, exp3))

# _get_meli_invoices (orders.py, invoice.origin = so.name): sigue buscando por el nombre vigente
inv_model = 'account.move'
so = env['sale.order'].search([('meli_order_id', '=', str(2000000000831102))], limit=1)
if so:
    rec(env[inv_model].search_count([('invoice_origin', '=', so.name)]) >= 0, '[shipping_id] busqueda por origin = nombre vigente %r sin error' % so.name)

env.cr.rollback()
print('\n'.join(OUT))
print('RESUMEN %d OK / %d FAIL' % (sum(o.startswith('OK') for o in OUT), sum(o.startswith('FAIL') for o in OUT)))
