# PLAN (EJECUCIÓN) — `meli_include_taxes` en `product.pricelist` — 17.0

- **Pedido:** FCA, 7-sep-2026: *"ok implementalo porfa"* sobre el plan
  `PLAN-2026-09-07-meli-include-taxes-en-la-lista-de-precios.md`.
- **Branch:** `claude/meli-include-taxes-pricelist-17.0`, creado **desde `origin/17.0`** (rama de
  deploy), worktree `meli_oerp/claude-include-taxes-17.0`. Semáforo `sync-lock` de `meli_oerp` tomado.
- **Alcance de ESTA tanda:** `meli_oerp` 17.0. `meli_oerp_multiple` y las otras 3 versiones **después**,
  y sólo si ésta queda verificada (sin precisión en uno, no se masifica).

## Hallazgo que cambia el riesgo respecto del plan original
En el **source** `meli_oerp/17.0/models/versions.py:216` la constante es **`price_list_apply_tax = True`**.
En la copia desplegada de Legión es **`False`** (su `versions.py:154`) — o sea **la de Legión es una
customización local**, no el default. Eso confirma lo que dijo FCA y **agrava la trampa de migración**:

⛔ **La migración corre DESPUÉS de cargar el código nuevo, así que lee la constante NUEVA.** Si un
cliente que hoy tiene `False` toma el `versions.py` del source (que dice `True`), la migración escribe
`True` en todas sus listas y **la primera corrida del cron publica todo el catálogo con IVA sumado**.
⇒ **La migración no puede depender sólo de la constante.** Se agrega un pin explícito por parámetro
del sistema: `meli_oerp.price_list_apply_tax` (`ir.config_parameter`). Si está seteado, **gana**.

## Pasos
- [ ] `models/product_pricelist.py` — campo `meli_include_taxes`, default `True`
- [ ] `models/versions.py` — helper `ml_apply_taxes(pricelist)` **en un solo lugar** (no copiar el
      `if` en cada punto de uso: eran 3 copias y así se desincronizan)
- [ ] `models/product.py:1443` — usar el helper
- [ ] `models/company.py` — related editable para verlo **al lado del selector de lista**
- [ ] `views/company_view.xml` + `views/product_pricelist_view.xml`
- [ ] `migrations/17.0.26.95/post-migrate.py` con el pin por parámetro
- [ ] `__manifest__.py`: versión + el view nuevo en `data`
- [ ] Verificar: sintaxis Python, XML bien formado, y **el campo no puede quedar sin declarar en la vista**

## Criterio de terminado
1. Python y XML parsean.
2. El helper es el **único** lugar donde se decide; los puntos de uso sólo lo llaman.
3. La migración tiene el pin y está escrita de forma que **un cliente con `False` no despierte en `True`**.
4. Commiteado en el branch de tarea. **El merge a `17.0` y el deploy a cualquier cliente se confirman
   con FCA** — no se hace acá.
5. Lo que NO se toca en esta tanda queda declarado: `meli_oerp_multiple` (que es el que corre Legión)
   y las versiones 16/18/19.
