# -*- coding: utf-8 -*-
"""Privacidad en los logs del suite MercadoLibre (26.427).

Los logs del servidor (archivo, journald, agregadores, Odoo.sh) los lee gente y sistemas que no
tienen por qué ver datos personales de los compradores ni credenciales de la cuenta de ML.
Reglas:

* Un contacto se identifica en el log por su **id** de Odoo (y el ``meli_buyer_id`` si hace falta),
  nunca por su nombre.
* Un documento (CUIT/CUIL/DNI/CPF/CNPJ/RFC/VAT) se loguea **enmascarado**: ``***1234`` (últimos 4)
  o ``FALTA`` si no hay. Alcanza para diagnosticar "¿se guardó?" y "¿es el mismo?" sin exponerlo.
* Tokens de ML (``APP_USR-…``, ``TG-…``, ``Bearer …``, ``access_token=…``) no se loguean nunca. El
  filtro :class:`MeliSecretLogFilter` los tapa en el mensaje y en el traceback de cualquier logger
  del suite, como red de seguridad para los ``str(e)`` de errores de red que traen la URL completa.

Módulo puro (sin imports de Odoo) para poder testearlo y reusarlo desde los módulos hermanos.
"""
import logging
import re

_TOKEN_PATTERNS = (
    # access_token=..., refresh_token=..., client_secret=..., code=... en URLs / querystrings
    # (también percent-encoded: access_token%3D...)
    (re.compile(r'(?i)(access_token|refresh_token|client_secret|secret_key)(=|%3D|"\s*:\s*"|\'\s*:\s*\')[^&\s"\'<>,}]+'),
     lambda m: m.group(1) + m.group(2) + '***'),
    # Authorization: Bearer <token>
    (re.compile(r'(?i)\b(Bearer\s+)[A-Za-z0-9._~+/=-]{8,}'), lambda m: m.group(1) + '***'),
    # Tokens de ML sueltos: APP_USR-<app>-<fecha>-<hex>-<user>, TG-<...> (refresh / code)
    (re.compile(r'\b(APP_USR|TG)-[A-Za-z0-9_-]{12,}'), lambda m: m.group(1) + '-***'),
)
_FAST_CHECK = re.compile(r'(?i)token|secret|bearer|APP_USR|TG-')


def meli_redact_text(value):
    """Texto con los secretos de ML tapados. Acepta cualquier cosa (la pasa a str)."""
    if value is None or value is False:
        return value
    s = value if isinstance(value, str) else str(value)
    if not _FAST_CHECK.search(s):
        return s
    for rx, repl in _TOKEN_PATTERNS:
        s = rx.sub(repl, s)
    return s


_PII_PATTERNS = (
    # "The VAT number [20123456789] for partner [Juan Pérez] does not seem to be valid" (base_vat)
    (re.compile(r'\[[^\[\]\n]{1,160}\]'), '[***]'),
    (re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+'), '***@***'),
    # documentos / teléfonos: 7 a 14 dígitos sueltos (no toca MLA123…, ni ids de orden de 16 dígitos)
    (re.compile(r'(?<![\w.-])\d{7,14}(?![\w.-])'), lambda m: '***' + m.group(0)[-4:]),
)


def meli_redact_pii_text(value):
    """Texto de un error de VALIDACIÓN DE CONTACTO con los datos personales tapados: lo que va entre
    corchetes (así los nombra base_vat), emails y números de documento/teléfono. Usar sólo en errores
    de alta/edición de contactos (en otros contextos taparía datos útiles para diagnosticar)."""
    if value is None or value is False:
        return value
    s = meli_redact_text(value if isinstance(value, str) else str(value))
    for rx, repl in _PII_PATTERNS:
        s = rx.sub(repl, s)
    return s


def meli_pii_err(exc):
    """``Clase: mensaje`` de una excepción de contacto, con datos personales y tokens tapados."""
    try:
        return '%s: %s' % (type(exc).__name__, meli_redact_pii_text(str(exc)))
    except Exception:
        return type(exc).__name__


# extra= para un registro con traceback de un error de contacto: el filtro tapa también el traceback.
MELI_PII_EXTRA = {'meli_pii': True}


def meli_mask_doc(value, keep=4):
    """Documento fiscal/identidad enmascarado para logs: ``***1234``; ``FALTA`` si está vacío."""
    if value in (0, '0'):
        return '0'   # DocNro 0 = consumidor final / sin documento: no es un dato personal
    if not value:
        return 'FALTA'
    s = re.sub(r'[\s.\-/]', '', str(value))
    if len(s) <= keep + 2:
        return '***'
    return '***' + s[-keep:]


def meli_partner_ref(partner):
    """Referencia a un res.partner para logs: ``id:123`` (+ ``meli_buyer_id`` si lo tiene). Nunca el nombre."""
    if not partner:
        return 'None'
    try:
        ids = getattr(partner, 'ids', None)
        if ids is not None and len(ids) != 1:
            return 'ids:%s' % (ids,)
        ref = 'id:%s' % (partner.id,)
        buyer = getattr(partner, 'meli_buyer_id', False) if 'meli_buyer_id' in getattr(partner, '_fields', {}) else False
        if buyer:
            ref += ' meli_buyer_id:%s' % (buyer,)
        return ref
    except Exception:
        return '?'


class MeliSecretLogFilter(logging.Filter):
    """Tapa tokens/secretos de ML en el mensaje (y en el traceback) antes de que se emita el registro.

    Nunca descarta un registro y nunca levanta excepción: si algo falla, deja pasar el original.
    """

    def filter(self, record):
        try:
            pii = getattr(record, 'meli_pii', False)
            redact = meli_redact_pii_text if pii else meli_redact_text
            msg = record.getMessage()
            red = redact(msg)
            if red != msg:
                record.msg = red
                record.args = None
            if record.exc_info and not getattr(record, 'exc_text', None):
                txt = logging.Formatter().formatException(record.exc_info)
                red_txt = redact(txt)
                if red_txt != txt:
                    record.exc_text = red_txt
        except Exception:
            pass
        return True


_FILTER = MeliSecretLogFilter()


def meli_install_log_filter(prefix):
    """Instala el filtro en todos los loggers ya creados cuyo nombre empieza con ``prefix``
    (p.ej. ``odoo.addons.meli_oerp``). Idempotente. Llamar al final del ``__init__`` del addon,
    cuando ya se importaron sus módulos (cada archivo crea su logger con ``getLogger(__name__)``)."""
    names = [n for n in list(logging.Logger.manager.loggerDict) if n == prefix or n.startswith(prefix + '.')]
    if prefix not in names:
        names.append(prefix)
    for n in names:
        lg = logging.getLogger(n)
        if _FILTER not in lg.filters:
            lg.addFilter(_FILTER)
    return len(names)
