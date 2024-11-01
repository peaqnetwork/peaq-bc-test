import sys
sys.path.append('./')
import time

from substrateinterface import SubstrateInterface, Keypair
from tools.utils import get_all_events
from peaq.utils import get_block_height, get_block_hash
from tools.peaq_eth_utils import sign_and_submit_evm_transaction
from tools.utils import get_collators
from tools.peaq_eth_utils import get_contract
from tools.peaq_eth_utils import get_eth_info
from tools.runtime_upgrade import wait_until_block_height
from tools.peaq_eth_utils import get_eth_chain_id
from web3 import Web3
import argparse


PARACHAIN_STAKING_ABI_FILE = 'ETH/parachain-staking/abi'
PARACHAIN_STAKING_ADDR = '0x0000000000000000000000000000000000000807'


def get_collator_stake(substrate: SubstrateInterface, validator: str) -> int:
    key = Keypair(ss58_address=validator)
    collator_info = get_collators(substrate, key)
    return int(collator_info['stake'].value)


def get_validators_info(substrate):
    validators = substrate.query('Session', 'Validators', [])
    return [validator.value for validator in validators]


def check_delegator_reward_event(substrate, addr, number):
    for i in range(number):
        time.sleep(6)
        print(f'Check delegator reward event {i}')
        block_height = get_block_height(substrate)
        block_hash = get_block_hash(substrate, block_height)
        result = get_all_events(
            substrate,
            block_hash,
            'ParachainStaking', 'Rewarded')
        reward_info = {
            event.value['attributes'][0]: event.value['attributes'][1]
            for event in result
        }
        if addr in reward_info:
            print(f'Delegator reward event {addr} found, block height {block_height}, reward {reward_info[addr]}')
            continue
        else:
            print(f'Delegator reward {addr} event {block_height} not found')
            return False
    return True


def wait_next_session(substrate, block_hash):
    current_session = substrate.query("Session", "CurrentIndex", [], block_hash)
    for i in range(20):
        block_hash = get_block_hash(substrate, get_block_height(substrate))
        now_session = substrate.query("Session", "CurrentIndex", [], block_hash)
        if now_session != current_session:
            print(f'Wait for next session {now_session} > {current_session}')
            return
        time.sleep(6)
    print('Wait for next session failed')


