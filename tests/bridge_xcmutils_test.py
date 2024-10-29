import unittest
from tests.utils_func import restart_parachain_and_runtime_upgrade
from tools.constants import WS_URL, ETH_URL, ACA_WS_URL, RELAYCHAIN_WS_URL
from tools.constants import ACA_PD_CHAIN_ID
from tools.constants import PARACHAIN_WS_URL
from tools.runtime_upgrade import wait_until_block_height
from tools.peaq_eth_utils import get_contract
from tools.peaq_eth_utils import get_eth_info
from tools.peaq_eth_utils import get_eth_chain_id
from tools.asset import setup_asset_if_not_exist, setup_xc_register_if_not_exist
from substrateinterface import SubstrateInterface, Keypair
from peaq.utils import ExtrinsicBatch
from web3 import Web3
from tools.constants import KP_GLOBAL_SUDO
from tools.peaq_eth_utils import sign_and_submit_evm_transaction
from peaq.utils import get_account_balance
from tests import utils_func as TestUtils
from tools.asset import PEAQ_ASSET_LOCATION, PEAQ_METADATA, PEAQ_ASSET_ID
from tools.asset import wait_for_account_asset_change_wrap
from tools.asset import get_tokens_account_from_pallet_tokens
import pytest


GAS_LIMIT = 10633039
ABI_FILE = 'ETH/xcmutils/abi'
XCMUTILS_ADDRESS = '0x0000000000000000000000000000000000000804'


