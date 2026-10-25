# -*- coding: utf-8 -*-
from . import test_542_661_generico
from . import test_525_stock_diag_full
from . import test_525_claim_link
from . import test_ventas_ml_cupon_envio
from . import test_import_cupon_linea
from . import test_462_filtros_facturacion
from . import test_462_envio_facturacion
from . import test_adopcion_linea
from . import test_513_direcciones_manuales

from . import test_26278_cancel_por_motivo
from . import test_26306_full_return_legacy
from . import test_431_import_lock
from . import test_452_envio_archivado
from . import test_682_dni_movil
from . import test_526_envio_facturada
from . import test_158_envio_a_facturar
# Tests puros (unittest.TestCase, se corren con `python3 tests/<archivo>.py`). Importados para que el
# lint de Odoo (test_test_holes) los vea; el runner de Odoo no los ejecuta (no heredan odoo.tests.TestCase).
from . import test_address_lock_pure
from . import test_billing_info_endpoint_pure
from . import test_cancel_decision_pure
from . import test_mlm_cfdi_pure
from . import test_receiver_cost_pure
from . import test_sku_token_pure
from . import test_26309_venta_bloqueada
