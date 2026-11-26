# Offline tests of the check functions behind the AC-28, AC-29, AC-30 and AC-81 tests: no network. Each check
# gets a result shaped like the local-network dry run and must accept it, then the same result with the
# one thing that check is about broken (an XCM to the relay, no Transfer event, no local XCM, TotalIssuance
# one higher) and must reject it.
import copy
import unittest

from tools.dry_run import check_routed_via_asset_hub, check_transfer_event, check_local_xcm_recorded
from tools.dry_run import check_xcm_issuance

ALICE = '5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY'
BOB = '5FHneW46xGXgs5mUiveU4sbTyGBzmstUspZC92UhjJM694ty'
BOB_ID = '0x8eaf04151687736326c9fea17e25fc5287613693c912909cb226aa4794f26a48'
RELAY_TOKEN = {'parents': 1, 'interior': 'Here'}
OK = ('Ok', {'actual_weight': None, 'pays': 0})


def location(parents, *junctions):
    return {'V5': {'parents': parents, 'interior': {f'X{len(junctions)}': list(junctions)} if junctions else 'Here'}}


def to_asset_hub(last):
    message = [
        {'WithdrawAsset': [{'id': RELAY_TOKEN, 'fun': {'Fungible': 10 ** 13}}]},
        'ClearOrigin',
        {'BuyExecution': {'fees': {'id': RELAY_TOKEN, 'fun': {'Fungible': 5 * 10 ** 12}}, 'weight_limit': 'Unlimited'}},
        last,
        {'SetTopic': '0x' + '11' * 32},
    ]
    return {'execution_result': OK, 'emitted_events': [], 'local_xcm': None,
            'forwarded_xcms': [(location(1, {'Parachain': 1000}), [{'V5': message}])]}


DEPOSIT_TO_BOB = {'DepositAsset': {'assets': {'Wild': {'AllCounted': 1}}, 'beneficiary': location(
    0, {'AccountId32': {'network': None, 'id': BOB_ID}})['V5']}}
RESERVE_TO_3000 = {'DepositReserveAsset': {'assets': {'Wild': {'AllCounted': 1}},
                                           'dest': location(1, {'Parachain': 3000})['V5'], 'xcm': []}}


def sent_to_the_relay(effects):
    """The same forwarded XCM, addressed to the relay instead of Asset Hub."""
    broken = copy.deepcopy(effects)
    broken['forwarded_xcms'][0] = (location(1), broken['forwarded_xcms'][0][1])
    return broken


class TestRoutedViaAssetHub(unittest.TestCase):
    def test_ac28_accepts_a_transfer_forwarded_to_asset_hub(self):
        check_routed_via_asset_hub(to_asset_hub(DEPOSIT_TO_BOB))

    def test_ac28_rejects_a_transfer_forwarded_to_the_relay(self):
        with self.assertRaisesRegex(AssertionError, 'forwarded to the relay'):
            check_routed_via_asset_hub(sent_to_the_relay(to_asset_hub(DEPOSIT_TO_BOB)))

    def test_ac28_rejects_a_failed_transfer_with_nothing_forwarded(self):
        failed = to_asset_hub(DEPOSIT_TO_BOB)
        failed['execution_result'] = ('Err', {'Module': {'index': 36, 'error': '0x05000000'}})
        failed['forwarded_xcms'] = []
        with self.assertRaisesRegex(AssertionError, 'the transfer failed'):
            check_routed_via_asset_hub(failed)

    def test_ac28_rejects_an_extra_instruction_that_sends_on_to_the_relay(self):
        effects = to_asset_hub(DEPOSIT_TO_BOB)
        message = effects['forwarded_xcms'][0][1][0]['V5']
        message.insert(3, {'DepositReserveAsset': {'assets': {'Wild': {'AllCounted': 1}},
                                                   'dest': location(1)['V5'], 'xcm': []}})
        with self.assertRaisesRegex(AssertionError, 'expected the instructions'):
            check_routed_via_asset_hub(effects)

    def test_ac29_accepts_a_reserve_deposit_to_the_sibling_through_asset_hub(self):
        check_routed_via_asset_hub(to_asset_hub(RESERVE_TO_3000), reserve_dest=(1, ({'Parachain': 3000},)))

    def test_ac29_rejects_the_same_message_sent_to_the_relay(self):
        with self.assertRaisesRegex(AssertionError, 'forwarded to the relay'):
            check_routed_via_asset_hub(sent_to_the_relay(to_asset_hub(RESERVE_TO_3000)),
                                       reserve_dest=(1, ({'Parachain': 3000},)))


class TestDryRunApiChecks(unittest.TestCase):
    def transfer_effects(self):
        # as the peaq-dev dry run of Balances.transfer_keep_alive decoded it, plus a Withdraw before it
        events = [{'event_index': '0408', 'module_id': 'Balances', 'event_id': 'Withdraw',
                   'attributes': {'who': ALICE, 'amount': 1}},
                  {'event_index': '0402', 'module_id': 'Balances', 'event_id': 'Transfer',
                   'attributes': {'from': ALICE, 'to': BOB, 'amount': 10 ** 18}}]
        return {'execution_result': OK, 'emitted_events': events, 'local_xcm': None, 'forwarded_xcms': []}

    def test_ac81_1_accepts_the_transfer_event(self):
        check_transfer_event(self.transfer_effects(), ALICE, BOB, 10 ** 18)

    def test_ac81_1_rejects_no_emitted_events(self):
        effects = self.transfer_effects()
        effects['emitted_events'] = []
        with self.assertRaisesRegex(AssertionError, 'no Balances.Transfer'):
            check_transfer_event(effects, ALICE, BOB, 10 ** 18)

    def test_ac81_3_accepts_a_recorded_local_xcm(self):
        check_local_xcm_recorded({'execution_result': OK, 'emitted_events': [], 'forwarded_xcms': [],
                                  'local_xcm': {'V5': [{'WithdrawAsset': []}]}})

    def test_ac81_3_rejects_no_local_xcm(self):
        with self.assertRaisesRegex(AssertionError, 'local_xcm is None'):
            check_local_xcm_recorded({'execution_result': OK, 'emitted_events': [], 'forwarded_xcms': [],
                                      'local_xcm': None})


class TestXcmIssuance(unittest.TestCase):
    # the readings test_xcm_execution_mints_nothing printed for block #48 in its first peaq-dev
    # local-network run on 2026-11-26 (later runs check other blocks, with other numbers)
    READINGS = {
        'issuance_before': 400001089421613764048877070, 'issuance_after': 400001091324201283074752260,
        'block_reward': 1902587519025875190,
        'sinks_before': 67161339879208486273, 'sinks_after': 69063927860525290388, 'native_fee': 462290928925,
        'foreign_fee': 500, 'revenue_before': 0, 'revenue_after': 500,
    }

    def test_ac30_accepts_issuance_moved_by_the_block_reward_alone(self):
        check_xcm_issuance(self.READINGS)

    def test_ac30_rejects_total_issuance_one_higher(self):
        with self.assertRaisesRegex(AssertionError, 'the XCM changed it by 1'):
            check_xcm_issuance(dict(self.READINGS, issuance_after=self.READINGS['issuance_after'] + 1))


if __name__ == '__main__':
    unittest.main()