@pytest.mark.relaunch
@pytest.mark.eth
@pytest.mark.xcm
class TestBridgeXCMUtils(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        restart_parachain_and_runtime_upgrade()
        wait_until_block_height(SubstrateInterface(url=RELAYCHAIN_WS_URL), 1)
        wait_until_block_height(SubstrateInterface(url=PARACHAIN_WS_URL), 1)

    def setUp(self):
        self.si_peaq = SubstrateInterface(url=WS_URL)
        wait_until_block_height(SubstrateInterface(url=PARACHAIN_WS_URL), 1)
        self.w3 = Web3(Web3.HTTPProvider(ETH_URL))
        self.kp_eth = get_eth_info()
        self.eth_chain_id = get_eth_chain_id(self.si_peaq)

    def _fund_eth_account(self):
        # transfer
        batch = ExtrinsicBatch(self.si_peaq, KP_GLOBAL_SUDO)
        batch.compose_call(
            'Balances',
            'transfer_keep_alive',
            {
                'dest': self.kp_eth['substrate'],
                'value': 1000 * 10 ** 18,
            }
        )
        batch.execute()

    def _compose_xcm_execute_message(self, kp):
        account = kp.public_key
        instr1 = {
            'WithdrawAsset': [
                [{
                  'id': {
                      'parents': '0',
                      'interior': 'Here',
                  },
                  'fun': {'Fungible': 10 ** 18},
                }],
            ]
        }
        instr2 = {
            'DepositAsset': {
                'assets': {'Wild': {'AllCounted': 1}},
                'beneficiary': {
                    'parents': '0',
                    'interior': {
                        'X1': [{
                            'AccountId32': {
                                'network': None,
                                'id': account,
                            }
                        }]
                    }
                }
            }
        }
        message = {'V4': [[instr1, instr2]]}
        maxWeight = {'ref_time': 2 * 10 ** 21, 'proof_size': 10 ** 12}

        encoded_tx = self.si_peaq.compose_call(
            call_module='PolkadotXcm',
            call_function='execute',
            call_params={
                'message': message,
                'max_weight': maxWeight,
            }
        )
        return encoded_tx["call_args"]["message"]

    def _compose_xcm_send_message(self, kp):
        account = kp.public_key
        instr1 = {
            'WithdrawAsset': [
                [{
                  'id': {
                        'parents': '0',
                        'interior': 'Here',
                  },
                  'fun': {'Fungible': 10 ** 18},
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
                    'fun': {'Fungible': 10 ** 18},
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

        encoded_tx = self.si_peaq.compose_call(
            call_module='PolkadotXcm',
            call_function='send',
            call_params={
                'dest': {'V4': {
                    'parents': '1',
                    'interior': {
                        'X1': [{
                            'Parachain': '3000'
                        }]
                    },
                }},
                'message': message,
            }
        )
        return encoded_tx["call_args"]["message"]

    def wait_for_aca_account_token_change(self, addr, asset_id, prev_token=0):
        return wait_for_account_asset_change_wrap(
            self.si_aca, addr, asset_id, prev_token, get_tokens_account_from_pallet_tokens)

    @pytest.mark.skipif(TestUtils.is_not_dev_chain() is True, reason='Note enable xcm_execute on non-dev chain')
    def test_xcm_execute(self):
        self._fund_eth_account()

        kp_dst = Keypair.create_from_mnemonic(Keypair.generate_mnemonic())
        encoded_calldata = self._compose_xcm_execute_message(kp_dst).encode().data

        kp_sign = self.kp_eth['kp']
        contract = get_contract(self.w3, XCMUTILS_ADDRESS, ABI_FILE)
        nonce = self.w3.eth.get_transaction_count(kp_sign.ss58_address)
        tx = contract.functions.xcmExecute(
            encoded_calldata, 20000000000,
            ).build_transaction({
                'from': kp_sign.ss58_address,
                'gas': GAS_LIMIT,
                'maxFeePerGas': self.w3.to_wei(21000, 'gwei'),
                'maxPriorityFeePerGas': self.w3.to_wei(2, 'gwei'),
                'nonce': nonce,
                'chainId': self.eth_chain_id
            })

        evm_receipt = sign_and_submit_evm_transaction(tx, self.w3, kp_sign)
        self.assertEqual(evm_receipt['status'], 1, f'Error: {evm_receipt}: {evm_receipt["status"]}')

        balance = get_account_balance(self.si_peaq, kp_dst.ss58_address)
        self.assertNotEqual(balance, 0, f'Error: {balance}')

    def test_xcm_send(self):
        self.si_peaq = SubstrateInterface(url=WS_URL)
        self.si_aca = SubstrateInterface(url=ACA_WS_URL)

        receipt = setup_asset_if_not_exist(
            self.si_aca, KP_GLOBAL_SUDO, PEAQ_ASSET_ID['para'], PEAQ_METADATA)
        self.assertTrue(receipt.is_success, f'Failed to register asset: {receipt.error_message}')
        receipt = setup_xc_register_if_not_exist(
            self.si_aca, KP_GLOBAL_SUDO, PEAQ_ASSET_ID['para'], PEAQ_ASSET_LOCATION['para'], 100)
        self.assertTrue(receipt.is_success, f'Failed to register xc asset: {receipt.error_message}')

        self._fund_eth_account()
        # compose the message
        kp_dst = Keypair.create_from_mnemonic(Keypair.generate_mnemonic())
        encoded_calldata = self._compose_xcm_send_message(kp_dst).encode().data

        # Use the pallet send to send it
        kp_sign = self.kp_eth['kp']
        contract = get_contract(self.w3, XCMUTILS_ADDRESS, ABI_FILE)
        nonce = self.w3.eth.get_transaction_count(kp_sign.ss58_address)
        tx = contract.functions.xcmSend(
            [1, ['0x00'+f'00000{hex(ACA_PD_CHAIN_ID)[2:]}']], encoded_calldata,
            ).build_transaction({
                'from': kp_sign.ss58_address,
                'gas': GAS_LIMIT,
                'maxFeePerGas': self.w3.to_wei(21000, 'gwei'),
                'maxPriorityFeePerGas': self.w3.to_wei(2, 'gwei'),
                'nonce': nonce,
                'chainId': self.eth_chain_id
            })

        evm_receipt = sign_and_submit_evm_transaction(tx, self.w3, kp_sign)
        self.assertEqual(evm_receipt['status'], 1, f'Error: {evm_receipt}: {evm_receipt["status"]}')
        # Cannot test on remote side because Acala we used cannot resolve the origin (1, parachain, account)

    def test_get_units_per_second(self):
        contract = get_contract(self.w3, XCMUTILS_ADDRESS, ABI_FILE)
        data = contract.functions.getUnitsPerSecond([0, []]).call()
        self.assertNotEqual(data, 0)

    def test_weight_message(self):
        contract = get_contract(self.w3, XCMUTILS_ADDRESS, ABI_FILE)
        kp_dst = Keypair.create_from_mnemonic(Keypair.generate_mnemonic())
        encoded_calldata = self._compose_xcm_execute_message(kp_dst).encode().data

        data = contract.functions.weightMessage(encoded_calldata).call()
        self.assertNotEqual(data, 0)
