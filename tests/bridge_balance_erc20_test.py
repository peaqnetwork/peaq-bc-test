import pytest
import unittest
import time

from substrateinterface import SubstrateInterface, Keypair
from peaq.utils import ExtrinsicBatch
from peaq.utils import get_account_balance
from tools.utils import get_modified_chain_spec
from tests.evm_utils import sign_and_submit_evm_transaction
from tools.constants import WS_URL, ETH_URL
from tools.constants import KP_GLOBAL_SUDO
from tools.peaq_eth_utils import get_contract
from tools.peaq_eth_utils import get_eth_chain_id
from tools.peaq_eth_utils import get_eth_info
from peaq.utils import get_chain
from tools.utils import batch_fund
from web3 import Web3
from eth_account import Account as ETHAccount
from eth_account.messages import encode_structured_data


BALANCE_ERC20_ABI_FILE = 'ETH/balance-erc20/abi'
BALANCE_ERC20_PERMIT_ABI_FILE = 'ETH/balance-erc20-permit/abi'
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

    def evm_balances_erc20_transfer_to_account_id(self, contract, eth_kp_src, ss58_kp_src, amount):
        w3 = self._w3
        nonce = w3.eth.get_transaction_count(eth_kp_src.ss58_address)
        tx = contract.functions.transferToAccountId(ss58_kp_src.public_key, amount).build_transaction({
            'from': eth_kp_src.ss58_address,
            'nonce': nonce,
            'chainId': self._eth_chain_id})

        return sign_and_submit_evm_transaction(tx, w3, eth_kp_src)

    def generate_permit_signature(self, contract, owner_kp, spender_address, value, deadline):
        """Generate EIP-712 permit signature"""
        # Get domain separator and nonce
        expected_domain_separator = contract.functions.DOMAIN_SEPARATOR().call()
        nonce = contract.functions.nonces(owner_kp.ss58_address).call()

        # Get token name from the regular ERC20 contract
        erc20_contract = get_contract(self._w3, BALANCE_ERC20_ADDR, BALANCE_ERC20_ABI_FILE)
        token_name = erc20_contract.functions.name().call()

        # EIP-712 structured data for permit
        message = {
            'types': {
                'EIP712Domain': [
                    {'name': 'name', 'type': 'string'},
                    {'name': 'version', 'type': 'string'},
                    {'name': 'chainId', 'type': 'uint256'},
                    {'name': 'verifyingContract', 'type': 'address'}
                ],
                'Permit': [
                    {'name': 'owner', 'type': 'address'},
                    {'name': 'spender', 'type': 'address'},
                    {'name': 'value', 'type': 'uint256'},
                    {'name': 'nonce', 'type': 'uint256'},
                    {'name': 'deadline', 'type': 'uint256'}
                ]
            },
            'primaryType': 'Permit',
            'domain': {
                'name': token_name,
                'version': '1',
                'chainId': self._eth_chain_id,
                'verifyingContract': BALANCE_ERC20_ADDR
            },
            'message': {
                'owner': owner_kp.ss58_address,
                'spender': spender_address,
                'value': value,
                'nonce': nonce,
                'deadline': deadline
            }
        }

        # Validate our domain construction matches the contract's domain separator
        encoded_data = encode_structured_data(message)
        computed_domain_separator = encoded_data.header
        assert computed_domain_separator == expected_domain_separator, \
            f"Domain separator mismatch: computed {computed_domain_separator.hex()} != expected {expected_domain_separator.hex()}"

        # Sign the structured data
        private_key = owner_kp.private_key
        signature = ETHAccount.sign_message(encoded_data, private_key)

        # Extract v, r, s components
        v = signature.v
        r = signature.r.to_bytes(32, byteorder='big')
        s = signature.s.to_bytes(32, byteorder='big')

        return v, r, s, nonce

    def evm_permit(self, contract, owner_kp, spender_address, value, deadline, v, r, s):
        """Execute permit function"""
        w3 = self._w3
        nonce = w3.eth.get_transaction_count(owner_kp.ss58_address)
        tx = contract.functions.permit(
            owner_kp.ss58_address,
            spender_address,
            value,
            deadline,
            v,
            r,
            s
        ).build_transaction({
            'from': owner_kp.ss58_address,
            'nonce': nonce,
            'chainId': self._eth_chain_id
        })

        return sign_and_submit_evm_transaction(tx, w3, owner_kp)

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
        batch = ExtrinsicBatch(self._substrate, KP_GLOBAL_SUDO)
        batch_fund(batch, self._eth_kp_src['substrate'], 100 * 10 ** 18)
        receipt = batch.execute()
        self.assertTrue(receipt.is_success)
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

    def test_transfer_to_account_id(self):
        batch = ExtrinsicBatch(self._substrate, KP_GLOBAL_SUDO)
        batch_fund(batch, self._eth_kp_src['substrate'], 100 * 10 ** 18)
        receipt = batch.execute()
        self.assertTrue(receipt.is_success)

        erc_transfer_num = 2 * 10 ** 18
        contract = get_contract(self._w3, BALANCE_ERC20_ADDR, BALANCE_ERC20_ABI_FILE)

        ss58_kp_src = Keypair.create_from_mnemonic(Keypair.generate_mnemonic())
        eth_kp_balance_pre = contract.functions.balanceOf(self._eth_kp_src['eth']).call()

        evm_receipt = self.evm_balances_erc20_transfer_to_account_id(contract, self._eth_kp_src['kp'], ss58_kp_src, erc_transfer_num)
        self.assertEqual(evm_receipt['status'], 1, f'Error: {evm_receipt}: {evm_receipt["status"]}')

        eth_kp_balance_post = contract.functions.balanceOf(self._eth_kp_src['eth']).call()
        sub_kp_balance_post = get_account_balance(self._substrate, ss58_kp_src.ss58_address)

        # Loss is (erc_transfer_num + tx fee)
        # Not sure where to get accurate tx fee
        self.assertGreater(
            eth_kp_balance_pre - eth_kp_balance_post, erc_transfer_num,
            f'Error: {self._eth_kp_src["eth"]} difference incorrect'
        )
        self.assertEqual(
            sub_kp_balance_post, erc_transfer_num,
            f'Error: Transfer to {ss58_kp_src.ss58_address} failed.'
        )

    def test_permit_functionality(self):
        """Test ERC-20 permit functionality using EIP-712 signatures"""
        # Get contracts - permit ABI for permit functions, ERC20 ABI for standard functions
        permit_contract = get_contract(self._w3, BALANCE_ERC20_ADDR, BALANCE_ERC20_PERMIT_ABI_FILE)
        erc20_contract = get_contract(self._w3, BALANCE_ERC20_ADDR, BALANCE_ERC20_ABI_FILE)

        # Try to call permit functions - this will fail if not implemented
        try:
            domain_separator = permit_contract.functions.DOMAIN_SEPARATOR().call()
            self.assertIsNotNone(domain_separator)
        except Exception as e:
            self.skipTest(f"Contract does not support permit functionality: {e}")

        # Setup accounts with funds
        batch = ExtrinsicBatch(self._substrate, KP_GLOBAL_SUDO)
        batch_fund(batch, self._eth_kp_src['substrate'], 100 * 10 ** 18)
        batch_fund(batch, self._eth_kp_dst['substrate'], 100 * 10 ** 18)
        receipt = batch.execute()
        self.assertTrue(receipt.is_success)

        # Test permit parameters
        permit_value = 5 * 10 ** 18
        deadline = int(time.time()) + 3600  # 1 hour from now

        # Get initial nonce
        initial_nonce = permit_contract.functions.nonces(self._eth_kp_src['eth']).call()

        # Generate permit signature
        v, r, s, nonce = self.generate_permit_signature(
            permit_contract,
            self._eth_kp_src['kp'],
            self._eth_kp_dst['eth'],
            permit_value,
            deadline
        )

        self.assertEqual(nonce, initial_nonce, f"Nonce mismatch: {nonce} != {initial_nonce}")

        # Execute permit
        permit_receipt = self.evm_permit(
            permit_contract,
            self._eth_kp_src['kp'],
            self._eth_kp_dst['eth'],
            permit_value,
            deadline,
            v, r, s
        )
        self.assertEqual(permit_receipt['status'], 1, f'Permit failed: {permit_receipt}')

        # Verify allowance was set using ERC20 contract
        allowance = erc20_contract.functions.allowance(self._eth_kp_src['eth'], self._eth_kp_dst['eth']).call()
        self.assertEqual(allowance, permit_value, f'Allowance not set correctly: {allowance} != {permit_value}')

        # Verify nonce was incremented
        new_nonce = permit_contract.functions.nonces(self._eth_kp_src['eth']).call()
        self.assertEqual(new_nonce, initial_nonce + 1, f'Nonce not incremented: {new_nonce} != {initial_nonce + 1}')

        # Test transferFrom using the permit allowance (using ERC20 contract)
        empty_addr = get_eth_info()
        transfer_receipt = self.evm_balance_erc20_transfer_from(
            erc20_contract,
            self._eth_kp_dst['kp'],
            self._eth_kp_src['eth'],
            empty_addr['eth'],
            permit_value
        )
        self.assertEqual(transfer_receipt['status'], 1, f'TransferFrom failed: {transfer_receipt}')

        # Verify transfer worked using ERC20 contract
        final_balance = erc20_contract.functions.balanceOf(empty_addr['eth']).call()
        self.assertEqual(final_balance, permit_value, f'Transfer amount incorrect: {final_balance} != {permit_value}')

        # Verify allowance was consumed using ERC20 contract
        final_allowance = erc20_contract.functions.allowance(self._eth_kp_src['eth'], self._eth_kp_dst['eth']).call()
        self.assertEqual(final_allowance, 0, f'Allowance not consumed: {final_allowance} != 0')

    def test_permit_expired_deadline(self):
        """Test permit with expired deadline"""
        permit_contract = get_contract(self._w3, BALANCE_ERC20_ADDR, BALANCE_ERC20_PERMIT_ABI_FILE)

        # Skip if permit not supported
        try:
            permit_contract.functions.DOMAIN_SEPARATOR().call()
        except Exception as e:
            self.skipTest(f"Contract does not support permit functionality: {e}")

        # Setup accounts with funds
        batch = ExtrinsicBatch(self._substrate, KP_GLOBAL_SUDO)
        batch_fund(batch, self._eth_kp_src['substrate'], 100 * 10 ** 18)
        receipt = batch.execute()
        self.assertTrue(receipt.is_success)

        # Use expired deadline (past timestamp)
        permit_value = 5 * 10 ** 18
        expired_deadline = int(time.time()) - 3600  # 1 hour ago

        # Generate permit signature with expired deadline
        v, r, s, nonce = self.generate_permit_signature(
            permit_contract,
            self._eth_kp_src['kp'],
            self._eth_kp_dst['eth'],
            permit_value,
            expired_deadline
        )

        # Execute permit - should fail
        try:
            permit_receipt = self.evm_permit(
                permit_contract,
                self._eth_kp_src['kp'],
                self._eth_kp_dst['eth'],
                permit_value,
                expired_deadline,
                v, r, s
            )
            # If it doesn't revert, the transaction should fail
            self.assertEqual(permit_receipt['status'], 0, 'Permit with expired deadline should fail')
        except ValueError as e:
            # Expected - permit should revert with deadline/expired related message
            error_msg = str(e).lower()
            self.assertTrue(
                'expired' in error_msg or 'deadline' in error_msg or 'invalid permit' in error_msg,
                f'Should revert with deadline-related error, got: {e}'
            )

    def test_permit_invalid_signature(self):
        """Test permit with invalid signature"""
        permit_contract = get_contract(self._w3, BALANCE_ERC20_ADDR, BALANCE_ERC20_PERMIT_ABI_FILE)

        # Skip if permit not supported
        try:
            permit_contract.functions.DOMAIN_SEPARATOR().call()
        except Exception as e:
            self.skipTest(f"Contract does not support permit functionality: {e}")

        # Setup accounts with funds
        batch = ExtrinsicBatch(self._substrate, KP_GLOBAL_SUDO)
        batch_fund(batch, self._eth_kp_src['substrate'], 100 * 10 ** 18)
        receipt = batch.execute()
        self.assertTrue(receipt.is_success)

        permit_value = 5 * 10 ** 18
        deadline = int(time.time()) + 3600

        # Use invalid signature components
        invalid_v = 28
        invalid_r = b'\x00' * 32
        invalid_s = b'\x00' * 32

        # Execute permit with invalid signature - should fail
        try:
            permit_receipt = self.evm_permit(
                permit_contract,
                self._eth_kp_src['kp'],
                self._eth_kp_dst['eth'],
                permit_value,
                deadline,
                invalid_v, invalid_r, invalid_s
            )
            # If it doesn't revert, the transaction should fail
            self.assertEqual(permit_receipt['status'], 0, 'Permit with invalid signature should fail')
        except ValueError as e:
            # Expected - permit should revert with "Invalid permit" message
            self.assertIn('Invalid permit', str(e), 'Should revert with Invalid permit message')
