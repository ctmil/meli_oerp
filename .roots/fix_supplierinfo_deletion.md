# Fix: Supplier Info (product.supplierinfo) Unintended Deletion

## Problem

When editing a product variant (e.g., setting `meli_id` in the variant popup), all `product.supplierinfo` records linked to the product template were being deleted upon save.

**Affected versions:** Odoo 17, 18, 19 (field definitions are identical across versions).

## Root Cause

### Two identical One2many fields

In `product.template`, Odoo defines two fields that point to the **exact same records**:

```python
# addons/product/models/product_template.py
seller_ids = fields.One2many('product.supplierinfo', 'product_tmpl_id', 'Vendors', depends_context=('company',))
variant_seller_ids = fields.One2many('product.supplierinfo', 'product_tmpl_id')
```

Both are `One2many` to `product.supplierinfo` via the same inverse field `product_tmpl_id`.

### View switching logic

The `purchase` module switches which field is displayed based on the number of variants:

```xml
<!-- purchase/views/product_views.xml -->
<field name="seller_ids"         invisible="product_variant_count > 1" />
<field name="variant_seller_ids" invisible="product_variant_count <= 1" />
```

When a product has **more than 1 variant**, the form shows `variant_seller_ids`.

### The deletion chain

1. User opens a product template with 2+ variants
2. Opens the variant popup, edits a field (e.g., `meli_id`), saves
3. The web client marks `variant_seller_ids` as "dirty"
4. On save, the web client sends `variant_seller_ids` with **DELETE commands**:
   ```
   variant_seller_ids: [[2, 13818], [2, 13819]]  # Command 2 = DELETE
   ```
5. The ORM processes these via `fields_relational.py` `write_real()` -> `flush()` -> `unlink()`
6. The `_inverse_related` mechanism cascades, writing `seller_ids: SET(6, 0, [])` (replace with empty list)
7. All supplierinfo records are destroyed

### Key traceback (confirmed via debug interceptors)

```
product_template.py:529     write(vals)  # vals contains variant_seller_ids
  orm/models.py:4469        field.write(self, value)
  fields_relational.py:733  write_batch
  fields_relational.py:754  write_real
  fields_relational.py:1038 flush()
  fields_relational.py:990  comodel.browse(to_delete).unlink()  # Records deleted here
```

## Fix

**File:** `meli_oerp/models/product.py` - `product_template.write()`

The fix intercepts `write()` on `product.template` and strips purely destructive commands from `variant_seller_ids` and `seller_ids`:

```python
def write(self, vals):
    for field_name in ('variant_seller_ids', 'seller_ids'):
        if field_name in vals:
            cmds = vals[field_name]
            if cmds and not any(
                isinstance(c, (list, tuple)) and c[0] in (0, 1, 4)
                for c in cmds
            ):
                # Only destructive commands with no constructive ones
                del vals[field_name]
    return super().write(vals)
```

### Logic

ORM command types for One2many fields:
- **Constructive:** `0` (create), `1` (update), `4` (link)
- **Destructive:** `2` (delete), `3` (unlink), `5` (delete all), `6` (replace/set)

If a write contains **only destructive commands** with **no constructive ones**, it's an unintended side-effect of the form save (not a deliberate user action). Legitimate supplier edits always include at least one create (`0`) or update (`1`) command.

## Debug Tools (can be removed in production)

### Supplierinfo unlink logger

`product_supplierinfo_debug` class in `meli_oerp/models/product.py` logs every `product.supplierinfo.unlink()` call with partner, template, variant, and price info.

### Debug button

`action_debug_supplierinfo` button on the product template form logs all current supplierinfo records for inspection.

## Verification

After applying the fix, the log shows:

```
Stripping destructive variant_seller_ids commands on template ids=[15259]: [[2, 13818], [2, 13819]]
Stripping destructive variant_seller_ids commands on template ids=[15259]: [(SET, 0, [])]
Stripping destructive seller_ids commands on template ids=[15259]: [(SET, 0, [])]
```

No `SUPPLIERINFO UNLINK` messages appear. Records are preserved.
