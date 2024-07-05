import unittest
from substrateinterface import SubstrateInterface
from tools.utils import WS_URL, get_modified_chain_spec
from tests.utils_func import is_krest_related_chain
from peaq.utils import get_block_height
from tools.utils import KP_GLOBAL_SUDO
from peaq.utils import ExtrinsicBatch
from tools.utils import get_event
from tools.runtime_upgrade import wait_until_block_height
from tests.utils_func import restart_parachain_and_runtime_upgrade
from enum import Enum
from peaq.utils import get_chain
import pytest
import time

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
    'krest-network': 0,
    'peaq-dev': 1
}

INFLATION_RECALCULATION = {
    'peaq-network': 2628000,
    'krest-network': 3469624,
    'peaq-dev': 2628000
}

# Expected recalculation target at genesis
RECALCULATION_AFTER = 2628000
WAIT_BLOCKS = 5


class InflationState(Enum):
    InflationConfiguration = 'InflationConfiguration'
    YearlyInflationParameters = 'InflationParameters'
    BlockRewards = 'BlockRewards'
    CurrentYear = 'CurrentYear'
    RecalculationAt = 'DoRecalculationAt'


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
        restart_parachain_and_runtime_upgrade()
        wait_until_block_height(SubstrateInterface(url=WS_URL), 1)

        self.substrate = SubstrateInterface(url=WS_URL)
        self.chain_spec = get_chain(self.substrate)
        self.chain_spec = get_modified_chain_spec(self.chain_spec)

    @pytest.mark.skipif(is_krest_related_chain() is False, reason='Only need to test on the krest chain')
    def test_set_recalculation_time_on_delay_tge(self):
        # Setup and trigger the delay TGE
        block_height = get_block_height(self.substrate)
        trigger_height = block_height + WAIT_BLOCKS
        total_supply = 1 * 10 ** 9 * 10 ** 18
        batch = ExtrinsicBatch(self.substrate, KP_GLOBAL_SUDO)
        batch.compose_sudo_call(
            'InflationManager',
            'set_delayed_tge',
            {
                'block': trigger_height,
                'issuance': total_supply
            },
        )
        receipt = batch.execute_n_clear()
        self.assertTrue(receipt.is_success, f'Failed to set delay TGE: {receipt}')

        for i in range(10 * 2):
            now_height = get_block_height(self.substrate)
            print(f'now_height: {now_height}, trigger_height: {trigger_height}')
            if now_height >= trigger_height:
                break
            time.sleep(12)

        next_recalculate_at = self.substrate.query(
            module='InflationManager',
            storage_function='DoRecalculationAt',
            params=[]
        )
        self.assertEqual(trigger_height + 2628000, next_recalculate_at.value)

        # Setup and trigger the recalculation time
        # It's the main purpose for testing
        block_height = get_block_height(self.substrate)
        trigger_height = block_height + WAIT_BLOCKS
        batch.compose_sudo_call(
            'InflationManager',
            'set_recalculation_time',
            {
                'block': trigger_height,
            },
        )
        receipt = batch.execute_n_clear()
        self.assertTrue(receipt.is_success, f'Failed to set recalculation time: {receipt}')

        for i in range(10 * 2):
            now_height = get_block_height(self.substrate)
            print(f'now_height: {now_height}, trigger_height: {trigger_height}')
            if now_height >= trigger_height:
                break
            time.sleep(12)

        now_height = get_block_height(self.substrate)
        self.assertGreaterEqual(now_height, trigger_height)

        prev_base_inflation_parameters = self._fetch_pallet_storage(
            InflationState.YearlyInflationParameters.value,
            block_height)
        now_base_inflation_parameters = self._fetch_pallet_storage(
            InflationState.YearlyInflationParameters.value,
            now_height)
        self.assertNotEqual(prev_base_inflation_parameters, now_base_inflation_parameters)
        next_recalculate_at = self.substrate.query(
            module='InflationManager',
            storage_function='DoRecalculationAt',
            params=[]
        )
        self.assertEqual(trigger_height + 2628000, next_recalculate_at.value)

    @pytest.mark.skipif(is_krest_related_chain() is True, reason='Only need to test non krestchain')
    def test_set_delay_tge_fail_non_krest(self):
        block_height = get_block_height(self.substrate)
        trigger_height = block_height + WAIT_BLOCKS
        # 9 Billion
        total_supply = 1 * 10 ** 9 * 10 ** 18
        batch = ExtrinsicBatch(self.substrate, KP_GLOBAL_SUDO)
        batch.compose_sudo_call(
            'InflationManager',
            'set_delayed_tge',
            {
                'block': trigger_height,
                'issuance': total_supply
            },
        )
        receipt = batch.execute_n_clear()
        self.assertTrue(receipt.is_success, f'Failed to set delay TGE: {receipt}')

        event = get_event(self.substrate, receipt.block_hash, 'Sudo', 'Sudid')
        self.assertTrue('Err' in event.value['attributes']['sudo_result'])

    @pytest.mark.skipif(is_krest_related_chain() is True, reason='Only need to test on the non krest chain')
    def test_set_recalculation_time_on_init_tge(self):
        first_recalculate_at = self.substrate.query(
            module='InflationManager',
            storage_function='DoRecalculationAt',
            params=[]
        )

        # Setup and trigger the recalculation time
        # It's the main purpose for testing
        block_height = get_block_height(self.substrate)
        trigger_height = block_height + WAIT_BLOCKS
        batch = ExtrinsicBatch(self.substrate, KP_GLOBAL_SUDO)
        batch.compose_sudo_call(
            'InflationManager',
            'set_recalculation_time',
            {
                'block': trigger_height,
            },
        )
        receipt = batch.execute_n_clear()
        self.assertTrue(receipt.is_success, f'Failed to set recalculation time: {receipt}')

        for i in range(10 * 2):
            now_height = get_block_height(self.substrate)
            print(f'now_height: {now_height}, trigger_height: {trigger_height}')
            if now_height >= trigger_height:
                break
            time.sleep(12)

        now_height = get_block_height(self.substrate)
        self.assertGreaterEqual(now_height, trigger_height)

        prev_base_inflation_parameters = self._fetch_pallet_storage(
            InflationState.YearlyInflationParameters.value,
            block_height)
        now_base_inflation_parameters = self._fetch_pallet_storage(
            InflationState.YearlyInflationParameters.value,
            now_height)
        self.assertNotEqual(prev_base_inflation_parameters, now_base_inflation_parameters)
        next_recalculate_at = self.substrate.query(
            module='InflationManager',
            storage_function='DoRecalculationAt',
            params=[]
        )
        self.assertEqual(trigger_height + 2628000, next_recalculate_at.value)
        self.assertNotEqual(first_recalculate_at.value, next_recalculate_at.value)

    @pytest.mark.skipif(is_krest_related_chain() is False, reason='Only need to test on the krest chain')
    def test_set_delay_tge_more(self):
        block_height = get_block_height(self.substrate)
        trigger_height = block_height + WAIT_BLOCKS
        # 9 Billion
        total_supply = 1 * 10 ** 9 * 10 ** 18
        batch = ExtrinsicBatch(self.substrate, KP_GLOBAL_SUDO)
        batch.compose_sudo_call(
            'InflationManager',
            'set_delayed_tge',
            {
                'block': trigger_height,
                'issuance': total_supply
            },
        )
        receipt = batch.execute_n_clear()
        self.assertTrue(receipt.is_success, f'Failed to set delay TGE: {receipt}')
        event = get_event(self.substrate, receipt.block_hash, 'Sudo', 'Sudid')
        self.assertFalse('Err' in event.value['attributes']['sudo_result'])

        for i in range(10 * 2):
            now_height = get_block_height(self.substrate)
            print(f'now_height: {now_height}, trigger_height: {trigger_height}')
            if now_height >= trigger_height:
                break
            time.sleep(12)

        now_height = get_block_height(self.substrate)
        self.assertGreaterEqual(now_height, trigger_height)

        prev_base_inflation_parameters = self._fetch_pallet_storage(
            InflationState.YearlyInflationParameters.value,
            block_height)
        now_base_inflation_parameters = self._fetch_pallet_storage(
            InflationState.YearlyInflationParameters.value,
            now_height)
        self.assertNotEqual(prev_base_inflation_parameters, now_base_inflation_parameters)
        total_balance = self.substrate.query(
            module='Balances',
            storage_function='TotalIssuance',
            params=[],
        )
        self.assertGreaterEqual(total_balance.value, total_supply)
        next_recalculate_at = self.substrate.query(
            module='InflationManager',
            storage_function='DoRecalculationAt',
            params=[]
        )
        self.assertEqual(trigger_height + 2628000, next_recalculate_at.value)

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
        self.assertEqual(onchain_do_recalculation_at, INFLATION_RECALCULATION[self.chain_spec])
