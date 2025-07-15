import pytest
import unittest
from substrateinterface import SubstrateInterface
from web3 import Web3
from tools.constants import WS_URL, ETH_URL
from tools.peaq_eth_utils import get_eth_info
from tools.runtime_upgrade import wait_until_block_height
from tests.utils_func import restart_with_setup
from tests.evm_sc.event import EventSCBehavior
from peaq.utils import ExtrinsicBatch
from peaq.eth import calculate_evm_account
from tools.peaq_eth_utils import calculate_asset_to_evm_address
from tools.constants import KP_GLOBAL_SUDO
from peaq.utils import get_account_balance


@pytest.mark.eth
class TestEVMEventOnly(unittest.TestCase):
    def setUp(self):
        restart_with_setup()
        wait_until_block_height(SubstrateInterface(url=WS_URL), 3)
        self._substrate = SubstrateInterface(url=WS_URL)
        self._w3 = Web3(Web3.HTTPProvider(ETH_URL))
        self._kp_src = get_eth_info()

    def test_evm_event_only(self):
        """Test only the event-emitting contract"""
        # Fund the account
        batch = ExtrinsicBatch(self._substrate, KP_GLOBAL_SUDO)
        batch.compose_sudo_call(
            'Balances',
            'force_set_balance',
            {
                'who': self._kp_src['substrate'],
                'new_free': 10000 * 10**18,
            }
        )
        receipt = batch.execute()
        self.assertTrue(receipt.is_success, f"Failed to fund account: {receipt.error_message}")
        
        # Transfer some balance to EVM account
        eth_deposited_src = calculate_evm_account(self._kp_src['substrate'])
        balance_before = get_account_balance(self._substrate, eth_deposited_src)
        
        batch = ExtrinsicBatch(self._substrate, self._kp_src['kp'])
        batch.compose_call(
            'EVM',
            'deposit',
            {
                'target': calculate_asset_to_evm_address(self._kp_src['eth']),
                'value': 100 * 10**18,
            }
        )
        receipt = batch.execute()
        self.assertTrue(receipt.is_success, f"Failed to deposit to EVM: {receipt.error_message}")
        
        # Create and test the event contract
        event_contract = EventSCBehavior(self, self._w3, self._kp_src)
        
        # Deploy the contract
        event_contract.deploy()
        
        # Trigger events
        event_contract.trigger_event()
        
        print("Event contract test completed successfully!")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])