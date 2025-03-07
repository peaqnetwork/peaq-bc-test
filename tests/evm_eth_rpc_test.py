import pytest

from substrateinterface import SubstrateInterface, Keypair, KeypairType
from tools.runtime_upgrade import wait_until_block_height
from peaq.eth import calculate_evm_account, calculate_evm_addr
from peaq.extrinsic import transfer
from peaq.utils import ExtrinsicBatch
from tools.constants import KP_GLOBAL_SUDO
from tools.constants import WS_URL, ETH_URL
from tests.evm_utils import sign_and_submit_evm_transaction
from tools.peaq_eth_utils import get_eth_chain_id
from tools.peaq_eth_utils import deploy_contract
from tools.peaq_eth_utils import call_eth_transfer_a_lot
from tools.peaq_eth_utils import get_eth_balance, get_contract
from tools.peaq_eth_utils import TX_SUCCESS_STATUS
from tools.utils import get_withdraw_events, get_deposit_events
from peaq.utils import get_account_balance
from tests import utils_func as TestUtils
from tools.peaq_eth_utils import get_eth_info
from tools.utils import batch_fund
from web3 import Web3
import unittest

import pprint
pp = pprint.PrettyPrinter(indent=4)

ERC_TOKEN_TRANSFER = 34
HEX_STR = '1111'
GAS_LIMIT = 4294967
TOKEN_NUM = 10 * 10 ** 18
ABI_FILE = 'ETH/identity/abi'
TOKEN_NUM_BASE = pow(10, 18)


MNEMONIC = [
    'trouble kangaroo brave step craft valve have dash unique vehicle melt broccoli',
    # 0x434DB4884Fa631c89E57Ea04411D6FF73eF0E297
    'lunar hobby hungry vacant imitate silly amused soccer face census keep kiwi',
    # 0xC5BDf22635Df81f897C1BB2B24b758dEB21f522d,
]


def send_eth_token(w3, kp_src, kp_dst, token_num, eth_chain_id):
    nonce = w3.eth.get_transaction_count(kp_src.ss58_address)
    tx = {
        'from': kp_src.ss58_address,
        'to': kp_dst.ss58_address,
        'value': token_num,
        'nonce': nonce,
        'chainId': eth_chain_id,
        'gas': GAS_LIMIT,
        'gasPrice': w3.eth.gas_price,
    }
    return sign_and_submit_evm_transaction(tx, w3, kp_src)


def get_contract_data(w3, address, filename):
    contract = get_contract(w3, address, filename)
    data = contract.functions.memoryStored().call()
    return data.hex()


def call_copy(w3, address, kp_src, eth_chain_id, file_name, data):
    contract = get_contract(w3, address, file_name)

    nonce = w3.eth.get_transaction_count(kp_src.ss58_address)
    tx = contract.functions.callDatacopy(bytes.fromhex(data)).build_transaction({
        'from': kp_src.ss58_address,
        'nonce': nonce,
        'chainId': eth_chain_id})

    receipt = sign_and_submit_evm_transaction(tx, w3, kp_src)
    return receipt['status'] == TX_SUCCESS_STATUS


