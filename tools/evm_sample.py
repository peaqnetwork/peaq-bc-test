import sys
sys.path.append('./')


from web3 import Web3
from tools.peaq_eth_utils import deploy_contract, get_contract
from substrateinterface import SubstrateInterface, Keypair, KeypairType
from tools.constants import WS_URL, ETH_URL
from tools.peaq_eth_utils import sign_and_submit_evm_transaction
from peaq.eth import calculate_evm_account
from peaq.extrinsic import transfer


BYTECODE_FILE = 'ETH/event_sample/bytecode'
ABI_FILE = 'ETH/event_sample/abi'
ETH_CHAIN_ID = 9999
GAS_LIMIT = 4294967
ETH_PRIVATE_KEY = '0xa2899b053679427c8c446dc990c8990c75052fd3009e563c6a613d982d6842fe'


def setup(kp_eth_src):
    KP_SRC = Keypair.create_from_uri('//Alice')
    substrate = SubstrateInterface(url=WS_URL)
    token_num = 10000 * pow(10, 15)
    receipt = transfer(substrate, KP_SRC, calculate_evm_account(kp_eth_src.ss58_address), token_num)
    print(f'call_eth_transfer_a_lot: {receipt.is_success}')


if __name__ == '__main__':
    kp_eth_src = Keypair.create_from_private_key(ETH_PRIVATE_KEY, crypto_type=KeypairType.ECDSA)
    w3 = Web3(Web3.HTTPProvider(ETH_URL))

    setup(kp_eth_src)
    with open(BYTECODE_FILE) as f:
        bytecode = f.read().strip()

    address = deploy_contract(w3, kp_eth_src, ETH_CHAIN_ID, ABI_FILE, bytecode)
    # import pdb
    # pdb.set_trace()
    # address = '0xb3284a2229214c4E0611A8E7d2620Bf2054417D3'
    contract = get_contract(w3, address, ABI_FILE)

    # Call the execute function
    nonce = w3.eth.get_transaction_count(kp_eth_src.ss58_address)
    tx = contract.functions.test().build_transaction({
        'from': kp_eth_src.ss58_address,
        'gas': GAS_LIMIT,
        'maxFeePerGas': w3.to_wei(21000, 'gwei'),
        'maxPriorityFeePerGas': w3.to_wei(2, 'gwei'),
        'nonce': nonce,
        'chainId': ETH_CHAIN_ID})

    tx_receipt = sign_and_submit_evm_transaction(tx, w3, kp_eth_src)
    import pdb
    pdb.set_trace()
    block_number = tx_receipt['blockNumber']
    print(block_number)

    event = contract.events.Log.create_filter(fromBlock=block_number, toBlock=block_number)
    events = event.get_all_entries()
    print(events)
