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

from substrateinterface.utils.hasher import blake2_256

from tools.constants import KP_GLOBAL_SUDO, PARACHAIN_WS_URL
from tools.coretime_utils import get_parachain_id
from tools.asset import RELAY_ASSET_ID, RELAY_ASSET_LOCATION, RELAY_METADATA, UNITS_PER_SECOND
from tools.asset import setup_asset_if_not_exist, setup_xc_register_if_not_exist
from tools.asset import get_tokens_account_from_pallet_assets
from tools.dry_run import check_xcm_issuance

SIBLING_WS = 'ws://127.0.0.1:10144'
SIBLING_PARA = 3000
# Events in block N that move PEAQ for reasons other than the XCM: the issuance and pot sums
# would not add up, so the message is sent again and another block is checked.
UNRELATED_EVENTS = {('Balances', 'DustLost'), ('ParachainStaking', 'Rewarded')}
ISSUANCE_ATTEMPTS = 3


def sibling_sovereign(para_id, ss58_format):
    """peaq SiblingParachainConvertsVia -> into_account_truncating:
    raw bytes b"sibl" + para_id(u32 LE), zero-padded to 32 (NOT hashed)."""
    pub = (b'sibl' + para_id.to_bytes(4, 'little')).ljust(32, b'\x00')
    return pub, Keypair(public_key=pub, ss58_format=ss58_format).ss58_address


def pallet_account(pallet_id, ss58_format):
    """PalletId::into_account_truncating: b"modl" + the 8-byte id, zero-padded to 32."""
    return Keypair(public_key=(b'modl' + pallet_id).ljust(32, b'\x00'), ss58_format=ss58_format).ss58_address


def sink_accounts(si, ss58_format):
    """The accounts BlockReward pays into (BlockReward::resolve of each sink target)."""
    accounts = []
    for sink in si.query('BlockReward', 'Sinks').value:
        (kind, value), = sink['target'].items()
        raw = bytes.fromhex(value[2:]) if isinstance(value, str) else bytes(value)
        if kind == 'Pallet':
            accounts.append(pallet_account(raw, ss58_format))
        else:  # Evm: HashedAddressMapping<BlakeTwo256>
            accounts.append(Keypair(public_key=blake2_256(b'evm:' + raw), ss58_format=ss58_format).ss58_address)
    return accounts


