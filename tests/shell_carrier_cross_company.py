# Test #529 (carrier de envio de OTRA compania) — `odoo shell -d <db_de_prueba> < este_archivo`.
# Bloquea la red y hace ROLLBACK. NO correr contra produccion.
import requests, sys
requests.Session.request = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("RED BLOQUEADA"))
R = []
def check(n, c):
    R.append((n, bool(c))); print(("OK   " if c else "FAIL ") + n)
class _Resp:
    status_code = 200
    def json(self): return {}
class _M:
    access_token = 'x'
    def need_login(self, *a, **k): return False
    def get(self, *a, **k): return _Resp()
    post = put = delete = get
DUMMY = _M()
def fill(model, vals):
    M = env[model]
    for fn, f in M._fields.items():
        if f.required and fn not in vals and f.store and not f.default and not f.compute and not f.related:
            if f.type == 'many2one':
                vals[fn] = env[f.comodel_name].search([], limit=1).id
            elif f.type in ('char', 'text'):
                vals[fn] = 'banco'
            elif f.type == 'selection':
                vals[fn] = f.get_values(env)[0]
    return M.create(vals)

A = env.company
B = env['res.company'].create({'name': 'Cia B banco', 'currency_id': A.currency_id.id})
env.user.company_ids = [(4, B.id)]
NAME = 'Personalizado MFlex'
def mkprod(name, comp):
    return env['product.product'].create({'name': name, 'default_code': 'ENVIO-' + comp.name[:5], 'type': 'service', 'company_id': comp.id})
prodA = mkprod(NAME, A)
carA = env['delivery.carrier'].create({'name': NAME, 'company_id': A.id, 'product_id': prodA.id})
partner = env['res.partner'].create({'name': 'Comprador banco'})

def run(comp, label):
    """Venta de `comp` con envio Flex (self_service) -> carrier resuelto + mensajes."""
    sp = env.cr.savepoint()
    so = env['sale.order'].with_company(comp).create({'partner_id': partner.id, 'company_id': comp.id})
    order = fill('mercadolibre.orders', {'order_id': 'T' + label, 'name': 'T' + label})
    shp = fill('mercadolibre.shipment', {'sale_order': so.id, 'logistic_type': 'self_service', 'mode': 'me2', 'tracking_method': False, 'name': 'S' + label})
    err = None
    seen = {'car': None, 'line': 0}
    def _local(frame, event, arg):
        c = frame.f_locals.get('ship_carrier_id')
        if c is not None and hasattr(c, '_name'):
            seen['car'] = c
        seen['line'] = frame.f_lineno
        return _local
    def _glob(frame, event, arg):
        if frame.f_code.co_name == '_update_sale_order_shipping_info':
            return _local
        return None
    sys.settrace(_glob)
    try:
        shp.with_company(comp)._update_sale_order_shipping_info(order, meli=DUMMY, config=comp)
    except Exception as e:
        err = repr(e)[:160]
    finally:
        sys.settrace(None)
    car = seen['car'] or env['delivery.carrier']
    bodies = ' | '.join(m.body or '' for m in so.message_ids)
    out = dict(car=car, car_comp=car.company_id, ok_msg='Companias Coinciden OK' in bodies,
               bad_msg='Companias no coinciden' in bodies, err=err, last_line=seen['line'], so_carrier=so.carrier_id, so_comp=so.company_id)
    sp.rollback()
    print(label, {k: (v.ids if hasattr(v, 'ids') else v) for k, v in out.items()})
    return out

# T1 (caso Kindon): carrier homonimo SOLO en la cia A, venta en la cia B
r = run(B, 'T1')
check('T1 venta cia B NO toma el carrier de la cia A', r['car'] and r['car'] != carA)
check('T1 carrier resultante es de la cia B o sin compania', r['car'] and r['car_comp'] in (B, env['res.company']))
check('T1 "Coinciden OK" solo si de verdad coinciden', r['ok_msg'] == (not r['bad_msg']))
# T2: carrier homonimo SIN compania disponible -> lo usa (antes de crear uno)
carF = env['delivery.carrier'].create({'name': NAME, 'company_id': False, 'product_id': env['product.product'].create({'name': NAME, 'default_code': 'ENVIO-F', 'type': 'service', 'company_id': False}).id})
r = run(B, 'T2')
check('T2 venta cia B usa el carrier sin compania', r['car'] == carF)
carF.unlink()
# T3 control: venta en la cia A sigue tomando el carrier de A
r = run(A, 'T3')
check('T3 control cia A toma su carrier (sin cambio)', r['car'] == carA)
check('T3 control cia A postea "Coinciden OK"', r['ok_msg'] and not r['bad_msg'])
# T4: mapeo mal configurado (cia B -> carrier de A): no se dice OK, se avisa el desajuste
env['meli_oerp.carrier.mapping'].create({'meli_name': NAME, 'company_id': B.id, 'carrier_id': carA.id})
r = run(B, 'T4')
check('T4 mapeo cruzado: NO postea "Coinciden OK"', not r['ok_msg'])
check('T4 mapeo cruzado: postea "Companias no coinciden"', r['bad_msg'])

env.cr.rollback()
print('TOTAL', len(R), 'FAIL', len([1 for _n, ok in R if not ok]), [n for n, ok in R if not ok])
