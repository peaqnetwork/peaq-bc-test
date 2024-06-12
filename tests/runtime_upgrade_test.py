# Test for the peaq-did/peaq-rbac/peaq-storage before and after the runtime upgrade

import sys
sys.path.append('./')
import unittest
from tools.restart import restart_parachain_launch
from tools.utils import KP_GLOBAL_SUDO
from peaq.sudo_extrinsic import funds
from tests.utils_func import is_runtime_upgrade_test, get_runtime_upgrade_path
import pytest
from substrateinterface import SubstrateInterface, Keypair
from tools.runtime_upgrade import wait_until_block_height
from tools.runtime_upgrade import do_runtime_upgrade
from tools.utils import PARACHAIN_WS_URL
from peaq.utils import ExtrinsicBatch
from peaq.did import did_add_payload, did_rpc_read
from tools.peaq_eth_utils import generate_random_hex
from peaq.storage import storage_add_payload, storage_rpc_read
from peaq.rbac import rbac_add_role_payload, rbac_rpc_fetch_role


class TestRuntimeUpgrade(unittest.TestCase):

    def setUp(self):
        restart_parachain_launch()
        wait_until_block_height(SubstrateInterface(url=PARACHAIN_WS_URL), 1)
        self.substrate = SubstrateInterface(url=PARACHAIN_WS_URL,)
        self.kp_src = Keypair.create_from_uri('//Moon')
        funds(self.substrate,
              KP_GLOBAL_SUDO,
              [self.kp_src.ss58_address],
              1000 * 10 ** 18)

    def generate_random_hex(self, length):
        return '0x' + ''.join([generate_random_hex()[2:] for i in range(int(length / 32) + 1)])[:length]

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason='Skip for runtime upgrade test')
    def test_pallet_did(self):
        # Setup the did attribute
        # TODO, Need to check 256...???
        DID_KEY_LEN = 64 * 2
        DID_VALUE_LEN = 2560 * 2
        batch = ExtrinsicBatch(self.substrate, self.kp_src)
        key = self.generate_random_hex(DID_KEY_LEN)
        value = self.generate_random_hex(DID_VALUE_LEN)
        did_add_payload(batch, self.kp_src.ss58_address, key, value)
        receipt = batch.execute()
        self.assertTrue(receipt.is_success,
                        f'failed to add did: receipt={receipt}')

        # Runtime upgrade
        path = get_runtime_upgrade_path()
        do_runtime_upgrade(path)

        # Check the did attribute
        data = did_rpc_read(self.substrate, self.kp_src.ss58_address, key)
        self.assertEqual(data['name'], key)
        self.assertEqual(data['value'], value)

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason='Skip for runtime upgrade test')
    def test_pallet_rbac(self):
        ROLE_KEY_LEN = 32 * 2
        ROLE_VALUE_LEN = 64 * 2
        key = self.generate_random_hex(ROLE_KEY_LEN)
        name = self.generate_random_hex(ROLE_VALUE_LEN)

        batch = ExtrinsicBatch(self.substrate, self.kp_src)
        rbac_add_role_payload(batch, key, name)
        receipt = batch.execute()
        self.assertTrue(receipt.is_success,
                        f'failed to add role: receipt={receipt}')

        path = get_runtime_upgrade_path()
        do_runtime_upgrade(path)

        # Check the did attribute
        data = rbac_rpc_fetch_role(self.substrate, self.kp_src.ss58_address, key[2:])
        self.assertEqual(data['Ok']['id'], key[2:])
        self.assertEqual(data['Ok']['name'], name[2:])

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason='Skip for runtime upgrade test')
    def test_pallet_storage(self):
        # [TODO] Use 256, the error happens, need to extract to another test
        STORAGE_KEY_LEN = 64 * 2
        STORAGE_VALUE_LEN = 256 * 2
        batch = ExtrinsicBatch(self.substrate, self.kp_src)
        item_type = self.generate_random_hex(STORAGE_KEY_LEN)
        item = self.generate_random_hex(STORAGE_VALUE_LEN)
        storage_add_payload(batch, item_type, item)

        receipt = batch.execute()
        self.assertTrue(receipt.is_success,
                        f'failed to add storage: receipt={receipt}')

        path = get_runtime_upgrade_path()
        do_runtime_upgrade(path)

        # Check the did attribute
        data = storage_rpc_read(self.substrate, self.kp_src.ss58_address, item_type)
        self.assertEqual(data['item'], item)
