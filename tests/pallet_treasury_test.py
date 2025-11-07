import pytest

from substrateinterface import SubstrateInterface, Keypair
from tools.constants import WS_URL, TOKEN_NUM_BASE_DEV, KP_GLOBAL_SUDO
from peaq.utils import show_extrinsic
from peaq.utils import ExtrinsicBatch
from tools.utils import batch_fund, get_event
import unittest
import random

# Assumptions
# 1. Treasury address is:'5EYCAe5ijiYfyeZ2JJCGq56LmPyNRAKzpG4QkoQkkQNB5e6Z'

# Global Constants

# accounts to carty out diffirent transactions
KP_USER = Keypair.create_from_uri('//Alice')
KP_COUNCIL_FIRST_MEMBER = Keypair.create_from_uri('//Bob')
KP_COUNCIL_SECOND_MEMBER = Keypair.create_from_uri('//Eve')
KP_BENEFICIARY = Keypair.create_from_uri('//Dave')
KP_TREASURY = '5EYCAe5ijiYfyeZ2JJCGq56LmPyNRAKzpG4QkoQkkQNB5e6Z'

WEIGHT_BOND = {
    'ref_time': 1000000000,
    'proof_size': 1000000
}
LENGTH_BOND = 100
TOTAL_AMOUNT = 20 ** 5 * 10 ** 18
# AMOUNT must be less than TOTAL_AMOUNT to ensure treasury has enough funds
AMOUNT = random.randint(1, 1000)  # Max 1000 tokens for quick testing

DIVISION_FACTOR = pow(10, 7)


def cast_vote(substrate, kp_member, proposal_hash, proposal_index, vote):
    batch = ExtrinsicBatch(substrate, kp_member)
    batch.compose_call(
        'Council',
        'vote',
        {
            'proposal': proposal_hash,
            'index': proposal_index,
            'approve': vote
        })
    return batch.execute()


def set_member_by_sudo(batch, members, kp_prime_member, old_count, kp_prime):
    batch.compose_sudo_call(
        'Council',
        'set_members',
        {
            'new_members': members,
            'prime': kp_prime,
            'old_count': len(members)
        })


def close_vote(substrate, kp_member, proposal_hash, proposal_index, weight_bond,
               length_bond):
    batch = ExtrinsicBatch(substrate, kp_member)
    batch.compose_call(
        'Council',
        'close',
        {
            'proposal_hash': proposal_hash,
            'index': proposal_index,
            'proposal_weight_bound': weight_bond,
            'length_bound': length_bond
        }
    )
    return batch.execute()


def trigger_payout(substrate, kp_caller, spend_index):
    """Trigger payout for an approved spend"""
    batch = ExtrinsicBatch(substrate, kp_caller)
    batch.compose_call(
        'Treasury',
        'payout',
        {
            'index': spend_index
        })
    return batch.execute()


# To directly spend funds from treasury
def spend(substrate, value, beneficiary):
    batch = ExtrinsicBatch(substrate, KP_GLOBAL_SUDO)
    batch.compose_sudo_call(
        'Treasury',
        'spend',
        {
            'asset_kind': [],
            'amount': value * TOKEN_NUM_BASE_DEV,
            'beneficiary': beneficiary.ss58_address,
            'valid_from': None,
        })
    return batch.execute()


