import pytest
import unittest
from tests.utils_func import restart_parachain_and_runtime_upgrade
from tools.runtime_upgrade import wait_until_block_height
from substrateinterface import SubstrateInterface, Keypair
from tools.constants import WS_URL, ETH_URL, RELAYCHAIN_WS_URL
from tests.evm_utils import sign_and_submit_evm_transaction
from peaq.utils import ExtrinsicBatch
from tests import utils_func as TestUtils
from tools.peaq_eth_utils import get_contract
from tools.peaq_eth_utils import get_eth_chain_id
from tools.peaq_eth_utils import get_eth_info
from tools.evm_claim_sign import calculate_claim_signature, claim_account
from tools.constants import KP_GLOBAL_SUDO, KP_COLLATOR, BLOCK_GENERATE_TIME
from peaq.utils import get_block_hash, get_chain
from tools.utils import get_modified_chain_spec
from web3 import Web3


PARACHAIN_STAKING_ABI_FILE = 'ETH/parachain-staking/abi'
PARACHAIN_STAKING_ADDR = '0x0000000000000000000000000000000000000807'

UNSTAKING_PERIOD_BLOCKS = {
    'peaq-network': int(14 * 24 * 60 * 60 / BLOCK_GENERATE_TIME),
    'peaq-dev': int(7 * 60 / BLOCK_GENERATE_TIME),
    'krest-network': int(4 * 60 * 60 / BLOCK_GENERATE_TIME),
}


