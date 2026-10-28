# -*- coding: utf-8 -*-
"""26.329 (caso-K09 cliente C, bus 2026-09-25T11:30:34Z): cron_sync_claims traia reclamos donde la cuenta es
COMPRADORA (complainant): 403 en el detalle + ERROR por corrida + reclamo ajeno. Sin red."""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from ..models.claim import meli_claim_we_are_complainant

SELLER = '511115418'


class _Resp:
    def __init__(self, data):
        self._d = data

    def json(self):
        return self._d


class _Meli:
    access_token = 'TEST'
    seller_id = SELLER

    def __init__(self, data):
        self.data = data

    def need_login(self):
        return False

    def get(self, path, params=None, **kw):
        return _Resp({'data': self.data})


def _claim(cid, role_nuestro):
    otro = 'respondent' if role_nuestro == 'complainant' else 'complainant'
    return {'id': cid, 'players': [
        {'role': role_nuestro, 'type': 'buyer' if role_nuestro == 'complainant' else 'seller', 'user_id': int(SELLER)},
        {'role': otro, 'type': 'seller', 'user_id': 2715707573},
    ]}


@tagged('post_install', '-at_install', 'meli', 'meli_26329')
class TestClaimsRol(TransactionCase):

    def test_helper(self):
        self.assertTrue(meli_claim_we_are_complainant(_claim(1, 'complainant'), SELLER))
        self.assertFalse(meli_claim_we_are_complainant(_claim(1, 'respondent'), SELLER))
        self.assertFalse(meli_claim_we_are_complainant(_claim(1, 'complainant'), ''), "sin seller_id: como antes")
        self.assertFalse(meli_claim_we_are_complainant({'id': 1}, SELLER))

    def test_sync_omite_los_de_comprador(self):
        Claims = self.env['mercadolibre.claim']
        procesados = []
        meli = _Meli([_claim(5378034971, 'complainant'), _claim(5990450019, 'respondent')])
        with patch.object(type(Claims), 'fetch_claim', lambda self, claim_id=None, meli=None, config=None: None), \
                patch.object(type(Claims), 'process_claim',
                             lambda self, claim_id=None, Claim=None, meli=None, config=None: procesados.append(Claim['id'])):
            n = Claims.sync_claims(meli=meli, config=self.env.company)
        self.assertEqual(procesados, [5990450019])
        self.assertEqual(n, 1)