@pytest.mark.substrate
class TestTreasury(unittest.TestCase):
    def setUp(self):
        self.substrate = SubstrateInterface(url=WS_URL)

    # To submit a spend proposal using modern Treasury.spend()
    def propose_spend(self, value, beneficiary, kp_member):

        treasury_payload = self.substrate.compose_call(
            call_module='Treasury',
            call_function='spend',
            call_params={
                'asset_kind': (),
                'amount': value*TOKEN_NUM_BASE_DEV,
                'beneficiary': beneficiary.ss58_address,
                'valid_from': None
            })

        batch = ExtrinsicBatch(self.substrate, kp_member)
        batch.compose_call(
            'Council',
            'propose',
            {
                'threshold': 2,
                'proposal': treasury_payload.value,
                'length_bound': LENGTH_BOND
            })
        receipt = batch.execute()

        self.assertTrue(receipt.is_success,
                        f'Extrinsic Failed: {receipt.error_message}' +
                        f'{self.substrate.get_events(receipt.block_hash)}')

        for event in self.substrate.get_events(receipt.block_hash):
            if event.value['event_id'] == 'Proposed':
                print(event.value['attributes'])
                pi = event.value['attributes']['proposal_index']
                ph = event.value['attributes']['proposal_hash']

        show_extrinsic(receipt, 'propose_spend')
        return (pi, ph)

    def check_approve_proposal(self):

        proposal_index = None
        proposal_hash = None

        # Get beneficiary balance before spend
        balance_before = self.substrate.query('System', 'Account', [KP_BENEFICIARY.ss58_address])
        balance_before_free = balance_before.value['data']['free']
        print(f"Beneficiary balance before: {balance_before_free}")

        # Check treasury balance
        treasury_balance = self.substrate.query('System', 'Account', [KP_TREASURY])
        treasury_free = treasury_balance.value['data']['free']
        print(f"Treasury balance: {treasury_free}")
        print(f"Spend amount will be: {AMOUNT * TOKEN_NUM_BASE_DEV}")

        # submit a proposal
        proposal_index, proposal_hash = self.propose_spend(AMOUNT,
                                                           KP_BENEFICIARY,
                                                           KP_USER)

        # To submit votes by all council member to APPROVE the motion
        # Result: 2/3 votes YES = 66.7% approval (meets >50% threshold)
        receipt = cast_vote(self.substrate, KP_USER, proposal_hash, proposal_index, True)
        self.assertTrue(receipt.is_success,
                        f'Extrinsic Failed: {receipt.error_message}' +
                        f'{self.substrate.get_events(receipt.block_hash)}')

        receipt = cast_vote(self.substrate, KP_COUNCIL_FIRST_MEMBER, proposal_hash,
                            proposal_index,
                            True)
        self.assertTrue(receipt.is_success,
                        f'Extrinsic Failed: {receipt.error_message}' +
                        f'{self.substrate.get_events(receipt.block_hash)}')

        receipt = cast_vote(self.substrate, KP_COUNCIL_SECOND_MEMBER, proposal_hash,
                            proposal_index,
                            False)
        self.assertTrue(receipt.is_success,
                        f'Extrinsic Failed: {receipt.error_message}' +
                        f'{self.substrate.get_events(receipt.block_hash)}')

        # To close voting processes
        receipt = close_vote(self.substrate, KP_COUNCIL_FIRST_MEMBER, proposal_hash,
                             proposal_index,
                             WEIGHT_BOND,
                             LENGTH_BOND)
        self.assertTrue(receipt.is_success, f'Extrinsic Failed: {receipt.error_message}')

        # Extract SpendIndex from AssetSpendApproved event
        spend_index = None
        for event in self.substrate.get_events(receipt.block_hash):
            if event.value['event_id'] == 'AssetSpendApproved':
                spend_index = event.value['attributes']['index']
                print(f"Treasury spend approved with index: {spend_index}")
                print(f"Spend details: {event.value['attributes']}")
                break

        self.assertIsNotNone(spend_index, "Treasury spend was not approved by Council")

        # Trigger payout (anyone can do this)
        print(f"Triggering payout for spend index {spend_index}...")
        receipt = trigger_payout(self.substrate, KP_USER, spend_index)
        self.assertTrue(receipt.is_success,
                        f'Payout failed: {receipt.error_message}' +
                        f'{self.substrate.get_events(receipt.block_hash)}')

        # Verify payout was successful
        paid_event_found = False
        for event in self.substrate.get_events(receipt.block_hash):
            if event.value['event_id'] == 'Paid':
                paid_event_found = True
                print(f"✅ Payout executed: {event.value['attributes']}")
                break

        self.assertTrue(paid_event_found, "Paid event not found after payout")

        # Verify beneficiary balance increased
        balance_after = self.substrate.query('System', 'Account', [KP_BENEFICIARY.ss58_address])
        balance_after_free = balance_after.value['data']['free']
        balance_increase = balance_after_free - balance_before_free

        print(f"Beneficiary balance after: {balance_after_free}")
        print(f"Balance increase: {balance_increase}")
        print(f"Expected amount: {AMOUNT * TOKEN_NUM_BASE_DEV}")

        self.assertEqual(balance_increase, AMOUNT * TOKEN_NUM_BASE_DEV,
                         f"Balance increase {balance_increase} does not match expected {AMOUNT * TOKEN_NUM_BASE_DEV}")

        print("✅ Council-approved treasury spend executed successfully!")

    def check_reject_proposal(self):
        """
        Test rejection scenario: 1 YES vote vs 2 NO votes = 33.3% approval
        With SpendOrigin requiring >50% approval, the treasury spend will NOT be approved.
        The Council.close() will succeed but the inner Treasury.spend() will fail.
        """
        proposal_index = None
        proposal_hash = None

        # submit a proposal
        proposal_index, proposal_hash = self.propose_spend(AMOUNT,
                                                           KP_BENEFICIARY,
                                                           KP_USER)

        # To submit votes by all council member to REJECT the proposal
        # Result: 1/3 votes YES = 33.3% approval (does NOT meet >50% threshold)
        receipt = cast_vote(self.substrate, KP_USER, proposal_hash,
                            proposal_index,
                            True)
        self.assertTrue(receipt.is_success,
                        f'Extrinsic Failed: {receipt.error_message}' +
                        f'{self.substrate.get_events(receipt.block_hash)}')

        receipt = cast_vote(self.substrate, KP_COUNCIL_FIRST_MEMBER, proposal_hash,
                            proposal_index,
                            False)
        self.assertTrue(receipt.is_success,
                        f'Extrinsic Failed: {receipt.error_message}' +
                        f'{self.substrate.get_events(receipt.block_hash)}')

        receipt = cast_vote(self.substrate, KP_COUNCIL_SECOND_MEMBER, proposal_hash,
                            proposal_index,
                            False)
        self.assertTrue(receipt.is_success,
                        f'Extrinsic Failed: {receipt.error_message}' +
                        f'{self.substrate.get_events(receipt.block_hash)}')

        # To close voting processes
        receipt = close_vote(self.substrate, KP_COUNCIL_SECOND_MEMBER, proposal_hash,
                             proposal_index,
                             WEIGHT_BOND,
                             LENGTH_BOND)
        self.assertTrue(receipt.is_success, f'Extrinsic Failed: {receipt.error_message}')

        # Verify that treasury spend was NOT approved (insufficient votes)
        spend_approved = False
        for event in self.substrate.get_events(receipt.block_hash):
            if event.value['event_id'] == 'AssetSpendApproved':
                spend_approved = True
                break

        self.assertFalse(spend_approved,
                         "Treasury spend should NOT be approved with only 33% approval")

        print("✅ Proposal correctly rejected due to insufficient approval (33% < 50%)")

    def check_treasury_rewards(self):
        # To get current block reward as configured in BlockReward.BlockIssueReward
        result = get_event(
            self.substrate,
            self.substrate.get_block_hash(),
            'BlockReward', 'BlockRewardsDistributed')
        print(f'self.substrate.get_block_hash(): {self.substrate.get_block_hash()}')
        self.assertIsNotNone(result, 'BlockReward event not found')
        block_reward = result.value['attributes']
        print("Block reward:", block_reward)

        # To get treasury percentage in block reward
        # as configured in BlockReward.RewardDistributionConfigStorage
        result = self.substrate.query('BlockReward', 'RewardDistributionConfigStorage')
        treasury_percentage = ((result['treasury_percent']).decode()) / DIVISION_FACTOR
        print("Treasury percentage: ", '{:.2f}%'.format(treasury_percentage))

        # To get expected reward to be distributd to treasury
        expected_reward_dist_to_treasury = int(
                                        (treasury_percentage/100)*block_reward)
        print("Treasury expected reward:", expected_reward_dist_to_treasury)

        actual_reward_dist_to_treasury = 0

        # Examine events for most recent block
        for event in self.substrate.get_events():
            if event.value['event_id'] != 'Deposit':
                continue
            if event.value['attributes']['who'] != KP_TREASURY:
                continue
            actual_reward_dist_to_treasury = event.value['attributes']['amount']
            break

        print("Treasury actual reward: ", actual_reward_dist_to_treasury)

        # In future, after we introduce the transaction fee
        # into the reward system, this equation will not works
        # and hence this test needs to be updated accordingly
        self.assertAlmostEqual(
            actual_reward_dist_to_treasury / expected_reward_dist_to_treasury,
            1, 7,
            f'Actual {actual_reward_dist_to_treasury} and expected reward '
            f'{expected_reward_dist_to_treasury} distribution are not equal')

        print('✅ Reward distributed to treasury as expected')

    def test_tresury_approve(self):
        print('----Start of pallet_treasury_test!! ----')
        print()

        batch = ExtrinsicBatch(self.substrate, KP_GLOBAL_SUDO)
        batch_fund(batch, KP_USER, TOTAL_AMOUNT)
        batch_fund(batch, KP_COUNCIL_FIRST_MEMBER, TOTAL_AMOUNT)
        batch_fund(batch, KP_COUNCIL_SECOND_MEMBER, TOTAL_AMOUNT)

        # Fund treasury account for payouts
        # Verify treasury account derivation
        batch.compose_sudo_call(
            'Balances',
            'force_set_balance',
            {
                'who': KP_TREASURY,
                'new_free': TOTAL_AMOUNT
            })

        print("--set member test started---")
        council_members = [KP_USER.ss58_address,
                           KP_COUNCIL_FIRST_MEMBER.ss58_address,
                           KP_COUNCIL_SECOND_MEMBER.ss58_address]

        set_member_by_sudo(batch,
                           council_members,
                           KP_USER.ss58_address,
                           0,
                           KP_USER.ss58_address)
        receipt = batch.execute_n_clear()
        self.assertTrue(receipt.is_success, f'Extrinsic Failed: {receipt.error_message}')

        print("--set member test completed successfully!---")
        print()

        print("---proposal approval test started---")
        self.check_approve_proposal()
        print("---proposal approval test completed successfully---")
        print()

    def test_tresury_reject(self):
        print('----Start of pallet_treasury_test!! ----')
        print()

        batch = ExtrinsicBatch(self.substrate, KP_GLOBAL_SUDO)
        batch_fund(batch, KP_USER, TOTAL_AMOUNT)
        batch_fund(batch, KP_COUNCIL_FIRST_MEMBER, TOTAL_AMOUNT)
        batch_fund(batch, KP_COUNCIL_SECOND_MEMBER, TOTAL_AMOUNT)

        # Fund treasury account for payouts
        print(f"Funding treasury account: {KP_TREASURY}")
        batch.compose_sudo_call(
            'Balances',
            'force_set_balance',
            {
                'who': KP_TREASURY,
                'new_free': TOTAL_AMOUNT
            })

        print("--set member test started---")
        council_members = [KP_USER.ss58_address,
                           KP_COUNCIL_FIRST_MEMBER.ss58_address,
                           KP_COUNCIL_SECOND_MEMBER.ss58_address]

        set_member_by_sudo(batch,
                           council_members,
                           KP_USER.ss58_address,
                           0,
                           KP_USER.ss58_address)
        receipt = batch.execute_n_clear()
        self.assertTrue(receipt.is_success, f'Extrinsic Failed: {receipt.error_message}')

        print("---proposal rejection test started---")
        self.check_reject_proposal()
        print("---proposal rejection test completed successfully---")
        print()

    def test_treasury_others(self):
        print('----Start of pallet_treasury_test!! ----')
        print()

        batch = ExtrinsicBatch(self.substrate, KP_GLOBAL_SUDO)
        batch_fund(batch, KP_USER, TOTAL_AMOUNT)
        batch_fund(batch, KP_COUNCIL_FIRST_MEMBER, TOTAL_AMOUNT)
        batch_fund(batch, KP_COUNCIL_SECOND_MEMBER, TOTAL_AMOUNT)

        # Fund treasury account for payouts
        print(f"Funding treasury account: {KP_TREASURY}")
        batch.compose_sudo_call(
            'Balances',
            'force_set_balance',
            {
                'who': KP_TREASURY,
                'new_free': TOTAL_AMOUNT
            })

        print("--set member test started---")
        council_members = [KP_USER.ss58_address,
                           KP_COUNCIL_FIRST_MEMBER.ss58_address,
                           KP_COUNCIL_SECOND_MEMBER.ss58_address]

        set_member_by_sudo(batch,
                           council_members,
                           KP_USER.ss58_address,
                           0,
                           KP_USER.ss58_address)
        receipt = batch.execute_n_clear()
        self.assertTrue(receipt.is_success, f'Extrinsic Failed: {receipt.error_message}')

        print("---Spend test started---")
        receipt = spend(self.substrate, AMOUNT, KP_BENEFICIARY)
        self.assertTrue(receipt.is_success,
                        f'Extrinsic Failed: {receipt.error_message}' +
                        f'{self.substrate.get_events(receipt.block_hash)}')
        print("Spend test completed successfully")
        print()

        print("---Treasury reward distribution test started---")
        self.check_treasury_rewards()
        print("---Treasury reward distribution test completed successfully---")
        print()

        print('---- End of pallet_treasury_test!! ----')
