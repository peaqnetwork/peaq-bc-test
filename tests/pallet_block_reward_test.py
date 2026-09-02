from substrateinterface import SubstrateInterface, Keypair
from tools.constants import WS_URL
from tools.utils import PERBILL_PERCENT
from tools.utils import block_reward_pallet_sink
from tools.utils import get_block_reward_sink_share
from tools.utils import get_block_reward_sinks
from tools.utils import get_event
from tools.utils import set_block_reward_sinks
import unittest
import pytest

COLLATOR_REWARD_RATE = 0.1
WAIT_TIME_PERIOD = 12 * 3


@pytest.mark.substrate
class TestPalletBlockReward(unittest.TestCase):

    def setUp(self):
        self.substrate = SubstrateInterface(url=WS_URL)
        self.kp_src = Keypair.create_from_uri('//Alice')
        self.ori_sinks = get_block_reward_sinks(self.substrate)

    def tearDown(self):
        receipt = set_block_reward_sinks(self.substrate, self.ori_sinks)
        self.assertTrue(receipt.is_success,
                        'cannot restore the block reward sinks')

    def test_set_sinks(self):
        set_value = [
            block_reward_pallet_sink('treasury', 40 * PERBILL_PERCENT),
            block_reward_pallet_sink('stake', 60 * PERBILL_PERCENT),
        ]
        receipt = set_block_reward_sinks(self.substrate, set_value)
        self.assertTrue(receipt.is_success,
                        'cannot setup the block reward sinks')

        self.assertEqual(
            get_block_reward_sink_share(self.substrate, 'treasury'),
            40 * PERBILL_PERCENT)
        self.assertEqual(
            get_block_reward_sink_share(self.substrate, 'stake'),
            60 * PERBILL_PERCENT)
        self.assertEqual(len(get_block_reward_sinks(self.substrate)), 2)

    def test_add_sink(self):
        # Start from a known two-sink split so the test does not depend on
        # whatever the chain happens to be configured with.
        receipt = set_block_reward_sinks(self.substrate, [
            block_reward_pallet_sink('treasury', 70 * PERBILL_PERCENT),
            block_reward_pallet_sink('stake', 30 * PERBILL_PERCENT),
        ])
        self.assertTrue(receipt.is_success,
                        'cannot setup the baseline block reward sinks')

        # Take 10% off the treasury share and route it to a third pot. Shares
        # must still add up to exactly 100% or the pallet rejects the call.
        receipt = set_block_reward_sinks(self.substrate, [
            block_reward_pallet_sink('treasury', 60 * PERBILL_PERCENT),
            block_reward_pallet_sink('stake', 30 * PERBILL_PERCENT),
            block_reward_pallet_sink('coretime', 10 * PERBILL_PERCENT),
        ])
        self.assertTrue(receipt.is_success, 'cannot add the new sink')

        now_sinks = get_block_reward_sinks(self.substrate)
        self.assertEqual(len(now_sinks), 3, f'sink was not added: {now_sinks}')
        self.assertEqual(
            get_block_reward_sink_share(self.substrate, 'coretime'),
            10 * PERBILL_PERCENT,
            'the added sink does not carry the expected share')
        self.assertEqual(
            get_block_reward_sink_share(self.substrate, 'treasury'),
            60 * PERBILL_PERCENT,
            'the existing sink was not reduced to make room')

        event = get_event(
            self.substrate, receipt.block_hash,
            'BlockReward', 'TokenSinksUpdated')
        self.assertIsNotNone(event, 'TokenSinksUpdated event not found')
