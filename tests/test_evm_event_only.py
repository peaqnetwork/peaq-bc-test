import pytest
import unittest
from substrateinterface import SubstrateInterface
from web3 import Web3
from tools.constants import WS_URL, ETH_URL
from tools.peaq_eth_utils import get_eth_info
from tools.runtime_upgrade import wait_until_block_height
from tests.evm_sc.event import EventSCBehavior
from peaq.utils import ExtrinsicBatch
from tools.constants import KP_GLOBAL_SUDO
from tools.coretime_utils import get_parachain_id
# from tools.coretime_utils import setup_coretime


@pytest.mark.eth
class TestEVMEventOnly(unittest.TestCase):
    def setUp(self):
        wait_until_block_height(SubstrateInterface(url=WS_URL), 3)
        self._substrate = SubstrateInterface(url=WS_URL)
        self._w3 = Web3(Web3.HTTPProvider(ETH_URL))
        self._kp_src = get_eth_info()

        # Setup coretime cores
        parachain_id = get_parachain_id()
        self.assertIsNotNone(parachain_id, "Parachain ID must exist")
        # cores_assigned = setup_coretime(parachain_id)
        # print(f"Coretime setup: {cores_assigned} cores assigned for parachain {parachain_id}")

    def test_evm_event_only(self):
        """Test only the event-emitting contract"""
        # Fund the Ethereum address directly using Address20 format
        batch = ExtrinsicBatch(self._substrate, KP_GLOBAL_SUDO)
        batch.compose_sudo_call(
            'Balances',
            'force_set_balance',
            {
                'who': {'Address20': self._kp_src['kp'].ss58_address},
                'new_free': 10000 * 10**18,
            }
        )
        receipt = batch.execute()
        self.assertTrue(receipt.is_success, f"Failed to fund account: {receipt.error_message}")

        # Create and test the event contract
        event_contract = EventSCBehavior(self, self._w3, self._kp_src)

        # Deploy the contract
        event_contract.deploy()

        # Trigger events
        event_contract.trigger_event()

        print("Event contract test completed successfully!")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
