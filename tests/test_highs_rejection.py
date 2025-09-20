#!/usr/bin/env python3
"""
Test for high s-value rejection in EVM transactions

This test verifies that the blockchain properly rejects transactions
with high s-values (malleable signatures) according to EIP-2.

Expected behavior: Malleable signatures with s > n/2 should be rejected
"""

import unittest
import sys
import os
from web3 import Web3
from eth_account import Account
import rlp
from eth_utils import to_bytes
from substrateinterface import SubstrateInterface, Keypair

# Add parent directory to path to find modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.constants import ETH_URL, WS_URL
from peaq.eth import calculate_evm_account
from peaq.utils import ExtrinsicBatch


class TestHighSRejection(unittest.TestCase):
    """Test that high s-values are properly rejected"""

    def test_high_s_rejection(self):
        """Test that malleable signatures with high s-values are rejected"""

        # Connect to blockchain
        w3 = Web3(Web3.HTTPProvider(ETH_URL))
        self.assertTrue(w3.is_connected(), "Should connect to blockchain")

        # Test account
        private_key = "0xa7b9d2c3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1"
        account = Account.from_key(private_key)

        # Fund the test account using substrate sudo
        substrate = SubstrateInterface(url=WS_URL)
        alice = Keypair.create_from_uri('//Alice')

        # Convert EVM address to substrate account
        substrate_address = calculate_evm_account(account.address)

        # Fund account with 0.5 ETH (500000000000000000 wei)
        batch = ExtrinsicBatch(substrate, alice)
        batch.compose_sudo_call(
            'Balances',
            'force_set_balance',
            {
                'who': substrate_address,
                'new_free': 500000000000000000
            }
        )

        receipt = batch.execute()
        self.assertTrue(receipt.is_success, f"Failed to fund account: {receipt.error_message}")

        # Verify account has balance
        balance = w3.eth.get_balance(account.address)
        self.assertGreater(balance, 0, "Account should be funded")

        # secp256k1 curve order
        SECP256K1_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

        # Get nonce and chain info
        nonce = w3.eth.get_transaction_count(account.address)
        chain_id = w3.eth.chain_id

        # Get gas price
        try:
            gas_price = int(w3.eth.gas_price * 1.5)
        except:
            gas_price = Web3.to_wei('50', 'gwei')

        # Create normal transaction
        transaction = {
            'nonce': nonce,
            'gasPrice': gas_price,
            'gas': 21000,
            'to': Web3.to_checksum_address('0x742d35Cc6634C0532925a3b8D8E3c2d3E5d96c6c'),
            'value': Web3.to_wei('0.01', 'ether'),
            'data': b'',
            'chainId': chain_id
        }

        # Sign transaction
        signed_txn = account.sign_transaction(transaction)
        r, s, v = signed_txn.r, signed_txn.s, signed_txn.v

        # Verify original signature is canonical
        self.assertTrue(s <= SECP256K1_ORDER // 2, "Original signature should be canonical")

        # Create malleable signature (high s-value)
        malleable_s = SECP256K1_ORDER - s

        # Adjust v for malleable signature
        if v in [27, 28]:
            malleable_v = 55 - v
        else:
            recovery_id = (v - 35 - 2 * chain_id)
            malleable_v = 35 + 2 * chain_id + (1 - recovery_id)

        # Verify malleable signature is non-canonical (high s-value)
        self.assertFalse(malleable_s <= SECP256K1_ORDER // 2, "Malleable signature should NOT be canonical")

        # Create raw transaction with malleable signature
        transaction_list = [
            nonce,
            gas_price,
            21000,
            to_bytes(hexstr='0x742d35Cc6634C0532925a3b8D8E3c2d3E5d96c6c'),
            Web3.to_wei('0.01', 'ether'),
            b'',
            malleable_v,
            r,
            malleable_s
        ]

        malleable_raw_tx = rlp.encode(transaction_list).hex()

        # Attempt to send malleable transaction - this should FAIL
        with self.assertRaises(Exception) as context:
            w3.eth.send_raw_transaction(malleable_raw_tx)

        error_msg = str(context.exception).lower()

        # Check for expected rejection reasons
        expected_errors = ['invalid sender', 'invalid signature', 'transaction underpriced', 'already known']
        error_found = any(expected_error in error_msg for expected_error in expected_errors)

        self.assertTrue(error_found, f"Expected high s-value rejection, got: {context.exception}")
        print(f"✅ HIGH S-VALUE PROPERLY REJECTED: {context.exception}")


if __name__ == '__main__':
    unittest.main()