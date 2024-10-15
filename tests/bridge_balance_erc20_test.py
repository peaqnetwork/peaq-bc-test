import pytest
import unittest

from substrateinterface import SubstrateInterface, Keypair
from peaq.utils import ExtrinsicBatch
from peaq.utils import get_account_balance
from tools.utils import get_modified_chain_spec
from tools.peaq_eth_utils import sign_and_submit_evm_transaction
from tools.constants import WS_URL, ETH_URL
from tools.constants import KP_GLOBAL_SUDO
from tools.peaq_eth_utils import get_contract
from tools.peaq_eth_utils import get_eth_chain_id
from tools.peaq_eth_utils import get_eth_info
from peaq.utils import get_chain
from tools.utils import batch_fund
from web3 import Web3


BALANCE_ERC20_ABI_FILE = 'ETH/balance-erc20/abi'
BALANCE_ERC20_ADDR = '0x0000000000000000000000000000000000000809'


TEST_METADATA = {
    'peaq-network': {
        'name': 'peaq token',
        'symbol': 'PEAQ',
        'decimals': 18,
    },
    'peaq-dev': {
        'name': 'Agung token',
        'symbol': 'AGNG',
        'decimals': 18,
    },
    'krest-network': {
        'name': 'Krest token',
        'symbol': 'KREST',
        'decimals': 18,
    }
}


def batch_transfer(batch, addr_dst, token_num):
    batch.compose_call(
        'Balances',
        'transfer_keep_alive',
        {
            'dest': addr_dst,
            'value': token_num
        }
    )


