import unittest
import pytest

from substrateinterface import SubstrateInterface, Keypair
from tools.utils import get_modified_chain_spec
from tools.constants import WS_URL, ACA_WS_URL
from peaq.utils import get_block_height, get_block_hash, get_chain
from tests.utils_func import restart_parachain_and_runtime_upgrade
from tools.runtime_upgrade import wait_until_block_height
from tools.utils import get_event, get_account_balance
from tools.constants import KP_GLOBAL_SUDO
from peaq.utils import ExtrinsicBatch
from tests import utils_func as TestUtils


import pprint
pp = pprint.PrettyPrinter(indent=4)

STATE_INFOS = [{
    # Forked chain didn't copy the parachain staking, it's the default value
    'module': 'ParachainStaking',
    'storage_function': 'MaxSelectedCandidates',
    'type': {
        'peaq-dev': 4,
        'krest-network': 4,
        'peaq-network': 4
    }
}, {
    # Forked chain didn't copy the parachain staking, it's the default value
    'module': 'ParachainStaking',
    'storage_function': 'Round',
    'type': {
        # From runtime ugprade, we have to change it to 20
        'peaq-dev': {'length': 20},
        'krest-network': {'length': 2400},
        'peaq-network': {'length': 2400},
    }
}, {
    'module': 'BlockReward',
    'storage_function': 'RewardDistributionConfigStorage',
    'type': {
        # It's special case because below is percentage,
        # and then you have to divide by 1000000000
        'peaq-dev': {
            'treasury_percent': 250000000,
            'collators_delegators_percent': 400000000,
            'coretime_percent': 100000000,
            'subsidization_pool_percent': 50000000,
            'depin_staking_percent': 50000000,
            'depin_incentivization_percent': 150000000,
        },
        'krest-network': {
            'treasury_percent': 250000000,
            'collators_delegators_percent': 400000000,
            'coretime_percent': 100000000,
            'subsidization_pool_percent': 50000000,
            'depin_staking_percent': 50000000,
            'depin_incentivization_percent': 150000000,
        },
        'peaq-network': {
            'treasury_percent': 250000000,
            'collators_delegators_percent': 400000000,
            'coretime_percent': 100000000,
            'subsidization_pool_percent': 50000000,
            'depin_staking_percent': 50000000,
            'depin_incentivization_percent': 150000000,
        },
        'peaq-network-fork': {
            'treasury_percent': 250000000,
            'collators_delegators_percent': 400000000,
            'coretime_percent': 100000000,
            'subsidization_pool_percent': 50000000,
            'depin_staking_percent': 50000000,
            'depin_incentivization_percent': 150000000,
        }
    }
}]


CONSTANT_INFOS = [{
    'module': 'ParachainStaking',
    'storage_function': 'MaxCollatorsPerDelegator',
    'type': {
        'peaq-dev': 8,
        'krest-network': 8,
        'peaq-network': 8,
    }
}, {
    'module': 'ParachainStaking',
    'storage_function': 'MaxDelegationsPerRound',
    'type': {
        'peaq-dev': 1,
        'krest-network': 1,
        'peaq-network': 1,
    }
}, {
    'module': 'ParachainStaking',
    'storage_function': 'MaxDelegatorsPerCollator',
    'type': {
        'peaq-dev': 100,
        'krest-network': 25,
        'peaq-network': 100,
    }
}, {
    'module': 'ParachainStaking',
    'storage_function': 'MaxTopCandidates',
    'type': {
        'peaq-dev': 64,
        'krest-network': 128,
        'peaq-network': 64,
    }
}, {
    'module': 'ParachainStaking',
    'storage_function': 'MinCollatorCandidateStake',
    'type': {
        'peaq-dev': 32000,
        'krest-network': 50000 * 10 ** 18,
        'peaq-network': 50000 * 10 ** 18,
    }
}, {
    'module': 'ParachainStaking',
    'storage_function': 'MinCollatorStake',
    'type': {
        'peaq-dev': 32000,
        'krest-network': 50000 * 10 ** 18,
        'peaq-network': 50000 * 10 ** 18,
    }
}, {
    'module': 'ParachainStaking',
    'storage_function': 'MinDelegation',
    'type': {
        'peaq-dev': 20000,
        'krest-network': 100 * 10 ** 18,
        'peaq-network': 100 * 10 ** 18,
    }
}, {
    'module': 'ParachainStaking',
    'storage_function': 'MinDelegatorStake',
    'type': {
        'peaq-dev': 20000,
        'krest-network': 100 * 10 ** 18,
        'peaq-network': 100 * 10 ** 18,
    }
}]


def skip_test_total_issuance():
    # If it's peaq-dev-fork, we don't need to test because it's already updated at 0.0.17
    # If it's peaq-network-fork, we don't need to test because it's already updated at 0.0.6

    substrate = SubstrateInterface(url=WS_URL)
    chain_spec = get_chain(substrate)
    return 'krest-network-fork' != chain_spec


