"""XCM checks through DryRunApi and XcmPaymentApi, on a local network that produces blocks.

- AC-28: XTokens.transfer of the relay token "to the relay" goes to Asset Hub (para 1000), the
  relay token's reserve since ORML #1035, and nothing goes to the relay.
- AC-29: the relay token sent to a sibling also goes through Asset Hub, which deposits it on to
  the sibling with DepositReserveAsset.
- AC-81: DryRunApi and XcmPaymentApi answer at a block after #0: a transfer's dry run lists its
  Balances.Transfer, the delivery fee to the relay, and a PolkadotXcm.transfer_assets dry run
  records the XCM it ran locally.

AC-28 and AC-29 dry-run a transfer whose XCM is queued for para 1000, which only succeeds when
the chain has an HRMP channel to 1000. The local network needs a stand-in para 1000 with a channel
from the chain under test; without one these two tests are skipped.
"""
import unittest

import pytest
from substrateinterface import SubstrateInterface, Keypair
from peaq.utils import ExtrinsicBatch

from tools.constants import KP_GLOBAL_SUDO, PARACHAIN_WS_URL
from tools.asset import RELAY_ASSET_ID, RELAY_ASSET_LOCATION, RELAY_METADATA, UNITS_PER_SECOND
from tools.asset import setup_asset_if_not_exist, setup_xc_register_if_not_exist
from tools.asset import get_tokens_account_from_pallet_assets
from tools.dry_run import XcmRuntimeApis, check_routed_via_asset_hub, check_transfer_event
from tools.dry_run import check_local_xcm_recorded

ONE_PEAQ = 10 ** 18
RELAY_TOKEN_AMOUNT = 10 ** 13  # 10 DOT, 12 decimals
KP_BOB = Keypair.create_from_uri('//Bob')
ASSET_HUB_PARA = 1000
SIBLING_PARA = 3000


def account(kp):
    return {'AccountId32': {'network': None, 'id': f'0x{kp.public_key.hex()}'}}


