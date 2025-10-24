"""
EVM Migration Test Suite - Storage Operations
This test file focuses on storage operations and state management.
"""
import pytest
import unittest
from substrateinterface import SubstrateInterface
from tools.constants import KP_GLOBAL_SUDO, WS_URL, ETH_URL
from tools.runtime_upgrade import wait_until_block_height
from tools.peaq_eth_utils import get_eth_info
from peaq.sudo_extrinsic import funds
from web3 import Web3
from tests.utils_func import restart_with_setup, start_runtime_upgrade_only, is_runtime_upgrade_test
from tests.evm_sc.storage import StorageTestSCBehavior
from tests.evm_sc.upgrade import UpgradeSCBehavior
from tests.evm_sc.struct import StructSCBehavior


@pytest.mark.eth
@pytest.mark.detail_upgrade_check
class TestEVMStorageMigration(unittest.TestCase):
    """Test storage operations behavior during EVM migration"""

    def setUp(self):
        """Setup test environment and initialize contracts"""
        restart_with_setup()
        wait_until_block_height(SubstrateInterface(url=WS_URL), 3)
        self._substrate = SubstrateInterface(url=WS_URL)
        self._w3 = Web3(Web3.HTTPProvider(ETH_URL))

        # Initialize storage-related contracts
        self._storage = StorageTestSCBehavior(self, self._w3, get_eth_info())
        self._upgrade = UpgradeSCBehavior(self, self._w3, get_eth_info())
        self._struct = StructSCBehavior(self, self._w3, get_eth_info())

        # Compose arguments for all contracts
        self._storage.compose_all_args()
        self._upgrade.compose_all_args()
        self._struct.compose_all_args()

        # Fund all required accounts
        ss58_addrs = []
        ss58_addrs += self._storage.get_fund_ss58_keys()
        ss58_addrs += self._upgrade.get_fund_ss58_keys()
        ss58_addrs += self._struct.get_fund_ss58_keys()

        funds(self._substrate, KP_GLOBAL_SUDO, ss58_addrs, 1000 * 10**18)

        # Deploy all contracts
        self._storage.deploy()
        self._upgrade.deploy()
        self._struct.deploy()

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="No-upgrade test")
    def test_storage_no_upgrade(self):
        """Test storage functionality without runtime upgrade"""
        print("\n=== Testing Storage No Upgrade ===")
        self._storage.run_test_scenario()
        print("✅ Storage no-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="No-upgrade test")
    def test_upgrade_no_upgrade(self):
        """Test upgrade functionality without runtime upgrade"""
        print("\n=== Testing Upgrade No Upgrade ===")
        self._upgrade.run_test_scenario()
        print("✅ Upgrade no-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="No-upgrade test")
    def test_struct_no_upgrade(self):
        """Test struct functionality without runtime upgrade"""
        print("\n=== Testing Struct No Upgrade ===")
        self._struct.run_test_scenario()
        print("✅ Struct no-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Upgrade test")
    def test_storage_with_upgrade(self):
        """Test storage functionality with runtime upgrade and verify consistency"""
        print("\n=== Testing Storage With Upgrade ===")
        self._storage.run_test_scenario()
        start_runtime_upgrade_only()
        self._storage.run_post_upgrade_scenario()
        self._storage.check_migration_difference()
        print("✅ Storage with-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Upgrade test")
    def test_upgrade_with_upgrade(self):
        """Test upgrade functionality with runtime upgrade and verify consistency"""
        print("\n=== Testing Upgrade With Upgrade ===")
        self._upgrade.run_test_scenario()
        start_runtime_upgrade_only()
        self._upgrade.run_post_upgrade_scenario()
        self._upgrade.check_migration_difference()
        print("✅ Upgrade with-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Upgrade test")
    def test_struct_with_upgrade(self):
        """Test struct functionality with runtime upgrade and verify consistency"""
        print("\n=== Testing Struct With Upgrade ===")
        self._struct.run_test_scenario()
        start_runtime_upgrade_only()
        self._struct.run_post_upgrade_scenario()
        self._struct.check_migration_difference()
        print("✅ Struct with-upgrade test PASSED")
