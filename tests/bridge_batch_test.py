import unittest
import pytest

from tools.constants import WS_URL, ETH_URL
# from tools.runtime_upgrade import wait_until_block_height
from tools.peaq_eth_utils import get_contract
from tools.peaq_eth_utils import GAS_LIMIT, get_eth_info
from tools.peaq_eth_utils import get_eth_chain_id
from substrateinterface import SubstrateInterface
from peaq.utils import ExtrinsicBatch
from web3 import Web3
from tools.constants import KP_GLOBAL_SUDO
from tests.evm_utils import sign_and_submit_evm_transaction
from tools.peaq_eth_utils import generate_random_hex


KEY1 = generate_random_hex()
VALUE1 = '0x01'
KEY2 = generate_random_hex()
VALUE2 = '0x02'

ABI_FILE = 'ETH/batch/abi'
BATCH_ADDRESS = '0x0000000000000000000000000000000000000805'

DID_ABI_FILE = 'ETH/did/abi'
DID_ADDRESS = '0x0000000000000000000000000000000000000800'

STORAGE_ABI_FILE = 'ETH/storage/abi'
STORAGE_ADDRESS = '0x0000000000000000000000000000000000000801'


@pytest.mark.eth
class TestBridgeBatch(unittest.TestCase):
    def setUp(self):
        self.si_peaq = SubstrateInterface(url=WS_URL)
        self.w3 = Web3(Web3.HTTPProvider(ETH_URL))
        self.kp_eth = get_eth_info()

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

    def get_did_calldata(self, eth_kp, addr, contract, key, value):
        tx = contract.functions.add_attribute(eth_kp.ss58_address, key, value, 1000000).build_transaction({
            'from': eth_kp.ss58_address,
            'nonce': 0,
            'chainId': self.eth_chain_id})
        return tx['data']

    def test_batch_all(self):
        self.eth_chain_id = get_eth_chain_id(self.si_peaq)
        self._fund_eth_account()

        storage_contract = get_contract(self.w3, STORAGE_ADDRESS, STORAGE_ABI_FILE)

        kp_sign = self.kp_eth['kp']
        contract = get_contract(self.w3, BATCH_ADDRESS, ABI_FILE)
        nonce = self.w3.eth.get_transaction_count(kp_sign.ss58_address)
        tx = contract.functions.batchAll(
            [Web3.to_checksum_address(STORAGE_ADDRESS), Web3.to_checksum_address(STORAGE_ADDRESS)],
            [0, 0],
            [storage_contract.encodeABI(fn_name='addItem', args=[KEY1, VALUE1]),
             storage_contract.encodeABI(fn_name='addItem', args=[KEY2, VALUE2])],
            [0, 0],
            ).build_transaction({
                'from': kp_sign.ss58_address,
                'nonce': nonce,
                'chainId': self.eth_chain_id
            })

        evm_receipt = sign_and_submit_evm_transaction(tx, self.w3, kp_sign)
        self.assertEqual(evm_receipt['status'], 1, f'Error: {evm_receipt}: {evm_receipt["status"]}')

        # Check
        data = storage_contract.functions.getItem(kp_sign.ss58_address, KEY1).call()
        self.assertEqual(f'0x{data.hex()}', VALUE1)
        data = storage_contract.functions.getItem(kp_sign.ss58_address, KEY2).call()
        self.assertEqual(f'0x{data.hex()}', VALUE2)

    def test_batch_some(self):
        self.eth_chain_id = get_eth_chain_id(self.si_peaq)
        self._fund_eth_account()

        storage_contract = get_contract(self.w3, STORAGE_ADDRESS, STORAGE_ABI_FILE)

        kp_sign = self.kp_eth['kp']
        contract = get_contract(self.w3, BATCH_ADDRESS, ABI_FILE)
        nonce = self.w3.eth.get_transaction_count(kp_sign.ss58_address)
        # We have to setup the fee by ourselves to avoid the fee error
        tx = contract.functions.batchSome(
            [Web3.to_checksum_address(STORAGE_ADDRESS),
             Web3.to_checksum_address(STORAGE_ADDRESS),
             Web3.to_checksum_address(STORAGE_ADDRESS)],
            [0, 0, 0],
            [storage_contract.encodeABI(fn_name='addItem', args=[KEY1, VALUE1]),
             storage_contract.encodeABI(fn_name='updateItem', args=["0x1234", VALUE2]),
             storage_contract.encodeABI(fn_name='addItem', args=[KEY2, VALUE2])],
            [0, 0, 0],
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

        # Check
        data = storage_contract.functions.getItem(kp_sign.ss58_address, KEY1).call()
        self.assertEqual(f'0x{data.hex()}', VALUE1)
        data = storage_contract.functions.getItem(kp_sign.ss58_address, KEY2).call()
        self.assertEqual(f'0x{data.hex()}', VALUE2)

    def test_batch_some_until_fail(self):
        self.eth_chain_id = get_eth_chain_id(self.si_peaq)
        self._fund_eth_account()

        storage_contract = get_contract(self.w3, STORAGE_ADDRESS, STORAGE_ABI_FILE)

        kp_sign = self.kp_eth['kp']
        contract = get_contract(self.w3, BATCH_ADDRESS, ABI_FILE)
        nonce = self.w3.eth.get_transaction_count(kp_sign.ss58_address)
        # We have to setup the fee by ourselves to avoid the fee error
        tx = contract.functions.batchSomeUntilFailure(
            [Web3.to_checksum_address(STORAGE_ADDRESS),
             Web3.to_checksum_address(STORAGE_ADDRESS),
             Web3.to_checksum_address(STORAGE_ADDRESS)],
            [0, 0, 0],
            [storage_contract.encodeABI(fn_name='addItem', args=[KEY1, VALUE1]),
             storage_contract.encodeABI(fn_name='updateItem', args=["0x1234", VALUE2]),
             storage_contract.encodeABI(fn_name='addItem', args=[KEY2, VALUE2])],
            [0, 0, 0],
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

        # Check
        data = storage_contract.functions.getItem(kp_sign.ss58_address, KEY1).call()
        self.assertEqual(f'0x{data.hex()}', VALUE1)
        try:
            data = storage_contract.functions.getItem(kp_sign.ss58_address, KEY2).call()
        except ValueError:
            pass
        except Exception as e:
            raise e
