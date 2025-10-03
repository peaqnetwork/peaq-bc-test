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

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="Pre-migration test only")
    def test_event_before_migration(self):
        """Test event functionality before migration"""
        print("\n=== Testing Event Before Migration ===")
        try:
            self._event.before_migration_sc_behavior()
            print("✅ Event pre-migration test PASSED")
        except Exception as e:
            print(f"❌ Event pre-migration test FAILED: {e}")
            raise

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="Pre-migration test only")
    def test_error_handling_before_migration(self):
        """Test error handling functionality before migration"""
        print("\n=== Testing ErrorHandling Before Migration ===")
        try:
            self._error_handling.before_migration_sc_behavior()
            print("✅ ErrorHandling pre-migration test PASSED")
        except Exception as e:
            print(f"❌ ErrorHandling pre-migration test FAILED: {e}")
            raise

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="Pre-migration test only")
    def test_gas_before_migration(self):
        """Test gas functionality before migration"""
        print("\n=== Testing Gas Before Migration ===")
        try:
            self._gas.before_migration_sc_behavior()
            print("✅ Gas pre-migration test PASSED")
        except Exception as e:
            print(f"❌ Gas pre-migration test FAILED: {e}")
            raise

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="Pre-migration test only")
    def test_eip1153_before_migration(self):
        """Test EIP-1153 transient storage before migration"""
        print("\n=== Testing EIP1153 Before Migration ===")
        try:
            self._eip1153.before_migration_sc_behavior()
            print("✅ EIP1153 pre-migration test PASSED")
        except Exception as e:
            print(f"❌ EIP1153 pre-migration test FAILED: {e}")
            raise

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="Pre-migration test only")
    def test_eip5656_before_migration(self):
        """Test EIP-5656 MCOPY opcode before migration"""
        print("\n=== Testing EIP5656 Before Migration ===")
        try:
            self._eip5656.before_migration_sc_behavior()
            print("✅ EIP5656 pre-migration test PASSED")
        except Exception as e:
            print(f"❌ EIP5656 pre-migration test FAILED: {e}")
            raise

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Migration test only")
    def test_event_after_migration(self):
        """Test event functionality after migration and verify consistency"""
        print("\n=== Testing Event After Migration ===")
        try:
            self._event.before_migration_sc_behavior()
            start_runtime_upgrade_only()
            self._event.after_migration_sc_behavior()
            self._event.check_migration_difference()
            print("✅ Event migration test PASSED")
        except Exception as e:
            print(f"❌ Event migration test FAILED: {e}")
            raise

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Migration test only")
    def test_error_handling_after_migration(self):
        """Test error handling functionality after migration and verify consistency"""
        print("\n=== Testing ErrorHandling After Migration ===")
        try:
            self._error_handling.before_migration_sc_behavior()
            start_runtime_upgrade_only()
            self._error_handling.after_migration_sc_behavior()
            self._error_handling.check_migration_difference()
            print("✅ ErrorHandling migration test PASSED")
        except Exception as e:
            print(f"❌ ErrorHandling migration test FAILED: {e}")
            raise

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Migration test only")
    def test_gas_after_migration(self):
        """Test gas functionality after migration and verify consistency"""
        print("\n=== Testing Gas After Migration ===")
        try:
            self._gas.before_migration_sc_behavior()
            start_runtime_upgrade_only()
            self._gas.after_migration_sc_behavior()
            self._gas.check_migration_difference()
            print("✅ Gas migration test PASSED")
        except Exception as e:
            print(f"❌ Gas migration test FAILED: {e}")
            raise

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Migration test only")
    def test_eip1153_after_migration(self):
        """Test EIP-1153 transient storage after migration and verify consistency"""
        print("\n=== Testing EIP1153 After Migration ===")
        try:
            self._eip1153.before_migration_sc_behavior()
            start_runtime_upgrade_only()
            self._eip1153.after_migration_sc_behavior()
            self._eip1153.check_migration_difference()
            print("✅ EIP1153 migration test PASSED")
        except Exception as e:
            print(f"❌ EIP1153 migration test FAILED: {e}")
            raise

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Migration test only")
    def test_eip5656_after_migration(self):
        """Test EIP-5656 MCOPY opcode after migration and verify consistency"""
        print("\n=== Testing EIP5656 After Migration ===")
        try:
            self._eip5656.before_migration_sc_behavior()
            start_runtime_upgrade_only()
            self._eip5656.after_migration_sc_behavior()
            self._eip5656.check_migration_difference()
            print("✅ EIP5656 migration test PASSED")
        except Exception as e:
            print(f"❌ EIP5656 migration test FAILED: {e}")
            raise