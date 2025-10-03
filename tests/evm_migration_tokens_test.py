"""
EVM Migration Test Suite - Token Standards (ERC20, ERC721, ERC1155)
This test file focuses on token standard implementations during migration.
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
from tests.evm_sc.erc20 import ERC20SmartContractBehavior
from tests.evm_sc.erc721 import ERC721SmartContractBehavior
from tests.evm_sc.erc1155 import ERC1155SmartContractBehavior


@pytest.mark.eth
@pytest.mark.detail_upgrade_check
class TestEVMTokensMigration(unittest.TestCase):
    """Test token standards behavior during EVM migration"""

    def setUp(self):
        """Setup test environment and initialize contracts"""
        restart_with_setup()
        wait_until_block_height(SubstrateInterface(url=WS_URL), 3)
        self._substrate = SubstrateInterface(url=WS_URL)
        self._w3 = Web3(Web3.HTTPProvider(ETH_URL))

        # Initialize token contracts
        self._erc20 = ERC20SmartContractBehavior(self, self._w3, get_eth_info())
        self._erc721 = ERC721SmartContractBehavior(self, self._w3, get_eth_info())
        self._erc1155 = ERC1155SmartContractBehavior(self, self._w3, get_eth_info())

        # Compose arguments for all contracts
        self._erc20.compose_all_args()
        self._erc721.compose_all_args()
        self._erc1155.compose_all_args()

        # Fund all required accounts
        ss58_addrs = []
        ss58_addrs += self._erc20.get_fund_ss58_keys()
        ss58_addrs += self._erc721.get_fund_ss58_keys()
        ss58_addrs += self._erc1155.get_fund_ss58_keys()

        funds(self._substrate, KP_GLOBAL_SUDO, ss58_addrs, 1000 * 10**18)

        # Deploy all contracts
        self._erc20.deploy()
        self._erc721.deploy()
        self._erc1155.deploy()

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="Pre-migration test only")
    def test_erc20_before_migration(self):
        """Test ERC20 functionality before migration"""
        print("\n=== Testing ERC20 Before Migration ===")
        try:
            self._erc20.before_migration_sc_behavior()
            print("✅ ERC20 pre-migration test PASSED")
        except Exception as e:
            print(f"❌ ERC20 pre-migration test FAILED: {e}")
            raise

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="Pre-migration test only")
    def test_erc721_before_migration(self):
        """Test ERC721 functionality before migration"""
        print("\n=== Testing ERC721 Before Migration ===")
        try:
            self._erc721.before_migration_sc_behavior()
            print("✅ ERC721 pre-migration test PASSED")
        except Exception as e:
            print(f"❌ ERC721 pre-migration test FAILED: {e}")
            raise

    @pytest.mark.skipif(is_runtime_upgrade_test() is True, reason="Pre-migration test only")
    def test_erc1155_before_migration(self):
        """Test ERC1155 functionality before migration"""
        print("\n=== Testing ERC1155 Before Migration ===")
        try:
            self._erc1155.before_migration_sc_behavior()
            print("✅ ERC1155 pre-migration test PASSED")
        except Exception as e:
            print(f"❌ ERC1155 pre-migration test FAILED: {e}")
            raise

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Migration test only")
    def test_erc20_after_migration(self):
        """Test ERC20 functionality after migration and verify consistency"""
        print("\n=== Testing ERC20 After Migration ===")
        try:
            # Run pre-migration behavior first
            self._erc20.before_migration_sc_behavior()

            # Perform runtime upgrade
            start_runtime_upgrade_only()

            # Test post-migration behavior
            self._erc20.after_migration_sc_behavior()
            self._erc20.check_migration_difference()
            print("✅ ERC20 migration test PASSED")
        except Exception as e:
            print(f"❌ ERC20 migration test FAILED: {e}")
            raise

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Migration test only")
    def test_erc721_after_migration(self):
        """Test ERC721 functionality after migration and verify consistency"""
        print("\n=== Testing ERC721 After Migration ===")
        try:
            # Run pre-migration behavior first
            self._erc721.before_migration_sc_behavior()

            # Perform runtime upgrade
            start_runtime_upgrade_only()

            # Test post-migration behavior
            self._erc721.after_migration_sc_behavior()
            self._erc721.check_migration_difference()
            print("✅ ERC721 migration test PASSED")
        except Exception as e:
            print(f"❌ ERC721 migration test FAILED: {e}")
            raise

    @pytest.mark.skipif(is_runtime_upgrade_test() is False, reason="Migration test only")
    def test_erc1155_after_migration(self):
        """Test ERC1155 functionality after migration and verify consistency"""
        print("\n=== Testing ERC1155 After Migration ===")
        try:
            # Run pre-migration behavior first
            self._erc1155.before_migration_sc_behavior()

            # Perform runtime upgrade
            start_runtime_upgrade_only()

            # Test post-migration behavior
            self._erc1155.after_migration_sc_behavior()
            self._erc1155.check_migration_difference()
            print("✅ ERC1155 migration test PASSED")
        except Exception as e:
            print(f"❌ ERC1155 migration test FAILED: {e}")
            raise