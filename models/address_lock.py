# -*- coding: utf-8 -*-
"""[#caso-K03 cliente A, 26.282] Respetar direcciones cambiadas a mano en ventas de ML — lógica PURA.

Sin Odoo: se prueba con `python3 meli_oerp/tests/test_address_lock_pure.py`.

Problema: cada re-sincronización de la orden (cron o notificación) comparaba la dirección de
factura / entrega del pedido con la que resolvía desde ML y, si difería, la reescribía. Un cambio
manual del usuario volvía a la dirección original en la siguiente vuelta. Lo mismo con la calle,
ciudad y teléfono del CONTACTO de entrega.

Regla:
- El pedido guarda el último contacto que puso el CONECTOR (`meli_partner_*_auto_id`).
- En un pedido existente, el conector cambia el contacto sólo si el campo está vacío o si el
  valor actual sigue siendo el que puso él. Si es otro, lo cambió alguien a mano: se respeta.
- Pedidos anteriores al cambio (sin registro): se toma como "del conector" sólo el valor por
  defecto (el propio cliente del pedido); cualquier otro se respeta.
- Contacto de entrega: guarda la huella de la dirección que escribió el conector. Si la dirección
  actual no coincide con la huella, la editó alguien a mano y no se pisa. Sin huella (contactos
  anteriores) se mantiene el comportamiento previo y se registra la huella.
"""
import hashlib

ADDRESS_FIELDS = ('street', 'street2', 'city', 'zip', 'state_id', 'country_id', 'phone')

WRITE = 'write'      # el conector pone el contacto de ML
SAME = 'same'        # ya coincide: no se escribe, sólo se registra como del conector
MANUAL = 'manual'    # cambio manual: se respeta
NONE = 'none'        # ML no trajo contacto: no se toca


def _norm(value):
    if value is None or value is False:
        return ''
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ''
    return ' '.join(str(value).split()).lower()


def address_fingerprint(values):
    """Huella estable de una dirección (dict campo -> valor; los many2one van como id)."""
    values = values or {}
    raw = '\x1f'.join(_norm(values.get(f)) for f in ADDRESS_FIELDS)
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]


def address_manually_edited(stored_fingerprint, current_values):
    """True si hay huella registrada y la dirección actual ya no coincide."""
    if not stored_fingerprint:
        return False
    return stored_fingerprint != address_fingerprint(current_values)


def order_contact_locked(current_id, auto_id, partner_id, current_edited=False):
    """True si el contacto actual del pedido fue fijado a mano y el conector no debe tocarlo."""
    if not current_id:
        return False
    if current_edited:
        return True
    if auto_id:
        return current_id != auto_id
    # pedido anterior al registro: sólo el valor por defecto se considera del conector
    return current_id != partner_id


def decide_order_contact(is_new, current_id, auto_id, partner_id, ml_id, current_edited=False):
    """Qué hacer con partner_invoice_id / partner_shipping_id de un pedido.

    is_new: el pedido se está creando. current_id/auto_id/partner_id/ml_id: ids (o False).
    current_edited: el contacto actual tiene la dirección editada a mano (sólo entrega).
    """
    if not ml_id:
        return NONE
    if is_new or not current_id:
        return WRITE
    if current_id == ml_id:
        return SAME
    if order_contact_locked(current_id, auto_id, partner_id, current_edited):
        return MANUAL
    return WRITE