@pytest.mark.xcm
class TestXcmFeeToBlockReward(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.si = SubstrateInterface(url=PARACHAIN_WS_URL)
        cls.si_sibling = SubstrateInterface(url=SIBLING_WS)
        props = cls.si.rpc_request('system_properties', []).get('result') or {}
        cls.ss58 = props.get('ss58Format') or 42
        # para id of the chain under test (peaq=3338, peaq-dev=2000, krest=...);
        # the inbound XCM dest must target THIS chain, not a hardcoded value.
        cls.self_para = get_parachain_id()
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
        dest = {'V4': {'parents': 1, 'interior': {'X1': [{'Parachain': self.self_para}]}}}
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

    def _send_from_sibling_and_find_block(self, message):
        """Sends `message` from the sibling; returns the hash of the block that processed it, and its events."""
        start = self.si.get_block()['header']['number']
        dest = {'V4': {'parents': 1, 'interior': {'X1': [{'Parachain': self.self_para}]}}}
        b = ExtrinsicBatch(self.si_sibling, KP_GLOBAL_SUDO)
        b.compose_sudo_call('PolkadotXcm', 'send', {'dest': dest, 'message': message})
        self.assertTrue(b.execute().is_success, 'sibling polkadotXcm.send failed')
        checked = start
        for _ in range(30):
            time.sleep(2)
            head = self.si.get_block()['header']['number']
            for bn in range(checked + 1, head + 1):
                bh = self.si.get_block_hash(bn)
                events = [ev.value for ev in self.si.get_events(bh)]
                # Matched by origin only. A different message from the sibling would buy no relay-token
                # execution, so check_xcm_issuance fails on foreign_fee == 0 rather than passing.
                for v in events:
                    if v['module_id'] == 'MessageQueue' and v['event_id'] == 'Processed' \
                            and v['attributes'].get('origin') == {'Sibling': SIBLING_PARA}:
                        self.assertTrue(v['attributes'].get('success'), f'the XCM failed in block #{bn}: {v}')
                        return bn, bh, events
            checked = head
        self.fail(f'the XCM from the sibling was not processed in blocks #{start + 1}..#{checked}')

    def _issuance_readings(self, bh, sov, revenue, sinks):
        asset = RELAY_ASSET_ID['peaq']
        return {
            'issuance': self.si.query('Balances', 'TotalIssuance', block_hash=bh).value,
            'sinks': sum(self._free(a, bh) for a in sinks),
            'sov_native': self._free(sov, bh),
            'sov_foreign': get_tokens_account_from_pallet_assets(self.si, sov, asset, bh),
            'revenue': get_tokens_account_from_pallet_assets(self.si, revenue, asset, bh),
        }

    def test_xcm_execution_mints_nothing(self):
        # AC-30: an inbound XCM that buys execution twice, first in PEAQ and then in the relay token,
        # leaves TotalIssuance moved by the block reward alone.
        pub, sov = sibling_sovereign(SIBLING_PARA, self.ss58)
        asset = RELAY_ASSET_ID['peaq']
        receipt = setup_asset_if_not_exist(self.si, KP_GLOBAL_SUDO, asset, RELAY_METADATA)
        self.assertTrue(receipt.is_success, f'failed to create the relay token asset: {receipt.error_message}')
        receipt = setup_xc_register_if_not_exist(
            self.si, KP_GLOBAL_SUDO, asset, RELAY_ASSET_LOCATION['peaq'], UNITS_PER_SECOND)
        self.assertTrue(receipt.is_success, f'failed to register the relay token: {receipt.error_message}')

        # The sovereign holds PEAQ and the relay token, so WithdrawAsset can take both.
        foreign_amount = 10 ** 12
        issuer = self.si.query('Assets', 'Asset', [asset]).value['issuer']
        mint = self.si.compose_call('Assets', 'mint', {
            'id': asset, 'beneficiary': sov, 'amount': ISSUANCE_ATTEMPTS * foreign_amount})
        b = ExtrinsicBatch(self.si, KP_GLOBAL_SUDO)
        b.compose_sudo_call('Balances', 'force_set_balance', {'who': sov, 'new_free': 1000 * 10 ** 18})
        b.compose_call('Sudo', 'sudo_as', {'who': issuer, 'call': mint.value})
        self.assertTrue(b.execute().is_success, 'failed to fund the sibling sovereign')
        self.assertGreaterEqual(
            get_tokens_account_from_pallet_assets(self.si, sov, asset), ISSUANCE_ATTEMPTS * foreign_amount,
            'minting the relay token to the sibling sovereign did not take effect')

        # The fee of the second BuyExecution goes to PeaqXcmFungibleFeeHandler's account, PeaqPotAccount.
        revenue = pallet_account(b'PotStake', self.ss58)
        sinks = sink_accounts(self.si, self.ss58)
        native = {'id': {'parents': 0, 'interior': 'Here'}, 'fun': {'Fungible': 100 * 10 ** 18}}
        foreign = {'id': {'parents': 1, 'interior': 'Here'}, 'fun': {'Fungible': foreign_amount}}
        message = {'V4': [[
            {'WithdrawAsset': [[native, foreign]]},
            # The barrier turns this Unlimited into the message's weight.
            {'BuyExecution': {'fees': native, 'weight_limit': 'Unlimited'}},
            # An Unlimited BuyExecution after the first one buys nothing, so this one is Limited.
            {'BuyExecution': {'fees': foreign, 'weight_limit': {
                'Limited': {'ref_time': 10 ** 9, 'proof_size': 64 * 1024}}}},
            'RefundSurplus',
            {'DepositAsset': {
                'assets': {'Wild': 'All'},
                'beneficiary': {'parents': 0, 'interior': {
                    'X1': [{'AccountId32': {'network': None, 'id': f'0x{pub.hex()}'}}]}}}},
        ]]}

        for attempt in range(1, ISSUANCE_ATTEMPTS + 1):
            bn, bh, events = self._send_from_sibling_and_find_block(message)
            signed = [ex.value.get('call', {}).get('call_function') for ex in self.si.get_block(bh)['extrinsics']
                      if ex.value.get('signature')]
            unrelated = [(v['module_id'], v['event_id']) for v in events
                         if (v['module_id'], v['event_id']) in UNRELATED_EVENTS]
            processed = sum((v['module_id'], v['event_id']) == ('MessageQueue', 'Processed') for v in events)
            if signed or unrelated or processed > 1:
                print(f'attempt {attempt}: block #{bn} also has signed extrinsics {signed}, '
                      f'unrelated events {unrelated} or {processed - 1} other XCM; sending again')
                continue
            parent = self.si.get_block_header(bh)['header']['parentHash']
            before = self._issuance_readings(parent, sov, revenue, sinks)
            after = self._issuance_readings(bh, sov, revenue, sinks)
            readings = {
                'issuance_before': before['issuance'], 'issuance_after': after['issuance'],
                'block_reward': sum(int(v['attributes']) for v in events
                                    if (v['module_id'], v['event_id']) == ('BlockReward', 'BlockRewardsDistributed')),
                'sinks_before': before['sinks'], 'sinks_after': after['sinks'],
                'native_fee': before['sov_native'] - after['sov_native'],
                'foreign_fee': before['sov_foreign'] - after['sov_foreign'],
                'revenue_before': before['revenue'], 'revenue_after': after['revenue'],
            }
            print(f'block #{bn} readings: {readings}')
            check_xcm_issuance(readings)
            return
        self.fail(f'every one of {ISSUANCE_ATTEMPTS} blocks had other PEAQ movements; nothing was checked')


if __name__ == '__main__':
    unittest.main()
