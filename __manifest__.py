# -*- coding: utf-8 -*-
##############################################################################
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

{
    'name': 'MercadoLibre Publisher / Mercado Libre Odoo Connector',
    'summary': 'MercadoLibre Publisher / Mercado Libre Odoo Connector',
    'version': '14.0.21.90',
    'author': 'Moldeo Interactive',
    'website': 'https://www.moldeointeractive.com',
    "category": "Sales",
    "depends": ['base', 'product','sale_management','website_sale','stock','delivery'],
    'data': [
        'security/meli_oerp_security.xml',
        'security/ir.model.access.csv',
        'views/company_view.xml',
    	'views/posting_view.xml',
        'views/product_post.xml',
        'views/product_view.xml',
    	'views/category_view.xml',
    	'views/banner_view.xml',
        'views/warning_view.xml',
        'views/questions_view.xml',
        'views/orders_view.xml',
        'data/cron_jobs.xml',
        'data/error_template_data.xml',
        'data/parameters_data.xml',
	'report/report_shipment_view.xml',
        'report/report_invoice_shipment_view.xml',
	'views/shipment_view.xml',
	'views/notifications_view.xml'
    ],
    'price': '350.00',
    'currency': 'USD',
    "external_dependencies": {"python": ['pdf2image','meli']},
    'images': [ 'static/description/main_screenshot.png',
                'static/description/meli_oerp_screenshot.png',
                'static/description/meli_oerp_configuration_1.png',
                'static/description/meli_oerp_configuration_2.png',
                'static/description/meli_oerp_configuration_3.png',
                'static/description/meli_oerp_configuration_4.png',
                'static/description/moldeo_interactive_logo.png',
                'static/description/odoo_to_meli.png'],
    'demo_xml': [],
    'active': False,
    'installable': True,
    'application': True,
    'license': 'GPL-3'
}
