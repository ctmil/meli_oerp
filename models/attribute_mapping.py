# -*- coding: utf-8 -*-
"""[#539] Mapeo CAMPO de Odoo -> ATRIBUTO de MercadoLibre, con mapeo de VALORES.

POR QUE EXISTE
--------------
Hoy los atributos que se mandan a ML salen de las LINEAS DE ATRIBUTO de la plantilla
(product.attribute + product.attribute.value + una linea por producto). Para cargar decenas de
fichas desde un Excel eso es inviable: hay que crear un product.attribute.value por cada valor
distinto, y encima arrastra el riesgo de generar variantes.

Muchos clientes ya tienen los datos en campos propios (Studio o de un modulo suyo). Este mapeo
permite decir "el campo x_studio_set va al atributo EDITION de ML" una sola vez, y que valga para
todos los productos.

EL MAPEO DE VALORES NO ES UN EXTRA
----------------------------------
Medido sobre un caso real (DISELEC, categoria MLM3390 "Cartas Coleccionables T.C.G"): de 8 campos
mapeables, 4 apuntan a atributos con LISTA CERRADA de valores, y el texto de Odoo no coincide con
lo que ML espera:
    Condition "Near Mint"          -> ITEM_CONDITION  (ML solo acepta Nuevo / Usado)
    TCG "Magic: The Gathering"     -> CARD_GAME_NAME  (ML espera "Magic")
    Finish "Normal"                -> IS_FOIL_CARD    (No / Si)
    Rarity "Rara"                  -> RARITY_TYPE     (Comun, Rara, Super rara, Ultra rara, Secreta)
Sin traduccion de valores el mapeo no sirve para esa categoria.
"""

from odoo import fields, models, api
from . import versions

import json
import logging

_logger = logging.getLogger(__name__)


