# -*- coding: utf-8 -*-
##############################################################################
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from odoo import api, SUPERUSER_ID
import sys
import subprocess

import logging
_logger = logging.getLogger(__name__)

def pre_init_check(cr):
    """
    Check and install missing Python dependencies.
    Uses importlib.metadata (standard library Python 3.8+) or falls back to pkg_resources.
    If neither is available, skip the check silently.
    """
    required = {'meli', 'pdf2image', 'unidecode'}
    installed = set()

    # Try importlib.metadata first (standard library, Python 3.8+)
    try:
        from importlib.metadata import distributions
        installed = {dist.metadata['Name'].lower() for dist in distributions()}
    except ImportError:
        # Fallback to pkg_resources if available
        try:
            import pkg_resources
            installed = {pkg.key for pkg in pkg_resources.working_set}
        except ImportError:
            _logger.warning("meli_oerp: Cannot check dependencies (importlib.metadata and pkg_resources not available)")
            return True
    except Exception as e:
        _logger.warning("meli_oerp: Error checking dependencies: %s", str(e))
        return True

    missing = required - installed
    if missing:
        for mis in missing:
            pkg_to_install = mis
            if mis == "meli":
                pkg_to_install = "git+https://github.com/ctmil/python-sdk-2025.git"
            _logger.info("meli_oerp: Installing dependency: %s", pkg_to_install)
            try:
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg_to_install])
            except subprocess.CalledProcessError as e:
                _logger.error("meli_oerp: Failed to install %s: %s", pkg_to_install, str(e))
            except Exception as e:
                _logger.error("meli_oerp: Error installing %s: %s", pkg_to_install, str(e))

    return True

try:
    pre_init_check(cr=None)
except Exception as e:
    _logger.warning("meli_oerp: pre_init_check failed: %s", str(e))


def pre_init_hook(cr, registry=None):

    pass;
    #env = api.Environment(cr, SUPERUSER_ID, {})
    #env['ir.model'].search([('model', '=', 'warning')]).unlink()


def post_init_hook(cr, registry):
    """
    Increase 'Product Price' decimal precision to 6 digits.
    This allows storing prices with higher precision to avoid rounding
    errors when calculating inverse taxes (e.g., 21% IVA).
    """
    env = api.Environment(cr, SUPERUSER_ID, {})

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
