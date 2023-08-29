import unittest

from substrateinterface import SubstrateInterface
from tools.utils import WS_URL, get_chain, get_block_hash, get_block_height


import pprint
pp = pprint.PrettyPrinter(indent=4)

STATE_INFOS = [{
    'module': 'ParachainStaking',
    'storage_function': 'MaxSelectedCandidates',
    'type': {
        'peaq-dev': 4,
        'agung-network': 4,
        'krest-network': 4,
        'peaq-network': 4
    }
}, {
    'module': 'ParachainStaking',
    'storage_function': 'Round',
    'type': {
        'peaq-dev': {'length': 10},
        'agung-network': {'length': 600},
        'krest-network': {'length': 600},
        'peaq-network': {'length': 600},
    }
}, {
    'module': 'BlockReward',
    'storage_function': 'BlockIssueReward',
    'almost': True,
    'type': {
        'peaq-dev': 1 * 10 ** 18,
        'agung-network': 79098670000000008192,
        'krest-network': 7610350076100000000,
        'peaq-network': 79098670000000008192,
    }
}, {
    'module': 'BlockReward',
    'storage_function': 'MaxCurrencySupply',
    'almost': True,
    'type': {
        'peaq-dev': 4200000000 * 10 ** 18,
        'agung-network': 4200000000 * 10 ** 18,
        'krest-network': 400000000 * 10 ** 18,
        'peaq-network': 4200000000 * 10 ** 18,
    }
}, {
    'module': 'BlockReward',
    'storage_function': 'RewardDistributionConfigStorage',
    'type': {
        # It's special case because below is percentage,
        # and then you have to divide by 1000000000
        'peaq-dev': {
            'treasury_percent': 200000000,
            'dapps_percent': 250000000,
            'collators_percent': 100000000,
            'lp_percent': 250000000,
            'machines_percent': 100000000,
            'parachain_lease_fund_percent': 100000000
        },
        'agung-network': {
            'treasury_percent': 200000000,
            'dapps_percent': 250000000,
            'collators_percent': 100000000,
            'lp_percent': 250000000,
            'machines_percent': 100000000,
            'parachain_lease_fund_percent': 100000000
        },
        'krest-network': {
            'treasury_percent': 200000000,
            'dapps_percent': 250000000,
            'collators_percent': 100000000,
            'lp_percent': 250000000,
            'machines_percent': 100000000,
            'parachain_lease_fund_percent': 100000000
        },
        'peaq-network': {
            'treasury_percent': 200000000,
            'dapps_percent': 250000000,
            'collators_percent': 100000000,
            'lp_percent': 250000000,
            'machines_percent': 100000000,
            'parachain_lease_fund_percent': 100000000
        }
    }
}]


CONSTANT_INFOS = [{
    'module': 'ParachainStaking',
    'storage_function': 'MaxCollatorsPerDelegator',
    'type': {
        'peaq-dev': 1,
        'agung-network': 1,
        'krest-network': 1,
        'peaq-network': 1,
    }
}, {
    'module': 'ParachainStaking',
    'storage_function': 'MaxDelegationsPerRound',
    'type': {
        'peaq-dev': 1,
        'agung-network': 1,
        'krest-network': 1,
        'peaq-network': 1,
    }
}, {
    'module': 'ParachainStaking',
    'storage_function': 'MaxDelegatorsPerCollator',
    'type': {
        'peaq-dev': 25,
        'agung-network': 25,
        'krest-network': 25,
        'peaq-network': 25,
    }
}, {
    'module': 'ParachainStaking',
    'storage_function': 'MaxTopCandidates',
    'type': {
        'peaq-dev': 16,
        'agung-network': 16,
        'krest-network': 16,
        'peaq-network': 16,
    }
}, {
    'module': 'ParachainStaking',
    'storage_function': 'MinCollatorCandidateStake',
    'type': {
        'peaq-dev': 32000,
        'agung-network': 32000,
        'krest-network': 10000 * 10 ** 18,
        'peaq-network': 32000,
    }
}, {
    'module': 'ParachainStaking',
    'storage_function': 'MinCollatorStake',
    'type': {
        'peaq-dev': 32000,
        'agung-network': 32000,
        'krest-network': 10000 * 10 ** 18,
        'peaq-network': 32000,
    }
}, {
    'module': 'ParachainStaking',
    'storage_function': 'MinDelegation',
    'type': {
        'peaq-dev': 20000,
        'agung-network': 20000,
        'krest-network': 250 * 10 ** 18,
        'peaq-network': 20000,
    }
}, {
    'module': 'ParachainStaking',
    'storage_function': 'MinDelegatorStake',
    'type': {
        'peaq-dev': 20000,
        'agung-network': 20000,
        'krest-network': 250 * 10 ** 18,
        'peaq-network': 20000,
    }
}]


class TokenEconomyTest(unittest.TestCase):

    def modify_chain_spec(self):
        if 'peaq-dev-fork' == self._chain_spec:
            self._chain_spec = 'peaq-dev'

    def setUp(self):
        self._substrate = SubstrateInterface(url=WS_URL)
        current_height = get_block_height(self._substrate)
        self._block_hash = get_block_hash(self._substrate, current_height)
        self._chain_spec = get_chain(self._substrate)
        self.modify_chain_spec()

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

            golden_data = test['type'][self._chain_spec]
            if isinstance(golden_data, dict):
                for k, v in golden_data.items():
                    self.assertEqual(result.value[k], v, f'{result.value} != {k}: {v}')
            else:
                if 'almost' in test and test['almost']:
                    self.assertAlmostEqual(result.value / golden_data, 1, delta=6, msg=f'{result.value} != {test}')
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

            golden_data = test['type'][self._chain_spec]
            self.assertEqual(result.value, golden_data, f'{result.value} != {test}')