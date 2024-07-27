import unittest
import time
import pytest

from substrateinterface import SubstrateInterface
from peaq.utils import ExtrinsicBatch
from tools.peaq_eth_utils import get_contract
from tools.utils import KP_GLOBAL_SUDO
from tools.utils import WS_URL, ETH_URL
from tools.utils import get_account_balance_locked, sign_and_submit_evm_transaction
from tools.peaq_eth_utils import get_eth_chain_id
from tools.peaq_eth_utils import get_eth_info
from tools.utils import batch_fund
from web3 import Web3


VEST_ABI_FILE = 'ETH/vest/abi'
VEST_ADDR = '0x0000000000000000000000000000000000000808'
VEST_PERIOD = 100


@pytest.mark.eth
class TestBridgeVest(unittest.TestCase):
    def setUp(self):
        self._w3 = Web3(Web3.HTTPProvider(ETH_URL))
        self._substrate = SubstrateInterface(url=WS_URL)
        self._eth_chain_id = get_eth_chain_id(self._substrate)
        self._kp_moon = get_eth_info()
        self._kp_mars = get_eth_info()

    def evm_vest_transfer(self, contract, eth_kp_src, evm_dst, number, now):
        w3 = self._w3
        nonce = w3.eth.get_transaction_count(eth_kp_src.ss58_address)
        per_block = int(number / VEST_PERIOD)
        tx = contract.functions.vestedTransfer(evm_dst, int(number), per_block, now).build_transaction({
            'from': eth_kp_src.ss58_address,
            'gas': 10633039,
            'maxFeePerGas': w3.to_wei(250, 'gwei'),
            'maxPriorityFeePerGas': w3.to_wei(2, 'gwei'),
            'nonce': nonce,
            'chainId': self._eth_chain_id})

        return sign_and_submit_evm_transaction(tx, w3, eth_kp_src)

    def evm_vest(self, contract, eth_kp_src):
        w3 = self._w3
        nonce = w3.eth.get_transaction_count(eth_kp_src.ss58_address)
        tx = contract.functions.vest().build_transaction({
            'from': eth_kp_src.ss58_address,
            'gas': 10633039,
            'maxFeePerGas': w3.to_wei(250, 'gwei'),
            'maxPriorityFeePerGas': w3.to_wei(2, 'gwei'),
            'nonce': nonce,
            'chainId': self._eth_chain_id})

        return sign_and_submit_evm_transaction(tx, w3, eth_kp_src)

    def evm_vest_other(self, contract, eth_kp_src, evm_dst):
        w3 = self._w3
        nonce = w3.eth.get_transaction_count(eth_kp_src.ss58_address)
        tx = contract.functions.vestOther(evm_dst).build_transaction({
            'from': eth_kp_src.ss58_address,
            'gas': 10633039,
            'maxFeePerGas': w3.to_wei(250, 'gwei'),
            'maxPriorityFeePerGas': w3.to_wei(2, 'gwei'),
            'nonce': nonce,
            'chainId': self._eth_chain_id})

        return sign_and_submit_evm_transaction(tx, w3, eth_kp_src)

    def check_vested_transfer_from_event(self, event, caller, target, locked, per_block, starting_block):
        events = event.get_all_entries()
        self.assertEqual(f"{events[0]['args']['caller']}", caller)
        self.assertEqual(f"{events[0]['args']['target']}", target)
        self.assertEqual(events[0]['args']['locked'], locked)
        self.assertEqual(events[0]['args']['perBlock'], per_block)
        self.assertEqual(events[0]['args']['startingBlock'], starting_block)

    def check_vest_from_event(self, event, caller):
        events = event.get_all_entries()
        self.assertEqual(f"{events[0]['args']['caller']}", caller)

    def check_vest_others_from_event(self, event, caller, target):
        events = event.get_all_entries()
        self.assertEqual(f"{events[0]['args']['caller']}", caller)
        self.assertEqual(f"{events[0]['args']['target']}", target)

    def test_bridge_vest(self):
        contract = get_contract(self._w3, VEST_ADDR, VEST_ABI_FILE)

        batch = ExtrinsicBatch(self._substrate, KP_GLOBAL_SUDO)
        batch_fund(batch, self._kp_moon['substrate'], 100 * 10 ** 18)
        batch_fund(batch, self._kp_mars['substrate'], 100 * 10 ** 18)
        receipt = batch.execute()
        self.assertTrue(receipt.is_success)

        # VestTransfer
        now_block = self._substrate.get_block_number(None)
        print(f"now_block: {now_block}")
        tx_receipt = self.evm_vest_transfer(
            contract, self._kp_moon['kp'], self._kp_mars['eth'], 10 ** 18, now_block)
        self.assertTrue(tx_receipt.status)
        block_idx = tx_receipt['blockNumber']
        time.sleep(12)
        event = contract.events.VestedTransfer.create_filter(fromBlock=block_idx, toBlock=block_idx)
        self.check_vested_transfer_from_event(
            event,
            self._kp_moon['eth'],
            self._kp_mars['eth'],
            10 ** 18,
            int(10 ** 18 / VEST_PERIOD),
            now_block
        )

        # Vest
        prev_locked = get_account_balance_locked(self._substrate, self._kp_mars['substrate'])
        tx_receipt = self.evm_vest(contract, self._kp_mars['kp'])
        self.assertTrue(tx_receipt.status)
        now_locked = get_account_balance_locked(self._substrate, self._kp_mars['substrate'])
        self.assertLess(now_locked, prev_locked)
        block_idx = tx_receipt['blockNumber']
        event = contract.events.Vest.create_filter(fromBlock=block_idx, toBlock=block_idx)
        self.check_vest_from_event(
            event,
            self._kp_mars['eth'],
        )

        # VestOther
        prev_locked = get_account_balance_locked(self._substrate, self._kp_mars['substrate'])
        tx_receipt = self.evm_vest_other(
            contract, self._kp_moon['kp'], self._kp_mars['eth'])
        self.assertTrue(tx_receipt.status)
        now_locked = get_account_balance_locked(self._substrate, self._kp_mars['substrate'])
        self.assertLess(now_locked, prev_locked)
        block_idx = tx_receipt['blockNumber']
        event = contract.events.VestOther.create_filter(fromBlock=block_idx, toBlock=block_idx)
        self.check_vest_others_from_event(
            event,
            self._kp_moon['eth'],
            self._kp_mars['eth']
        )
