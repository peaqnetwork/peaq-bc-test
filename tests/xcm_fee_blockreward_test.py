"""XCMFEE-1: XCM execution fee routes to BlockReward.

An inbound sibling XCM that pays its BuyExecution fee in PEAQ-native (the
self-reserve asset) must route that fee to the BlockReward pallet via
``BlockRewardWrapper`` — the first entry of peaq's XCM Trader tuple
``UsingComponents<WeightToFee, SelfReserveLocation, .., BlockRewardWrapper>``
(runtime/peaq/src/xcm_config.rs). This closes the gap left by
pallet_block_reward_test.py, which only tests the reward-distribution
*config*, not the XCM-fee -> BlockReward routing path.

Triggered from sibling para 3000 because peaq blocks local
``polkadotXcm.execute`` (``XcmExecuteFilter = Nothing``); the only way to
exercise the Trader is an inbound message. The sibling sovereign account is
funded with native PEAQ so ``WithdrawAsset`` can pay the execution fee.
"""
import time
import unittest

import pytest
from substrateinterface import SubstrateInterface, Keypair
from peaq.utils import ExtrinsicBatch

from tools.constants import KP_GLOBAL_SUDO, PARACHAIN_WS_URL

SIBLING_WS = 'ws://127.0.0.1:10144'
SIBLING_PARA = 3000
SELF_PARA = 3338


def sibling_sovereign(para_id, ss58_format):
    """peaq SiblingParachainConvertsVia -> into_account_truncating:
    raw bytes b"sibl" + para_id(u32 LE), zero-padded to 32 (NOT hashed)."""
    pub = (b'sibl' + para_id.to_bytes(4, 'little')).ljust(32, b'\x00')
    return pub, Keypair(public_key=pub, ss58_format=ss58_format).ss58_address


@pytest.mark.xcm
class TestXcmFeeToBlockReward(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.si = SubstrateInterface(url=PARACHAIN_WS_URL)
        cls.si_sibling = SubstrateInterface(url=SIBLING_WS)
        props = cls.si.rpc_request('system_properties', []).get('result') or {}
        cls.ss58 = props.get('ss58Format') or 42
        # ensure the 3000<->3338 HRMP channel exists (tolerant if already open)
        try:
            from tools.xcm_setup import setup_hrmp_channel
            setup_hrmp_channel()
        except Exception:
            pass
        # the sibling must be authoring blocks or polkadotXcm.send never finalizes
        b1 = cls.si_sibling.get_block()['header']['number']
        time.sleep(8)
        if cls.si_sibling.get_block()['header']['number'] == b1:
            raise unittest.SkipTest(
                f'sibling para {SIBLING_PARA} not producing blocks (needs coretime); '
                f'cannot trigger inbound XCM')

    def _free(self, who, bh=None):
        return self.si.query('System', 'Account', [who], block_hash=bh).value['data']['free']

    def test_xcm_execution_fee_routes_to_block_reward(self):
        pub, sov = sibling_sovereign(SIBLING_PARA, self.ss58)

        # fund the sibling sovereign so its inbound WithdrawAsset can pay the fee
        fund = 1000 * 10 ** 18
        b = ExtrinsicBatch(self.si, KP_GLOBAL_SUDO)
        b.compose_sudo_call('Balances', 'force_set_balance', {'who': sov, 'new_free': fund})
        self.assertTrue(b.execute().is_success, 'failed to fund sibling sovereign')

        sov_before = self._free(sov)
        start = self.si.get_block()['header']['number']

        # sibling 3000 sends an inbound XCM buying execution in PEAQ-native (Here).
        # WithdrawAsset(N) -> BuyExecution(fee) -> RefundSurplus -> DepositAsset(rest back).
        amount = {'id': {'parents': 0, 'interior': 'Here'}, 'fun': {'Fungible': 100 * 10 ** 18}}
        message = {'V4': [[
            {'WithdrawAsset': [[amount]]},
            {'BuyExecution': {'fees': amount, 'weight_limit': 'Unlimited'}},
            'RefundSurplus',
            {'DepositAsset': {
                'assets': {'Wild': 'All'},
                'beneficiary': {'parents': 0, 'interior': {
                    'X1': [{'AccountId32': {'network': None, 'id': f'0x{pub.hex()}'}}]}}}},
        ]]}
        dest = {'V4': {'parents': 1, 'interior': {'X1': [{'Parachain': SELF_PARA}]}}}
        b2 = ExtrinsicBatch(self.si_sibling, KP_GLOBAL_SUDO)
        b2.compose_sudo_call('PolkadotXcm', 'send', {'dest': dest, 'message': message})
        self.assertTrue(b2.execute().is_success, 'sibling polkadotXcm.send failed')

        # locate the 3338 block that processed our inbound sibling message
        processed_bh = None
        fee_events = []
        for _ in range(30):
            time.sleep(2)
            head = self.si.get_block()['header']['number']
            for bn in range(start + 1, head + 1):
                bh = self.si.get_block_hash(bn)
                ours = False
                fees = []
                for ev in self.si.get_events(bh):
                    v = ev.value
                    mod, evt = v.get('module_id'), v.get('event_id')
                    attrs = v.get('attributes')
                    if mod == 'MessageQueue' and evt == 'Processed' \
                            and attrs.get('origin') == {'Sibling': SIBLING_PARA}:
                        ours = True
                        self.assertTrue(attrs.get('success'),
                                        'inbound XCM did not execute successfully')
                    if mod == 'BlockReward' and evt == 'TransactionFeesDistributed':
                        fees.append(int(attrs))
                if ours:
                    processed_bh, fee_events = bh, fees
                    break
            if processed_bh:
                break

        self.assertIsNotNone(processed_bh, 'inbound XCM was never processed on 3338')

        # The fee taken from the payer (sovereign) must equal a BlockReward
        # TransactionFeesDistributed value in the same block: fee routed to
        # BlockReward, exact amount, no leak and no double-count.
        fee_paid = sov_before - self._free(sov, processed_bh)
        self.assertGreater(fee_paid, 0, 'no XCM execution fee was charged')
        self.assertIn(
            fee_paid, fee_events,
            f'XCM execution fee {fee_paid} not routed to BlockReward '
            f'(TransactionFeesDistributed values seen: {fee_events})')


if __name__ == '__main__':
    unittest.main()