@pytest.mark.relaunch
@pytest.mark.eth
class bridge_parachain_staking_test(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        restart_parachain_and_runtime_upgrade()
        wait_until_block_height(SubstrateInterface(url=RELAYCHAIN_WS_URL), 1)
        wait_until_block_height(SubstrateInterface(url=WS_URL), 1)

    def setUp(self):
        wait_until_block_height(SubstrateInterface(url=WS_URL), 1)

        self._substrate = SubstrateInterface(url=WS_URL)
        self._w3 = Web3(Web3.HTTPProvider(ETH_URL))
        self._kp_moon = get_eth_info()
        self._kp_mars = get_eth_info()
        self._eth_chain_id = get_eth_chain_id(self._substrate)
        self._kp_src = Keypair.create_from_uri('//Moon')
        self._kp_new_collator = Keypair.create_from_uri('//NewMoon01')
        self._chain_spec = get_modified_chain_spec(get_chain(self._substrate))

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
        batch.compose_sudo_call(
            'Balances',
            'force_set_balance',
            {
                'who': self._kp_new_collator.ss58_address,
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

    def evm_delegator_stake_more(self, contract, eth_kp_src, sub_collator_addr, stake):
        w3 = self._w3
        nonce = w3.eth.get_transaction_count(eth_kp_src.ss58_address)
        tx = contract.functions.delegatorStakeMore(sub_collator_addr, stake).build_transaction({
            'from': eth_kp_src.ss58_address,
            'nonce': nonce,
            'chainId': self._eth_chain_id})

        return sign_and_submit_evm_transaction(tx, w3, eth_kp_src)

    def evm_delegator_stake_less(self, contract, eth_kp_src, sub_collator_addr, stake):
        w3 = self._w3
        nonce = w3.eth.get_transaction_count(eth_kp_src.ss58_address)
        tx = contract.functions.delegatorStakeLess(sub_collator_addr, stake).build_transaction({
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

    def test_get_collator_list(self):
        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)

        out = contract.functions.getCollatorList().call()
        out = sorted(out, key=lambda x: x[1], reverse=True)
        golden_data = self._substrate.query('ParachainStaking', 'TopCandidates')
        golden_data = golden_data.value
        self.assertEqual(len(out), len(golden_data))

        for i in range(len(out)):
            # self.assertEqual(out[i]['addr'], golden_data[i]['collator'])
            pk = bytes.fromhex(self._substrate.ss58_decode(golden_data[i]["owner"]))
            self.assertEqual(out[i][0], pk)
            self.assertEqual(out[i][1], golden_data[i]['amount'])

    def get_event(self, block_hash, module, event):
        events = self._substrate.get_events(block_hash)
        for e in events:
            if e.value['event']['module_id'] == module and e.value['event']['event_id'] == event:
                return {'attributes': e.value['event']['attributes']}
        return None

    # Make sure the lock token cannot be transfered
    @pytest.mark.skipif(not TestUtils.is_not_dev_chain(), reason='Run on other chain')
    def test_evm_api_cannot_transfer_over_stake_others(self):
        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
        out = contract.functions.getCollatorList().call()
        out = sorted(out, key=lambda x: x[1], reverse=True)

        collator_eth_addr = out[0][0]
        collator_num = out[0][1]
        receipt = self._fund_users(collator_num * 2)
        self.assertEqual(receipt.is_success, True, f'fund_users fails, receipt: {receipt}')

        evm_receipt = self.evm_join_delegators(contract, self._kp_moon['kp'], collator_eth_addr, collator_num)
        self.assertEqual(evm_receipt['status'], 1, f'join fails, evm_receipt: {evm_receipt}')
        bl_hash = get_block_hash(self._substrate, evm_receipt['blockNumber'])
        event = self.get_event(bl_hash, 'ParachainStaking', 'Delegation')
        self.assertEqual(
            event['attributes'],
            (self._kp_moon['substrate'], collator_num, KP_COLLATOR.ss58_address, 2 * collator_num),
            f'join fails, event: {event}')

        stake = self.get_stake_number(self._kp_moon['substrate'])
        self.assertEqual(stake['total'], collator_num, f'join fails, stake: {stake}, collator_num: {collator_num}')

        transfer_token = int(stake['delegations'][0]['amount'] * 1.5)
        tx = {
            'to': self._kp_mars['eth'],
            'value': transfer_token,
            'nonce': self._w3.eth.get_transaction_count(self._kp_moon['eth']),
            'chainId': self._eth_chain_id,
            'gas': 21000,
            'maxFeePerGas': 1000 * 10 ** 9,
            'maxPriorityFeePerGas': 1000 * 10 ** 9,
        }
        with self.assertRaises(ValueError) as tx_info:
            sign_and_submit_evm_transaction(tx, self._w3, self._kp_moon['kp'])

        self.assertIn('insufficient funds', tx_info.exception.args[0]['message'])

    # Make sure the lock token cannot be transfered
    @pytest.mark.skipif(TestUtils.is_not_dev_chain(), reason='Only run on dev chain')
    def test_evm_api_cannot_transfer_over_stake_agung(self):
        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
        out = contract.functions.getCollatorList().call()
        out = sorted(out, key=lambda x: x[1], reverse=True)

        collator_eth_addr = out[0][0]
        collator_num = out[0][1]
        receipt = self._fund_users(collator_num * 2)
        self.assertEqual(receipt.is_success, True, f'fund_users fails, receipt: {receipt}')

        evm_receipt = self.evm_join_delegators(contract, self._kp_moon['kp'], collator_eth_addr, collator_num)
        self.assertEqual(evm_receipt['status'], 1, f'join fails, evm_receipt: {evm_receipt}')
        bl_hash = get_block_hash(self._substrate, evm_receipt['blockNumber'])
        event = self.get_event(bl_hash, 'ParachainStaking', 'Delegation')
        self.assertEqual(
            event['attributes'],
            (self._kp_moon['substrate'], collator_num, KP_COLLATOR.ss58_address, 2 * collator_num),
            f'join fails, event: {event}')

        stake = self.get_stake_number(self._kp_moon['substrate'])
        self.assertEqual(stake['total'], collator_num, f'join fails, stake: {stake}, collator_num: {collator_num}')

        transfer_token = int(stake['delegations'][0]['amount'] * 1.5)
        tx = {
            'to': self._kp_mars['eth'],
            'value': transfer_token,
            'nonce': self._w3.eth.get_transaction_count(self._kp_moon['eth']),
            'chainId': self._eth_chain_id,
            'gas': 21000,
            'maxFeePerGas': 1000 * 10 ** 9,
            'maxPriorityFeePerGas': 1000 * 10 ** 9,
        }
        receipt = sign_and_submit_evm_transaction(tx, self._w3, self._kp_moon['kp'])
        # Need to check whether the other chain...
        block_hash = get_block_hash(self._substrate, receipt['blockNumber'])
        event = self.get_event(block_hash, 'Ethereum', 'Executed')
        self.assertEqual(event['attributes']['exit_reason']['Succeed'], 'Stopped', f'transfer fails, receipt: {receipt}, event: {event}')

    def test_delegator_join_more_less_leave(self):
        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
        out = contract.functions.getCollatorList().call()
        out = sorted(out, key=lambda x: x[1], reverse=True)

        collator_eth_addr = out[0][0]
        collator_num = out[0][1]
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

        stake = self.get_stake_number(self._kp_moon['substrate'])
        self.assertEqual(stake['total'], collator_num, f'join fails, stake: {stake}, collator_num: {collator_num}')

        # Delegator stake more
        evm_receipt = self.evm_delegator_stake_more(contract, self._kp_moon['kp'], collator_eth_addr, collator_num)
        self.assertEqual(evm_receipt['status'], 1, f'stake more fails, evm_receipt: {evm_receipt}')

        # Check the delegator's stake
        stake = self.get_stake_number(self._kp_moon['substrate'])
        self.assertEqual(stake['total'], collator_num * 2, f'join fails, stake: {stake}, collator_num: {collator_num}')

        # Delegator stake less
        evm_receipt = self.evm_delegator_stake_less(contract, self._kp_moon['kp'], collator_eth_addr, collator_num)
        self.assertEqual(evm_receipt['status'], 1, f'stake more fails, evm_receipt: {evm_receipt}')

        # Check the delegator's stake
        stake = self.get_stake_number(self._kp_moon['substrate'])
        self.assertEqual(stake['total'], collator_num, f'join fails, stake: {stake}, collator_num: {collator_num}')

        # Delegator leave
        evm_receipt = self.evm_delegator_leave_delegators(contract, self._kp_moon['kp'])
        self.assertEqual(evm_receipt['status'], 1, f'leave fails, evm_receipt: {evm_receipt}')
        bl_hash = get_block_hash(self._substrate, evm_receipt['blockNumber'])
        event = self.get_event(bl_hash, 'ParachainStaking', 'DelegatorLeft')
        self.assertEqual(
            event['attributes'],
            (self._kp_moon['substrate'], collator_num),
            f'join fails, event: {event}')

        # Check unstaking period timing
        leave_block_number = evm_receipt['blockNumber']
        unstaking_data = self._substrate.query('ParachainStaking', 'Unstaking', [self._kp_moon['substrate']])
        self.assertTrue(unstaking_data.value, f'No unstaking data found or unstaking list is empty for delegator {self._kp_moon["substrate"]}')

        # Get chain-specific unstaking period
        unstaking_period = UNSTAKING_PERIOD_BLOCKS[self._chain_spec]
        expected_unlock_block = leave_block_number + unstaking_period

        # Extract the latest (most recent) unstaking entry - the one with the highest block number
        latest_unstaking_entry = max(unstaking_data.value, key=lambda x: x[0])
        actual_unlock_block = latest_unstaking_entry[0]

        self.assertEqual(
            actual_unlock_block,
            expected_unlock_block,
            f'Unstaking unlock block mismatch. Expected: {expected_unlock_block}, '
            f'Actual: {actual_unlock_block}, Leave block: {leave_block_number}, '
            f'Chain: {self._chain_spec}, Period: {unstaking_period}'
        )

    def set_commission_rate(self, rate, kp=KP_COLLATOR):
        batch = ExtrinsicBatch(self._substrate, kp)
        batch.compose_call(
            'ParachainStaking',
            'set_commission',
            {
                'commission': rate * 10_000,
            }
        )
        return batch.execute()

    def test_commission_rate(self):
        # Set commission rate as 20
        receipt = self.set_commission_rate(20)
        self.assertEqual(receipt.is_success, True, f'set_commission fails, receipt: {receipt}')

        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
        out = contract.functions.getCollatorList().call()
        out = sorted(out, key=lambda x: x[1], reverse=True)
        all_colators_info = self._substrate.query_map(
            module='ParachainStaking',
            storage_function='CandidatePool',
            params=[],
            start_key=None,
            page_size=1000,
        )

        evm_out = {info[0]: {
            'amount': info[1],
            'commission': info[2],
        } for info in out}

        for collator_id, collator_info in all_colators_info.records:
            pk = bytes.fromhex(self._substrate.ss58_decode(collator_info.value['id']))
            self.assertEqual(
                evm_out[pk]['commission'],
                collator_info.value['commission'],
                f'commission rate fails, out: {out}, all_colators_info: {all_colators_info}')
            self.assertEqual(
                evm_out[pk]['amount'],
                collator_info.value['stake'],
                f'commission rate fails, out: {out}, all_colators_info: {all_colators_info}')

        receipt = self.set_commission_rate(0)
        self.assertEqual(receipt.is_success, True, f'set_commission fails, receipt: {receipt}')

    def test_wait_list(self):
        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
        out = contract.functions.getCollatorList().call()
        out = sorted(out, key=lambda x: x[1], reverse=True)
        collator_num = out[0][1]
        receipt = self._fund_users(collator_num * 2)

        # Join one collator
        batch = ExtrinsicBatch(self._substrate, self._kp_new_collator)
        batch.compose_call(
            'ParachainStaking',
            'join_candidates',
            {
                'stake': collator_num,
            }
        )
        receipt = batch.execute()
        self.assertEqual(receipt.is_success, True, f'join_collator fails, receipt: {receipt}')
        receipt = self.set_commission_rate(10, self._kp_new_collator)
        self.assertEqual(receipt.is_success, True, f'set_commission fails, receipt: {receipt}')

        wait_list = contract.functions.getWaitList().call()
        wait_list = sorted(wait_list, key=lambda x: x[1], reverse=True)
        self.assertEqual(len(wait_list), 1)
        pk = bytes.fromhex(self._substrate.ss58_decode(self._kp_new_collator.ss58_address))
        self.assertEqual(wait_list[0][0], pk)
        self.assertEqual(wait_list[0][1], collator_num)
        self.assertEqual(wait_list[0][2], 10 * 10_000)

        # Check the wait list
        collator_list = contract.functions.getCollatorList().call()
        out = sorted(out, key=lambda x: x[1], reverse=True)
        self.assertEqual(len(collator_list), 2)
        self.assertTrue(wait_list[0][0] in [collator[0] for collator in collator_list])

        batch = ExtrinsicBatch(self._substrate, KP_GLOBAL_SUDO)
        batch.compose_sudo_call(
            'ParachainStaking',
            'force_remove_candidate',
            {
                'collator': self._kp_new_collator.ss58_address,
            }
        )
        receipt = batch.execute()
        self.assertEqual(receipt.is_success, True, f'force_remove_candidate fails, receipt: {receipt}')

    def test_delegator_revoke(self):
        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
        out = contract.functions.getCollatorList().call()
        out = sorted(out, key=lambda x: x[1], reverse=True)

        collator_eth_addr = out[0][0]
        collator_num = out[0][1]
        receipt = self._fund_users(collator_num * 2)
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

        # Delegator leave
        evm_receipt = self.evm_delegator_revoke_delegation(contract, self._kp_moon['kp'], collator_eth_addr)
        self.assertEqual(evm_receipt['status'], 1, f'leave fails, evm_receipt: {evm_receipt}')
        bl_hash = get_block_hash(self._substrate, evm_receipt['blockNumber'])
        event = self.get_event(bl_hash, 'ParachainStaking', 'DelegatorLeft')
        self.assertEqual(
            event['attributes'],
            (self._kp_moon['substrate'], collator_num),
            f'join fails, event: {event}')

        # Note: The unlock unstaked didn't success because we have to wait about 20+ blocks;
        # therefore, we don't test here. Can just test maunally

    def claim_collator_if_not_claimed(self, eth_kp):
        eth_kp = get_eth_info()
        signature = calculate_claim_signature(
            self._substrate,
            KP_COLLATOR.ss58_address,
            eth_kp['kp'].private_key.hex(),
            self._eth_chain_id)
        receipt = claim_account(self._substrate, KP_COLLATOR, eth_kp['kp'], signature)
        if not receipt.is_success and 'AccountIdHasMapped' == receipt.error_message['name']:
            return
        self.assertTrue(
            receipt.is_success, f'Failed to claim account {KP_COLLATOR.ss58_address}, {receipt.error_message}')

    # Can only test once before we restart
    def test_delegator_customized_claim(self):
        eth_kp = get_eth_info()
        self.claim_collator_if_not_claimed(eth_kp)

        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
        out = contract.functions.getCollatorList().call()
        out = sorted(out, key=lambda x: x[1], reverse=True)

        collator_eth_addr = out[0][0]
        collator_num = out[0][1]
        receipt = self._fund_users(collator_num * 2)
        self.assertEqual(receipt.is_success, True, f'fund_users fails, receipt: {receipt}')
        evm_receipt = self.evm_join_delegators(contract, self._kp_moon['kp'], collator_eth_addr, collator_num)
        self.assertEqual(evm_receipt['status'], 1, f'join fails, evm_receipt: {evm_receipt}')
        bl_hash = get_block_hash(self._substrate, evm_receipt['blockNumber'])
        event = self.get_event(bl_hash, 'ParachainStaking', 'Delegation')
        self.assertEqual(
            event['attributes'],
            (self._kp_moon['substrate'], collator_num, KP_COLLATOR.ss58_address, 2 * collator_num),
            f'join fails, event: {event}')

        evm_receipt = self.evm_delegator_leave_delegators(contract, self._kp_moon['kp'])
        self.assertEqual(evm_receipt['status'], 1, f'leave fails, evm_receipt: {evm_receipt}')
