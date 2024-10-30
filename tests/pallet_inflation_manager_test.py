import pytest
import unittest
from substrateinterface import SubstrateInterface
from tools.utils import get_modified_chain_spec
from tools.constants import WS_URL
from peaq.utils import get_block_height
# from tools.utils import wait_for_event
from enum import Enum
from peaq.utils import get_chain

# Expected InflationConfiguration at genesis
INFLATION_CONFIG = {
    'peaq-network': {
        'inflation_parameters': {
            'inflation_rate': 35000000,
            'disinflation_rate': 100000000,
        },
        'inflation_stagnation_rate': 10000000,
        'inflation_stagnation_year': 13,
    },
    'krest-network': {
        'inflation_parameters': {
          'inflation_rate': 25000000,
          'disinflation_rate': 100000000,
        },
        'inflation_stagnation_rate': 10000000,
        'inflation_stagnation_year': 10
    },
    'peaq-dev': {
        'inflation_parameters': {
          'inflation_rate': 25000000,
          'disinflation_rate': 100000000,
        },
        'inflation_stagnation_rate': 10000000,
        'inflation_stagnation_year': 10
    }
}

# Expected InflationParameters at genesis
INFLATION_PARAMETERS = {
    'peaq-network': {
        'inflation_rate': 35000000,
        'disinflation_rate': 1000000000,
    },
    'krest-network': {
        # This is the default value
        'inflation_rate': 35000000,
        'disinflation_rate': 100000000,
    },
    'peaq-dev': {
        'inflation_rate': 25000000,
        'disinflation_rate': 1000000000,
    }
}

INFLATION_YEAR = {
    'peaq-network': 1,
    'peaq-dev': 1,
    # Because of the delay TGE
    'krest-network': 0,
}

INFLATION_RECALCULATION = {
    'peaq-network': 5256000,
    'peaq-network-fork': 5684095,
    'peaq-dev': 5256000,
    'peaq-dev-fork': 10169264,
    # Because of the delay TGE
    'krest-network': 2915990,
    'krest-network-fork': 2915990,
}


class InflationState(Enum):
    InflationConfiguration = 'InflationConfiguration'
    YearlyInflationParameters = 'InflationParameters'
    BlockRewards = 'BlockRewards'
    CurrentYear = 'CurrentYear'
    RecalculationAt = 'DoRecalculationAt'


@pytest.mark.substrate
class TestPalletInflationManager(unittest.TestCase):
    # Fetches storage at latest block unless a blocknumber is provided
    def _fetch_pallet_storage(self, storage_name, block_number=None):
        block_hash = self.substrate.get_block(block_number=block_number)['header']['hash'] if block_number >= 0 else None

        return self.substrate.query(
            module='InflationManager',
            storage_function=storage_name,
            block_hash=block_hash
        ).value

    def setUp(self):
        self.substrate = SubstrateInterface(url=WS_URL)
        self.detail_chain_spec = get_chain(self.substrate)
        self.chain_spec = get_modified_chain_spec(self.detail_chain_spec)

    # Will fail after 1 year
    def test_now_state(self):
        block_height = get_block_height(self.substrate)

        # If it's forked chain, we shouldn't test
        # Set the inflation configuration
        golden_inflation_config = INFLATION_CONFIG[self.chain_spec]
        golden_inflation_parameters = INFLATION_PARAMETERS[self.chain_spec]
        golden_year = INFLATION_YEAR[self.chain_spec]

        onchain_inflation_config = self._fetch_pallet_storage(
            InflationState.InflationConfiguration.value,
            block_height)
        onchain_base_inflation_parameters = self._fetch_pallet_storage(
            InflationState.YearlyInflationParameters.value,
            block_height)
        onchain_year = self._fetch_pallet_storage(
            InflationState.CurrentYear.value,
            block_height)
        onchain_do_recalculation_at = self._fetch_pallet_storage(
            InflationState.RecalculationAt.value,
            block_height)

        self.assertEqual(golden_inflation_config, onchain_inflation_config)
        self.assertEqual(golden_inflation_parameters, onchain_base_inflation_parameters)
        self.assertEqual(onchain_year, golden_year)
        # If it's forked chain, it should be after 1 year + upgrade time
        self.assertEqual(onchain_do_recalculation_at, INFLATION_RECALCULATION[self.detail_chain_spec])
