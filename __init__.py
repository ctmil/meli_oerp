# -*- coding: utf-8 -*-
##############################################################################
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import sys
import subprocess
import pkg_resources

def pre_init_check(cr):
    required  = {'meli', 'pdf2image'}
    installed = {pkg.key for pkg in pkg_resources.working_set}
    missing   = required - installed

    if missing:
        # implement pip as a subprocess:
        for mis in missing:
            if mis=="meli":
                mis = "git+https://github.com/mercadolibre/python-sdk.git"
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', mis])
    return True

pre_init_check(cr=None)

from . import models
from . import controllers
#import wizard
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
