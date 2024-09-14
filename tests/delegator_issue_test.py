import unittest
import time
import pytest

from substrateinterface import SubstrateInterface, Keypair
from tools.utils import get_collators, batch_fund
from tools.utils import exist_pallet
from tools.constants import WS_URL, KP_GLOBAL_SUDO, KP_COLLATOR
from tools.constants import BLOCK_GENERATE_TIME
from peaq.utils import get_block_height, get_block_hash, get_chain
from peaq.utils import ExtrinsicBatch, get_account_balance
from tests.utils_func import restart_parachain_and_runtime_upgrade
from tools.utils import set_block_reward_configuration
import warnings


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


def set_coefficient(substrate, coefficient):
    batch = ExtrinsicBatch(substrate, KP_GLOBAL_SUDO)
    batch.compose_sudo_call(
        'StakingCoefficientRewardCalculator',
        'set_coefficient',
        {
            'coefficient': coefficient,
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
class TestDelegator(unittest.TestCase):
    def setUp(self):
        restart_parachain_and_runtime_upgrade()

        self.substrate = SubstrateInterface(
            url=WS_URL,
        )
        self.chain_name = get_chain(self.substrate)
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
        set_value = {
            'treasury_percent': 20000000,
            'depin_incentivization_percent': 10000000,
            'collators_delegators_percent': 20000000,
            'depin_staking_percent': 50000000,
            'coretime_percent': 40000000,
            'subsidization_pool_percent': 860000000,
        }
        receipt = set_block_reward_configuration(self.substrate, set_value)
        self.assertTrue(receipt.is_success,
                        'cannot setup the block reward configuration')

    def get_balance_difference(self, addr):
        current_height = get_block_height(self.substrate)
        current_block_hash = get_block_hash(self.substrate, current_height)
        now_balance = get_account_balance(self.substrate, addr, current_block_hash)

        previous_height = current_height - 1
        previous_block_hash = get_block_hash(self.substrate, previous_height)
        pre_balance = get_account_balance(self.substrate, addr, previous_block_hash)
        return now_balance - pre_balance

    def get_one_collator_without_delegator(self, keys):
        for key in keys:
            collator = get_collators(self.substrate, key)
            if str(collator['delegators']) == '[]':
                return collator
        return None

    def wait_get_reward(self, addr):
        time.sleep(BLOCK_GENERATE_TIME * 2)
        count_down = 0
        wait_time = 120
        prev_balance = get_account_balance(self.substrate, addr)
        while count_down < wait_time:
            if prev_balance != get_account_balance(self.substrate, addr):
                return True
            print(f'already wait about {count_down} seconds')
            count_down += 12
            time.sleep(BLOCK_GENERATE_TIME)
        return False

    # Deprecated: We don't use it now
    def test_issue_fixed_precentage(self):
        if not exist_pallet(self.substrate, 'StakingFixedRewardCalculator'):
            warnings.warn('StakingFixedRewardCalculator pallet not exist, skip the test')
            return

        collator_percentage = 80
        delegator_percentage = 20

        # Check it's the peaq-dev parachain
        self.assertTrue(self.chain_name in ['peaq-dev', 'peaq-dev-fork'])
        batch = ExtrinsicBatch(self.substrate, KP_GLOBAL_SUDO)
        batch.compose_sudo_call('StakingFixedRewardCalculator', 'set_reward_rate', {
            'collator_rate': collator_percentage,
            'delegator_rate': delegator_percentage,
        })
        batch_fund(batch, self.delegators[0], 10000 * 10 ** 18)
        batch_fund(batch, self.delegators[1], 10000 * 10 ** 18)
        receipt = batch.execute_n_clear()
        self.assertTrue(receipt.is_success, f'batch execute failed, error: {receipt.error_message}')

        # setup
        # Get the collator account
        collator = self.get_one_collator_without_delegator(self.collator)
        self.assertNotEqual(collator, None)

        # Add the delegator
        receipt = add_delegator(self.substrate, self.delegators[0], str(collator['id']), int(str(collator['stake'])))
        self.assertTrue(receipt.is_success, 'Add delegator failed')
        receipt = add_delegator(self.substrate, self.delegators[1], str(collator['id']), int(str(collator['stake'])))
        self.assertTrue(receipt.is_success, 'Add delegator failed')

        print('Wait for delegator get reward')
        self.assertTrue(self.wait_get_reward(self.delegators[0].ss58_address))

        delegators_reward = [self.get_balance_difference(delegator.ss58_address) for delegator in self.delegators]
        collator_reward = self.get_balance_difference(str(collator['id']))
        self.assertEqual(delegators_reward[0], delegators_reward[1], 'The reward is not equal')
        self.assertEqual(collator_percentage / delegators_reward * sum(delegators_reward),
                         collator_reward, 'The reward is not equal')

    def internal_test_issue_coefficient(self, mega_tokens):
        if not exist_pallet(self.substrate, 'StakingCoefficientRewardCalculator'):
            warnings.warn('StakingCoefficientRewardCalculator pallet not exist, skip the test')
            return

        # Check it's the peaq-dev parachain
        self.assertTrue(self.chain_name in [
            'peaq-dev', 'peaq-dev-fork',
            'krest-network', 'krest-network-fork',
            'peaq-network', 'peaq-network-fork'])

        batch = ExtrinsicBatch(self.substrate, KP_GLOBAL_SUDO)
        batch.compose_sudo_call('ParachainStaking', 'set_max_candidate_stake', {
            'new': 10 ** 5 * mega_tokens
        })
        batch.compose_sudo_call('StakingCoefficientRewardCalculator', 'set_coefficient', {
            'coefficient': 2,
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

        print('Wait for delegator get reward')
        self.assertTrue(self.wait_get_reward(self.delegators[0].ss58_address))

        delegators_reward = [self.get_balance_difference(delegator.ss58_address) for delegator in self.delegators]
        collator_reward = self.get_balance_difference(str(collator['id']))
        self.assertEqual(delegators_reward[0], delegators_reward[1], 'The reward is not equal')
        self.assertAlmostEqual(
            sum(delegators_reward) / collator_reward,
            1, 7,
            f'{sum(delegators_reward)} v.s. {collator_reward} is not equal')

    def test_issue_coeffective(self):
        self.internal_test_issue_coefficient(500000 * 10 ** 18)

    def test_issue_coeffective_large(self):
        self.internal_test_issue_coefficient(10 ** 15 * 10 ** 18)
