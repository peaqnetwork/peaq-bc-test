import pytest
import time

from substrateinterface import SubstrateInterface
from tools.constants import KP_GLOBAL_SUDO
from tools.runtime_upgrade import wait_until_block_height
from tools.constants import WS_URL, ETH_URL
from tools.peaq_eth_utils import get_eth_info
from peaq.sudo_extrinsic import funds
from web3 import Web3
from tests.utils_func import restart_with_setup, do_runtime_upgrade_with_setup
import unittest
# from tests.evm_sc.erc20 import ERC20SmartContractBehavior
# from tests.evm_sc.erc721 import ERC721SmartContractBehavior
# from tests.evm_sc.erc1155 import ERC1155SmartContractBehavior
# from tests.evm_sc.delegatecall import DelegateCallSCBehavior
# from tests.evm_sc.upgrade import UpgradeSCBehavior
# from tests.evm_sc.event import EventSCBehavior
# from tests.evm_sc.error_handling import ErrorHandlingSCBehavior
# from tests.evm_sc.struct import StructSCBehavior
from tests.evm_sc.reentry import ReentrySCBehavior

import pprint

pp = pprint.PrettyPrinter(indent=4)


@pytest.mark.eth
@pytest.mark.detail_upgrade_check
class TestEVMEthUpgrade(unittest.TestCase):
    def setUp(self):
        # restart_with_setup()
        wait_until_block_height(SubstrateInterface(url=WS_URL), 3)
        self._substrate = SubstrateInterface(url=WS_URL)
        self._w3 = Web3(Web3.HTTPProvider(ETH_URL))

    def test_same_behavior_upgrade(self):
        smart_contracts = [
            # ERC20SmartContractBehavior(self, self._w3, get_eth_info()),
            # ERC721SmartContractBehavior(self, self._w3, get_eth_info()),
            # ERC1155SmartContractBehavior(self, self._w3, get_eth_info()),
            # DelegateCallSCBehavior(self, self._w3, get_eth_info()),
            # UpgradeSCBehavior(self, self._w3, get_eth_info()),
            # EventSCBehavior(self, self._w3, get_eth_info()),
            # ErrorHandlingSCBehavior(self, self._w3, get_eth_info()),
            # StructSCBehavior(self, self._w3, get_eth_info()),
            ReentrySCBehavior(self, self._w3, get_eth_info()),
        ]
        for smart_contract in smart_contracts:
            smart_contract.compose_all_args()

        ss58_addrs = []
        for smart_contract in smart_contracts:
            ss58_addrs += smart_contract.get_fund_ss58_keys()

        funds(
            self._substrate, KP_GLOBAL_SUDO, ss58_addrs, 1000 * 10**18
        )

        for smart_contract in smart_contracts:
            smart_contract.deploy()

        for smart_contract in smart_contracts:
            smart_contract.before_migration_sc_behavior()
            time.sleep(6 * 3)

        # Upgrade
        # do_runtime_upgrade_with_setup()

        for smart_contract in smart_contracts:
            smart_contract.after_migration_sc_behavior()
            smart_contract.check_migration_difference()
            time.sleep(6 * 3)