class MeliAttributeMapping(models.Model):
    """Un campo de Odoo -> un atributo de MercadoLibre."""

    _name = "meli_oerp.attribute.mapping"
    _description = "Mapeo de campos de Odoo a atributos de MercadoLibre"
    _order = "sequence asc, id asc"

    name = fields.Char(string="Nombre", compute="_compute_name", store=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    # --- origen: el campo de Odoo -------------------------------------------------
    model_name = fields.Selection(
        [("product.template", "Plantilla de producto"),
         ("product.product", "Variante de producto")],
        string="Modelo", default="product.template", required=True,
        help="De donde se lee el valor. La variante gana sobre la plantilla si el campo existe en las dos.",
    )
    field_id = fields.Many2one(
        "ir.model.fields", string="Campo de Odoo", required=True, ondelete="cascade",
        domain="[('model', '=', model_name), ('store', '=', True)]",
        help="Campo del producto de donde sale el valor. Sirve cualquier campo almacenado, "
             "incluidos los creados con Studio (x_studio_...).",
    )
    field_name = fields.Char(related="field_id.name", string="Nombre técnico", readonly=True, store=True)

    # --- destino: el atributo de ML -----------------------------------------------
    meli_attribute_id = fields.Many2one(
        "mercadolibre.category.attribute", string="Atributo de MercadoLibre",
        help="Atributo de ML al que se manda el valor. Se eligen de los que ya importamos de ML "
             "(menú MercadoLibre > Atributos). Si el que buscás no está, importá la categoría primero.",
    )
    meli_att_id = fields.Char(
        string="ID del atributo", index=True,
        help="Id del atributo en MercadoLibre (BRAND, EDITION, ITEM_CONDITION...). Se completa solo "
             "al elegir el atributo; se puede escribir a mano si el atributo todavía no fue importado.",
    )
    category_id = fields.Many2one(
        "mercadolibre.category", string="Categoría de ML",
        help="Dejalo vacío para que el mapeo valga para TODAS las categorías. Completalo sólo si este "
             "campo significa algo distinto según la categoría.",
    )

    # --- traduccion de valores ----------------------------------------------------
    value_mapping_ids = fields.One2many(
        "meli_oerp.attribute.value.mapping", "mapping_id", string="Traducción de valores")
    value_mapping_count = fields.Integer(compute="_compute_value_mapping_count")
    meli_allowed_values = fields.Text(
        string="Valores que acepta ML", compute="_compute_meli_allowed_values",
        help="Valores permitidos por MercadoLibre para este atributo, tal como los importamos. "
             "Si dice 'texto libre', cualquier valor sirve y no hace falta traducir.",
    )

    # Convención del módulo para que el mismo código sirva en 16/17/18/19:
    # UniqueIndex en 17+, _sql_constraints en <17. Ver models/versions.py.
    _unique_field_att_categ = versions.UniqueIndex(
        "field_id, meli_att_id, category_id",
        message="Ya existe un mapeo para ese campo, ese atributo y esa categoría.")
    _sql_constraints = versions.sql_constraints_if_no_unique_index([
        ("uniq_field_att_categ", "field_id, meli_att_id, category_id",
         "Ya existe un mapeo para ese campo, ese atributo y esa categoría."),
    ])

    @api.depends("field_id", "meli_att_id")
    def _compute_name(self):
        for rec in self:
            rec.name = "%s → %s" % (rec.field_id.name or "?", rec.meli_att_id or "?")

    @api.depends("value_mapping_ids")
    def _compute_value_mapping_count(self):
        for rec in self:
            rec.value_mapping_count = len(rec.value_mapping_ids)

    @api.depends("meli_attribute_id")
    def _compute_meli_allowed_values(self):
        for rec in self:
            rec.meli_allowed_values = rec._meli_allowed_values_text()

    def _meli_allowed_values_text(self):
        """Texto legible con los valores que ML acepta, leidos de lo que ya importamos.

        `mercadolibre.category.attribute.values` guarda el JSON que devuelve ML. Es defensivo a
        proposito: si no parsea, se dice y no se rompe nada.
        """
        self.ensure_one()
        att = self.meli_attribute_id
        if not att:
            return ""
        raw = att.values if "values" in att._fields else None
        if not raw:
            return "Texto libre (MercadoLibre no restringe los valores de este atributo)."
        names = self._meli_allowed_value_names()
        if names is None:
            return "No se pudieron leer los valores permitidos (el dato guardado no es legible)."
        if not names:
            return "Texto libre (MercadoLibre no restringe los valores de este atributo)."
        return "Sólo acepta: " + ", ".join(names)

    def _meli_allowed_value_names(self):
        """Lista de nombres permitidos, o None si no se pudo leer. [] = texto libre."""
        self.ensure_one()
        att = self.meli_attribute_id
        raw = att and ("values" in att._fields) and att.values
        if not raw:
            return []
        data = None
        for parser in (json.loads, __import__("ast").literal_eval):
            try:
                data = parser(raw)
                break
            except Exception:
                continue
        if data is None:
            return None
        try:
            if isinstance(data, dict):
                data = data.get("values") or []
            return [str(v.get("name")) for v in data if isinstance(v, dict) and v.get("name")]
        except Exception:
            return None

    @api.onchange("meli_attribute_id")
    def _onchange_meli_attribute_id(self):
        for rec in self:
            if rec.meli_attribute_id:
                rec.meli_att_id = rec.meli_attribute_id.att_id

    @api.onchange("model_name")
    def _onchange_model_name(self):
        for rec in self:
            if rec.field_id and rec.field_id.model != rec.model_name:
                rec.field_id = False

    # ------------------------------------------------------------------ resolución
    def _meli_value_for(self, product):
        """Valor final a mandar a ML para `product`, o None si no corresponde mandar nada.

        Reglas (decididas por FCA el 24-ago-2026):
        - Si hay traduccion definida para el valor de Odoo, se usa la traduccion.
        - Si NO hay traduccion, SE MANDA EL VALOR TAL CUAL.
        - Si el atributo tiene lista cerrada y el valor no esta entre los permitidos, IGUAL SE MANDA
          (decision de FCA) pero queda un WARNING en el log: es el caso que hace fallar la
          publicacion entera con un error ilegible de ML, asi que tiene que ser rastreable.
        """
        self.ensure_one()
        if not product:
            return None
        fname = self.field_id.name
        if not fname:
            return None

        # la variante gana sobre la plantilla cuando el campo existe en las dos
        source = product
        if fname not in product._fields:
            source = getattr(product, "product_tmpl_id", None) or product
        if not source or fname not in source._fields:
            return None

        raw = source[fname]
        if raw is False or raw is None or raw == "":
            return None
        if hasattr(raw, "display_name") and hasattr(raw, "_name"):  # many2one
            raw = raw.display_name if raw else None
        value = str(raw).strip()
        if not value:
            return None

        for vm in self.value_mapping_ids:
            if (vm.odoo_value or "").strip().lower() == value.lower():
                if not vm.meli_value_name:
                    _logger.info(
                        "MELI mapeo: el valor '%s' del campo %s está mapeado a VACÍO -> no se manda %s",
                        value, fname, self.meli_att_id)
                    return None
                return vm.meli_value_name.strip()

        allowed = self._meli_allowed_value_names()
        if allowed:
            if value.lower() not in [a.lower() for a in allowed]:
                _logger.warning(
                    "MELI mapeo: '%s' (campo %s) NO está entre los valores que acepta %s [%s]. "
                    "Se manda igual; si ML lo rechaza, hay que agregar la traducción de ese valor.",
                    value, fname, self.meli_att_id, ", ".join(allowed[:8]))
        return value

    @api.model
    def _meli_attributes_from_mapping(self, product, meli_category=None, already=None):
        """Atributos que aportan los mapeos para `product`.

        `already` = ids de atributos ya resueltos por otro camino (lineas de atributo de Odoo):
        NO se pisan. El mapeo COMPLETA, no reemplaza.
        Devuelve una lista de dicts {'id':..., 'value_name':...}.
        """
        already = set(already or [])
        out = []
        if not product:
            return out
        domain = [("active", "=", True)]
        mappings = self.search(domain)
        for m in mappings:
            if not m.meli_att_id or m.meli_att_id in already:
                continue
            if m.category_id and meli_category and m.category_id.id != meli_category.id:
                continue
            value = m._meli_value_for(product)
            if value is None:
                continue
            out.append({"id": m.meli_att_id, "value_name": value})
            already.add(m.meli_att_id)
            _logger.info("MELI mapeo: %s = %s (desde %s)", m.meli_att_id, value, m.field_id.name)
        return out


class MeliAttributeValueMapping(models.Model):
    """Traduccion de UN valor de Odoo al valor que espera MercadoLibre."""

    _name = "meli_oerp.attribute.value.mapping"
    _description = "Traducción de valores para atributos de MercadoLibre"
    _order = "mapping_id, odoo_value"

    mapping_id = fields.Many2one(
        "meli_oerp.attribute.mapping", string="Mapeo", required=True, ondelete="cascade", index=True)
    odoo_value = fields.Char(
        string="Valor en Odoo", required=True,
        help="Valor tal como está en el campo del producto. No distingue mayúsculas de minúsculas.")
    meli_value_name = fields.Char(
        string="Valor en MercadoLibre",
        help="Valor que se manda a ML. Dejalo VACÍO para que ese valor no se mande "
             "(útil cuando un valor de Odoo no tiene equivalente y preferís omitir el atributo).")

    _unique_value_por_mapeo = versions.UniqueIndex(
        "mapping_id, odoo_value", message="Ese valor ya está traducido en este mapeo.")
    _sql_constraints = versions.sql_constraints_if_no_unique_index([
        ("uniq_value_por_mapeo", "mapping_id, odoo_value",
         "Ese valor ya está traducido en este mapeo."),
    ])
