# Prueba con Postgres REAL (#caso-K13): la MISMA orden de ML importada por dos procesos en paralelo.
# NO es un TestCase de Odoo (necesita dos transacciones reales que commitean). Se corre con
#   odoo-bin shell -c <conf> -d <db EFIMERA con meli_oerp> < meli_oerp/tests/shell_import_race_same_order.py
# Sin red (ML simulado). Deja datos de prueba en la base: usar SOLO una base descartable.
#
# Escenario medido en produccion (22-oct-2026, venta ML 2000644717164304): el barrido de
# `Cron Meli Orders` ya tenia su snapshot tomado cuando `Meli Process Order Notifications` importo y
# commiteo la orden; el barrido no la vio (REPEATABLE READ) y la importo de nuevo ⇒ DOS ventas.
#   B = barrido: abre su transaccion y toma snapshot.
#   A = notificacion: importa la orden y COMMITEA.
#   B importa la misma orden y commitea.
# Esperado SIN el fix: 2 sale.order / 2 mercadolibre.orders. CON el fix: 1 y 1 (B devuelve SKIP).
# Caso 2 (carrera solapada): A importa SIN commitear (tiene el lock), B intenta ⇒ CON el fix B saltea.
env = globals()["env"]  # lo inyecta `odoo shell`: declarado para el lint de Odoo (undefined-variable)
from unittest.mock import patch
import requests
from odoo import api, SUPERUSER_ID
from odoo.addons.meli_oerp.tests.test_import_cupon_linea import _FakeMeli, _order_json

reg = env.registry
company = env.company
pricelist = env['product.pricelist'].search([], limit=1) or env['product.pricelist'].create({'name': 'Lista ML'})
company.mercadolibre_pricelist = pricelist
# Como en produccion: SIN contacto fijo, cada import crea/busca el contacto del comprador (en la caso-K13
# quedo "Contacto principal creado" dos veces). Con un contacto fijo las dos transacciones escriben la
# misma fila y Postgres aborta la segunda: eso NO es lo que pasa en produccion.
if 'mercadolibre_contact_partner' in company._fields:
    company.mercadolibre_contact_partner = False
if 'mercadolibre_cron_get_orders_shipment_client' in company._fields:
    company.mercadolibre_cron_get_orders_shipment_client = True
if not env['product.product'].search([('meli_id', '=', 'MLM000TEST')], limit=1):
    env['product.product'].create({'name': 'Refaccion', 'taxes_id': [(5, 0, 0)], 'meli_id': 'MLM000TEST',
                                   'default_code': 'SKU000'})
# Como en produccion: el producto ya esta configurado (la 1.a importacion lo marca almacenable; si lo
# hace cada transaccion, chocan en product_template y no es el escenario real).
_prod = env['product.product'].search([('meli_id', '=', 'MLM000TEST')], limit=1)
if 'is_storable' in _prod._fields:
    _prod.is_storable = True
# meli_oerp_multiple de bases viejas (p.ej. 26.229) pide config = mercadolibre.configuration (con `accounts`).
CONFIG = ('mercadolibre.configuration', None)
if 'mercadolibre.configuration' in env and 'accounts' not in company._fields:
    _Conf = env['mercadolibre.configuration']
    _vals = {k: v for k, v in {'name': 'Prueba carrera K13', 'mercadolibre_pricelist': pricelist.id,
                                'mercadolibre_cron_get_orders_shipment_client': True,
                                'company_id': company.id}.items() if k in _Conf._fields}
    for _fn, _f in _Conf._fields.items():          # m2o obligatorios (almacen, etc.): el primero que haya
        if _f.required and _f.type == 'many2one' and _fn not in _vals:
            _vals[_fn] = env[_f.comodel_name].search([], limit=1).id
        elif _f.required and _f.type == 'selection' and _fn not in _vals:
            _vals[_fn] = _f._description_selection(env)[0][0]
    CONFIG = ('mercadolibre.configuration', _Conf.create(_vals).id)
env.cr.commit()
ROUTES = [('/items/', {'id': 'MLM000TEST'})]
OUT = []


