# -*- coding: utf-8 -*-
"""26.27x (#caso-K13) -- una orden de ML se importa UNA vez aunque dos procesos la traigan a la vez.

Medido en produccion (Odoo 18): `Cron Meli Orders` (barrido "ordenes de las ultimas 24 h que no
estan en Odoo") y `Meli Process Order Notifications` importaban la MISMA orden en paralelo:
cada uno buscaba la orden, no la veia y la creaba ⇒ dos mercadolibre.orders, dos envios, contacto
doble y DOS ventas. El lock que ya existia era por NOTIFICACION, no por ORDEN, y el barrido no
pasaba por el.

Dos piezas, las dos necesarias:
1. **Lock por orden** (`pg_try_advisory_xact_lock` sobre pack_id y order_id): dos transacciones no
   importan la misma orden/carrito al mismo tiempo. Es *try*: si otro proceso la esta importando,
   esta pasada la saltea (el otro la deja hecha; si fallara, el barrido la retoma). NO se espera
   el lock: la importacion ya hace llamadas de red dentro de la transaccion y esperar alargaria
   las dos (incidente cliente D 26.131: latencia ⇒ deadlocks ⇒ ventas sin confirmar).
2. **Snapshot vencido**: Odoo trabaja en REPEATABLE READ. Si el otro proceso COMMITEO la orden
   despues de que esta transaccion tomo su snapshot, el lock ya esta libre pero el `search` sigue
   sin verla. Se compara contra un cursor nuevo: si hay filas commiteadas que esta transaccion no
   ve, la orden ya la importo otro ⇒ se saltea (la proxima pasada la ve y la actualiza).
"""
import hashlib
import logging

_logger = logging.getLogger(__name__)

# Marca en el error devuelto: los que llaman lo tratan como SKIP, no como fallo.
PARALLEL_TAG = 'MELI_IMPORT_PARALLEL'


def _key64(key):
    digest = hashlib.sha1(('meli_order_import:%s' % key).encode('utf-8')).digest()
    return int.from_bytes(digest[:8], 'big', signed=True)


def _clean(values):
    return sorted({str(v) for v in (values or []) if v not in (None, False, '', 0, '0', 'None')})


def meli_import_try_lock(cr, keys):
    """True si esta transaccion tiene (o ya tenia: es re-entrante) el lock de TODAS las claves.

    Las claves son ids de ML (pack_id, order_id): son unicos en todo ML, asi que no hace falta la
    cuenta en la clave y dos caminos que reciben `config` distinto igual se excluyen entre si.
    El lock se libera solo al terminar la transaccion (commit o rollback).
    """
    for key in _clean(keys):
        cr.execute("SELECT pg_try_advisory_xact_lock(%s)", (_key64(key),))
        if not cr.fetchone()[0]:
            return False
    return True


def meli_import_stale(env, checks):
    """Filas commiteadas por OTRA transaccion despues de nuestro snapshot (invisibles para nosotros).

    checks: [(tabla, columna, [valores]), ...]. Devuelve un texto con lo encontrado, o None.
    Las filas que creo ESTA transaccion no cuentan: el cursor nuevo no las ve.
    """
    pending = [(t, c, _clean(v)) for t, c, v in checks]
    pending = [(t, c, v) for t, c, v in pending if v]
    if not pending:
        return None
    found = []
    with env.registry.cursor() as fresh:
        for table, column, values in pending:
            # table/column son literales de los llamadores (orders/shipment); los valores van como parámetro
            query = 'SELECT id FROM "%s" WHERE "%s" = ANY(%%s)' % (table, column)
            fresh.execute(query, (values,))  # pylint: disable=sql-injection
            committed = {r[0] for r in fresh.fetchall()}
            if not committed:
                continue
            env.cr.execute(query, (values,))  # pylint: disable=sql-injection
            visible = {r[0] for r in env.cr.fetchall()}
            unseen = committed - visible
            if unseen:
                found.append('%s.%s=%s ids=%s' % (table, column, ','.join(values), sorted(unseen)))
    return '; '.join(found) or None


def meli_import_guard(env, keys, checks, label=''):
    """Lock + snapshot. Devuelve None si se puede importar, o el motivo (con PARALLEL_TAG) si no."""
    if not meli_import_try_lock(env.cr, keys):
        msg = '%s: %s en importacion por otro proceso, se omite en esta pasada' % (PARALLEL_TAG, label)
        _logger.info(msg)
        return msg
    stale = meli_import_stale(env, checks)
    if stale:
        msg = '%s: %s ya importada por otro proceso (%s), se omite en esta pasada' % (PARALLEL_TAG, label, stale)
        _logger.info(msg)
        return msg
    return None
