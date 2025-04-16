import pytest

from substrateinterface import SubstrateInterface
from tools.constants import KP_GLOBAL_SUDO
from tools.runtime_upgrade import wait_until_block_height
from tools.constants import WS_URL, ETH_URL
from tools.peaq_eth_utils import get_eth_info
from peaq.sudo_extrinsic import funds
from web3 import Web3
from tests.utils_func import restart_with_setup, do_runtime_upgrade_with_setup
import unittest
from tests.evm_sc.erc20 import ERC20SmartContractBehavior

import pprint

pp = pprint.PrettyPrinter(indent=4)


@pytest.mark.eth
@pytest.mark.detail_upgrade_check
class TestEVMEthUpgrade(unittest.TestCase):
    def setUp(self):
        # restart_with_setup()
        # Restart to make sure it in the old state
        wait_until_block_height(SubstrateInterface(url=WS_URL), 3)
        self._substrate = SubstrateInterface(url=WS_URL)
        self._w3 = Web3(Web3.HTTPProvider(ETH_URL))

    def test_same_behavior_upgrade(self):
        erc20SC = ERC20SmartContractBehavior(self, self._w3, get_eth_info())
        erc20SC.compose_all_args()

        funds(
            self._substrate, KP_GLOBAL_SUDO, erc20SC.get_fund_ss58_keys(), 1000 * 10**18
        )

        erc20SC.deploy()

        erc20SC.before_migration_sc_behavior()

        # Upgrade
        do_runtime_upgrade_with_setup()

        erc20SC.after_migration_sc_behavior()

        erc20SC.check_migration_difference()
