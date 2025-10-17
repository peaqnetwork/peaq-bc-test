"""
EVM Migration Test Suite - Precompile Operations
This test file focuses on precompile contracts and chain info operations.
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
from tests.evm_sc.precompile import PrecompileTestSCBehavior
from tests.evm_sc.precompile_direct import PrecompileDirectTestBehavior
from tests.evm_sc.chain_info import ChainInfoTestBehavior


@pytest.mark.eth
@pytest.mark.detail_upgrade_check
class TestEVMPrecompileMigration(unittest.TestCase):
    """Test precompile operations behavior during EVM migration"""

    def setUp(self):
        """Setup test environment and initialize contracts"""
        restart_with_setup()
        wait_until_block_height(SubstrateInterface(url=WS_URL), 3)
        self._substrate = SubstrateInterface(url=WS_URL)
        self._w3 = Web3(Web3.HTTPProvider(ETH_URL))

        # Initialize precompile-related contracts
        self._precompile = PrecompileTestSCBehavior(self, self._w3, get_eth_info())
        self._precompile_direct = PrecompileDirectTestBehavior(self, self._w3, get_eth_info())
        self._chain_info = ChainInfoTestBehavior(self, self._w3, get_eth_info())

        # Compose arguments for all contracts
        self._precompile.compose_all_args()
        self._precompile_direct.compose_all_args()
        self._chain_info.compose_all_args()

        # Fund all required accounts
        ss58_addrs = []
        ss58_addrs += self._precompile.get_fund_ss58_keys()
        ss58_addrs += self._precompile_direct.get_fund_ss58_keys()
        ss58_addrs += self._chain_info.get_fund_ss58_keys()

        funds(self._substrate, KP_GLOBAL_SUDO, ss58_addrs, 1000 * 10**18)

        # Deploy all contracts
        self._precompile.deploy()
        self._precompile_direct.deploy()
        self._chain_info.deploy()

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="No-upgrade test")
    def test_precompile_no_upgrade(self):
        """Test precompile functionality without runtime upgrade"""
        print("\n=== Testing Precompile No Upgrade ===")
        self._precompile.run_test_scenario()
        print("✅ Precompile no-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="No-upgrade test")
    def test_precompile_direct_no_upgrade(self):
        """Test direct precompile functionality without runtime upgrade"""
        print("\n=== Testing PrecompileDirect No Upgrade ===")
        self._precompile_direct.run_test_scenario()
        print("✅ PrecompileDirect no-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="No-upgrade test")
    def test_chain_info_no_upgrade(self):
        """Test chain info functionality without runtime upgrade"""
        print("\n=== Testing ChainInfo No Upgrade ===")
        self._chain_info.run_test_scenario()
        print("✅ ChainInfo no-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Upgrade test")
    def test_precompile_with_upgrade(self):
        """Test precompile functionality with runtime upgrade and verify consistency"""
        print("\n=== Testing Precompile With Upgrade ===")
        self._precompile.run_test_scenario()
        start_runtime_upgrade_only()
        self._precompile.run_post_upgrade_scenario()
        self._precompile.check_migration_difference()
        print("✅ Precompile with-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Upgrade test")
    def test_precompile_direct_with_upgrade(self):
        """Test direct precompile functionality with runtime upgrade and verify consistency"""
        print("\n=== Testing PrecompileDirect With Upgrade ===")
        self._precompile_direct.run_test_scenario()
        start_runtime_upgrade_only()
        self._precompile_direct.run_post_upgrade_scenario()
        self._precompile_direct.check_migration_difference()
        print("✅ PrecompileDirect with-upgrade test PASSED")

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Upgrade test")
    def test_chain_info_with_upgrade(self):
        """Test chain info functionality with runtime upgrade and verify consistency"""
        print("\n=== Testing ChainInfo With Upgrade ===")
        self._chain_info.run_test_scenario()
        start_runtime_upgrade_only()
        self._chain_info.run_post_upgrade_scenario()
        self._chain_info.check_migration_difference()
        print("✅ ChainInfo with-upgrade test PASSED")