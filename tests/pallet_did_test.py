import unittest
import time
import pytest

from substrateinterface import SubstrateInterface, Keypair
from tools.utils import get_balance_reserve_value
from tools.constants import WS_URL
from peaq.utils import ExtrinsicBatch
from peaq.did import did_add_payload, did_update_payload, did_remove_payload, did_rpc_read


@pytest.mark.substrate
class TestPalletDid(unittest.TestCase):
    def setUp(self):
        self.substrate = SubstrateInterface(url=WS_URL)
        self.kp_src = Keypair.create_from_uri('//Alice')

    def test_did_add(self):
        reserved_before = get_balance_reserve_value(self.substrate, self.kp_src.ss58_address, 'peaq_did')
        name = int(time.time())
        batch = ExtrinsicBatch(self.substrate, self.kp_src)

        key = f'0x{name}'
        value = '0x02'
        did_add_payload(batch, self.kp_src.ss58_address, key, value)
        receipt = batch.execute_n_clear()
        self.assertTrue(receipt.is_success,
                        f'failed to add did: receipt={receipt}')

        data = did_rpc_read(self.substrate, self.kp_src.ss58_address, key)
        self.assertEqual(data['name'], key)
        self.assertEqual(data['value'], value)
        reserved_after = get_balance_reserve_value(self.substrate, self.kp_src.ss58_address, 'peaq_did')
        self.assertGreater(reserved_after, reserved_before)

    def test_did_update(self):
        name = int(time.time())
        key = f'0x{name}'
        value = '0x02'
        batch = ExtrinsicBatch(self.substrate, self.kp_src)

        did_add_payload(batch, self.kp_src.ss58_address, key, value)
        value = '0x03'
        did_update_payload(batch, self.kp_src.ss58_address, key, value)
        receipt = batch.execute_n_clear()
        self.assertTrue(receipt.is_success,
                        f'failed to update did: receipt={receipt}')

        data = did_rpc_read(self.substrate, self.kp_src.ss58_address, key)
        self.assertEqual(data['name'], key)
        self.assertEqual(data['value'], value)

    def test_did_remove(self):
        reserved_before = get_balance_reserve_value(self.substrate, self.kp_src.ss58_address, 'peaq_did')
        name = int(time.time())
        key = f'0x{name}'
        value = '0x02'
        batch = ExtrinsicBatch(self.substrate, self.kp_src)

        did_add_payload(batch, self.kp_src.ss58_address, key, value)
        did_remove_payload(batch, self.kp_src.ss58_address, key)
        receipt = batch.execute_n_clear()
        self.assertTrue(receipt.is_success,
                        f'failed to remove did: receipt={receipt}')

        data = did_rpc_read(self.substrate, self.kp_src.ss58_address, key)
        self.assertEqual(data, None)
        reserved_after = get_balance_reserve_value(self.substrate, self.kp_src.ss58_address, 'peaq_did')
        self.assertEqual(reserved_after, reserved_before)