@pytest.mark.xcm
class TestXcmDryRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.si = SubstrateInterface(url=PARACHAIN_WS_URL)
        cls.apis = XcmRuntimeApis(cls.si)
        cls.alice = KP_GLOBAL_SUDO.ss58_address
        # The dry runs use the best block, so this makes all of them run after block #0 (AC-81).
        best = cls.si.get_block()['header']['number']
        assert best >= 1, f'the chain is at block #{best}; these checks need a chain that produces blocks'

    def dry_run(self, module, function, params):
        effects = self.apis.dry_run_call(self.alice, self.si.compose_call(module, function, params))
        print(f'dry run {module}.{function}: {effects}')
        return effects

    def give_alice_relay_tokens(self):
        """Registers the relay token (asset 1 at (1, Here)) and mints some to Alice, the dry-run origin."""
        if not self.has_channel_to(ASSET_HUB_PARA):
            raise unittest.SkipTest(f'no HRMP channel to para {ASSET_HUB_PARA}, the Asset Hub stand-in')
        asset = RELAY_ASSET_ID['peaq']
        receipt = setup_asset_if_not_exist(self.si, KP_GLOBAL_SUDO, asset, RELAY_METADATA)
        self.assertTrue(receipt.is_success, f'failed to create the relay token asset: {receipt.error_message}')
        receipt = setup_xc_register_if_not_exist(
            self.si, KP_GLOBAL_SUDO, asset, RELAY_ASSET_LOCATION['peaq'], UNITS_PER_SECOND)
        self.assertTrue(receipt.is_success, f'failed to register the relay token: {receipt.error_message}')
        if get_tokens_account_from_pallet_assets(self.si, self.alice, asset) >= RELAY_TOKEN_AMOUNT:
            return
        issuer = self.si.query('Assets', 'Asset', [asset]).value['issuer']
        mint = self.si.compose_call('Assets', 'mint', {
            'id': asset, 'beneficiary': self.alice, 'amount': 10 * RELAY_TOKEN_AMOUNT})
        b = ExtrinsicBatch(self.si, KP_GLOBAL_SUDO)
        b.compose_call('Sudo', 'sudo_as', {'who': issuer, 'call': mint.value})
        self.assertTrue(b.execute().is_success, 'failed to mint the relay token')
        self.assertGreaterEqual(
            get_tokens_account_from_pallet_assets(self.si, self.alice, asset), RELAY_TOKEN_AMOUNT,
            'minting the relay token to Alice did not take effect')

    def has_channel_to(self, para_id):
        state = self.si.query('ParachainSystem', 'RelevantMessagingState').value
        return state is not None and any(int(c[0]) == para_id for c in state['egress_channels'])

    def xtokens_relay_token(self, interior):
        return self.dry_run('XTokens', 'transfer', {
            'currency_id': RELAY_ASSET_ID['peaq'],
            'amount': RELAY_TOKEN_AMOUNT,
            'dest': {'V4': {'parents': 1, 'interior': interior}},
            'dest_weight_limit': 'Unlimited',
        })

    def test_relay_token_to_the_relay_goes_to_asset_hub(self):
        # AC-28, once with the beneficiary on the relay and once on Asset Hub
        self.give_alice_relay_tokens()
        for interior in ({'X1': [account(KP_BOB)]},
                         {'X2': [{'Parachain': ASSET_HUB_PARA}, account(KP_BOB)]}):
            with self.subTest(dest=interior):
                check_routed_via_asset_hub(self.xtokens_relay_token(interior))

    def test_relay_token_to_a_sibling_goes_through_asset_hub(self):
        # AC-29
        self.give_alice_relay_tokens()
        effects = self.xtokens_relay_token({'X2': [{'Parachain': SIBLING_PARA}, account(KP_BOB)]})
        check_routed_via_asset_hub(effects, reserve_dest=(1, ({'Parachain': SIBLING_PARA},)))

    def test_transfer_dry_run_lists_the_transfer_event(self):
        # AC-81 (1)
        effects = self.dry_run('Balances', 'transfer_keep_alive', {'dest': KP_BOB.ss58_address, 'value': ONE_PEAQ})
        check_transfer_event(effects, self.alice, KP_BOB.ss58_address, ONE_PEAQ)

    def test_delivery_fee_to_the_relay(self):
        # AC-81 (2): the relay route is priced at () and charges nothing, which the stable2603
        # helper reports as Unimplemented (like the sibling route in AC-12).
        here = {'parents': 0, 'interior': 'Here'}
        message = {'V5': [[
            {'WithdrawAsset': [[{'id': here, 'fun': {'Fungible': ONE_PEAQ}}]]},
            {'BuyExecution': {'fees': {'id': here, 'fun': {'Fungible': ONE_PEAQ}}, 'weight_limit': 'Unlimited'}},
            {'DepositAsset': {'assets': {'Wild': 'All'},
                              'beneficiary': {'parents': 0, 'interior': {'X1': [account(KP_BOB)]}}}},
        ]]}
        result = self.apis.query_delivery_fees(
            {'V5': {'parents': 1, 'interior': 'Here'}}, message, {'V5': here})
        print(f'query_delivery_fees to the relay: {result}')
        self.assertEqual(result, ('Err', 'Unimplemented'))

    def test_transfer_assets_dry_run_records_the_local_xcm(self):
        # AC-81 (3): 1 PEAQ to Bob on the relay. PEAQ is a local reserve for the relay and peaq
        # allows reserve transfers of everything; only peaq's side of the dry run is checked.
        effects = self.dry_run('PolkadotXcm', 'transfer_assets', {
            'dest': {'V5': {'parents': 1, 'interior': 'Here'}},
            'beneficiary': {'V5': {'parents': 0, 'interior': {'X1': [account(KP_BOB)]}}},
            'assets': {'V5': [[{'id': {'parents': 0, 'interior': 'Here'}, 'fun': {'Fungible': ONE_PEAQ}}]]},
            'fee_asset_item': 0,
            'weight_limit': 'Unlimited',
        })
        check_local_xcm_recorded(effects)


if __name__ == '__main__':
    unittest.main()
