# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2009 Tiny SPRL (<http://tiny.be>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from odoo import fields, models, api

class MercadolibreBanner(models.Model):
    _name = "mercadolibre.banner"
    _description = "Plantillas descriptivas para MercadoLibre"

    name = fields.Char('Titulo plantilla')
    description = fields.Text(string='Plantilla descriptiva')
    header = fields.Text(string='Encabezado')
    footer = fields.Text(string='Pie')
    images = fields.Text(string='Imagenes (links)')
    images_id = fields.Many2many("mercadolibre.image",string="Imagenes Meli")

    # ------------------------------------------------------------------ [#539]
    # Lenguaje de plantilla para la descripcion.
    #
    # LA DESCRIPCION DE ML ES TEXTO PLANO. Medido en los dos extremos: mandamos
    # {"plain_text": ...} a PUT /items/{id}/description, y ML devuelve el campo `text` (el HTML)
    # VACIO. Por eso el Markdown que se escribe aca NO se manda tal cual: se aplana. Si se mandara
    # crudo, el comprador veria los asteriscos y las almohadillas.
    #
    # El Markdown sirve igual: es comodo de escribir y la MISMA plantilla se puede reusar en un
    # canal que si renderice (web, otro marketplace) sin reescribirla.

    # Marcador para poder SACAR el encabezado y el pie al importar desde ML.
    # Antes se hacia con un replace literal del header/footer, y eso deja de funcionar en cuanto la
    # plantilla tiene variables: lo publicado esta renderizado ("Set: Marvel") y la plantilla guarda
    # el crudo ("Set: {p.x_studio_set}"), no coinciden, el replace no borra nada y la descripcion se
    # ensucia un poco mas en CADA ida y vuelta. No se ve el dia uno; se ve a las 32 publicaciones.
    MELI_DESC_SEP = "\u2014\u2014\u2014"

    def _meli_template_context(self, product, attributes=None):
        """Diccionario de lo que la plantilla puede nombrar. WHITELIST: no se evalua codigo.

        - {p.campo}     -> campo del producto o de su plantilla (incluye los x_studio_*)
        - {ml.campo}    -> campos meli_* (los de la publicacion)
        - {attr.ATT_ID} -> atributo de ML YA RESUELTO (despues del mapeo), p.ej. {attr.RARITY_TYPE}
        """
        ctx = {"p": {}, "ml": {}, "attr": {}}
        if not product:
            return ctx
        tmpl = getattr(product, "product_tmpl_id", None) or product
        # OJO: los campos que EXISTEN pero estan vacios se cargan igual, con "". Es lo que permite
        # distinguir "el dato falta" (se borra la linea) de "el nombre del campo no existe" (error de
        # tipeo de quien escribio la plantilla, que se deja a la vista). Si los vacios no se cargaran,
        # un {p.x_studio_sett} mal escrito desapareceria en silencio y nadie lo encontraria nunca.
        for rec in (product, tmpl):
            if not rec:
                continue
            for fname, field in rec._fields.items():
                if field.type in ("binary", "one2many", "many2many"):
                    continue
                try:
                    val = rec[fname]
                except Exception:
                    continue
                if hasattr(val, "_name"):  # many2one
                    val = (val.display_name or "") if val else ""
                if val is False or val is None:
                    val = ""
                text = str(val).strip()
                # un valor con contenido siempre gana sobre uno vacio (product vs plantilla)
                if fname.startswith("meli_") and (text or fname not in ctx["ml"]):
                    ctx["ml"][fname] = text or ctx["ml"].get(fname, "")
                if text or fname not in ctx["p"]:
                    ctx["p"][fname] = text or ctx["p"].get(fname, "")
        for att in (attributes or []):
            if isinstance(att, dict) and att.get("id"):
                ctx["attr"].setdefault(str(att["id"]), str(att.get("value_name") or ""))
        return ctx

    def _meli_render_template(self, text, product, attributes=None):
        """Resuelve {p.x} / {ml.x} / {attr.X} y aplana el Markdown a texto plano.

        Reglas:
        - Un placeholder SIN valor deja la LINEA ENTERA fuera. (La descripcion escrita a mano del
          caso testigo tenia un "Rarity:" colgando sin valor: con esta regla no pasa.)
        - Un placeholder desconocido se deja tal cual: es un error de tipeo del que escribio la
          plantilla y esconderlo lo haria indetectable.
        """
        if not text:
            return ""
        ctx = self._meli_template_context(product, attributes=attributes)
        out_lines = []
        for line in str(text).replace("\r\n", "\n").split("\n"):
            rendered, missing = self._meli_render_line(line, ctx)
            if missing and not rendered.strip():
                continue
            if missing:
                continue
            out_lines.append(self._meli_markdown_to_plain(rendered))
        return "\n".join(out_lines).strip()

    def _meli_render_line(self, line, ctx):
        """Devuelve (linea_resuelta, hubo_placeholder_sin_valor)."""
        import re as _re
        missing = [False]

        def _sub(m):
            ns, key = m.group(1), m.group(2)
            bucket = ctx.get(ns)
            if bucket is None:
                return m.group(0)          # {desconocido.x}: namespace que no existe -> se deja
            if key not in bucket:
                # El CAMPO no existe: es un error de tipeo de quien escribio la plantilla. Se deja a
                # la vista a proposito. Si se borrara igual que un campo vacio, un {p.x_studio_sett}
                # mal escrito desapareceria en silencio y no habria forma de darse cuenta.
                return m.group(0)
            val = bucket.get(key)
            if val is None or val == "":
                missing[0] = True          # el campo EXISTE y esta vacio -> se cae la linea entera
                return ""
            return val

        rendered = _re.sub(r"\{(p|ml|attr)\.([A-Za-z0-9_]+)\}", _sub, line)
        return rendered, missing[0]

    def _meli_markdown_to_plain(self, line):
        """Subconjunto de Markdown -> texto plano (que es lo unico que ML muestra)."""
        import re as _re
        s = line
        m = _re.match(r"^\s{0,3}(#{1,6})\s+(.*)$", s)
        if m:
            return m.group(2).strip().upper()          # ML no tiene titulos
        s = _re.sub(r"^\s{0,3}[-*+]\s+", "\u2022 ", s)   # vinieta
        s = _re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1: \2", s)  # [texto](url)
        s = _re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
        s = _re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", s)
        s = _re.sub(r"__([^_]+)__", r"\1", s)
        s = _re.sub(r"`([^`]+)`", r"\1", s)
        s = _re.sub(r"^\s{0,3}>\s?", "", s)
        return s.rstrip()

    def get_description( self, product, attributes=None ):
        if not product:
            return ""

        header = self._meli_render_template(self.header, product, attributes=attributes)
        # El body sale de la plantilla si esta cargada; si no, del producto, como siempre.
        # `description` ("Plantilla descriptiva") existia en el modelo y NO se usaba: es el body.
        body = self._meli_render_template(self.description, product, attributes=attributes)
        if not body:
            body = product.meli_description or ""
        footer = self._meli_render_template(self.footer, product, attributes=attributes)

        partes = []
        if header:
            partes += [header, self.MELI_DESC_SEP]
        if body:
            partes.append(body)
        if footer:
            partes += [self.MELI_DESC_SEP, footer]
        return "\n".join(partes).strip()

    def get_from_ml_description( self, meli_description ):
        """Saca encabezado y pie de una descripcion traida de ML."""
        if not meli_description:
            return ""

        # Camino nuevo: cortar por los marcadores. Funciona AUNQUE la plantilla tenga variables,
        # que es donde el replace literal fallaba.
        if self.MELI_DESC_SEP in meli_description:
            partes = meli_description.split(self.MELI_DESC_SEP)
            if len(partes) >= 3:
                return self.MELI_DESC_SEP.join(partes[1:-1]).strip()
            if len(partes) == 2:
                # solo hubo encabezado o solo pie: se conserva el trozo mas largo
                return max(partes, key=lambda x: len(x.strip())).strip()

        # Camino viejo, para las descripciones publicadas antes de esto: replace literal.
        if self.header:
            meli_description = meli_description.replace(self.header, "").strip()
        if self.footer:
            meli_description = meli_description.replace(self.footer, "").strip()

        return meli_description.strip()
