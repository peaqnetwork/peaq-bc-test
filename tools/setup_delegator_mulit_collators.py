import sys
sys.path.append('./')
import time

from substrateinterface import SubstrateInterface, Keypair
from peaq.sudo_extrinsic import funds
from peaq.utils import ExtrinsicBatch
from tools.utils import get_collators
from tools.constants import KP_GLOBAL_SUDO, BLOCK_GENERATE_TIME
import argparse


def fund_delegators(substrate: SubstrateInterface, delegators: list, amount: int, batch_num: int = 500):
    delegators = [kp.ss58_address for kp in delegators]
    for i in range(0, len(delegators), batch_num):
        print(f'Funding {i} / {len(delegators)}')
        funds(substrate, KP_GLOBAL_SUDO, delegators[i:i + batch_num], amount)
        print(f'Funded {i} / {len(delegators)}')


def generate_delegators(number: int):
    return [Keypair.create_from_mnemonic(Keypair.generate_mnemonic()) for _ in range(number)]


def get_collator_stake(substrate: SubstrateInterface, validator: str) -> int:
    key = Keypair(ss58_address=validator)
    collator_info = get_collators(substrate, key)
    return int(collator_info['stake'].value)


def delegate_join_delegators(substrate: SubstrateInterface, delegators: list, collator_addr: str, collator_stake: int):
    for i, kp in enumerate(delegators):
        batch = ExtrinsicBatch(substrate, kp)
        batch.compose_call(
            'ParachainStaking',
            'join_delegators',
            {
                'collator': collator_addr,
                'amount': collator_stake
            }
        )
        batch.execute()


def delegate_delegators(substrate: SubstrateInterface, delegators: list, collator_addr: str, collator_stake: int):
    for i, kp in enumerate(delegators):
        batch = ExtrinsicBatch(substrate, kp)
        batch.compose_call(
            'ParachainStaking',
            'delegate_another_candidate',
            {
                'collator': collator_addr,
                'amount': collator_stake
            }
        )
        batch.execute()


def get_validators_info(substrate):
    validators = substrate.query('Session', 'Validators', [])
    return [validator.value for validator in validators]


def main():
    parser = argparse.ArgumentParser(description='Setup the delegator')
    parser.add_argument('--number', type=int, required=True, help='Number of collators one delegator want to delegate')
    parser.add_argument('--url', type=str, required=True, help='websocket URL')

    args = parser.parse_args()
    substrate = SubstrateInterface(url=args.url)

    validators = get_validators_info(substrate)
    if len(validators) == 0:
        print('No validators found')
        return
    if len(validators) < args.number:
        print(f'Number of validators {len(validators)} is less than {args.number}')
        return

    print(f'Number of validators are {len(validators)}')
    # Get default staking number
    total_collator_stake = sum(get_collator_stake(substrate, validator) for validator in validators[:args.number])
    fund_value = total_collator_stake * 3
    if fund_value < 2 * 10 ** 18:
        fund_value = 2 * 10 ** 18
        print(f'Collator stake {total_collator_stake} is less than {fund_value}, so we will fund it with {fund_value}')

    # Fund the delegators
    kps = generate_delegators(1)
    fund_delegators(substrate, kps, fund_value)
    time.sleep(BLOCK_GENERATE_TIME)

    # Delegate the first
    delegate_join_delegators(substrate, kps, validators[0], get_collator_stake(substrate, validators[0]))
    if args.number == 1:
        return

    # Delegate
    validators = validators[1:]
    for idx, validator in enumerate(validators[:args.number]):
        print(F'Setup delegators for {validator} start, {idx} / {len(validators)}')
        delegate_delegators(
            substrate,
            kps,
            validator,
            get_collator_stake(substrate, validator))
        print(f'Setup delegators for {validator} successfully, {idx} / {len(validators)}')

        while True:
            pending_tx = substrate.retrieve_pending_extrinsics()
            if len(pending_tx) < 5:
                print(f'The pending transactions are {len(pending_tx)}, we can continue')
                break
            else:
                print(f'Waiting for {len(pending_tx)} pending transactions')
            time.sleep(12)


if __name__ == '__main__':
    main()
