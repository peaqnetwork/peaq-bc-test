import unittest
import pytest
from substrateinterface import SubstrateInterface, Keypair, KeypairType
from tools.constants import WS_URL, ETH_URL
from tools.constants import KP_COLLATOR
from tools.evm_claim_sign import calculate_claim_signature, claim_account
from tests.utils_func import restart_parachain_and_runtime_upgrade
from tools.runtime_upgrade import wait_until_block_height
from tools.peaq_eth_utils import get_eth_chain_id, calculate_evm_default_addr
from peaq.utils import ExtrinsicBatch
from web3 import Web3
from peaq.eth import calculate_evm_addr


def claim_default_account(substrate, kp_sub):
    batch = ExtrinsicBatch(substrate, kp_sub)
    batch_claim_default_account(batch)
    return batch.execute()


def batch_claim_default_account(batch):
    batch.compose_call(
        'AddressUnification',
        'claim_default_account',
        {}
    )


def get_eth_block_author():
    w3 = Web3(Web3.HTTPProvider(ETH_URL))
    block = w3.eth.get_block('latest')
    return block['author']


@pytest.mark.eth
class TestCollatorBehavior(unittest.TestCase):
    def setUp(self):
        restart_parachain_and_runtime_upgrade()
        wait_until_block_height(SubstrateInterface(url=WS_URL), 2)
        self._substrate = SubstrateInterface(url=WS_URL)
        self._eth_chain_id = get_eth_chain_id(self._substrate)

    def test_author_check_address_unification(self):
        kp_eth = Keypair.create_from_mnemonic(Keypair.generate_mnemonic(), crypto_type=KeypairType.ECDSA)

        signature = calculate_claim_signature(
            self._substrate,
            KP_COLLATOR.ss58_address,
            kp_eth.private_key.hex(),
            self._eth_chain_id)

        # Execute
        receipt = claim_account(self._substrate, KP_COLLATOR, kp_eth, signature)
        self.assertTrue(receipt.is_success, f'Failed to claim account {KP_COLLATOR.ss58_address}, {receipt.error_message}')

        evm_block_author = get_eth_block_author()

        # Check
        self.assertEqual(
            Web3.to_checksum_address(evm_block_author),
            Web3.to_checksum_address(kp_eth.ss58_address), f'{evm_block_author} != {kp_eth.ss58_address}')

    def test_author_check_default_unify(self):
        # Directly test the author of the block without unification
        kp_sub = KP_COLLATOR
        kp_evm_addr = calculate_evm_addr(kp_sub.ss58_address)

        eth_default_addr = calculate_evm_default_addr(kp_sub.public_key)
        evm_block_author = get_eth_block_author()
        self.assertEqual(
            Web3.to_checksum_address(evm_block_author),
            Web3.to_checksum_address(kp_evm_addr), f'{evm_block_author} != {kp_evm_addr}')

        # Start to test default

        # Claim the default
        receipt = claim_default_account(self._substrate, kp_sub)
        self.assertTrue(
            receipt.is_success,
            f'Failed to claim default account {kp_sub.ss58_address}, {receipt.error_message}')

        evm_block_author = get_eth_block_author()

        # Check
        self.assertEqual(
            Web3.to_checksum_address(evm_block_author),
            Web3.to_checksum_address(eth_default_addr), f'{evm_block_author} != {eth_default_addr}')
