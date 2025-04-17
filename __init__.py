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
import pkg_resources

import logging
_logger = logging.getLogger(__name__)

def pre_init_check(cr):
    required  = {'meli', 'pdf2image', 'unidecode'}
    installed = {pkg.key for pkg in pkg_resources.working_set}
    missing   = required - installed
    #_logger.info("missing:"+str(missing))
    if missing:
        # implement pip as a subprocess:
        for mis in missing:
            if mis=="meli":
                mis = "git+https://github.com/mercadolibre/python-sdk.git"
            _logger.info("installing dependencies: "+str(mis))
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', mis])

    return True

pre_init_check(cr=None)


def pre_init_hook(cr, registry=None):

    pass;
    #env = api.Environment(cr, SUPERUSER_ID, {})
    #env['ir.model'].search([('model', '=', 'warning')]).unlink()


from . import models
from . import controllers
from . import wizard
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
