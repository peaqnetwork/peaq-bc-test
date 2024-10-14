import unittest
import time
import pytest

from substrateinterface import SubstrateInterface, Keypair
from tools.utils import PARACHAIN_STAKING_POT
from tools.utils import get_collators, batch_fund, get_existential_deposit
from tools.constants import WS_URL, KP_GLOBAL_SUDO, KP_COLLATOR
from peaq.utils import ExtrinsicBatch, get_account_balance
from tests.utils_func import restart_parachain_and_runtime_upgrade
from tools.utils import set_block_reward_configuration


def add_delegator(substrate, kp_delegator, addr_collator, stake_number):
    batch = ExtrinsicBatch(substrate, kp_delegator)
    batch.compose_call(
        'ParachainStaking',
        'join_delegators',
        {
            'collator': addr_collator,
            'amount': stake_number,
        }
    )
    return batch.execute()


def collator_stake_more(substrate, kp_collator, stake_number):
    batch = ExtrinsicBatch(substrate, kp_collator)
    batch.compose_call(
        'ParachainStaking',
        'candidate_stake_more',
        {
            'more': stake_number,
        }
    )
    return batch.execute()


def set_max_candidate_stake(substrate, stake):
    batch = ExtrinsicBatch(substrate, KP_GLOBAL_SUDO)
    batch.compose_sudo_call(
        'ParachainStaking',
        'set_max_candidate_stake',
        {
            'new': stake,
        }
    )
    return batch.execute()


def set_reward_rate(substrate, collator, delegator):
    batch = ExtrinsicBatch(substrate, KP_GLOBAL_SUDO)
    batch.compose_sudo_call(
        'StakingFixedRewardCalculator',
        'set_reward_rate',
        {
            'collator_rate': collator,
            'delegator_rate': delegator,
        }
    )
    return batch.execute()


@pytest.mark.relaunch
@pytest.mark.substrate
class TestDelegatorIssue(unittest.TestCase):
    def setUp(self):
        restart_parachain_and_runtime_upgrade()

        self.substrate = SubstrateInterface(
            url=WS_URL,
        )
        self.collator = [KP_COLLATOR]
        self.delegators = [
            Keypair.create_from_mnemonic(Keypair.generate_mnemonic()),
            Keypair.create_from_mnemonic(Keypair.generate_mnemonic())
        ]
        self.ori_reward_config = self.substrate.query(
            module='BlockReward',
            storage_function='RewardDistributionConfigStorage',
        )
        self.set_collator_delegator_precentage()

    def tearDown(self):
        receipt = set_block_reward_configuration(self.substrate, self.ori_reward_config.value)
        self.assertTrue(receipt.is_success, 'cannot reset the block reward configuration')

    def set_collator_delegator_precentage(self):
        # If the collator/delegator reward distirbution is less than ED, the collator/delegator cannot receive rewards
        set_value = {
            'treasury_percent': 20000000,
            'depin_incentivization_percent': 10000000,
            'collators_delegators_percent': 220000000,
            'depin_staking_percent': 50000000,
            'coretime_percent': 40000000,
            'subsidization_pool_percent': 660000000,
        }
        receipt = set_block_reward_configuration(self.substrate, set_value)
        self.assertTrue(receipt.is_success,
                        'cannot setup the block reward configuration')

    def get_one_collator_without_delegator(self, keys):
        for key in keys:
            collator = get_collators(self.substrate, key)
            if str(collator['delegators']) == '[]':
                return collator
        return None

    def test_delegator_issue(self):
        mega_tokens = 500000 * 10 ** 18
        batch = ExtrinsicBatch(self.substrate, KP_GLOBAL_SUDO)
        batch.compose_sudo_call('ParachainStaking', 'set_max_candidate_stake', {
            'new': 10 ** 5 * mega_tokens
        })
        batch_fund(batch, KP_COLLATOR, 20 * mega_tokens)
        batch_fund(batch, self.delegators[0], 10 * mega_tokens)
        batch_fund(batch, self.delegators[1], 10 * mega_tokens)
        receipt = batch.execute()
        self.assertTrue(receipt.is_success, f'batch execute failed, error: {receipt.error_message}')

        # Get the collator account
        receipt = collator_stake_more(self.substrate, KP_COLLATOR, 5 * mega_tokens)
        self.assertTrue(receipt.is_success, 'Stake failed')

        collator = self.get_one_collator_without_delegator(self.collator)
        self.assertGreaterEqual(int(str(collator['stake'])), 5 * mega_tokens)
        self.assertNotEqual(collator, None)

        # Add the delegator
        receipt = add_delegator(self.substrate, self.delegators[0], str(collator['id']), int(str(collator['stake'])))
        self.assertTrue(receipt.is_success, 'Add delegator failed')
        receipt = add_delegator(self.substrate, self.delegators[1], str(collator['id']), int(str(collator['stake'])))
        self.assertTrue(receipt.is_success, 'Add delegator failed')

        # Avoid the session in block height 10
        time.sleep(12 * 2)
        # Check the delegator's issue number
        batch = ExtrinsicBatch(self.substrate, KP_GLOBAL_SUDO)
        batch.compose_sudo_call(
            'ParachainStaking',
            'force_new_round',
            {}
        )
        first_receipt = batch.execute()
        self.assertTrue(first_receipt.is_success)

        second_receipt = batch.execute()
        self.assertTrue(second_receipt.is_success)

        time.sleep(12 * 2)

        first_new_session_block_hash = self.substrate.get_block_hash(first_receipt.block_number + 1)
        second_new_session_block_hash = self.substrate.get_block_hash(second_receipt.block_number + 1)

        pot_transferable_balance = \
            get_account_balance(self.substrate, PARACHAIN_STAKING_POT, second_receipt.block_hash) - \
            get_existential_deposit(self.substrate)

        # Check all collator reward in collators
        prev_c_balance = get_account_balance(self.substrate, collator['id'].value, first_new_session_block_hash)
        now_c_balance = get_account_balance(self.substrate, collator['id'].value, second_new_session_block_hash)

        prev_d_1_balance = get_account_balance(self.substrate, self.delegators[0].ss58_address, first_new_session_block_hash)
        now_d_1_balance = get_account_balance(self.substrate, self.delegators[0].ss58_address, second_new_session_block_hash)

        prev_d_2_balance = get_account_balance(self.substrate, self.delegators[1].ss58_address, first_new_session_block_hash)
        now_d_2_balance = get_account_balance(self.substrate, self.delegators[1].ss58_address, second_new_session_block_hash)

        total_diff = now_c_balance - prev_c_balance + now_d_1_balance - prev_d_1_balance + now_d_2_balance - prev_d_2_balance
        self.assertAlmostEqual(
            total_diff / pot_transferable_balance,
            1, 7,
            f'{total_diff} v.s. {pot_transferable_balance} is not equal')

        self.assertEqual(now_c_balance - prev_c_balance, now_d_1_balance - prev_d_1_balance)
        self.assertEqual(now_c_balance - prev_c_balance, now_d_2_balance - prev_d_2_balance)
        self.assertEqual(now_d_1_balance - prev_d_1_balance, now_d_2_balance - prev_d_2_balance)
