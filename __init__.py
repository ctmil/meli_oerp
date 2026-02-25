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


def post_init_hook(env_or_cr, registry=None):
    """
    Increase 'Product Price' decimal precision to 6 digits.
    This allows storing prices with higher precision to avoid rounding
    errors when calculating inverse taxes (e.g., 21% IVA).

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

    # Find and update existing 'Product Price' precision
    precision = env['decimal.precision'].search([('name', '=', 'Product Price')], limit=1)
    if precision:
        if precision.digits < 6:
            _logger.info("MELI: Updating 'Product Price' decimal precision from %d to 6 digits", precision.digits)
            precision.write({'digits': 6})
    else:
        _logger.info("MELI: Creating 'Product Price' decimal precision with 6 digits")
        env['decimal.precision'].create({
            'name': 'Product Price',
            'digits': 6
        })


from . import models
from . import controllers
from . import wizard
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