def delegate_join_delegators(w3, eth_chain_id, delegators, collator_addr, collator_stake):
    contract = get_contract(w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
    for i, eth_kp in enumerate(delegators):
        eth_kp_src = eth_kp['kp']
        nonce = w3.eth.get_transaction_count(eth_kp_src.ss58_address)
        tx = contract.functions.joinDelegators(collator_addr, collator_stake).build_transaction({
            'from': eth_kp_src.ss58_address,
            'nonce': nonce,
            'chainId': eth_chain_id})

        return sign_and_submit_evm_transaction(tx, w3, eth_kp_src)


def delegate_delegators(w3, eth_chain_id, delegators, collator_addr, collator_stake):
    contract = get_contract(w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
    for i, eth_kp in enumerate(delegators):
        eth_kp_src = eth_kp['kp']
        nonce = w3.eth.get_transaction_count(eth_kp_src.ss58_address)
        tx = contract.functions.delegateAnotherCandidate(collator_addr, collator_stake).build_transaction({
            'from': eth_kp_src.ss58_address,
            'nonce': nonce,
            'chainId': eth_chain_id})

        return sign_and_submit_evm_transaction(tx, w3, eth_kp_src)


def delegator_leave_delegators(w3, eth_chain_id, eth_kp_src):
    contract = get_contract(w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
    nonce = w3.eth.get_transaction_count(eth_kp_src.ss58_address)
    tx = contract.functions.leaveDelegators().build_transaction({
        'from': eth_kp_src.ss58_address,
        'nonce': nonce,
        'chainId': eth_chain_id})

    return sign_and_submit_evm_transaction(tx, w3, eth_kp_src)


def setup_delegators(substrate, w3, eth_chain_id, kps, validators, collator_nums, number):
    # Delegate the first
    evm_receipt = delegate_join_delegators(
        w3, eth_chain_id, kps, validators[0], collator_nums[0]
    )
    if evm_receipt['status'] != 1:
        raise IOError('Join delegators failed')
    if number == 1:
        return
    print('Wait for one session')
    block_hash = get_block_hash(substrate, evm_receipt['blockNumber'])
    wait_next_session(substrate, block_hash)

    # Delegate
    validators = validators[1:]
    collator_nums = collator_nums[1:]
    for idx, validator in enumerate(validators[:number]):
        print(F'Setup delegators for {validator} start, {idx} / {len(validators)}')
        evm_receipt = delegate_delegators(
            w3,
            eth_chain_id,
            kps,
            validator,
            collator_nums[idx])
        print(f'Setup delegators for {validator} successfully, {idx} / {len(validators)}')
        block_hash = get_block_hash(substrate, evm_receipt['blockNumber'])
        wait_next_session(substrate, block_hash)


def check_delegator_number(substrate, addr, number):
    out = substrate.query('ParachainStaking', 'DelegatorState', [addr])

    if out.value is None and number == 0:
        print(f'Delegator {number} found and okay')
        return True

    if out.value is None or 'delegations' not in out.value:
        print(f'Delegator number {number} not found')
        return False

    if len(out.value['delegations']) == number:
        print(f'Delegator number {number} found')
        return True
    else:
        print(f'Delegator number {number} not equal to {out.value["delegators"]}')
        return False


def main():  # noqa: C901
    parser = argparse.ArgumentParser(description='Setup the delegator')
    parser.add_argument('--number', type=int, required=True, help='Number of collators one delegator want to delegate')
    parser.add_argument('--ws', type=str, required=True, help='Substrate websocet URL')
    parser.add_argument('--rpc', type=str, required=True, help='ETH RPC URL')

    args = parser.parse_args()
    substrate = SubstrateInterface(url=args.ws)
    w3 = Web3(Web3.HTTPProvider(args.rpc))
    eth_chain_id = get_eth_chain_id(substrate)

    # Setup the delegator

    print('Wait until block height 1')
    wait_until_block_height(substrate, 1)
    contract = get_contract(w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
    validators = contract.functions.getCollatorList().call()
    collator_nums = [validator[1] for validator in validators]
    validators = [validator[0] for validator in validators]
    if len(validators) == 0:
        print('No validators found')
        return
    if len(validators) < args.number:
        print(f'Number of validators {len(validators)} is less than {args.number}')
        return

    print(f'Number of validators are {len(validators)}')

    # Change
    # Substrate addr: 5Hm8tdzjjPrGRonEsDvZZNdqS3d2brgYQkw7vPchwQYnB7kY
    target_kp = get_eth_info(
        'trumpet depth hidden success nominee twenty erode mixture pond bread easily cycle'
    )
    kps = [target_kp]

    # Leave the delegators
    try:
        evm_receipt = delegator_leave_delegators(w3, eth_chain_id, kps[0]['kp'])
        if evm_receipt['status'] != 1:
            print('Leave delegators failed')
            raise IOError('Leave delegators failed')
    except ValueError:
        pass

    for i in range(10000):
        print('Setup delegators start {}'.format(i))
        setup_delegators(substrate, w3, contract, eth_chain_id, kps, validators, collator_nums, args.number)

        if not check_delegator_number(substrate, kps[0]['substrate'], args.number):
            print('Delegator number not found')
            raise IOError('Delegator number not found')

        # Wait and check whether the delegators there
        if not check_delegator_reward_event(substrate, kps[0]['substrate'], 24):
            print('Delegator reward event not found')
            raise IOError('Delegator reward event not found')

        # Leave the delegators
        evm_receipt = delegator_leave_delegators(w3, eth_chain_id, kps[0]['kp'])
        if evm_receipt['status'] != 1:
            print('Leave delegators failed')
            raise IOError('Leave delegators failed')

        if not check_delegator_number(substrate, kps[0]['substrate'], 0):
            print('Delegator number not found')
            raise IOError('Delegator number not found')

        print('Setup delegators successfully {}'.format(i))


if __name__ == '__main__':
    main()
