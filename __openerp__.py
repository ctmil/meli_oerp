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
        'data/cron_jobs.xml',
        'data/error_template_data.xml',
        'data/parameters_data.xml',
        'views/company_view.xml',
    	'views/posting_view.xml',
        'views/product_post.xml',
        'views/product_view.xml',
    	'views/category_view.xml',
    	'views/banner_view.xml',
        'views/warning_view.xml',
        'views/questions_view.xml',
        'views/orders_view.xml',
    ],
    'demo_xml': [],
    'active': False,
    'installable': True,
    'application': True,
}
