import sys
sys.path.append('./')

from tools.asset import get_valid_asset_id
from peaq.eth import calculate_evm_account
from peaq.utils import ExtrinsicBatch
from tools.peaq_eth_utils import get_contract
from tools.peaq_eth_utils import calculate_asset_to_evm_address
from tools.peaq_eth_utils import get_eth_chain_id
from tools.peaq_eth_utils import GAS_LIMIT
from tools.peaq_eth_utils import sign_and_submit_evm_transaction
from tools.constants import WS_URL, ETH_URL
from substrateinterface import SubstrateInterface, Keypair, KeypairType
from tools.constants import KP_GLOBAL_SUDO
from web3 import Web3

ASSET_FACTORY_ABI_FILE = 'ETH/asset-factory/abi'
ASSET_FACTORY_ADDR = '0x0000000000000000000000000000000000000806'
IERC20PLUS_ABI_FILE = 'ETH/erc20/plus.abi'

OWNER_PRIVATE_KEY = '0x77007083faa6e64d0884009165627d0067f845c13736eff45e624702f797eff3'
SINGER_PRIVATE_KEY = '0x1b54e09b085972864787fcf08d06e2b16159a64655afb85cb8864f459125999e'
POSITION_MANAGER_ADDR = '0xb2f503ef77Aa708B072AE0faC86D6EE281b6BEdc'


def fund_users(substrate, kps):
    # Fund users
    batch = ExtrinsicBatch(substrate, KP_GLOBAL_SUDO)
    for kp in kps:
        batch.compose_sudo_call(
            'Balances',
            'force_set_balance',
            {
                'who': calculate_evm_account(kp.ss58_address),
                'new_free': 1000 * 10 ** 18,
            }
        )
    batch.execute()


def create_asset(substrate, w3, eth_chain_id, contract, owner_kp):
    asset_id = get_valid_asset_id(substrate)
    nonce = w3.eth.get_transaction_count(owner_kp.ss58_address)
    tx = contract.functions.create(asset_id, owner_kp.ss58_address, 1000).build_transaction({
        'from': owner_kp.ss58_address,
        'gas': GAS_LIMIT,
        'maxFeePerGas': w3.to_wei(21000, 'gwei'),
        'maxPriorityFeePerGas': w3.to_wei(2, 'gwei'),
        'nonce': nonce,
        'chainId': eth_chain_id})

    tx_receipt = sign_and_submit_evm_transaction(tx, w3, owner_kp)
    if tx_receipt['status'] != 1:
        raise Exception(f'Failed to create asset {asset_id} with tx, receipt: {tx_receipt}')
    return calculate_asset_to_evm_address(asset_id)


def force_create_asset(substrate, kp_sudo, kp_admin):
    asset_id = get_valid_asset_id(substrate)

    batch = ExtrinsicBatch(substrate, kp_sudo)
    batch.compose_sudo_call(
        'Assets',
        'force_create',
        {
            'id': asset_id,
            'owner': calculate_evm_account(kp_admin.ss58_address),
            'is_sufficient': True,
            'min_balance': 1000,
        }
    )
    receipt = batch.execute()
    if not receipt.is_success:
        raise Exception(f'Failed to create asset {asset_id}')
    return calculate_asset_to_evm_address(asset_id)


def mint_asset(substrate, w3, eth_chain_id, asset_addr, owner_kp, dest_kp, amount):
    contract = get_contract(w3, asset_addr, IERC20PLUS_ABI_FILE)

    nonce = w3.eth.get_transaction_count(owner_kp.ss58_address)
    tx = contract.functions.mint(dest_kp.ss58_address, amount).build_transaction({
        'from': owner_kp.ss58_address,
        'gas': GAS_LIMIT,
        'maxFeePerGas': w3.to_wei(21000, 'gwei'),
        'maxPriorityFeePerGas': w3.to_wei(2, 'gwei'),
        'nonce': nonce,
        'chainId': eth_chain_id})

    tx_receipt = sign_and_submit_evm_transaction(tx, w3, owner_kp)
    if tx_receipt['status'] != 1:
        raise Exception(f'Failed to mint asset {asset_addr}, receipt: {tx_receipt}')


def approval_asset(substrate, w3, eth_chain_id, asset_addr, owner_kp, addr, amount):
    contract = get_contract(w3, asset_addr, IERC20PLUS_ABI_FILE)

    nonce = w3.eth.get_transaction_count(owner_kp.ss58_address)
    tx = contract.functions.approve(addr, amount).build_transaction({
        'from': owner_kp.ss58_address,
        'gas': GAS_LIMIT,
        'maxFeePerGas': w3.to_wei(21000, 'gwei'),
        'maxPriorityFeePerGas': w3.to_wei(2, 'gwei'),
        'nonce': nonce,
        'chainId': eth_chain_id})

    tx_receipt = sign_and_submit_evm_transaction(tx, w3, owner_kp)
    if tx_receipt['status'] != 1:
        raise Exception(f'Failed to mint asset {asset_addr}, receipt: {tx_receipt}')


if __name__ == '__main__':

    owner_kp = Keypair.create_from_private_key(OWNER_PRIVATE_KEY, crypto_type=KeypairType.ECDSA)
    signer_kp = Keypair.create_from_private_key(SINGER_PRIVATE_KEY, crypto_type=KeypairType.ECDSA)

    substrate = SubstrateInterface(url=WS_URL)

    # Fund two account
    fund_users(substrate, [owner_kp, signer_kp])

    w3 = Web3(Web3.HTTPProvider(ETH_URL))
    eth_chain_id = get_eth_chain_id(substrate)

    contract = get_contract(w3, ASSET_FACTORY_ADDR, ASSET_FACTORY_ABI_FILE)

    # tether_addr = create_asset(substrate, w3, eth_chain_id, contract, owner_kp)
    # usdc_addr = create_asset(substrate, w3, eth_chain_id, contract, owner_kp)
    # btc_addr = create_asset(substrate, w3, eth_chain_id, contract, owner_kp)

    tether_addr = force_create_asset(substrate, KP_GLOBAL_SUDO, owner_kp)
    usdc_addr = force_create_asset(substrate, KP_GLOBAL_SUDO, owner_kp)
    btc_addr = force_create_asset(substrate, KP_GLOBAL_SUDO, owner_kp)

    mint_asset(substrate, w3, eth_chain_id, tether_addr, owner_kp, signer_kp, 100000 * 10 ** 18)
    mint_asset(substrate, w3, eth_chain_id, usdc_addr, owner_kp, signer_kp, 100000 * 10 ** 18)
    mint_asset(substrate, w3, eth_chain_id, btc_addr, owner_kp, signer_kp, 100000 * 10 ** 18)

    approval_asset(substrate, w3, eth_chain_id, tether_addr, signer_kp, POSITION_MANAGER_ADDR, 1000 * 10 ** 18)
    approval_asset(substrate, w3, eth_chain_id, usdc_addr, signer_kp, POSITION_MANAGER_ADDR, 1000 * 10 ** 18)
    # approval_asset(substrate, w3, eth_chain_id, btc_addr, signer_kp, POSITION_MANAGER_ADDR, 100000)

    print(f'USDC_ADDRESS={usdc_addr}')
    print(f'TETHER_ADDRESS={tether_addr}')
    print(f'WBTC_ADDRESS={btc_addr}')
