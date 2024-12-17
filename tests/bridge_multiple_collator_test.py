import pytest
import unittest
from tests.utils_func import restart_parachain_and_runtime_upgrade
from tools.runtime_upgrade import wait_until_block_height
from substrateinterface import SubstrateInterface, Keypair
from tools.constants import WS_URL, ETH_URL, RELAYCHAIN_WS_URL
from tests.evm_utils import sign_and_submit_evm_transaction
from peaq.utils import ExtrinsicBatch
from tools.peaq_eth_utils import get_contract
from tools.peaq_eth_utils import get_eth_chain_id
from tools.peaq_eth_utils import get_eth_info
from tools.constants import KP_GLOBAL_SUDO, KP_COLLATOR
from peaq.utils import get_block_hash
from web3 import Web3


PARACHAIN_STAKING_ABI_FILE = 'ETH/parachain-staking/abi'
PARACHAIN_STAKING_ADDR = '0x0000000000000000000000000000000000000807'


# [TODO] Should refine the functions
@pytest.mark.relaunch
@pytest.mark.eth
class bridge_parachain_staking_collators_test(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        restart_parachain_and_runtime_upgrade()
        wait_until_block_height(SubstrateInterface(url=RELAYCHAIN_WS_URL), 2)
        wait_until_block_height(SubstrateInterface(url=WS_URL), 2)

    def setUp(self):
        wait_until_block_height(SubstrateInterface(url=WS_URL), 3)

        self._substrate = SubstrateInterface(url=WS_URL)
        self._w3 = Web3(Web3.HTTPProvider(ETH_URL))
        self._kp_moon = get_eth_info()
        self._kp_mars = get_eth_info()
        self._eth_chain_id = get_eth_chain_id(self._substrate)
        self._kp_src = Keypair.create_from_uri('//Moon')

    def _fund_users(self, num=100 * 10 ** 18):
        if num < 100 * 10 ** 18:
            num = 100 * 10 ** 18
        # Fund users
        batch = ExtrinsicBatch(self._substrate, KP_GLOBAL_SUDO)
        batch.compose_sudo_call(
            'Balances',
            'force_set_balance',
            {
                'who': self._kp_moon['substrate'],
                'new_free': num,
            }
        )
        batch.compose_sudo_call(
            'Balances',
            'force_set_balance',
            {
                'who': self._kp_mars['substrate'],
                'new_free': num,
            }
        )
        batch.compose_sudo_call(
            'Balances',
            'force_set_balance',
            {
                'who': self._kp_src.ss58_address,
                'new_free': num,
            }
        )
        return batch.execute()

    def evm_join_delegators(self, contract, eth_kp_src, sub_collator_addr, stake):
        w3 = self._w3
        nonce = w3.eth.get_transaction_count(eth_kp_src.ss58_address)
        tx = contract.functions.joinDelegators(sub_collator_addr, stake).build_transaction({
            'from': eth_kp_src.ss58_address,
            'nonce': nonce,
            'chainId': self._eth_chain_id})

        return sign_and_submit_evm_transaction(tx, w3, eth_kp_src)

    def evm_delegate_another_candidate(self, contract, eth_kp_src, sub_collator_addr, stake):
        w3 = self._w3
        nonce = w3.eth.get_transaction_count(eth_kp_src.ss58_address)
        tx = contract.functions.delegateAnotherCandidate(sub_collator_addr, stake).build_transaction({
            'from': eth_kp_src.ss58_address,
            'nonce': nonce,
            'chainId': self._eth_chain_id})

        return sign_and_submit_evm_transaction(tx, w3, eth_kp_src)

    def evm_delegator_leave_delegators(self, contract, eth_kp_src):
        w3 = self._w3
        nonce = w3.eth.get_transaction_count(eth_kp_src.ss58_address)
        tx = contract.functions.leaveDelegators().build_transaction({
            'from': eth_kp_src.ss58_address,
            'nonce': nonce,
            'chainId': self._eth_chain_id})

        return sign_and_submit_evm_transaction(tx, w3, eth_kp_src)

    def evm_delegator_revoke_delegation(self, contract, eth_kp_src, sub_collator_addr):
        w3 = self._w3
        nonce = w3.eth.get_transaction_count(eth_kp_src.ss58_address)
        tx = contract.functions.revokeDelegation(sub_collator_addr).build_transaction({
            'from': eth_kp_src.ss58_address,
            'nonce': nonce,
            'chainId': self._eth_chain_id})

        return sign_and_submit_evm_transaction(tx, w3, eth_kp_src)

    def evm_delegator_unlock_unstaked(self, contract, eth_kp_src, eth_addr):
        w3 = self._w3
        nonce = w3.eth.get_transaction_count(eth_kp_src.ss58_address)
        tx = contract.functions.unlockUnstaked(eth_addr).build_transaction({
            'from': eth_kp_src.ss58_address,
            'nonce': nonce,
            'chainId': self._eth_chain_id})

        return sign_and_submit_evm_transaction(tx, w3, eth_kp_src)

    def get_stake_number(self, sub_addr):
        data = self._substrate.query('ParachainStaking', 'DelegatorState', [sub_addr])
        # {'delegations':
        #       [{'owner': '5CiPPseXPECbkjWCa6MnjNokrgYjMqmKndv2rSnekmSK2DjL', 'amount': 262144000}],
        #  'total': 262144000}
        return data.value

    def get_event(self, block_hash, module, event):
        events = self._substrate.get_events(block_hash)
        for e in events:
            if e.value['event']['module_id'] == module and e.value['event']['event_id'] == event:
                return {'attributes': e.value['event']['attributes']}
        return None

    def test_delegator_another_candidate(self):
        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
        out = contract.functions.getCollatorList().call()
        collator_num = out[0][1]
        collator_eth_addr = out[0][0]

        # Fund users
        receipt = self._fund_users(collator_num * 3)
        self.assertEqual(receipt.is_success, True, f'fund_users fails, receipt: {receipt}')

        evm_receipt = self.evm_join_delegators(contract, self._kp_moon['kp'], collator_eth_addr, collator_num)
        self.assertEqual(evm_receipt['status'], 1, f'join fails, evm_receipt: {evm_receipt}')
        bl_hash = get_block_hash(self._substrate, evm_receipt['blockNumber'])
        event = self.get_event(bl_hash, 'ParachainStaking', 'Delegation')
        self.assertEqual(
            event['attributes'],
            (self._kp_moon['substrate'], collator_num, KP_COLLATOR.ss58_address, 2 * collator_num),
            f'join fails, event: {event}')

        # Check the delegator's stake
        stake = self.get_stake_number(self._kp_moon['substrate'])
        self.assertEqual(stake['total'], collator_num, f'join fails, stake: {stake}, collator_num: {collator_num}')

        batch = ExtrinsicBatch(self._substrate, self._kp_src)
        batch.compose_call(
            'ParachainStaking',
            'join_candidates',
            {
                'stake': collator_num
            }
        )
        receipt = batch.execute()
        self.assertEqual(receipt.is_success, True, f'joinCandidate fails, receipt: {receipt}')

        # Force session * 2
        batch = ExtrinsicBatch(self._substrate, KP_GLOBAL_SUDO)
        batch.compose_sudo_call(
            'ParachainStaking',
            'force_new_round',
            {}
        )
        receipt = batch.execute()
        self.assertEqual(receipt.is_success, True, f'force_new_round fails, receipt: {receipt}')
        receipt = batch.execute()
        self.assertEqual(receipt.is_success, True, f'force_new_round fails, receipt: {receipt}')

        out = contract.functions.getCollatorList().call()
        collator_eth_addr = out[0][0]
        collator_eth_addr = [out[i][0] for i in range(len(out)) if out[i][0] != collator_eth_addr][0]

        evm_receipt = self.evm_delegate_another_candidate(contract, self._kp_moon['kp'], collator_eth_addr, collator_num)
        self.assertEqual(evm_receipt['status'], 1, f'join fails, evm_receipt: {evm_receipt}')
        stake = self.get_stake_number(self._kp_moon['substrate'])
        self.assertEqual(stake['total'], collator_num * 2, f'join fails, stake: {stake}, collator_num: {collator_num * 2}')

        # Force leave all
        evm_receipt = self.evm_delegator_leave_delegators(contract, self._kp_moon['kp'])
        self.assertEqual(evm_receipt['status'], 1, f'leave fails, evm_receipt: {evm_receipt}')
        stake = self.get_stake_number(self._kp_moon['substrate'])
        self.assertEqual(stake, None)
