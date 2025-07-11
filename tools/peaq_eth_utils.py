import json
from peaq.utils import ExtrinsicBatch
from substrateinterface import Keypair, KeypairType
from substrateinterface.utils import hasher
from peaq.eth import calculate_evm_account
from web3 import Web3
from web3 import exceptions as Web3Exceptions
from peaq import eth
from tools.constants import ETH_TIMEOUT
import time
from tools.constants import BLOCK_GENERATE_TIME
import random
import string


ERC20_ADDR_PREFIX = '0xffffffff00000000000000000000000000000000'
GAS_LIMIT = 4294967
TX_SUCCESS_STATUS = 1


def generate_random_hex(num_bytes=16):
    return f"0x{''.join(random.choice(string.ascii_letters) for i in range(num_bytes)).encode('utf-8').hex()}"


def get_contract(w3, address, file_name):
    with open(file_name) as f:
        abi = json.load(f)

    return w3.eth.contract(address, abi=abi)


def call_eth_transfer_a_lot(substrate, kp_src, eth_src, eth_dst):
    batch = ExtrinsicBatch(substrate, kp_src)
    batch.compose_call(
        'EVM',
        'call',
        {
            'source': eth_src,
            'target': eth_dst,
            'input': '0x',
            'value': int('0xfffffffffffffffff', 16),
            'gas_limit': GAS_LIMIT,
            'max_fee_per_gas': 21000 * 10 ** 9,
            'max_priority_fee_per_gas': 1 * 10 ** 9,
            'nonce': None,
            'access_list': []
        })
    return batch.execute()


def get_eth_balance(substrate, eth_src):
    bl_num = substrate.get_block_number(None)
    return int(substrate.rpc_request("eth_getBalance", [eth_src, bl_num]).get('result'), 16)


def deploy_contract_with_args(w3, kp_src, eth_chain_id, abi_file_name, bytecode, args):
    with open(abi_file_name) as f:
        abi = json.load(f)

    nonce = w3.eth.get_transaction_count(kp_src.ss58_address)
    tx = w3.eth.contract(
        abi=abi,
        bytecode=bytecode).constructor(*args).build_transaction({
            'from': kp_src.ss58_address,
            'nonce': nonce,
            'chainId': eth_chain_id})

    tx_receipt = sign_and_submit_evm_transaction(tx, w3, kp_src)

    address = tx_receipt['contractAddress']
    return address


def deploy_contract(w3, kp_src, eth_chain_id, abi_file_name, bytecode):
    with open(abi_file_name) as f:
        abi = json.load(f)

    nonce = w3.eth.get_transaction_count(kp_src.ss58_address)
    tx = w3.eth.contract(
        abi=abi,
        bytecode=bytecode).constructor().build_transaction({
            'from': kp_src.ss58_address,
            'nonce': nonce,
            'chainId': eth_chain_id})

    tx_receipt = sign_and_submit_evm_transaction(tx, w3, kp_src)

    address = tx_receipt['contractAddress']
    return address


def calculate_asset_to_evm_address(asset_id):
    number = int(ERC20_ADDR_PREFIX, 16) + int(asset_id)
    return Web3.to_checksum_address(hex(number))


def get_eth_chain_id(substrate):
    try:
        return eth.get_eth_chain_id(substrate)
    except KeyError:
        chain_name = substrate.rpc_request(method='system_chain', params=[]).get('result')
        forked_info = {
            'peaq-dev-fork': 9990,
            'agung-network-fork': 9990,
            'krest-network-fork': 2241,
            'peaq-network-fork': 3338,
        }
        return forked_info[chain_name]


def get_eth_info(mnemonic=""):
    if not mnemonic:
        mnemonic = Keypair.generate_mnemonic()
    kp = Keypair.create_from_mnemonic(mnemonic, crypto_type=KeypairType.ECDSA)
    return {
        'mnemonic': mnemonic,
        'kp': kp,
        'substrate': calculate_evm_account(kp.ss58_address),
        'eth': kp.ss58_address
    }


def calculate_evm_default_addr(sub_addr):
    evm_addr = b'evm:' + sub_addr
    hash_key = hasher.blake2_256(evm_addr)
    new_addr = '0x' + hash_key.hex()[:40]
    return Web3.to_checksum_address(new_addr.lower())


def send_raw_tx(w3, signed_txn):
    try:
        tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        print(f'evm tx: {tx_hash.hex()}')
        return tx_hash
    except ValueError as e:
        print("Error:", e)
        if "already known" in str(e):
            print("Transaction already known by the node.")
            return signed_txn.hash
        else:
            raise e


def wait_w3_tx(w3, tx_hash, timimeout=ETH_TIMEOUT):
    try:
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=ETH_TIMEOUT)
        while w3.eth.get_block('finalized').number < receipt.blockNumber:
            time.sleep(BLOCK_GENERATE_TIME)
    except Web3Exceptions.TimeExhausted:
        print(f'Timeout for tx: {tx_hash.hex()}')
    except Exception as e:
        raise e


def sign_and_submit_evm_transaction(tx, w3, signer):
    for i in range(3):
        signed_txn = w3.eth.account.sign_transaction(tx, private_key=signer.private_key)
        tx_hash = send_raw_tx(w3, signed_txn)
        wait_w3_tx(w3, tx_hash)

        # Check whether the block is finalized or not. If not, wait for it
        for i in range(3):
            try:
                receipt = w3.eth.get_transaction_receipt(tx_hash)
                # Check the transaction is existed or not, if not, go back to send again
                print(f'evm receipt: {receipt.blockNumber}-{receipt.transactionIndex}')
                return receipt
            except Web3Exceptions.TransactionNotFound:
                print(f'Tx {tx_hash.hex()} is not found')
                time.sleep(BLOCK_GENERATE_TIME * 2)
        else:
            print(f'Cannot find tx {tx_hash.hex()}')
            tx['data'] = tx['data'] + '00'
    raise IOError('Cannot send transaction')