@pytest.mark.relaunch
@pytest.mark.substrate
class TokenEconomyTest(unittest.TestCase):

    def get_info(self, test_type):
        if self._chain_spec not in test_type:
            return test_type[get_modified_chain_spec(self._chain_spec)]
        else:
            return test_type[self._chain_spec]

    @classmethod
    def setUpClass(cls):
        restart_parachain_and_runtime_upgrade()
        wait_until_block_height(SubstrateInterface(url=WS_URL), 1)

    def setUp(self):
        wait_until_block_height(SubstrateInterface(url=WS_URL), 2)
        wait_until_block_height(SubstrateInterface(url=ACA_WS_URL), 2)
        self._substrate = SubstrateInterface(url=WS_URL)
        current_height = get_block_height(self._substrate)
        self._block_hash = get_block_hash(self._substrate, current_height)
        self._chain_spec = get_chain(self._substrate)

    def test_chain_states(self):
        for test in STATE_INFOS:
            module = test['module']
            storage_function = test['storage_function']
            result = self._substrate.query(
                module=module,
                storage_function=storage_function,
                params=[],
                block_hash=self._block_hash,
            )

            golden_data = self.get_info(test['type'])
            if isinstance(golden_data, dict):
                for k, v in golden_data.items():
                    self.assertEqual(result.value[k], v, f'{result.value} != {k}: {v}, {storage_function}')
            else:
                if 'almost' in test and test['almost']:
                    self.assertAlmostEqual(result.value / golden_data, 1, 7, msg=f'{result.value} != {test}')
                else:
                    self.assertEqual(result.value, golden_data, f'{result.value} != {test}')

    def test_constants(self):
        for test in CONSTANT_INFOS:
            module = test['module']
            storage_function = test['storage_function']
            result = self._substrate.get_constant(
                module,
                storage_function,
                self._block_hash,
            )

            golden_data = self.get_info(test['type'])
            self.assertEqual(result.value, golden_data, f'{result.value} != {test}')

    @pytest.mark.skipif(TestUtils.is_local_new_chain() is True, reason='Dont need to test on the new chain')
    def test_block_reward(self):
        block_reward = {
            'peaq-dev-fork': int(1.902587519 * 10 ** 18),
            'krest-network-fork': int(3.805175038 * 10 ** 18),
            'peaq-network-fork': int(27.96803653 * 10 ** 18),
        }

        result = get_event(
            self._substrate,
            self._substrate.get_block_hash(),
            'BlockReward', 'BlockRewardsDistributed')
        self.assertIsNotNone(result, 'BlockReward event not found')
        self.assertAlmostEqual(
            result.value['attributes'] / block_reward[self._chain_spec],
            1, 7,
            msg=f'{result.value["attributes"]} != {block_reward[self._chain_spec]}')

    # The krest failed because it's used the delayed TGE, but that's okay
    @pytest.mark.skipif(
        skip_test_total_issuance() is True,
        reason='Dont need to test no the new chain and forked agung/peaq chain')
    def test_total_issuance(self):
        golden_issuance_number = {
            'peaq-dev-fork': int(400 * 10 ** 6 * 10 ** 18),
            'krest-network-fork': int(400 * 10 ** 6 * 10 ** 18),
            'peaq-network-fork': int(4200 * 10 ** 6 * 10 ** 18),
        }

        total_balance = self._substrate.query(
            module='Balances',
            storage_function='TotalIssuance',
            params=[],
        )
        self.assertGreater(
            total_balance.value,
            golden_issuance_number[self._chain_spec],
            f'{total_balance.value} <= {golden_issuance_number[self._chain_spec]}')

        # We only check the total issuance is greater than the golden issuance number because
        # when time goes on, the total issuance will be increased.

    # Will fail after this runtime upgrade
    # In the future, after we extract the inflation manager's pot, we will not be able to test this
    @pytest.mark.skipif(TestUtils.is_local_new_chain() is False, reason='Dont need to test on the new chain')
    def test_inflation_mgr_transfer_all_pot(self):
        kp_dst = Keypair.create_from_mnemonic(Keypair.generate_mnemonic())

        batch = ExtrinsicBatch(self._substrate, KP_GLOBAL_SUDO)
        batch.compose_sudo_call(
            'InflationManager',
            'transfer_all_pot',
            {
                'dest': kp_dst.ss58_address
            }
        )
        receipt = batch.execute()
        self.assertTrue(receipt.is_success, f'Failed to transfer all pot: {receipt}')

        balance = get_account_balance(self._substrate, kp_dst.ss58_address)
        self.assertGreater(balance, 0, f'Balance is zero: {balance}')
