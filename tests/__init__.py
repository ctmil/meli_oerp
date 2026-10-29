# -*- coding: utf-8 -*-
from . import test_k14_k19_generico
from . import test_k01_stock_diag_full
from . import test_k01_claim_link
from . import test_ventas_ml_cupon_envio
from . import test_import_cupon_linea
from . import test_k13_cupon_pack
from . import test_k21_filtros_facturacion
from . import test_k21_envio_facturacion
from . import test_adopcion_linea
from . import test_k03_direcciones_manuales

from . import test_26278_cancel_por_motivo
from . import test_26306_full_return_legacy
from . import test_k13_import_lock
from . import test_k20_envio_archivado
from . import test_k17_dni_movil
from . import test_k15_envio_facturada
from . import test_k02_envio_a_facturar
from . import test_k15_precio_linea_ml
# Tests puros (unittest.TestCase, se corren con `python3 tests/<archivo>.py`). Importados para que el
# lint de Odoo (test_test_holes) los vea; el runner de Odoo no los ejecuta (no heredan odoo.tests.TestCase).
from . import test_address_lock_pure
from . import test_billing_info_endpoint_pure
from . import test_cancel_decision_pure
from . import test_mlm_cfdi_pure
from . import test_receiver_cost_pure
from . import test_sku_token_pure
from . import test_26309_venta_bloqueada
from . import test_26310_mlb_ids_alfanumericos
from . import test_26310_mlb_site
from . import test_26313_action_assign_compat
from . import test_26326_pack_iva
from . import test_26328_sin_cuenta_y_c1
from . import test_26329_secretos_en_errores
from . import test_26329_claims_rol
from . import test_26332_cambios_producto
from . import test_696_retencion_notificaciones
from . import test_696_contacto_sin_writes_redundantes
from . import test_billing_address_misma_fuente
from . import test_cancel_guarda_entregada
