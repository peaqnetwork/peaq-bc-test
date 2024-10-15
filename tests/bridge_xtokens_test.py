import sys
sys.path.append('./')

import unittest
import pytest
from tests.utils_func import restart_parachain_and_runtime_upgrade
from tools.runtime_upgrade import wait_until_block_height
from substrateinterface import SubstrateInterface, Keypair
from tools.constants import ETH_URL, RELAYCHAIN_WS_URL
from tools.constants import WS_URL, ACA_WS_URL, PARACHAIN_WS_URL
from tools.peaq_eth_utils import sign_and_submit_evm_transaction
from peaq.utils import get_account_balance
from peaq.utils import ExtrinsicBatch
from tools.asset import convert_enum_to_asset_id
from tools.constants import KP_GLOBAL_SUDO, ACA_PD_CHAIN_ID
from tools.asset import batch_register_location, batch_set_units_per_second, setup_xc_register_if_not_exist
from tools.asset import setup_aca_asset_if_not_exist
from tools.asset import UNITS_PER_SECOND
from tools.asset import PEAQ_ASSET_LOCATION
from tools.asset import PEAQ_METADATA, PEAQ_ASSET_ID
from tools.utils import get_peaq_chain_id
from tools.asset import batch_create_asset, batch_mint, batch_set_metadata, batch_force_create_asset
from tools.peaq_eth_utils import calculate_asset_to_evm_address
from web3 import Web3
from tools.peaq_eth_utils import get_contract
from tools.peaq_eth_utils import get_eth_info
from tools.peaq_eth_utils import get_eth_chain_id
from tools.asset import wait_for_account_asset_change_wrap
from tools.asset import get_tokens_account_from_pallet_assets


PEAQ_PD_CHAIN_ID = get_peaq_chain_id()

ABI_FILE = 'ETH/xtokens/abi'
XTOKENS_ADDRESS = '0x0000000000000000000000000000000000000803'

TEST_TOKEN_NUM = 10 * 10 ** 18
INIT_TOKEN_NUM = 100 ** 18
# For avoid exhaust tokens
REMAIN_TOKEN_NUM = 10000

XCM_VER = 'V4'  # So far not tested with V2!

# From 3000
TEST_ASSET_METADATA = {
    'name': 'WOW',
    'symbol': 'WOW',
    'decimals': 18,
}

TEST_ASSET_IDX = 4
TEST_ASSET_ID = {
    'peaq': TEST_ASSET_IDX,
    'para': TEST_ASSET_IDX,
}

TEST_ASSET_TOKEN = {
    'peaq': {
        XCM_VER: {
            'parents': '0',
            'interior': {
                'X1': [{
                    'GeneralKey': {
                        'length': 2,
                        'data': [0, TEST_ASSET_IDX] + [0] * 30,
                    }
                }]
            }
        }
    },
    'para': {
        XCM_VER: {
            'parents': '1',
            'interior': {
                'X2': [{'Parachain': PEAQ_PD_CHAIN_ID}, {
                    'GeneralKey': {
                        'length': 2,
                        'data': [0, TEST_ASSET_IDX] + [0] * 30,
                    }
                }]
            }
        }
    }
}


TEST_SUFF_ASSET_IDX = 8
TEST_SUFF_ASSET_ID = {
    'peaq': TEST_SUFF_ASSET_IDX,
    'para': TEST_SUFF_ASSET_IDX,
}

TEST_SUFF_ASSET_TOKEN = {
    'peaq': {
        XCM_VER: {
            'parents': '0',
            'interior': {
                'X1': [{
                    'GeneralKey': {
                        'length': 2,
                        'data': [0, TEST_SUFF_ASSET_IDX] + [0] * 30,
                    }
                }]
            }
        }
    },
    'para': {
        XCM_VER: {
            'parents': '1',
            'interior': {
                'X2': [{'Parachain': PEAQ_PD_CHAIN_ID}, {
                    'GeneralKey': {
                        'length': 2,
                        'data': [0, TEST_SUFF_ASSET_IDX] + [0] * 30,
                    }
                }]
            }
        }
    }
}


