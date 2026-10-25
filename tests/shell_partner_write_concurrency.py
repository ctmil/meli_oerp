# Prueba con Postgres REAL: dos imports CONCURRENTES sobre el MISMO contacto de facturacion (26.228).
# NO es un TestCase de Odoo (necesita dos transacciones reales que commitean). Se corre con
#   odoo-bin shell -c <conf> -d <db efimera con meli_oerp> < meli_oerp/tests/shell_partner_write_concurrency.py
# Crea UN contacto, lo usa y lo borra al final. Sin red.
#
# Escenario (como dos crones/imports a la vez): B toma su snapshot, A hace el "write del import" sobre el
# contacto y commitea, despues B hace el mismo write. En REPEATABLE READ (el nivel de Odoo), si B toca la
# fila que A modifico despues de su snapshot, Postgres aborta B con SerializationFailure y la venta de B
# no se crea en ese ciclo.
#   ANTES (write incondicional + UPDATE SQL incondicional): B cae aunque A no cambio NINGUN valor.
#   AHORA (_meli_partner_vals_changed + _meli_partner_fiscal_sql_fix): sin cambios no hay UPDATE ⇒ B pasa.
#   Y si el valor SI cambia, se sigue escribiendo (no se pierde la actualizacion).
# Esperado con el fix: RESUMEN 4 OK / 0 FAIL. Sin el fix (codigo anterior): el caso AHORA no corre (SKIP).
env = globals()["env"]  # lo inyecta `odoo shell`: declarado para el lint de Odoo (undefined-variable)
import psycopg2
from odoo import api, SUPERUSER_ID
from odoo.addons.meli_oerp.models import orders as mo

HAS_FIX = hasattr(mo, '_meli_partner_vals_changed') and hasattr(mo, '_meli_partner_fiscal_sql_fix')
reg = env.registry
mx = env.ref('base.mx', raise_if_not_found=False) or env['res.country'].search([], limit=1)
P = env['res.partner'].create({'name': 'Contacto de facturacion compartido (prueba)', 'vat': 'XAXX010101XYZ',
                               'street': 'Calle 1', 'city': 'Ciudad', 'zip': '01000', 'country_id': mx.id})
env.cr.commit()
VALS = {'street': 'Calle 1', 'city': 'Ciudad', 'zip': '01000', 'country_id': mx.id,
        'name': 'Contacto de facturacion compartido (prueba)'}
FIX_FIELDS, FIX_VALS = ['vat = %s'], ['XAXX010101XYZ']
OUT = []


def import_write(cr, nuevo, vals):
    e = api.Environment(cr, SUPERUSER_ID, {})
    p = e['res.partner'].browse(P.id)
    if nuevo:
        v = mo._meli_partner_vals_changed(p, dict(vals))
        if v:
            p.write(v)
        p.invalidate_recordset()            # flush, como en orders_update_order_json
        mo._meli_partner_fiscal_sql_fix(cr, p.id, FIX_FIELDS, FIX_VALS)
    else:                                   # lo que hacia el import antes de 26.228
        p.write(dict(vals))
        p.invalidate_recordset()
        cr.execute("UPDATE res_partner SET " + ", ".join(FIX_FIELDS) + " WHERE id = %s",  # pylint: disable=sql-injection
                   tuple(FIX_VALS + [p.id]))


def concurrentes(nuevo, vals_a, vals_b):
    a, b = reg.cursor(), reg.cursor()
    try:
        b.execute("SELECT id FROM res_partner WHERE id = %s", (P.id,))   # snapshot de B
        import_write(a, nuevo, vals_a)
        a.commit()
        try:
            import_write(b, nuevo, vals_b)
            b.commit()
            return 'OK'
        except psycopg2.errors.SerializationFailure:
            b.rollback()
            return 'SerializationFailure'
    finally:
        a.close()
        b.close()


def check(nombre, got, want):
    OUT.append(('OK' if got == want else 'FAIL', nombre, got, want))


check('ANTES: dos imports sin cambios sobre el mismo contacto (control: reproduce el choque)',
      concurrentes(False, VALS, VALS), 'SerializationFailure')
if HAS_FIX:
    check('AHORA: dos imports sin cambios sobre el mismo contacto', concurrentes(True, VALS, VALS), 'OK')
    env.cr.commit()        # snapshot nuevo para la sesion del shell (es otra transaccion RR)
    env.invalidate_all()
    w0 = env['res.partner'].browse(P.id).write_date
    env.cr.commit()
    concurrentes(True, VALS, VALS)
    env.cr.commit()
    env.invalidate_all()
    check('AHORA: sin cambios no se toca la fila (write_date igual)',
          env['res.partner'].browse(P.id).write_date == w0, True)
    # un valor que SI cambia se sigue escribiendo
    a = reg.cursor()
    try:
        import_write(a, True, dict(VALS, street='Calle 2'))
        a.commit()
    finally:
        a.close()
    env.cr.commit()
    env.invalidate_all()
    check('AHORA: un valor que cambia se escribe igual', env['res.partner'].browse(P.id).street, 'Calle 2')
else:
    OUT.append(('SKIP', 'AHORA: el codigo cargado no tiene el fix 26.228', '-', '-'))

env.cr.commit()
env.invalidate_all()
env['res.partner'].browse(P.id).unlink()
env.cr.commit()
for r in OUT:
    print('%-4s | %s | got=%s want=%s' % r)
print('RESUMEN %d OK / %d FAIL / %d SKIP' % (sum(r[0] == 'OK' for r in OUT), sum(r[0] == 'FAIL' for r in OUT),
                                           sum(r[0] == 'SKIP' for r in OUT)))
