# -*- coding: utf-8 -*-
##############################################################################
#
#       Pere Ramon Erro Mas <pereerro@tecnoba.com> All Rights Reserved.
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

{
    'name': 'MercadoLibre Publisher',
    'version': '0.1',
    'author': 'Moldeo Interactive',
    'website': 'http://business.moldeo.coop',
    "category": "Sales",
    "depends": ['base', 'product','sale'],
    'data': [
	'company_view.xml',
	'posting_view.xml',
    'product_post.xml',
    'product_view.xml',	
	'category_view.xml',
	'banner_view.xml',
    'warning_view.xml',
    'questions_view.xml',
    'orders_view.xml',
    ],
    'demo_xml': [],
    'active': False,
    'installable': True,
    'application': True,
}
