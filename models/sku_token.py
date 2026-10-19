# -*- coding: utf-8 -*-
"""Match de SKU de Mercado Libre por TOKEN (opcion `mercadolibre_sku_token_match`).

Caso que lo origina (#543 Petswagon, 19-oct-2026): en ML el SKU se carga como
"codigo-descripcion" ("21342-VITAL PREMIUM PERRO ADULTO 20K") y en Odoo la referencia
interna es solo el codigo ("21342"). Todo el matching del suite es exacto
(`default_code =ilike sku`), asi que ninguna publicacion vinculaba.

Regla (estricta a proposito): el SKU se parte por los separadores configurados y
se acepta el producto SOLO si EXACTAMENTE UN token coincide con productos de Odoo
y ese token coincide con UN UNICO producto. Cualquier otra cosa (ningun token, dos
tokens que coinciden, un codigo repetido en Odoo) NO vincula: atar una publicacion
al producto equivocado se propaga a stock y a ventas.

Este modulo es PURO (sin Odoo): el acceso a la base lo inyecta el llamador como
`lookup(token)`. Asi se prueba sin levantar una base.
"""

import re

DEFAULT_SEPARATORS = "- /"

RESULT_OK = 'ok'
RESULT_NO_TOKENS = 'sin_tokens'
RESULT_NO_MATCH = 'sin_match'
RESULT_AMBIGUOUS_TOKENS = 'ambiguo_tokens'
RESULT_AMBIGUOUS_PRODUCT = 'ambiguo_producto'


def meli_sku_tokens(sku, separators=None):
    """Parte `sku` por los separadores (cada caracter de `separators` es uno).

    Devuelve la lista de tokens no vacios, sin repetir (case-insensitive, en orden).
    Si el SKU no tiene ningun separador devuelve [] -- el SKU entero ya lo cubre la
    busqueda exacta de siempre, no hay nada nuevo que probar.
    """
    if not sku or not isinstance(sku, str):
        return []
    seps = separators if (separators and isinstance(separators, str)) else DEFAULT_SEPARATORS
    chars = []
    for c in seps:
        if c.isspace():
            c = r'\s'
        else:
            c = re.escape(c)
        if c not in chars:
            chars.append(c)
    parts = re.split('(?:' + '|'.join(chars) + ')+', sku.strip())
    tokens = []
    seen = set()
    for part in parts:
        tok = part.strip()
        if not tok:
            continue
        key = tok.lower()
        if key in seen:
            continue
        seen.add(key)
        tokens.append(tok)
    if len(tokens) < 2:
        return []
    return tokens


def meli_sku_token_pick(sku, separators, lookup):
    """Aplica la regla "exactamente un token -> un unico producto".

    `lookup(token)` devuelve los productos que coinciden con ese token (recordset o
    lista; alcanza con que traiga hasta 2 para distinguir unico de repetido).

    Devuelve (match, token, resultado):
      - (productos_de_1, token, 'ok') si hay match unico;
      - (None, None|token, motivo) en cualquier otro caso.
    """
    tokens = meli_sku_tokens(sku, separators)
    if not tokens:
        return None, None, RESULT_NO_TOKENS
    hits = []
    for tok in tokens:
        found = lookup(tok)
        if found:
            hits.append((tok, found))
    if not hits:
        return None, None, RESULT_NO_MATCH
    if len(hits) > 1:
        return None, ",".join(t for t, _f in hits), RESULT_AMBIGUOUS_TOKENS
    tok, found = hits[0]
    if len(found) != 1:
        return None, tok, RESULT_AMBIGUOUS_PRODUCT
    return found, tok, RESULT_OK


def like_escape(value):
    """Escapa comodines de LIKE para que un token se compare literal con `=ilike`."""
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
