# PLAN — `meli_include_taxes`: subir el flag de impuestos de constante de código a campo de la lista

- **Quién lo pide:** FCA, 7-sep-2026, textual: *"idealmente sería que sea un campo a nivel del modelo
  de la lista de precio (`meli_include_taxes`, al publicar en meli, incluir impuestos, siempre
  prendido y se apaga cuando se quiere)"*.
- **De dónde sale:** frente de Legión Extranjera (427) del 7-sep. FCA recordó que en ese cliente
  *"teníamos un campo en el `versions.py` que ajustábamos solo para que no agregue los impuestos"*.
  Existe y es real.
- **Alcance:** suite `meli_oerp` / `meli_oerp_multiple`, las 4 versiones (16.0 · 17.0 · 18.0 · 19.0).
- **Estado:** **plan, no ejecutado.** Producción de 427 ya quedó resuelta por otra vía (ver abajo).

## Qué hay hoy
`price_list_apply_tax` es una **constante a nivel módulo**: `meli_oerp/models/versions.py:154`,
hoy `False`. La leen tres lugares:
- `meli_oerp_multiple/models/connection_binding.py:544` (precio de la variante)
- `meli_oerp_multiple/models/connection_binding.py:2897` (precio de la plantilla)
- `meli_oerp/models/product.py:975`

El bloque es el mismo en los tres: si `price_list_apply_tax` **y** `ml_tax_excluded(...)` **y** el
producto tiene `taxes_id`, recorre los impuestos de venta con `price_include=False` y hace
`new_price = txfixed + new_price * (1 + txpercent*0.01)`.

### Los tres problemas de que sea una constante
1. **Se toca editando código.** Cambiar el criterio comercial de un cliente exige un commit y un
   deploy. Es la clase de ajuste que termina hecho a mano en el server y drifteando.
2. **Es global al módulo, y la decisión no lo es.** Un cliente puede tener **una lista con IVA
   incluido y otra sin**: hoy no se puede expresar, porque el flag es uno solo para toda la instancia.
3. **Es invisible.** Nadie que mire la configuración desde la UI puede saber que está apagado. En
   427 estuvo `False` desde el 23-oct-2025 y no aparece en ninguna pantalla.

## Qué se propone
Un campo **`meli_include_taxes` en `product.pricelist`**, no en `mercadolibre.configuration`.
**El porqué de esa elección:** la pregunta *"¿estos precios ya llevan el impuesto adentro?"* es una
propiedad **de la lista**, no de la conexión con MercadoLibre. Una instancia puede publicar desde más
de una lista (la de ARS y la de USD ya conviven en la config: `mercadolibre_pricelist` y
`mercadolibre_pricelist_usd`), y cada una puede tener su respuesta. Ponerlo en la config obliga a que
todas compartan criterio.

```python
# product_pricelist.py  (meli_oerp)
meli_include_taxes = fields.Boolean(
    string="Al publicar en MeLi, incluir impuestos",
    default=True,
    help="Si está activo, al publicar el precio a MercadoLibre se le suman los impuestos de venta "
         "que no estén incluidos en el precio. Apagalo cuando los precios de esta lista YA los "
         "tienen adentro; si no, se cobran dos veces.")
```
- **Default `True`** — es lo que pidió FCA (*"siempre prendido y se apaga cuando se quiere"*), y es
  el comportamiento seguro: publicar de más se ve, publicar de menos se pierde.
- Ubicación en la vista: **al lado del selector de lista**, en la config de MeLi, y también en el
  form de `product.pricelist` para que se vea desde donde se define la lista.

### El reemplazo en los tres puntos de uso
```python
# antes
if ( price_list_apply_tax and tax_excluded and product and product.taxes_id ):
# despues
aplica = pl.meli_include_taxes if (pl and 'meli_include_taxes' in pl._fields) else price_list_apply_tax
if ( aplica and tax_excluded and product and product.taxes_id ):
```
La constante **queda como respaldo** para instancias que todavía no migraron el dato — igual que el
respaldo de nombres viejos de credenciales del htree: se saca recién cuando todas estén migradas.

## ⛔ La trampa de la migración, que es lo que puede romper precios en producción
El default `True` **invierte el comportamiento actual** en toda instancia donde hoy la constante está
en `False` — y en 427 lo está. Si se instala el campo con `default=True` **sin dato de migración**,
la primera corrida del cron publica **todos los precios con impuesto sumado**: en una lista con IVA
21% eso es **publicar un 21% más caro en todo el catálogo**, y el cliente se entera vendiendo cero.

**Por eso el `default` de la definición no alcanza: hace falta un script de migración que escriba el
valor de la constante en las listas existentes**, y sólo las listas creadas después nacen en `True`.
```python
# migrations/<ver>/post-migrate.py
# Las listas que YA existen heredan el comportamiento vigente, no el default nuevo.
for pl in env['product.pricelist'].search([]):
    pl.meli_include_taxes = price_list_apply_tax
```

## Criterio de terminado
1. El campo existe en `product.pricelist`, con default `True`, y se ve **al lado del selector de
   lista** en la config de MeLi.
2. Los **tres** puntos de uso lo leen, con respaldo a la constante.
3. **Migración escrita y corrida**: en una instancia con la constante en `False`, todas las listas
   preexistentes quedan en `False`. **Verificado leyendo el dato, no asumiendo el default.**
4. **Control positivo obligatorio antes de deployar a un cliente:** sobre UNA publicación, medir el
   precio publicado **antes y después** del cambio y comprobar que **no se movió** (para una lista que
   quedó en `False`). Instrumento: `.roots/scripts/meli-probe.py` → `precio-censo` y `precio-diff`.
   Si el censo pasa de 0 desfasadas a N, la migración está mal y hay que frenar.
5. Las 4 versiones alineadas (`/sources-align`) y los `.roots` por versión al día (`/roots-refresh`).

## Contexto: por qué esto NO fue lo que arregló a Legión
El desfasaje de 427 (17 publicaciones activas con precio viejo) **no lo causaba este flag**. La causa
medida fue otra: con `conn_variation_id` cargado en el binding y **0 variaciones** hoy en la
publicación, `x_product_post_price` manda **`{"variations": []}`** — lista vacía — y ML contesta
**200 sin cambiar el precio**, mientras el conector loguea *"Posted price ok"* y escribe
`price_update`. Se corrigieron las 17 en producción el 7-sep y el censo posterior da **0 de 200**.
⚠️ Y el cruce dice que **esa rama no alcanza como explicación completa**: 54 activas caen en ella y
sólo 17 estaban desfasadas, y una desfasada (`MLA2900311364`) **no** estaba en esa rama.
**Ese fix es un frente aparte de éste** y está descrito en el `.roots` del cliente.
