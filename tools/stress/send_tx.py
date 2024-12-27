import sys
sys.path.append('.')

from web3 import Web3
from peaq.sudo_extrinsic import funds
from tools.peaq_eth_utils import get_eth_info
from substrateinterface import SubstrateInterface, Keypair
from tools.constants import KP_GLOBAL_SUDO
from tools.peaq_eth_utils import get_contract
from peaq.utils import ExtrinsicBatch
from tools.peaq_eth_utils import generate_random_hex
from peaq.did import did_add_payload
from tools.peaq_eth_utils import get_eth_chain_id
import multiprocessing
import time


DID_ADDRESS = '0x0000000000000000000000000000000000000800'
ABI_FILE = 'ETH/did/abi'
WAIT_PERIOD = 30


EVM_MNOMENICS = [
    "crew inform cost enable chase noodle remember visa term april path staff",
    "paper twist paddle sign path empty ski upgrade early spice chaos auto",
    "scrap dove disease donkey guess mushroom scorpion night jelly seven humor fault",
    "bunker exchange cancel bid tilt rival alert deal network correct quote inmate",
    "claim tomorrow expose soldier rebuild prefer drive alarm medal little armor want",
]

SUBSTRATE_MOMENNTS = [
    "harbor camp unveil few second banana sell globe soft special again trophy",
    "awake sample rent another cute quarter impact apple erupt maximum quick glove",
    "actor must science canyon pact camp begin truly family tape huge achieve",
    "man ritual loan fuel reflect math wait image turn busy tomorrow come",
    "mule quiz plunge shock galaxy north catalog mail fire forest talent army",
]


def fund_evm(substrate_url):
    substrate = SubstrateInterface(substrate_url)
    eth_info = [get_eth_info(EVM_MNOMENICS[i]) for i in range(5)]
    receipt = funds(
        substrate, KP_GLOBAL_SUDO,
        [eth_info[i]['substrate'] for i in range(5)],
        10000 * 10 ** 18)
    if not receipt.is_success:
        raise Exception("EVM fund failed")


def stress_evm_one_account(substrate_url, evm_url, mnomenic):
    with SubstrateInterface(substrate_url) as substrate:
        eth_chain_id = get_eth_chain_id(substrate)

    eth_key = get_eth_info(mnomenic)
    w3 = Web3(Web3.HTTPProvider(evm_url))
    contract = get_contract(w3, DID_ADDRESS, ABI_FILE)
    fail_count = 0
    for i in range(10000000):
        nonce = w3.eth.get_transaction_count(eth_key['kp'].ss58_address)
        key = generate_random_hex(20)
        value = generate_random_hex(20)
        tx = contract.functions.addAttribute(eth_key['kp'].ss58_address, key, value, 100000).build_transaction({
            'from': eth_key['kp'].ss58_address,
            'nonce': nonce,
            'chainId': eth_chain_id})

        signed_txn = w3.eth.account.sign_transaction(tx, private_key=eth_key['kp'].private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt['status'] != 1:
            fail_count += 1
        if i % 20 == 0:
            print(f"EVM did_add success: {eth_key['kp'].ss58_address} already send {i} tx, failed {fail_count}")
        time.sleep(WAIT_PERIOD)


def stress_evm(substrate_url, evm_url):
    args = [(substrate_url, evm_url, EVM_MNOMENICS[i]) for i in range(len(EVM_MNOMENICS))]
    with multiprocessing.Pool(5) as p:
        print('start the substrate stress test')
        p.starmap(stress_evm_one_account, args)


def fund_substrate(substrate_url):
    substrate = SubstrateInterface(substrate_url)
    receipt = funds(
        substrate, KP_GLOBAL_SUDO,
        [Keypair.create_from_mnemonic(SUBSTRATE_MOMENNTS[i]).ss58_address for i in range(5)],
        10000 * 10 ** 18)
    print(f"Substrate fund receipt: {receipt}")
    if not receipt.is_success:
        raise Exception("Substrate fund failed")


def stress_substrate_one_account(substrate_url, kp_src):
    substrate = SubstrateInterface(substrate_url)
    fail_acount = 0
    for i in range(10000000):
        key = generate_random_hex(20)
        value = generate_random_hex(20)
        batch = ExtrinsicBatch(substrate, kp_src)
        did_add_payload(batch, kp_src.ss58_address, key, value)
        receipt = batch.execute_n_clear()
        if not receipt.is_success:
            fail_acount += 1
            print(f"Substrate did_add failed: {receipt.extrinsic_hash}")
        if i % 10 == 0:
            print(f"Substrate did_add success: {kp_src.ss58_address} already send {i} tx, failed {fail_acount}")
        time.sleep(WAIT_PERIOD)


def stress_substrate(substrate_url):
    kp_srcs = [Keypair.create_from_mnemonic(SUBSTRATE_MOMENNTS[i]) for i in range(5)]
    args = [(substrate_url, kp_src) for kp_src in kp_srcs]
    with multiprocessing.Pool(5) as p:
        print('start the substrate stress test')
        p.starmap(stress_substrate_one_account, args)


if __name__ == '__main__':
    substrate_url = 'wss://docker-test.peaq.network'
    evm_url = 'https://docker-test.peaq.network'

    fund_evm(substrate_url)
    process1 = multiprocessing.Process(target=stress_evm, args=(substrate_url, evm_url,))
    # send substrate
    fund_substrate(substrate_url)
    process2 = multiprocessing.Process(target=stress_substrate, args=(substrate_url,))
    process1.start()
    process2.start()

    process1.join()
    process2.join()
