# -*- coding: utf-8 -*-
##############################################################################
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from odoo import api, SUPERUSER_ID

import logging
_logger = logging.getLogger(__name__)



def pre_init_hook(cr):
    """Pre-init hook compatible with Odoo 14-19"""
    pass


PRODUCT_PRICE_DIGITS_PARAM = 'meli_oerp.product_price_digits'
PRODUCT_PRICE_DIGITS_DEFAULT = 6


def _meli_product_price_target_digits(env):
    """#542/#659: precision objetivo de 'Product Price' segun ir.config_parameter.

    - parametro ausente/vacio  -> 6 (comportamiento historico)
    - '0' / 'false' / 'no' / 'off' / 'keep' -> None (no tocar la precision)
    - entero N (1..10)         -> N
    """
    raw = env['ir.config_parameter'].sudo().get_param(PRODUCT_PRICE_DIGITS_PARAM)
    if raw is None or raw is False or str(raw).strip() == '':
        return PRODUCT_PRICE_DIGITS_DEFAULT
    raw = str(raw).strip().lower()
    if raw in ('0', 'false', 'no', 'off', 'keep'):
        return None
    try:
        digits = int(raw)
    except ValueError:
        _logger.warning("MELI: %s=%r no es un entero; se usa %d",
                        PRODUCT_PRICE_DIGITS_PARAM, raw, PRODUCT_PRICE_DIGITS_DEFAULT)
        return PRODUCT_PRICE_DIGITS_DEFAULT
    if digits < 1 or digits > 10:
        _logger.warning("MELI: %s=%d fuera de rango (1..10); no se toca la precision",
                        PRODUCT_PRICE_DIGITS_PARAM, digits)
        return None
    return digits


def post_init_hook(env_or_cr, registry=None):
    """
    Increase 'Product Price' decimal precision (default 6 digits).
    This allows storing prices with higher precision to avoid rounding
    errors when calculating inverse taxes (e.g., 21% IVA).

    #542/#659: opcional. Se controla con el parametro de sistema
    'meli_oerp.product_price_digits' (ver _meli_product_price_target_digits).
    Nunca BAJA una precision ya configurada: sólo la sube hasta el objetivo.
    Corre sólo al INSTALAR el módulo (no en -u), así que no afecta a las
    instalaciones existentes.

    Compatible with:
    - Odoo 14-16: receives (cr, registry)
    - Odoo 17-19: receives (env) directly
    """
    # Check if we received env directly (Odoo 17+) or cr (Odoo 14-16)
    if hasattr(env_or_cr, 'cr'):
        # Odoo 17+: first argument is already the Environment
        env = env_or_cr
    else:
        # Odoo 14-16: first argument is cursor, need to create Environment
        env = api.Environment(env_or_cr, SUPERUSER_ID, {})

    target = _meli_product_price_target_digits(env)
    if target is None:
        _logger.info("MELI: %s desactivado; no se toca la precision 'Product Price'",
                     PRODUCT_PRICE_DIGITS_PARAM)
        return

    # Find and update existing 'Product Price' precision
    precision = env['decimal.precision'].search([('name', '=', 'Product Price')], limit=1)
    if precision:
        if precision.digits < target:
            _logger.info("MELI: Updating 'Product Price' decimal precision from %d to %d digits", precision.digits, target)
            precision.write({'digits': target})
    else:
        _logger.info("MELI: Creating 'Product Price' decimal precision with %d digits", target)
        env['decimal.precision'].create({
            'name': 'Product Price',
            'digits': target
        })


from . import models
from . import controllers
from . import wizard
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
