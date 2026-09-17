# meli_oerp - Tasks

> Tareas en progreso.

---

## Abierto — se resuelve CLIENTE POR CLIENTE, en su próxima actualización

### GTIN cargado como atributo de variante (desde 17-sep-2026)
El fix de esta versión evita que el problema **se cree**, pero **no cambia solo** los atributos que
una instancia ya tenga en modo variante.

**Al actualizar un cliente, correr esto en su base:**
```sql
select pa.id, pa.name, pa.create_variant, mca.att_id
  from product_attribute pa
  join mercadolibre_category_attribute mca on mca.id = pa.meli_default_id_attribute
 where mca.att_id in ('GTIN','SELLER_SKU') and pa.create_variant = 'always';
```
- **Vacío** ⇒ nada que hacer, el fix ya lo protege hacia adelante.
- **Con filas** ⇒ anotarlo y **hablarlo con el cliente antes de tocar**: cambiar una línea de
  atributo **borra y recrea las variantes** de esas plantillas.

**Estado por cliente:**
| cuenta | cliente | atributos en `always` | resuelto |
|---|---|---|---|
| 409 | Home I Cuadrado (Mocoroa) | `GTIN` — "Código universal de producto", 197 plantillas | **no** — se ve junto con él |

*(Ir agregando una fila por cliente a medida que se actualiza.)*

---

## En Progreso

*Sin tareas activas*

---
