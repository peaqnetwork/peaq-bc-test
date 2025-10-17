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

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="No-upgrade test")
    def test_delegatecall_no_upgrade(self):
        """Test delegate call functionality without runtime upgrade"""
        print("\n=== Testing DelegateCall No Upgrade ===")
        self._delegatecall.run_test_scenario()
        print("✅ DelegateCall no-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="No-upgrade test")
    def test_calltest_no_upgrade(self):
        """Test call test functionality without runtime upgrade"""
        print("\n=== Testing CallTest No Upgrade ===")
        self._calltest.run_test_scenario()
        print("✅ CallTest no-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="No-upgrade test")
    def test_reentry_no_upgrade(self):
        """Test reentrancy protection without runtime upgrade"""
        print("\n=== Testing Reentry No Upgrade ===")
        self._reentry.run_test_scenario()
        print("✅ Reentry no-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="No-upgrade test")
    def test_calldata_no_upgrade(self):
        """Test calldata functionality without runtime upgrade"""
        print("\n=== Testing Calldata No Upgrade ===")
        self._calldata.run_test_scenario()
        print("✅ Calldata no-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="No-upgrade test")
    def test_calldata_heavy_no_upgrade(self):
        """Test heavy calldata functionality without runtime upgrade"""
        print("\n=== Testing CalldataHeavy No Upgrade ===")
        self._calldata_heavy.run_test_scenario()
        print("✅ CalldataHeavy no-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Upgrade test")
    def test_delegatecall_with_upgrade(self):
        """Test delegate call functionality with runtime upgrade and verify consistency"""
        print("\n=== Testing DelegateCall With Upgrade ===")
        self._delegatecall.run_test_scenario()
        start_runtime_upgrade_only()
        self._delegatecall.run_post_upgrade_scenario()
        self._delegatecall.check_migration_difference()
        print("✅ DelegateCall with-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Upgrade test")
    def test_calltest_with_upgrade(self):
        """Test call test functionality with runtime upgrade and verify consistency"""
        print("\n=== Testing CallTest With Upgrade ===")
        self._calltest.run_test_scenario()
        start_runtime_upgrade_only()
        self._calltest.run_post_upgrade_scenario()
        self._calltest.check_migration_difference()
        print("✅ CallTest with-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Upgrade test")
    def test_reentry_with_upgrade(self):
        """Test reentrancy protection with runtime upgrade and verify consistency"""
        print("\n=== Testing Reentry With Upgrade ===")
        self._reentry.run_test_scenario()
        start_runtime_upgrade_only()
        self._reentry.run_post_upgrade_scenario()
        self._reentry.check_migration_difference()
        print("✅ Reentry with-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Upgrade test")
    def test_calldata_with_upgrade(self):
        """Test calldata functionality with runtime upgrade and verify consistency"""
        print("\n=== Testing Calldata With Upgrade ===")
        self._calldata.run_test_scenario()
        start_runtime_upgrade_only()
        self._calldata.run_post_upgrade_scenario()
        self._calldata.check_migration_difference()
        print("✅ Calldata with-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Upgrade test")
    def test_calldata_heavy_with_upgrade(self):
        """Test heavy calldata functionality with runtime upgrade and verify consistency"""
        print("\n=== Testing CalldataHeavy With Upgrade ===")
        self._calldata_heavy.run_test_scenario()
        start_runtime_upgrade_only()
        self._calldata_heavy.run_post_upgrade_scenario()
        self._calldata_heavy.check_migration_difference()
        print("✅ CalldataHeavy with-upgrade test PASSED")