"""
EVM Migration Test Suite - Call Operations
This test file focuses on call operations, delegate calls, and related functionality.
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
from tests.evm_sc.delegatecall import DelegateCallSCBehavior
from tests.evm_sc.calltest import CallTestSCBehavior
from tests.evm_sc.reentry import ReentrySCBehavior
from tests.evm_sc.calldata import CalldataSCBehavior
from tests.evm_sc.calldata_heavy import CalldataHeavyTestBehavior


@pytest.mark.eth
@pytest.mark.detail_upgrade_check
class TestEVMCallsMigration(unittest.TestCase):
    """Test call operations behavior during EVM migration"""

    def setUp(self):
        """Setup test environment and initialize contracts"""
        restart_with_setup()
        wait_until_block_height(SubstrateInterface(url=WS_URL), 3)
        self._substrate = SubstrateInterface(url=WS_URL)
        self._w3 = Web3(Web3.HTTPProvider(ETH_URL))

        # Initialize call-related contracts
        self._delegatecall = DelegateCallSCBehavior(self, self._w3, get_eth_info())
        self._calltest = CallTestSCBehavior(self, self._w3, get_eth_info())
        self._reentry = ReentrySCBehavior(self, self._w3, get_eth_info())
        self._calldata = CalldataSCBehavior(self, self._w3, get_eth_info())
        self._calldata_heavy = CalldataHeavyTestBehavior(self, self._w3, get_eth_info())

        # Compose arguments for all contracts
        self._delegatecall.compose_all_args()
        self._calltest.compose_all_args()
        self._reentry.compose_all_args()
        self._calldata.compose_all_args()
        self._calldata_heavy.compose_all_args()

        # Fund all required accounts
        ss58_addrs = []
        ss58_addrs += self._delegatecall.get_fund_ss58_keys()
        ss58_addrs += self._calltest.get_fund_ss58_keys()
        ss58_addrs += self._reentry.get_fund_ss58_keys()
        ss58_addrs += self._calldata.get_fund_ss58_keys()
        ss58_addrs += self._calldata_heavy.get_fund_ss58_keys()

        funds(self._substrate, KP_GLOBAL_SUDO, ss58_addrs, 1000 * 10**18)

        # Deploy all contracts
        self._delegatecall.deploy()
        self._calltest.deploy()
        self._reentry.deploy()
        self._calldata.deploy()
        self._calldata_heavy.deploy()

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="Pre-migration test only")
    def test_delegatecall_before_migration(self):
        """Test delegate call functionality before migration"""
        print("\n=== Testing DelegateCall Before Migration ===")
        try:
            self._delegatecall.before_migration_sc_behavior()
            print("✅ DelegateCall pre-migration test PASSED")
        except Exception as e:
            print(f"❌ DelegateCall pre-migration test FAILED: {e}")
            raise

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="Pre-migration test only")
    def test_calltest_before_migration(self):
        """Test call test functionality before migration"""
        print("\n=== Testing CallTest Before Migration ===")
        try:
            self._calltest.before_migration_sc_behavior()
            print("✅ CallTest pre-migration test PASSED")
        except Exception as e:
            print(f"❌ CallTest pre-migration test FAILED: {e}")
            raise

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="Pre-migration test only")
    def test_reentry_before_migration(self):
        """Test reentrancy protection before migration"""
        print("\n=== Testing Reentry Before Migration ===")
        try:
            self._reentry.before_migration_sc_behavior()
            print("✅ Reentry pre-migration test PASSED")
        except Exception as e:
            print(f"❌ Reentry pre-migration test FAILED: {e}")
            raise

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="Pre-migration test only")
    def test_calldata_before_migration(self):
        """Test calldata functionality before migration"""
        print("\n=== Testing Calldata Before Migration ===")
        try:
            self._calldata.before_migration_sc_behavior()
            print("✅ Calldata pre-migration test PASSED")
        except Exception as e:
            print(f"❌ Calldata pre-migration test FAILED: {e}")
            raise

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="Pre-migration test only")
    def test_calldata_heavy_before_migration(self):
        """Test heavy calldata functionality before migration"""
        print("\n=== Testing CalldataHeavy Before Migration ===")
        try:
            self._calldata_heavy.before_migration_sc_behavior()
            print("✅ CalldataHeavy pre-migration test PASSED")
        except Exception as e:
            print(f"❌ CalldataHeavy pre-migration test FAILED: {e}")
            raise

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Migration test only")
    def test_delegatecall_after_migration(self):
        """Test delegate call functionality after migration and verify consistency"""
        print("\n=== Testing DelegateCall After Migration ===")
        try:
            self._delegatecall.before_migration_sc_behavior()
            start_runtime_upgrade_only()
            self._delegatecall.after_migration_sc_behavior()
            self._delegatecall.check_migration_difference()
            print("✅ DelegateCall migration test PASSED")
        except Exception as e:
            print(f"❌ DelegateCall migration test FAILED: {e}")
            raise

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Migration test only")
    def test_calltest_after_migration(self):
        """Test call test functionality after migration and verify consistency"""
        print("\n=== Testing CallTest After Migration ===")
        try:
            self._calltest.before_migration_sc_behavior()
            start_runtime_upgrade_only()
            self._calltest.after_migration_sc_behavior()
            self._calltest.check_migration_difference()
            print("✅ CallTest migration test PASSED")
        except Exception as e:
            print(f"❌ CallTest migration test FAILED: {e}")
            raise

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Migration test only")
    def test_reentry_after_migration(self):
        """Test reentrancy protection after migration and verify consistency"""
        print("\n=== Testing Reentry After Migration ===")
        try:
            self._reentry.before_migration_sc_behavior()
            start_runtime_upgrade_only()
            self._reentry.after_migration_sc_behavior()
            self._reentry.check_migration_difference()
            print("✅ Reentry migration test PASSED")
        except Exception as e:
            print(f"❌ Reentry migration test FAILED: {e}")
            raise

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Migration test only")
    def test_calldata_after_migration(self):
        """Test calldata functionality after migration and verify consistency"""
        print("\n=== Testing Calldata After Migration ===")
        try:
            self._calldata.before_migration_sc_behavior()
            start_runtime_upgrade_only()
            self._calldata.after_migration_sc_behavior()
            self._calldata.check_migration_difference()
            print("✅ Calldata migration test PASSED")
        except Exception as e:
            print(f"❌ Calldata migration test FAILED: {e}")
            raise

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Migration test only")
    def test_calldata_heavy_after_migration(self):
        """Test heavy calldata functionality after migration and verify consistency"""
        print("\n=== Testing CalldataHeavy After Migration ===")
        try:
            self._calldata_heavy.before_migration_sc_behavior()
            start_runtime_upgrade_only()
            self._calldata_heavy.after_migration_sc_behavior()
            self._calldata_heavy.check_migration_difference()
            print("✅ CalldataHeavy migration test PASSED")
        except Exception as e:
            print(f"❌ CalldataHeavy migration test FAILED: {e}")
            raise