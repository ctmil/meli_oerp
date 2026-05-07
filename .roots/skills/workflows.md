# meli_oerp - Workflows

> Procedimientos específicos de este módulo.

---

## WF-001: Regenerar PDF de este módulo

**ID:** WF-001
**Trigger:** Se modifica `meli_oerp/.roots/docs/manual.md`
**Salida:** `docs_output/manual-base-meli-odoo.pdf` actualizado

### Pasos rápidos

```bash
# Desde la raíz del repo
cp docs_output/pdf_style.css /tmp/meli_pdf_style.css
python3 << 'PYEOF'
import subprocess, os, re, datetime

BASE = "/home/user/moldeomint"
CSS  = "/tmp/meli_pdf_style.css"
DATE = datetime.date.today().strftime("%d/%m/%Y")

doc = {
    "title": "Módulo Base — Importación y Publicación",
    "subtitle": "Ventas · Publicaciones · Preguntas · Envíos",
    "module": "meli_oerp",
    "files": [f"{BASE}/meli_oerp/.roots/docs/manual.md"],
    "out": f"{BASE}/docs_output/manual-base-meli-odoo.pdf",
}

with open(CSS) as fh:
    css = fh.read()

md = open(doc["files"][0]).read()
result = subprocess.run(
    ["pandoc", "--from=gfm", "--to=html5", "--standalone",
     "--metadata", f"title={doc['title']}"],
    input=md, capture_output=True, text=True
)
body = re.search(r'<body[^>]*>(.*?)</body>', result.stdout, re.DOTALL).group(1)
cover = f'<div class="cover"><div class="logo-bar">MELI · ODOO CONNECTOR</div><h1>{doc["title"]}</h1><div class="subtitle">{doc["subtitle"]}</div><div class="accent-line"></div><div class="meta">Módulo: <strong>{doc["module"]}</strong><br>Generado: {DATE}<br><em>moldeointeractive.com</em></div></div>'
html = f'<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><title>{doc["title"]}</title><style>{css}</style></head><body>{cover}{body}</body></html>'
tmp = "/tmp/meli_build.html"
open(tmp, 'w').write(html)
subprocess.run(["weasyprint", tmp, doc["out"]], capture_output=True)
print(f"OK: {doc['out'].split('/')[-1]} ({os.path.getsize(doc['out'])//1024}KB)")
PYEOF

# Verificar y commitear
ls -lh docs_output/manual-base-meli-odoo.pdf
git add docs_output/manual-base-meli-odoo.pdf
git commit -m "docs: regenerate manual-base-meli-odoo.pdf"
git push -u origin $(git branch --show-current)
```

> **Nota:** Si el PDF sale muy chico (<30KB), `pdf_style.css` no se copió bien. Verificar que existe en `docs_output/pdf_style.css`.

**Ver también:** `.roots/meli/skills/workflows.md → WF-001` para el workflow completo de todos los módulos.

---

## WF-002: Documentar cambios tras un push

Ver `.roots/meli/skills/workflows.md → WF-002` para el procedimiento completo.

**Archivos a actualizar en este módulo:**
1. `meli_oerp/.roots/debug/fixes-log.md` — entradas FIX-XXX con commit hash
2. `meli_oerp/.roots/journal/changelog.md` — versión nueva
3. `meli_oerp/.roots/docs/manual.md` — secciones nuevas o troubleshooting
4. Si se modificó manual.md: ejecutar WF-001 arriba

---