@pytest.mark.eth
class TestEVMEthRPC(unittest.TestCase):
    def setUp(self):
        wait_until_block_height(SubstrateInterface(url=WS_URL), 3)
        self._conn = SubstrateInterface(url=WS_URL)
        self._eth_chain_id = get_eth_chain_id(self._conn)
        self._kp_src = Keypair.create_from_uri('//Alice')
        self._eth_src = calculate_evm_addr(self._kp_src.ss58_address)
        self._kp_eth_src = Keypair.create_from_mnemonic(MNEMONIC[0], crypto_type=KeypairType.ECDSA)
        self._kp_eth_dst = Keypair.create_from_mnemonic(MNEMONIC[1], crypto_type=KeypairType.ECDSA)
        self._w3 = Web3(Web3.HTTPProvider(ETH_URL))
        self._eth_deposited_src = calculate_evm_account(self._eth_src)

    def test_evm_api_balance_same(self):
        self._kp_moon = get_eth_info()
        self._kp_mars = get_eth_info()

        batch = ExtrinsicBatch(self._conn, KP_GLOBAL_SUDO)
        batch_fund(batch, self._kp_moon['substrate'], int(1.05 * 10 ** 18))
        receipt = batch.execute()
        self.assertTrue(receipt.is_success)

        sub_balance = get_account_balance(self._conn, self._kp_moon['substrate'])
        eth_balance = self._w3.eth.get_balance(self._kp_moon['kp'].ss58_address)
        self.assertEqual(sub_balance, eth_balance, f"sub: {sub_balance} != eth: {eth_balance}")

    @pytest.mark.skipif(TestUtils.is_not_peaq_chain() is True, reason='Only peaq chain evm tx change')
    def test_evm_fee(self):
        self._kp_moon = get_eth_info()
        self._kp_mars = get_eth_info()
        batch = ExtrinsicBatch(self._conn, KP_GLOBAL_SUDO)
        batch_fund(batch, self._kp_moon['substrate'], 1000 * 10 ** 18)
        receipt = batch.execute()
        self.assertTrue(receipt.is_success)

        prev_balance = self._w3.eth.get_balance(self._kp_moon['kp'].ss58_address)
        nonce = self._w3.eth.get_transaction_count(self._kp_moon['kp'].ss58_address)
        # gas/maxFeePerGas/maxPriorityFeePerGas is decided by metamask's value
        tx = {
            'from': self._kp_moon['kp'].ss58_address,
            'to': self._kp_mars['kp'].ss58_address,
            'value': 1 * 10 ** 18,
            'gas': 21000,
            'maxFeePerGas': 1000 * 10 ** 9,
            'maxPriorityFeePerGas': 1000 * 10 ** 9,
            'nonce': nonce,
            'chainId': self._eth_chain_id
        }
        response = sign_and_submit_evm_transaction(tx, self._w3, self._kp_moon['kp'])
        self.assertTrue(response['status'] == TX_SUCCESS_STATUS, f'failed: {response}')

        new_balance = self._w3.eth.get_balance(self._kp_moon['kp'].ss58_address)
        self.assertGreater(prev_balance - new_balance - 1 * 10 ** 18, 0.002 * 10 ** 18)

    def test_evm_remaining_without_ed(self):
        self._kp_moon = get_eth_info()
        self._kp_mars = get_eth_info()

        batch = ExtrinsicBatch(self._conn, KP_GLOBAL_SUDO)
        batch_fund(batch, self._kp_moon['substrate'], int(1.05 * 10 ** 18))
        receipt = batch.execute()
        self.assertTrue(receipt.is_success)

        nonce = self._w3.eth.get_transaction_count(self._kp_moon['kp'].ss58_address)
        # gas/maxFeePerGas/maxPriorityFeePerGas is decided by metamask's value
        tx = {
            'from': self._kp_moon['kp'].ss58_address,
            'to': self._kp_mars['kp'].ss58_address,
            'value': 1 * 10 ** 18,
            'gas': 21000,
            'maxFeePerGas': 1000 * 10 ** 9,
            'maxPriorityFeePerGas': 1000 * 10 ** 9,
            'nonce': nonce,
            'chainId': self._eth_chain_id
        }
        response = sign_and_submit_evm_transaction(tx, self._w3, self._kp_moon['kp'])
        self.assertTrue(response['status'] == TX_SUCCESS_STATUS, f'failed: {response}')

        new_balance = self._w3.eth.get_balance(self._kp_moon['kp'].ss58_address)
        self.assertGreater(10 ** 18, new_balance)

    def test_evm_rpc_transfer(self):
        conn = self._conn
        eth_chain_id = self._eth_chain_id
        kp_src = self._kp_src
        eth_src = self._eth_src
        kp_eth_src = self._kp_eth_src
        kp_eth_dst = self._kp_eth_dst
        eth_deposited_src = self._eth_deposited_src
        w3 = self._w3

        # Setup
        transfer(conn, kp_src, eth_deposited_src, TOKEN_NUM)

        receipt = call_eth_transfer_a_lot(conn, kp_src, eth_src, kp_eth_src.ss58_address.lower())
        self.assertTrue(receipt.is_success, f'call_eth_transfer_a_lot failed: {receipt}')
        eth_after_balance = get_eth_balance(conn, kp_eth_src.ss58_address)
        print(f'dst ETH balance: {eth_after_balance}')

        block = w3.eth.get_block('latest')
        self.assertNotEqual(block['number'], 0)

        token_num = 10 * TOKEN_NUM_BASE
        dst_eth_before_balance = w3.eth.get_balance(kp_eth_dst.ss58_address)

        print(f'before, dst eth: {dst_eth_before_balance}')
        src_eth_balance = w3.eth.get_balance(kp_eth_src.ss58_address)
        print(f'src eth: {src_eth_balance}')

        # Execute -> Call eth transfer
        tx_receipt = send_eth_token(w3, kp_eth_src, kp_eth_dst, token_num, eth_chain_id)
        self.assertEqual(tx_receipt['status'], TX_SUCCESS_STATUS, f'send eth token failed: {tx_receipt}')

        # Check
        dst_eth_after_balance = w3.eth.get_balance(kp_eth_dst.ss58_address)
        print(f'after, dst eth: {dst_eth_after_balance}')
        # In empty account, the token_num == token_num - enssential num
        self.assertGreater(dst_eth_after_balance, dst_eth_before_balance,
                           f'{dst_eth_after_balance} <= {dst_eth_before_balance}')

    def test_evm_rpc_identity_contract(self):
        conn = self._conn
        eth_chain_id = self._eth_chain_id
        kp_src = self._kp_src
        eth_src = self._eth_src
        kp_eth_src = self._kp_eth_src
        eth_deposited_src = self._eth_deposited_src
        w3 = self._w3

        transfer(conn, kp_src, eth_deposited_src, TOKEN_NUM)

        receipt = call_eth_transfer_a_lot(conn, kp_src, eth_src, kp_eth_src.ss58_address.lower())
        self.assertTrue(receipt.is_success, f'call_eth_transfer_a_lot failed: {receipt}')

        with open('ETH/identity/bytecode') as f:
            bytecode = f.read().strip()

        # Execute -> Deploy contract
        address = deploy_contract(w3, kp_eth_src, eth_chain_id, ABI_FILE, bytecode)
        self.assertNotEqual(address, None, 'contract address is None')

        # Check
        data = get_contract_data(w3, address, ABI_FILE)
        self.assertEqual(data, '', f'contract data is not empty {data}.hex()')

        # Execute -> Call set
        self.assertTrue(call_copy(w3, address, kp_eth_src, eth_chain_id, ABI_FILE, HEX_STR))

        out = get_contract_data(w3, address, ABI_FILE)
        self.assertEqual(out, HEX_STR, 'call copy failed')

    def test_evm_tip(self):
        self._kp_moon = get_eth_info()
        self._kp_mars = get_eth_info()
        batch = ExtrinsicBatch(self._conn, KP_GLOBAL_SUDO)
        batch_fund(batch, self._kp_moon['substrate'], 1000 * 10 ** 18)
        receipt = batch.execute()
        self.assertTrue(receipt.is_success)

        nonce = self._w3.eth.get_transaction_count(self._kp_moon['kp'].ss58_address)
        # gas/maxFeePerGas/maxPriorityFeePerGas is decided by metamask's value
        tx = {
            'from': self._kp_moon['kp'].ss58_address,
            'to': self._kp_mars['kp'].ss58_address,
            'value': 1 * 10 ** 18,
            'gas': 21000,
            'maxFeePerGas': int(7.2 * 10 ** 13) + int(2 * 10 ** 9),
            'maxPriorityFeePerGas': int(7.2 * 10 ** 13),
            'nonce': nonce,
            'chainId': self._eth_chain_id
        }
        response = sign_and_submit_evm_transaction(tx, self._w3, self._kp_moon['kp'])

        self.assertTrue(response['status'] == TX_SUCCESS_STATUS, f'failed: {response}')

        now_block_number = response.blockNumber
        now_block_hash = self._conn.get_block_hash(now_block_number)

        # Get the EVM tx id
        block = self._conn.get_block(now_block_hash)
        evm_tx_id = -1
        for index, extrinsic in enumerate(block['extrinsics']):
            if str(extrinsic['call']['call_module']['name']) != 'Ethereum':
                continue
            if str(extrinsic['call']['call_function']['name']) != 'transact':
                continue
            evm_tx_id = index
            break

        self.assertNotEqual(evm_tx_id, -1, 'evm_tx_id should not be -1, not found')
        withdraws = get_withdraw_events(self._conn, now_block_hash, evm_tx_id)
        deposits = get_deposit_events(self._conn, now_block_hash, evm_tx_id)
        total_deposits = sum([deposit['value'] for deposit in deposits])
        total_withdraws = sum([withdraw['value'] for withdraw in withdraws])
        self.assertEqual(total_deposits, total_withdraws, 'total deposits and withdraws should be equal')
