import unittest
from tests.utils_func import restart_parachain_and_runtime_upgrade
from tools.constants import WS_URL, ACA_WS_URL
from tools.constants import ACA_PD_CHAIN_ID
from tools.constants import PARACHAIN_WS_URL
from tools.runtime_upgrade import wait_until_block_height
from substrateinterface import SubstrateInterface, Keypair
from peaq.utils import ExtrinsicBatch
from tools.constants import KP_GLOBAL_SUDO
from peaq.utils import get_account_balance
from tools.asset import get_valid_asset_id
from tools.utils import get_modified_chain_spec
from tools.peaq_eth_utils import generate_random_hex
from peaq.did import did_rpc_read
from peaq.utils import get_chain
import pytest


@pytest.mark.relaunch
@pytest.mark.xcm
class TestXCMSend(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        restart_parachain_and_runtime_upgrade()
        wait_until_block_height(SubstrateInterface(url=PARACHAIN_WS_URL), 1)

    def setUp(self):
        self.si_peaq = SubstrateInterface(url=WS_URL)
        wait_until_block_height(SubstrateInterface(url=PARACHAIN_WS_URL), 1)
        self.setup_sibling_parachain_account()

    # Just calculate the sibling parachain account by moonbeam's xcm-utils tool
    # Here is the command but remember to change the parachain id
    # yarn calculate-multilocation-derivative-account --a 0xd43593c715fdd31c61141abd04a99fd6822c8558854ccde39a5684e7a56da27d --p 2000 --parents
    def setup_sibling_parachain_account(self):
        chain_spec = get_chain(self.si_peaq)
        chain = get_modified_chain_spec(chain_spec)
        if chain == 'peaq-dev':
            self.sibling_parachain_addr = '5F7JyCFcjQFvSiA3F2Qc6GFiUG4bcTZzrw7qmk654jhEAcBG'
        elif chain == 'krest':
            self.sibling_parachain_addr = '5GUrLK65TVgmN9AKrGC3bB72QmftqYhp1MhwbXEWQkuSiPQT'
        elif chain == 'peaq':
            self.sibling_parachain_addr = '5FKuGfGf4bCFBQkNpLhEStVQGkx8QfDRKEqBbmQmijDj2zTu'

    def _fund_eth_account(self):
        # transfer
        batch = ExtrinsicBatch(self.si_peaq, KP_GLOBAL_SUDO)
        batch.compose_call(
            'Balances',
            'transfer_keep_alive',
            {
                'dest': self.kp_eth['substrate'],
                'value': 100 * 10 ** 18,
            }
        )
        batch.execute()

    def aca_fund(self, substrate, kp_sudo, ss58_addr, new_free):
        batch = ExtrinsicBatch(substrate, kp_sudo)
        batch.compose_sudo_call(
            'Balances',
            'force_set_balance',
            {
                'who': ss58_addr,
                'new_free': new_free,
            }
        )
        return batch.execute()

    def _compose_valid_asset_create(self, substrate, kp, asset_id):
        encoded_tx = substrate.compose_call(
            call_module='Assets',
            call_function='create',
            call_params={
                'id': asset_id,
                'admin': kp.ss58_address,
                'min_balance': 101,
            }
        )
        return str(encoded_tx.encode())

    def _compose_random_did_create(self, substrate, kp, did_name):
        encoded_tx = substrate.compose_call(
            call_module='PeaqDid',
            call_function='add_attribute',
            call_params={
                'did_account': kp.ss58_address,
                'name': did_name,
                'value': generate_random_hex(10),
                'valid_for': None,
            }
        )
        return str(encoded_tx.encode())

    def _compose_xcm_send_message_dict(self, kp):
        account = f'0x{kp.public_key.hex()}'
        instr1 = {
            'WithdrawAsset': [
                [{
                  'id': {
                        'parents': '0',
                        'interior': 'Here',
                  },
                  'fun': {'Fungible': 100 * 10 ** 18},
                }],
            ]
        }
        instr2 = {
            'BuyExecution': {
                'fees': {
                    'id': {
                        'parents': '0',
                        'interior': 'Here',
                    },
                    'fun': {'Fungible': 100 * 10 ** 18},
                },
                'weight_limit': 'Unlimited',
            }
        }

        instr3 = {
            'DepositAsset': {
                'assets': {'Wild': 'All'},
                'beneficiary': {
                    'parents': '0',
                    'interior': {
                        'X1': [{
                            'AccountId32': {'network': None, 'id': account}
                        }]
                    }
                }
            }
        }
        message = {'V4': [[instr1, instr2, instr3]]}

        return {
            'dest': {'V4': {
                'parents': '1',
                'interior': {
                    'X1': [{
                        'Parachain': ACA_PD_CHAIN_ID
                    }]
                },
            }},
            'message': message,
        }

    def _compose_xcm_send_message_call(self, kp, call):
        account = f'0x{kp.public_key.hex()}'
        instr1 = {
            'WithdrawAsset': [
                [{
                  'id': {
                        'parents': '0',
                        'interior': 'Here',
                  },
                  'fun': {'Fungible': 100 * 10 ** 18},
                }],
            ]
        }
        instr2 = {
            'BuyExecution': {
                'fees': {
                    'id': {
                        'parents': '0',
                        'interior': 'Here',
                    },
                    'fun': {'Fungible': 90 * 10 ** 18},
                },
                'weight_limit': 'Unlimited',
            }
        }

        instr3 = {
            'Transact': {
                'origin_kind': 'SovereignAccount',
                'require_weight_at_most': {
                    'ref_time': 400128448000,
                    'proof_size': 10000
                },
                'call': call
            }
        }

        instr4 = 'RefundSurplus'
        instr5 = {
            'DepositAsset': {
                'assets': {'Wild': 'All'},
                'beneficiary': {
                    'parents': '0',
                    'interior': {
                        'X1': [{
                            'AccountId32': {'network': None, 'id': account}
                        }]
                    }
                }
            }
        }

        message = {'V4': [[instr1, instr2, instr3, instr4, instr5]]}

        return {
            'dest': {'V4': {
                'parents': '1',
                'interior': {
                    'X1': [{
                        'Parachain': ACA_PD_CHAIN_ID
                    }]
                },
            }},
            'message': message,
        }

    @pytest.mark.xcm
    def test_xcm_send_from_substrate_transfer(self):
        self.si_peaq = SubstrateInterface(url=WS_URL)
        self.si_aca = SubstrateInterface(url=ACA_WS_URL)

        self.aca_fund(self.si_aca, KP_GLOBAL_SUDO, self.sibling_parachain_addr, 10000 * 10 ** 18)

        # compose the message
        kp_dst = Keypair.create_from_mnemonic(Keypair.generate_mnemonic())
        self.aca_fund(self.si_aca, KP_GLOBAL_SUDO, kp_dst.ss58_address, 10 * 10 ** 18)
        ori_balance = get_account_balance(self.si_aca, kp_dst.ss58_address)

        # Use the pallet send to send it
        batch = ExtrinsicBatch(self.si_peaq, KP_GLOBAL_SUDO)
        batch.compose_call(
            'PolkadotXcm',
            'send',
            self._compose_xcm_send_message_dict(kp_dst)
        )
        receipt = batch.execute()
        self.assertTrue(receipt.is_success, f'Failed to send xcm: {receipt.error_message}')
        after_balance = get_account_balance(self.si_aca, kp_dst.ss58_address)
        self.assertGreater(after_balance, ori_balance, f'Error: {after_balance} {ori_balance}')

    @pytest.mark.xcm
    def test_xcm_send_from_substrate_asset_create(self):
        self.si_peaq = SubstrateInterface(url=WS_URL)
        self.si_aca = SubstrateInterface(url=ACA_WS_URL)

        self.aca_fund(self.si_aca, KP_GLOBAL_SUDO, self.sibling_parachain_addr, 10000 * 10 ** 18)

        # compose the message
        kp_dst = Keypair.create_from_mnemonic(Keypair.generate_mnemonic())
        self.aca_fund(self.si_aca, KP_GLOBAL_SUDO, kp_dst.ss58_address, 1000 * 10 ** 18)
        ori_balance = get_account_balance(self.si_aca, kp_dst.ss58_address)

        asset_id = get_valid_asset_id(self.si_aca)
        asset = self.si_aca.query("Assets", "Asset", [asset_id]).value
        self.assertEqual(asset, None, f'Error: {asset}')

        asset_call = self._compose_valid_asset_create(self.si_aca, KP_GLOBAL_SUDO, asset_id)

        # Use the pallet send to send it
        batch = ExtrinsicBatch(self.si_peaq, KP_GLOBAL_SUDO)
        batch.compose_call(
            'PolkadotXcm',
            'send',
            self._compose_xcm_send_message_call(
                kp_dst,
                asset_call)
        )
        receipt = batch.execute()
        self.assertTrue(receipt.is_success, f'Failed to send xcm: {receipt.error_message}')

        asset = self.si_aca.query("Assets", "Asset", [asset_id]).value
        self.assertNotEqual(asset, None, f'Error: {asset}')
        after_balance = get_account_balance(self.si_aca, kp_dst.ss58_address)
        self.assertGreater(after_balance, ori_balance, f'Error: {after_balance} {ori_balance}')

    @pytest.mark.xcm
    def test_xcm_send_from_substrate_did_create_fail(self):
        self.si_peaq = SubstrateInterface(url=WS_URL)
        self.si_aca = SubstrateInterface(url=ACA_WS_URL)

        self.aca_fund(self.si_aca, KP_GLOBAL_SUDO, self.sibling_parachain_addr, 10000 * 10 ** 18)

        # compose the message
        kp_dst = Keypair.create_from_mnemonic(Keypair.generate_mnemonic())
        self.aca_fund(self.si_aca, KP_GLOBAL_SUDO, kp_dst.ss58_address, 1000 * 10 ** 18)
        ori_balance = get_account_balance(self.si_aca, kp_dst.ss58_address)

        did_name = generate_random_hex(5)
        did = did_rpc_read(self.si_aca, self.sibling_parachain_addr, did_name)
        self.assertEqual(did, None, f'Error: {did}')

        did_call = self._compose_random_did_create(self.si_aca, kp_dst, did_name)
        # Use the pallet send to send it
        batch = ExtrinsicBatch(self.si_peaq, KP_GLOBAL_SUDO)
        batch.compose_call(
            'PolkadotXcm',
            'send',
            self._compose_xcm_send_message_call(
                kp_dst,
                did_call)
        )
        receipt = batch.execute()
        self.assertTrue(receipt.is_success, f'Failed to send xcm: {receipt.error_message}')

        # Currently, the peaq did didn't add into the safecallfilter
        # The did read will fail
        did = did_rpc_read(self.si_aca, kp_dst.ss58_address, did_name)
        self.assertEqual(did, None, f'Error: {did}')

        # The kp_dst.ss58_address cannot receive the refund because the did create fails
        # The balance should be the same and remaining tokens goes into the asset trap
        after_balance = get_account_balance(self.si_aca, kp_dst.ss58_address)
        self.assertEqual(after_balance, ori_balance, f'Error: {after_balance} != {ori_balance}')