@pytest.mark.eth
class balance_erc20_asset_test(unittest.TestCase):
    def setUp(self):
        self._substrate = SubstrateInterface(url=WS_URL)
        self._w3 = Web3(Web3.HTTPProvider(ETH_URL))
        self._kp_creator = Keypair.create_from_uri('//Alice')
        self._kp_admin = Keypair.create_from_uri('//Bob')
        self._eth_kp_src = get_eth_info()
        self._eth_kp_dst = get_eth_info()
        self._eth_chain_id = get_eth_chain_id(self._substrate)
        self._chain_spec = get_chain(self._substrate)
        self._chain_spec = get_modified_chain_spec(self._chain_spec)

    def evm_erc20_transfer(self, contract, eth_kp_src, eth_dst, token_num):
        w3 = self._w3
        nonce = w3.eth.get_transaction_count(eth_kp_src.ss58_address)
        tx = contract.functions.transfer(eth_dst, token_num).build_transaction({
            'from': eth_kp_src.ss58_address,
            'nonce': nonce,
            'chainId': self._eth_chain_id})

        return sign_and_submit_evm_transaction(tx, w3, eth_kp_src)

    def evm_erc20_approval(self, contract, eth_kp_src, eth_approval, token_num):
        w3 = self._w3
        nonce = w3.eth.get_transaction_count(eth_kp_src.ss58_address)
        tx = contract.functions.approve(eth_approval, token_num).build_transaction({
            'from': eth_kp_src.ss58_address,
            'nonce': nonce,
            'chainId': self._eth_chain_id})

        return sign_and_submit_evm_transaction(tx, w3, eth_kp_src)

    def evm_balance_erc20_transfer_from(self, contract, eth_kp, eth_from, eth_to, token_num):
        w3 = self._w3
        nonce = w3.eth.get_transaction_count(eth_kp.ss58_address)
        tx = contract.functions.transferFrom(eth_from, eth_to, token_num).build_transaction({
            'from': eth_kp.ss58_address,
            'nonce': nonce,
            'chainId': self._eth_chain_id})

        return sign_and_submit_evm_transaction(tx, w3, eth_kp)

    def test_balance_erc20_metadata(self):
        contract = get_contract(self._w3, BALANCE_ERC20_ADDR, BALANCE_ERC20_ABI_FILE)
        data = contract.functions.name().call()
        self.assertEqual(
            data, TEST_METADATA[self._chain_spec]['name'],
            f'Error: {data} != {TEST_METADATA[self._chain_spec]["name"]}')
        data = contract.functions.symbol().call()
        self.assertEqual(
            data, TEST_METADATA[self._chain_spec]['symbol'],
            f'Error: {data} != {TEST_METADATA[self._chain_spec]["symbol"]}')
        data = contract.functions.decimals().call()
        self.assertEqual(
            data, TEST_METADATA[self._chain_spec]['decimals'],
            f'Error: {data} != {TEST_METADATA[self._chain_spec]["decimals"]}')

    def test_balance_erc20_total_issuance(self):
        contract = get_contract(self._w3, BALANCE_ERC20_ADDR, BALANCE_ERC20_ABI_FILE)
        data = contract.functions.totalSupply().call()
        total_balance = self._substrate.query(
            module='Balances',
            storage_function='TotalIssuance',
            params=[],
        )
        self.assertEqual(
            data, total_balance.value,
            f'Error: {data} != {total_balance.value}')

    def test_balance_erc20_balance_of(self):
        contract = get_contract(self._w3, BALANCE_ERC20_ADDR, BALANCE_ERC20_ABI_FILE)
        evm_balance = contract.functions.balanceOf(self._eth_kp_src['eth']).call()
        sub_balance = get_account_balance(self._substrate, self._eth_kp_src['substrate'])
        self.assertEqual(
            evm_balance, sub_balance,
            f'Error: {evm_balance} != {sub_balance}')

    def test_balance_erc20_transfer(self):
        batch = ExtrinsicBatch(self._substrate, KP_GLOBAL_SUDO)
        batch_fund(batch, self._eth_kp_src['substrate'], 100 * 10 ** 18)
        batch_fund(batch, self._eth_kp_dst['substrate'], 100 * 10 ** 18)
        receipt = batch.execute()
        self.assertTrue(receipt.is_success)

        contract = get_contract(self._w3, BALANCE_ERC20_ADDR, BALANCE_ERC20_ABI_FILE)

        # Check minted to eth address
        pre_dst_balance = contract.functions.balanceOf(self._eth_kp_dst['eth']).call()
        erc_transfer_num = 2 * 10 ** 18

        # Execute transfer
        evm_receipt = self.evm_erc20_transfer(
            contract,
            self._eth_kp_src['kp'],
            self._eth_kp_dst['eth'],
            erc_transfer_num)
        self.assertEqual(evm_receipt['status'], 1, f'Error: {evm_receipt}: {evm_receipt["status"]}')

        # Check balance after transfer
        aft_dst_balance = contract.functions.balanceOf(self._eth_kp_dst['eth']).call()
        self.assertEqual(
            aft_dst_balance, pre_dst_balance + erc_transfer_num,
            f'Error: {aft_dst_balance} != {pre_dst_balance + erc_transfer_num}')

    def test_balance_erc20_approval(self):
        batch = ExtrinsicBatch(self._substrate, KP_GLOBAL_SUDO)
        batch_fund(batch, self._eth_kp_src['substrate'], 100 * 10 ** 18)
        batch_fund(batch, self._eth_kp_dst['substrate'], 100 * 10 ** 18)
        receipt = batch.execute()
        self.assertTrue(receipt.is_success)

        erc_transfer_num = 2 * 10 ** 18

        contract = get_contract(self._w3, BALANCE_ERC20_ADDR, BALANCE_ERC20_ABI_FILE)
        evm_receipt = self.evm_erc20_approval(
            contract,
            self._eth_kp_src['kp'],
            self._eth_kp_dst['eth'],
            erc_transfer_num)
        self.assertEqual(evm_receipt['status'], 1, f'Error: {evm_receipt}: {evm_receipt["status"]}')

        data = contract.functions.allowance(self._eth_kp_src['eth'], self._eth_kp_dst['eth']).call()
        self.assertEqual(
            data, erc_transfer_num,
            f'Error: {data} != {erc_transfer_num}')

        empty_addr = get_eth_info()

        evm_receipt = self.evm_balance_erc20_transfer_from(
            contract,
            self._eth_kp_dst['kp'],
            self._eth_kp_src['eth'],
            empty_addr['eth'],
            erc_transfer_num)
        self.assertEqual(evm_receipt['status'], 1, f'Error: {evm_receipt}: {evm_receipt["status"]}')

        # Spend all
        data = contract.functions.allowance(self._eth_kp_src['eth'], self._eth_kp_dst['eth']).call()
        self.assertEqual(
            data, 0,
            f'Error: {data} != 0')

        # Check balance
        balance = contract.functions.balanceOf(empty_addr['eth']).call()
        self.assertEqual(
            balance, erc_transfer_num,
            f'Error: {balance} != {erc_transfer_num}')
