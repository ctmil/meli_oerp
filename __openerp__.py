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
    'version': '1.0',
    'author': 'Moldeo Interactive Coop. Ltda.',
    'website': 'http://www.moldeointeractive.com.ar',
    "category": "Sales",
    "depends": ['base', 'product','sale','website_sale','stock'],
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