def aca_fund(substrate, kp_sudo, kp_dst, new_free):
    batch = ExtrinsicBatch(substrate, kp_sudo)
    batch.compose_sudo_call(
        'Balances',
        'force_set_balance',
        {
            'who': kp_dst.ss58_address,
            'new_free': new_free,
        }
    )
    return batch.execute()


def send_xtoken_transfer(w3, eth_chain_id, kp_sign, kp_dst, parachain_id, asset_id, token):
    contract = get_contract(w3, XTOKENS_ADDRESS, ABI_FILE)
    nonce = w3.eth.get_transaction_count(kp_sign.ss58_address)

    tx = contract.functions.transfer(
        calculate_asset_to_evm_address(asset_id),
        token,
        [1, ['0x00'+f'00000{hex(parachain_id)[2:]}', f'0x01{kp_dst.public_key.hex()}00']],
        10 ** 12).build_transaction({
            'from': kp_sign.ss58_address,
            'nonce': nonce,
            'chainId': eth_chain_id
        })

    return sign_and_submit_evm_transaction(tx, w3, kp_sign)


def send_xtoken_transfer_multi_asset(w3, eth_chain_id, kp_sign, kp_dst, parachain_id, asset_id, token):
    contract = get_contract(w3, XTOKENS_ADDRESS, ABI_FILE)
    nonce = w3.eth.get_transaction_count(kp_sign.ss58_address)

    tx = contract.functions.transferMultiasset(
        [0, []],
        token,
        [1, ['0x00'+f'00000{hex(parachain_id)[2:]}', f'0x01{kp_dst.public_key.hex()}00']],
        10 ** 12).build_transaction({
            'from': kp_sign.ss58_address,
            'nonce': nonce,
            'chainId': eth_chain_id
        })

    return sign_and_submit_evm_transaction(tx, w3, kp_sign)


def send_xtoken_transfer_multi_currencies(w3, eth_chain_id, kp_sign, kp_dst, parachain_id, asset_id, token):
    contract = get_contract(w3, XTOKENS_ADDRESS, ABI_FILE)
    nonce = w3.eth.get_transaction_count(kp_sign.ss58_address)

    tx = contract.functions.transferMultiCurrencies(
        [(calculate_asset_to_evm_address(asset_id), token),
         (calculate_asset_to_evm_address(0), token)],
        0,
        [1, ['0x00'+f'00000{hex(parachain_id)[2:]}', f'0x01{kp_dst.public_key.hex()}00']],
        10 ** 12).build_transaction({
            'from': kp_sign.ss58_address,
            'nonce': nonce,
            'chainId': eth_chain_id
        })

    return sign_and_submit_evm_transaction(tx, w3, kp_sign)


def send_xtoken_transfer_multi_assets(w3, eth_chain_id, kp_sign, kp_dst, parachain_id, asset_id, token):
    contract = get_contract(w3, XTOKENS_ADDRESS, ABI_FILE)
    nonce = w3.eth.get_transaction_count(kp_sign.ss58_address)

    tx = contract.functions.transferMultiAssets(
        [([0, []], token),
         ([0, ['0x0602' + '00' + f'0{asset_id}' + '00' * 30]], token)],
        0,
        [1, ['0x00'+f'00000{hex(parachain_id)[2:]}', f'0x01{kp_dst.public_key.hex()}00']],
        10 ** 12).build_transaction({
            'from': kp_sign.ss58_address,
            'nonce': nonce,
            'chainId': eth_chain_id
        })

    return sign_and_submit_evm_transaction(tx, w3, kp_sign)