def do_import(cr, oid, buyer=123001):
    e = api.Environment(cr, SUPERUSER_ID, {})
    oj = _order_json(oid=oid, unit=500.0, paid=500.0, coupon=0)
    oj['buyer']['id'] = buyer          # un comprador por caso: en prod cada venta trae el suyo
    with patch('odoo.addons.meli_oerp.models.orders.requests.get',
               side_effect=requests.exceptions.ConnectionError('sin red')):
        return e['mercadolibre.orders'].orders_update_order_json(
            {'id': False, 'order_json': oj},
            meli=_FakeMeli(ROUTES), config=(e[CONFIG[0]].browse(CONFIG[1]) if CONFIG[1] else e['res.company'].browse(company.id)))


def count(oid):
    with reg.cursor() as cr:
        cr.execute("SELECT count(*) FROM sale_order WHERE meli_order_id = %s", (str(oid),))
        so = cr.fetchone()[0]
        cr.execute("SELECT count(*) FROM mercadolibre_orders WHERE order_id = %s", (str(oid),))
        return so, cr.fetchone()[0]


def check(name, oid, expect_so):
    so, mo = count(oid)
    ok = (so == expect_so and mo == expect_so)
    OUT.append('%s %s: sale.order=%s mercadolibre.orders=%s (esperado %s)' % ('OK  ' if ok else 'FAIL', name, so, mo, expect_so))


# Caso 1: snapshot vencido (el mecanismo de produccion)
OID1 = 2000249442298414
crB = reg.cursor()
crB.execute("SELECT count(*) FROM mercadolibre_orders")   # B toma su snapshot (el barrido ya consulto antes)
with reg.cursor() as crA:
    rA = do_import(crA, OID1)                             # A importa y commitea al salir del with
try:
    rB = do_import(crB, OID1)
    crB.commit()
except Exception as ex:
    rB = 'EXC %s' % ex
    crB.rollback()
crB.close()
OUT.append('caso1 A=%s' % (str(rA)[:80],))
OUT.append('caso1 B=%s' % (str(rB)[:160],))
check('caso1 snapshot vencido', OID1, 1)

# Caso 2: carrera solapada (A tiene la orden a medio importar, sin commitear)
OID2 = 2000193764088544
crA = reg.cursor()
rA = do_import(crA, OID2, buyer=123002)                                 # A importo pero NO commiteo todavia
crB = reg.cursor()
crB.execute("SET LOCAL lock_timeout = '5s'")              # sin el fix B no espera nada; con el fix tampoco
try:
    rB = do_import(crB, OID2, buyer=123002)
    crB.commit()
except Exception as ex:                                   # sin fix: B puede quedar bloqueado por filas de A
    rB = 'EXC %s' % ex
    crB.rollback()
crB.close()
crA.commit(); crA.close()
OUT.append('caso2 B=%s' % (str(rB)[:160],))
check('caso2 carrera solapada', OID2, 1)

# Caso 3: la RED de seguridad sola (indice unico parcial de meli_oerp_multiple), con el lock apagado.
with reg.cursor() as _c:
    _c.execute("SELECT 1 FROM pg_indexes WHERE indexname = 'mercadolibre_orders_order_account_uniq_new'")
    HAS_INDEX = bool(_c.fetchone())
try:
    from odoo.addons.meli_oerp.models import orders as _mo_mod
    HAS_GUARD = hasattr(_mo_mod, '_meli_import_guard')
except Exception:
    HAS_GUARD = False
if HAS_INDEX and HAS_GUARD:
    OID3 = 2000569100331333
    with patch.object(_mo_mod, '_meli_import_guard', return_value=None):
        crB = reg.cursor()
        crB.execute("SELECT count(*) FROM mercadolibre_orders")
        with reg.cursor() as crA:
            do_import(crA, OID3, buyer=123003)
        try:
            rB = do_import(crB, OID3, buyer=123003)
            crB.rollback() if 'error' in str(rB) else crB.commit()
        except Exception as ex:
            rB = 'EXC %s' % ex
            crB.rollback()
        crB.close()
    OUT.append('caso3 B=%s' % (str(rB)[:160],))
    check('caso3 sin lock, solo indice unico', OID3, 1)
else:
    OUT.append('SKIP caso3: indice=%s guard=%s' % (HAS_INDEX, HAS_GUARD))

print('\n'.join(['RESUMEN #caso-K13 carrera misma orden:'] + OUT))
print('RESUMEN %d OK / %d FAIL' % (sum(1 for o in OUT if o.startswith('OK')), sum(1 for o in OUT if o.startswith('FAIL'))))
