# -*- coding: utf-8 -*-
"""26.389 (deuda 515) -- funciones PURAS (sin ORM) para igualar codigos de barras GTIN.
Las usan models/meli_gtin.py y models/orders.py; viven aparte para no importar modelos
desde orders.py antes de que exista mercadolibre.orders. Ver el docstring de meli_gtin.py."""

GTIN_LENGTHS = (8, 12, 13, 14)


def meli_gtin_keys(code):
    """Formas equivalentes de un codigo de barras para buscarlo en `product.barcode`.

    - Numerico de 8 a 14 digitos (GTIN): el codigo tal cual + el mismo numero rellenado a
      8/12/13/14 (solo los anchos donde entra). '07502300970043' -> incluye '7502300970043'.
    - Cualquier otra cosa (SKU alfanumerico, codigo corto): solo el codigo tal cual. Un
      codigo interno corto NO se iguala a un GTIN.
    """
    if code is None or code is False:
        return []
    s = str(code).strip()
    if not s:
        return []
    keys = [s]
    if not (s.isdigit() and GTIN_LENGTHS[0] <= len(s) <= GTIN_LENGTHS[-1]):
        return keys
    core = s.lstrip('0')
    if not core:
        return keys
    for n in GTIN_LENGTHS:
        if len(core) <= n:
            k = core.zfill(n)
            if k not in keys:
                keys.append(k)
    return keys


def meli_item_gtins(item_json, variation_id=None):
    """GTIN(s) declarados en un aviso de ML: primero los de la variacion vendida, si no los del
    aviso. `value_name` puede traer varios separados por coma."""
    if not isinstance(item_json, dict):
        return []

    def _from_attrs(attrs):
        out = []
        for att in (attrs or []):
            if not isinstance(att, dict) or att.get("id") != "GTIN":
                continue
            raw = att.get("value_name")
            if not raw:
                vals = att.get("values") or []
                raw = vals and isinstance(vals[0], dict) and vals[0].get("name")
            for part in str(raw or '').replace(';', ',').split(','):
                part = part.strip()
                if part and part not in out:
                    out.append(part)
        return out

    if variation_id:
        for var in (item_json.get("variations") or []):
            if isinstance(var, dict) and str(var.get("id")) == str(variation_id):
                found = _from_attrs(var.get("attributes"))
                if found:
                    return found
    return _from_attrs(item_json.get("attributes"))


def meli_gtin_same(a, b):
    """True si `a` y `b` son el mismo codigo de barras (iguales, o el mismo GTIN con otro ancho)."""
    if not a or not b:
        return False
    if str(a).strip() == str(b).strip():
        return True
    return bool(set(meli_gtin_keys(a)) & set(meli_gtin_keys(b)))