@pytest.mark.relaunch
@pytest.mark.eth
@pytest.mark.xcm
class TestBridgeXTokens(unittest.TestCase):
    def get_parachain_id(self, relay_substrate):
        result = relay_substrate.query(
            'Paras',
            'Parachains',
        )
        return result.value[0]

    @classmethod
    def setUpClass(cls):
        restart_parachain_and_runtime_upgrade()
        wait_until_block_height(SubstrateInterface(url=RELAYCHAIN_WS_URL), 1)
        wait_until_block_height(SubstrateInterface(url=PARACHAIN_WS_URL), 1)
        wait_until_block_height(SubstrateInterface(url=ACA_WS_URL), 1)

    def setUp(self):
        wait_until_block_height(SubstrateInterface(url=PARACHAIN_WS_URL), 1)
        wait_until_block_height(SubstrateInterface(url=ACA_WS_URL), 1)

        self.si_peaq = SubstrateInterface(url=WS_URL,)
        self.si_aca = SubstrateInterface(url=ACA_WS_URL)
        self.alice = Keypair.create_from_uri('//Alice')
        self.kp_eth = get_eth_info()
        self._w3 = Web3(Web3.HTTPProvider(ETH_URL))
        self.eth_chain_id = get_eth_chain_id(self.si_peaq)

        # transfer
        batch = ExtrinsicBatch(self.si_peaq, self.alice)
        batch.compose_call(
            'Balances',
            'transfer_keep_alive',
            {
                'dest': self.kp_eth['substrate'],
                'value': 100 * 10 ** 18,
            }
        )
        batch.execute()

    def setup_xc_register_if_not_exist(self, asset_id, location, units_per_second):
        resp = self.si_peaq.query("XcAssetConfig", "AssetIdToLocation", [asset_id])
        if resp.value:
            return
        batch = ExtrinsicBatch(self.si_peaq, KP_GLOBAL_SUDO)
        batch_register_location(batch, asset_id, location)
        batch_set_units_per_second(batch, location, units_per_second)
        receipt = batch.execute()
        self.assertTrue(receipt.is_success, f"Failed to register location {location}, {receipt.error_message}")

    def get_balance_account_from_pallet_balance(self, addr, _):
        return get_account_balance(self.si_peaq, addr)

    def wait_for_aca_account_token_change(self, addr, asset_id, block_num, prev_token=0):
        return wait_for_account_asset_change_wrap(
            self.si_aca, addr, asset_id, prev_token, block_num, get_tokens_account_from_pallet_assets)

    def is_asset_exist(self, asset_id, is_sufficient):
        asset = self.si_peaq.query("Assets", "Asset", [convert_enum_to_asset_id({'Token': asset_id})])
        if not asset.value:
            return False
        if asset.value['is_sufficient'] != is_sufficient:
            raise IOError(f'Asset {asset_id} is not sufficient: {asset.value.is_sufficient}')
        return True

    def _set_up_peaq_asset_on_peaq(self, asset_id, asset_location, para_addr, is_sufficent=False):
        batch = ExtrinsicBatch(self.si_peaq, KP_GLOBAL_SUDO)
        if not self.is_asset_exist(asset_id, is_sufficent):
            if is_sufficent:
                batch_force_create_asset(batch, KP_GLOBAL_SUDO.ss58_address, asset_id)
            else:
                batch_create_asset(batch, KP_GLOBAL_SUDO.ss58_address, asset_id)
            batch_set_metadata(
                batch, asset_id,
                TEST_ASSET_METADATA['name'], TEST_ASSET_METADATA['symbol'], TEST_ASSET_METADATA['decimals'])
        batch_mint(batch, para_addr, asset_id, 10 * TEST_TOKEN_NUM)
        receipt = batch.execute()
        self.assertTrue(receipt.is_success, f'Failed to create asset: {receipt.error_message}')
        receipt = setup_xc_register_if_not_exist(
            self.si_peaq, KP_GLOBAL_SUDO, asset_id,
            asset_location, UNITS_PER_SECOND)
        self.assertTrue(receipt.is_success, f'Failed to register foreign asset: {receipt.error_message}')

    @pytest.mark.xcm
    def test_native_from_peaq_to_aca(self):
        receipt = setup_aca_asset_if_not_exist(
            self.si_aca, KP_GLOBAL_SUDO, PEAQ_ASSET_ID['para'], PEAQ_ASSET_LOCATION['para'], PEAQ_METADATA)
        self.assertTrue(receipt.is_success, f'Failed to register foreign asset: {receipt.error_message}')

        kp_para_dst = Keypair.create_from_mnemonic(Keypair.generate_mnemonic())
        receipt = aca_fund(self.si_aca, KP_GLOBAL_SUDO, kp_para_dst, INIT_TOKEN_NUM)
        self.assertTrue(receipt.is_success, f'Failed to fund tokens to aca: {receipt.error_message}')

        aca_block_num = self.si_aca.get_block_number(None)
        evm_receipt = send_xtoken_transfer(
            self._w3, self.eth_chain_id, self.kp_eth['kp'], kp_para_dst,
            ACA_PD_CHAIN_ID, PEAQ_ASSET_ID['peaq'], TEST_TOKEN_NUM)
        self.assertEqual(evm_receipt['status'], 1, f'Error: {evm_receipt}: {evm_receipt["status"]}')

        # Extract...
        got_token = self.wait_for_aca_account_token_change(kp_para_dst.ss58_address, PEAQ_ASSET_ID['para'], aca_block_num)
        self.assertNotEqual(got_token, 0)

    @pytest.mark.xcm
    def test_asset_from_peaq_to_aca_with_sufficient(self):
        # From Alice transfer to kp_para_src (other chain)
        asset_id = TEST_SUFF_ASSET_ID['peaq']
        self._set_up_peaq_asset_on_peaq(asset_id, TEST_SUFF_ASSET_TOKEN['peaq'], self.kp_eth['substrate'], True)

        kp_para_src = Keypair.create_from_mnemonic(Keypair.generate_mnemonic())
        # register on aca
        receipt = setup_aca_asset_if_not_exist(
            self.si_aca,
            KP_GLOBAL_SUDO,
            TEST_SUFF_ASSET_ID['para'],
            TEST_SUFF_ASSET_TOKEN['para'],
            TEST_ASSET_METADATA)
        self.assertTrue(receipt.is_success, f'Failed to register foreign asset: {receipt.error_message}')

        receipt = aca_fund(self.si_aca, KP_GLOBAL_SUDO, kp_para_src, INIT_TOKEN_NUM)
        self.assertTrue(receipt.is_success, f'Failed to fund tokens to aca: {receipt.error_message}')

        aca_block_num = self.si_aca.get_block_number(None)
        evm_receipt = send_xtoken_transfer(
            self._w3, self.eth_chain_id, self.kp_eth['kp'], kp_para_src,
            ACA_PD_CHAIN_ID, TEST_SUFF_ASSET_ID['peaq'], TEST_TOKEN_NUM)
        self.assertEqual(evm_receipt['status'], 1, f'Error: {evm_receipt}: {evm_receipt["status"]}')

        # Extract...
        got_token = self.wait_for_aca_account_token_change(kp_para_src.ss58_address, TEST_SUFF_ASSET_ID['para'], aca_block_num)
        self.assertNotEqual(got_token, 0)

    @pytest.mark.xcm
    def test_bridge_xtoken_single_transfer_multi_asset(self):
        receipt = setup_aca_asset_if_not_exist(
            self.si_aca, KP_GLOBAL_SUDO, PEAQ_ASSET_ID['para'], PEAQ_ASSET_LOCATION['para'], PEAQ_METADATA)
        self.assertTrue(receipt.is_success, f'Failed to register foreign asset: {receipt.error_message}')

        kp_para_dst = Keypair.create_from_mnemonic(Keypair.generate_mnemonic())
        receipt = aca_fund(self.si_aca, KP_GLOBAL_SUDO, kp_para_dst, INIT_TOKEN_NUM)
        self.assertTrue(receipt.is_success, f'Failed to fund tokens to aca: {receipt.error_message}')

        aca_block_num = self.si_aca.get_block_number(None)
        evm_receipt = send_xtoken_transfer_multi_asset(
            self._w3, self.eth_chain_id, self.kp_eth['kp'], kp_para_dst,
            ACA_PD_CHAIN_ID, PEAQ_ASSET_ID['peaq'], TEST_TOKEN_NUM)
        self.assertEqual(evm_receipt['status'], 1, f'Error: {evm_receipt}: {evm_receipt["status"]}')

        got_token = self.wait_for_aca_account_token_change(kp_para_dst.ss58_address, PEAQ_ASSET_ID['para'], aca_block_num)
        self.assertNotEqual(got_token, 0)

    @pytest.mark.xcm
    def test_bridge_xtoken_transfer_multi_currencies(self):
        # From Alice transfer to kp_para_src (other chain)
        asset_id = TEST_ASSET_ID['peaq']
        self._set_up_peaq_asset_on_peaq(asset_id, TEST_ASSET_TOKEN['peaq'], self.kp_eth['substrate'], True)

        kp_para_src = Keypair.create_from_mnemonic(Keypair.generate_mnemonic())
        # register on aca
        receipt = setup_aca_asset_if_not_exist(
            self.si_aca, KP_GLOBAL_SUDO, TEST_ASSET_ID['para'], TEST_ASSET_TOKEN['para'], TEST_ASSET_METADATA)
        self.assertTrue(receipt.is_success, f'Failed to register foreign asset: {receipt.error_message}')
        receipt = setup_aca_asset_if_not_exist(
            self.si_aca, KP_GLOBAL_SUDO, PEAQ_ASSET_ID['para'], PEAQ_ASSET_LOCATION['para'], PEAQ_METADATA)
        self.assertTrue(receipt.is_success, f'Failed to register foreign asset: {receipt.error_message}')

        receipt = aca_fund(self.si_aca, KP_GLOBAL_SUDO, kp_para_src, INIT_TOKEN_NUM)
        self.assertTrue(receipt.is_success, f'Failed to fund tokens to aca: {receipt.error_message}')

        aca_block_num = self.si_aca.get_block_number(None)
        evm_receipt = send_xtoken_transfer_multi_currencies(
            self._w3, self.eth_chain_id, self.kp_eth['kp'], kp_para_src,
            ACA_PD_CHAIN_ID, TEST_ASSET_ID['peaq'], TEST_TOKEN_NUM)
        self.assertEqual(evm_receipt['status'], 1, f'Error: {evm_receipt}: {evm_receipt["status"]}')

        got_token = self.wait_for_aca_account_token_change(kp_para_src.ss58_address, TEST_ASSET_ID['para'], aca_block_num)
        self.assertNotEqual(got_token, 0)
        got_token = get_tokens_account_from_pallet_assets(
            self.si_aca, kp_para_src.ss58_address, PEAQ_ASSET_ID['para'])
        self.assertNotEqual(got_token, 0)

    @pytest.mark.xcm
    def test_bridge_xtoken_transfer_multi_assets(self):
        # From Alice transfer to kp_para_src (other chain)
        asset_id = TEST_ASSET_ID['peaq']
        self._set_up_peaq_asset_on_peaq(asset_id, TEST_ASSET_TOKEN['peaq'], self.kp_eth['substrate'], True)

        kp_para_src = Keypair.create_from_mnemonic(Keypair.generate_mnemonic())
        # register on aca
        receipt = setup_aca_asset_if_not_exist(
            self.si_aca, KP_GLOBAL_SUDO, TEST_ASSET_ID['para'], TEST_ASSET_TOKEN['para'], TEST_ASSET_METADATA)
        self.assertTrue(receipt.is_success, f'Failed to register foreign asset: {receipt.error_message}')
        receipt = setup_aca_asset_if_not_exist(
            self.si_aca, KP_GLOBAL_SUDO, PEAQ_ASSET_ID['para'], PEAQ_ASSET_LOCATION['para'], PEAQ_METADATA)
        self.assertTrue(receipt.is_success, f'Failed to register foreign asset: {receipt.error_message}')

        receipt = aca_fund(self.si_aca, KP_GLOBAL_SUDO, kp_para_src, INIT_TOKEN_NUM)
        self.assertTrue(receipt.is_success, f'Failed to fund tokens to aca: {receipt.error_message}')

        aca_block_num = self.si_aca.get_block_number(None)
        evm_receipt = send_xtoken_transfer_multi_assets(
            self._w3, self.eth_chain_id, self.kp_eth['kp'], kp_para_src,
            ACA_PD_CHAIN_ID, TEST_ASSET_ID['peaq'], TEST_TOKEN_NUM)
        self.assertEqual(evm_receipt['status'], 1, f'Error: {evm_receipt}: {evm_receipt["status"]}')

        got_token = self.wait_for_aca_account_token_change(kp_para_src.ss58_address, TEST_ASSET_ID['para'], aca_block_num)
        self.assertNotEqual(got_token, 0)
        got_token = get_tokens_account_from_pallet_assets(
            self.si_aca, kp_para_src.ss58_address, PEAQ_ASSET_ID['para'])
        self.assertNotEqual(got_token, 0)
