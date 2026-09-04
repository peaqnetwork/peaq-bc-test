"""
EVM Migration Test Suite - Advanced Features
This test file focuses on advanced EVM features including EIPs, events, error handling, and gas operations.
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
from tests.evm_sc.event import EventSCBehavior
from tests.evm_sc.error_handling import ErrorHandlingSCBehavior
from tests.evm_sc.gas import GasSCBehavior
from tests.evm_sc.eip1153_transient import EIP1153TransientTestBehavior
from tests.evm_sc.eip5656_mcopy import EIP5656MCOPYTestBehavior


@pytest.mark.eth
@pytest.mark.detail_upgrade_check
class TestEVMAdvancedMigration(unittest.TestCase):
    """Test advanced EVM features behavior during migration"""

    def setUp(self):
        """Setup test environment and initialize contracts"""
        restart_with_setup()
        wait_until_block_height(SubstrateInterface(url=WS_URL), 3)
        self._substrate = SubstrateInterface(url=WS_URL)
        self._w3 = Web3(Web3.HTTPProvider(ETH_URL))

        # Initialize advanced feature contracts
        self._event = EventSCBehavior(self, self._w3, get_eth_info())
        self._error_handling = ErrorHandlingSCBehavior(self, self._w3, get_eth_info())
        self._gas = GasSCBehavior(self, self._w3, get_eth_info())
        self._eip1153 = EIP1153TransientTestBehavior(self, self._w3, get_eth_info())
        self._eip5656 = EIP5656MCOPYTestBehavior(self, self._w3, get_eth_info())

        # Compose arguments for all contracts
        self._event.compose_all_args()
        self._error_handling.compose_all_args()
        self._gas.compose_all_args()
        self._eip1153.compose_all_args()
        self._eip5656.compose_all_args()

        # Fund all required accounts
        ss58_addrs = []
        ss58_addrs += self._event.get_fund_ss58_keys()
        ss58_addrs += self._error_handling.get_fund_ss58_keys()
        ss58_addrs += self._gas.get_fund_ss58_keys()
        ss58_addrs += self._eip1153.get_fund_ss58_keys()
        ss58_addrs += self._eip5656.get_fund_ss58_keys()

        funds(self._substrate, KP_GLOBAL_SUDO, ss58_addrs, 1000 * 10**18)

        # Deploy all contracts
        self._event.deploy()
        self._error_handling.deploy()
        self._gas.deploy()
        self._eip1153.deploy()
        self._eip5656.deploy()

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="No-upgrade test")
    def test_event_no_upgrade(self):
        """Test event functionality without runtime upgrade"""
        print("\n=== Testing Event No Upgrade ===")
        self._event.run_test_scenario()
        print("✅ Event no-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="No-upgrade test")
    def test_error_handling_no_upgrade(self):
        """Test error handling functionality without runtime upgrade"""
        print("\n=== Testing ErrorHandling No Upgrade ===")
        self._error_handling.run_test_scenario()
        print("✅ ErrorHandling no-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="No-upgrade test")
    def test_gas_no_upgrade(self):
        """Test gas functionality without runtime upgrade"""
        print("\n=== Testing Gas No Upgrade ===")
        self._gas.run_test_scenario()
        print("✅ Gas no-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="No-upgrade test")
    def test_eip1153_no_upgrade(self):
        """Test EIP-1153 transient storage without runtime upgrade"""
        print("\n=== Testing EIP1153 No Upgrade ===")
        self._eip1153.run_test_scenario()
        print("✅ EIP1153 no-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="No-upgrade test")
    def test_eip5656_no_upgrade(self):
        """Test EIP-5656 MCOPY opcode without runtime upgrade"""
        print("\n=== Testing EIP5656 No Upgrade ===")
        self._eip5656.run_test_scenario()
        print("✅ EIP5656 no-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Upgrade test")
    def test_event_with_upgrade(self):
        """Test event functionality with runtime upgrade and verify consistency"""
        print("\n=== Testing Event With Upgrade ===")
        self._event.run_test_scenario()
        start_runtime_upgrade_only()
        self._event.run_post_upgrade_scenario()
        self._event.check_migration_difference()
        print("✅ Event with-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Upgrade test")
    def test_error_handling_with_upgrade(self):
        """Test error handling functionality with runtime upgrade and verify consistency"""
        print("\n=== Testing ErrorHandling With Upgrade ===")
        self._error_handling.run_test_scenario()
        start_runtime_upgrade_only()
        self._error_handling.run_post_upgrade_scenario()
        self._error_handling.check_migration_difference()
        print("✅ ErrorHandling with-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Upgrade test")
    def test_gas_with_upgrade(self):
        """Test gas functionality with runtime upgrade and verify consistency"""
        print("\n=== Testing Gas With Upgrade ===")
        self._gas.run_test_scenario()
        start_runtime_upgrade_only()
        self._gas.run_post_upgrade_scenario()
        self._gas.check_migration_difference()
        print("✅ Gas with-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Upgrade test")
    def test_eip1153_with_upgrade(self):
        """Test EIP-1153 transient storage with runtime upgrade and verify consistency"""
        print("\n=== Testing EIP1153 With Upgrade ===")
        self._eip1153.run_test_scenario()
        start_runtime_upgrade_only()
        self._eip1153.run_post_upgrade_scenario()
        self._eip1153.check_migration_difference()
        print("✅ EIP1153 with-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Upgrade test")
    def test_eip5656_with_upgrade(self):
        """Test EIP-5656 MCOPY opcode with runtime upgrade and verify consistency"""
        print("\n=== Testing EIP5656 With Upgrade ===")
        self._eip5656.run_test_scenario()
        start_runtime_upgrade_only()
        self._eip5656.run_post_upgrade_scenario()
        self._eip5656.check_migration_difference()
        print("✅ EIP5656 with-upgrade test PASSED")
