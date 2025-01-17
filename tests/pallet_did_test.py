import unittest
import pytest

from substrateinterface import SubstrateInterface, Keypair
from tools.utils import get_balance_reserve_value
from tools.constants import WS_URL
from peaq.utils import ExtrinsicBatch
from peaq.did import did_add_payload, did_update_payload, did_remove_payload, did_rpc_read
from tools.peaq_eth_utils import generate_random_hex
from tools.runtime_upgrade import wait_until_block_height
from tools.constants import PARACHAIN_WS_URL, RELAYCHAIN_WS_URL
from peaq.utils import get_chain
from tools.utils import get_modified_chain_spec


DID_MIN_DEPOSIT = {
    'peaq-dev': 0.1 * 10 ** 18,
    'krest-network': 0.1 * 10 ** 18,
    'peaq-network': 0.005 * 10 ** 18,
}


@pytest.mark.substrate
class TestPalletDid(unittest.TestCase):
    def setUp(self):
        self.substrate = SubstrateInterface(url=WS_URL)
        self.kp_src = Keypair.create_from_uri('//Alice')
        wait_until_block_height(SubstrateInterface(url=RELAYCHAIN_WS_URL), 1)
        wait_until_block_height(SubstrateInterface(url=PARACHAIN_WS_URL), 1)
        self.chain_spec = get_chain(self.substrate)
        self.chain_spec = get_modified_chain_spec(self.chain_spec)

    def test_did_add(self):
        key = generate_random_hex(20)
        reserved_before = get_balance_reserve_value(self.substrate, self.kp_src.ss58_address, 'peaq_did')
        batch = ExtrinsicBatch(self.substrate, self.kp_src)

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
        self.assertGreaterEqual(reserved_after - reserved_before, DID_MIN_DEPOSIT[self.chain_spec])

    def test_did_update(self):
        key = generate_random_hex(20)
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
        key = generate_random_hex(20)
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
