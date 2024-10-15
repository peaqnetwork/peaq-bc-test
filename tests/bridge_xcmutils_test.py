import unittest
from tests.utils_func import restart_parachain_and_runtime_upgrade
from tools.constants import WS_URL, ETH_URL, ACA_WS_URL
from tools.constants import ACA_PD_CHAIN_ID
from tools.runtime_upgrade import wait_until_block_height
from tools.peaq_eth_utils import get_contract
from tools.peaq_eth_utils import get_eth_info
from tools.peaq_eth_utils import get_eth_chain_id
from substrateinterface import SubstrateInterface, Keypair
from peaq.utils import ExtrinsicBatch
from web3 import Web3
from tools.constants import KP_GLOBAL_SUDO
from tools.peaq_eth_utils import sign_and_submit_evm_transaction
from peaq.utils import get_account_balance
from tests import utils_func as TestUtils
from tools.asset import wait_for_account_asset_change_wrap
from tools.asset import get_tokens_account_from_pallet_tokens
from tools.utils import get_modified_chain_spec
from peaq.utils import get_chain
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
        wait_until_block_height(SubstrateInterface(url=WS_URL), 1)
        wait_until_block_height(SubstrateInterface(url=ACA_WS_URL), 1)

    def setUp(self):
        self.si_peaq = SubstrateInterface(url=WS_URL)
        wait_until_block_height(SubstrateInterface(url=WS_URL), 1)
        self.w3 = Web3(Web3.HTTPProvider(ETH_URL))
        self.kp_eth = get_eth_info("sphere gasp actual clock wreck rural essay name claw deputy party output")
        self.eth_chain_id = get_eth_chain_id(self.si_peaq)
        self.setup_sibling_parachain_account()

    # Just calculate the sibling parachain account by moonbeam's xcm-utils tool
    # Here is the command but remember to change the parachain id
    # yarn calculate-multilocation-derivative-account --a 0x55eebfdbb6af8aecbc9664bb229c48e2fceb381ce9d93a3ed698d4177da3e8e6 --p 2000 --parents
    def setup_sibling_parachain_account(self):
        # substrate addr is 5E1NrJDAqp5R3JDBBn2JGaHpUMo5kbCNXtV2asLzaw2MZfwr
        chain_spec = get_chain(self.si_peaq)
        chain = get_modified_chain_spec(chain_spec)
        if chain == 'peaq-dev':
            self.sibling_parachain_addr = '5HYXs9665LtfnxvBz9FrXCrUGwNTWBrkotqtdFw1VAsYAiiJ'
        elif chain == 'krest-network':
            self.sibling_parachain_addr = '5Ex5h1ExXEX3DkLc3gPr7yhCgvUmovLV16A7NATbeJH6UScH'
        elif chain == 'peaq-network':
            self.sibling_parachain_addr = '5HSpy8Hc4ciygtDTHTdj6FKpPvwXDjY8riWMaqDkCgbiHfAx'

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
                        'Parachain': str(ACA_PD_CHAIN_ID)
                    }]
                },
            }},
            'message': message,
        }

    def _compose_xcm_send_message(self, kp):
        encoded_tx = self.si_peaq.compose_call(
            call_module='PolkadotXcm',
            call_function='send',
            call_params=self._compose_xcm_send_message_dict(kp)
        )
        return encoded_tx["call_args"]["message"]

    def wait_for_aca_account_token_change(self, addr, asset_id, prev_token=0):
        return wait_for_account_asset_change_wrap(
            self.si_aca, addr, asset_id, prev_token, get_tokens_account_from_pallet_tokens)

    @pytest.mark.xcm
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
                'nonce': nonce,
                'chainId': self.eth_chain_id
            })

        evm_receipt = sign_and_submit_evm_transaction(tx, self.w3, kp_sign)
        self.assertEqual(evm_receipt['status'], 1, f'Error: {evm_receipt}: {evm_receipt["status"]}')

        balance = get_account_balance(self.si_peaq, kp_dst.ss58_address)
        self.assertNotEqual(balance, 0, f'Error: {balance}')

    @pytest.mark.xcm
    def test_xcm_send(self):
        self.si_peaq = SubstrateInterface(url=WS_URL)
        self.si_aca = SubstrateInterface(url=ACA_WS_URL)

        self._fund_eth_account()
        self.aca_fund(self.si_aca, KP_GLOBAL_SUDO, self.sibling_parachain_addr, 1000 * 10 ** 18)

        # compose the message
        kp_dst = Keypair.create_from_mnemonic(Keypair.generate_mnemonic())
        self.aca_fund(self.si_aca, KP_GLOBAL_SUDO, kp_dst.ss58_address, 1000 * 10 ** 18)
        orig_balance = get_account_balance(self.si_aca, kp_dst.ss58_address)

        encoded_calldata = self._compose_xcm_send_message(kp_dst).encode().data

        # Use the pallet send to send it
        kp_sign = self.kp_eth['kp']
        contract = get_contract(self.w3, XCMUTILS_ADDRESS, ABI_FILE)
        nonce = self.w3.eth.get_transaction_count(kp_sign.ss58_address)
        tx = contract.functions.xcmSend(
            [1, ['0x00'+f'00000{hex(ACA_PD_CHAIN_ID)[2:]}']], encoded_calldata,
            ).build_transaction({
                'from': kp_sign.ss58_address,
                'nonce': nonce,
                'chainId': self.eth_chain_id
            })

        evm_receipt = sign_and_submit_evm_transaction(tx, self.w3, kp_sign)
        self.assertEqual(evm_receipt['status'], 1, f'Error: {evm_receipt}: {evm_receipt["status"]}')

        new_balance = get_account_balance(self.si_aca, kp_dst.ss58_address)
        self.assertGreater(new_balance, orig_balance, f'Error: {new_balance}, dst: {kp_dst.ss58_address}')

    @pytest.mark.xcm
    def test_get_units_per_second(self):
        contract = get_contract(self.w3, XCMUTILS_ADDRESS, ABI_FILE)
        data = contract.functions.getUnitsPerSecond([0, []]).call()
        self.assertNotEqual(data, 0)

    @pytest.mark.xcm
    def test_weight_message(self):
        contract = get_contract(self.w3, XCMUTILS_ADDRESS, ABI_FILE)
        kp_dst = Keypair.create_from_mnemonic(Keypair.generate_mnemonic())
        encoded_calldata = self._compose_xcm_execute_message(kp_dst).encode().data

        data = contract.functions.weightMessage(encoded_calldata).call()
        self.assertNotEqual(data, 0)
