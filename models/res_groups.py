# -*- coding: utf-8 -*-
"""Selector de privilegios del form de usuario en el idioma del usuario (Odoo 19.x).

El widget ``res_user_group_ids`` de Ajustes > Usuarios arma secciones, privilegios y niveles con
``res.groups._get_view_group_hierarchy()``. En algunos builds del core 19.x (p. ej. 19.1a1) ese método
está cacheado con ``@ormcache(cache='groups')`` SIN el idioma en la clave: el primer idioma que lo
calcula tras un reinicio (un cron o un usuario en inglés) queda servido a todos, y el privilegio
«Mercado Libre» con sus niveles (Lector / Encargado / Administrador) sale en inglés aunque la
traducción exista. En el core estable 19.0 y en 20.0 la clave ya incluye ``self.env.lang``: ahí
este override no hace nada (se detecta mirando la clave del ormcache del core).
"""
from odoo import api, models, tools

try:
    from odoo.addons.base.models.res_groups import ResGroups as _CoreResGroups
    _CORE_CACHE = getattr(_CoreResGroups.__dict__.get('_get_view_group_hierarchy'), '__cache__', None)
except Exception:  # pragma: no cover - core sin el método
    _CORE_CACHE = None

# True sólo si el core cachea la jerarquía sin el idioma en la clave.
_CORE_CACHE_SIN_LANG = bool(
    _CORE_CACHE is not None
    and getattr(_CORE_CACHE, 'method', None) is not None
    and not any('lang' in str(arg) for arg in (getattr(_CORE_CACHE, 'args', None) or ()))
)


class ResGroups(models.Model):
    _inherit = 'res.groups'

    @api.model
    def _get_view_group_hierarchy(self):
        if not _CORE_CACHE_SIN_LANG:
            return super()._get_view_group_hierarchy()
        return self._meli_view_group_hierarchy_por_idioma()

    @api.model
    @tools.ormcache('self.env.lang', cache='groups')
    def _meli_view_group_hierarchy_por_idioma(self):
        # Cuerpo crudo del core (sin su ormcache), cacheado por idioma en el mismo cache 'groups'
        # que el core invalida al cambiar grupos/privilegios.
        return _CORE_CACHE.method(self)
