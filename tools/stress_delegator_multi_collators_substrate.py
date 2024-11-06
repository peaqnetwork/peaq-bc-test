import sys
sys.path.append('./')
import time

from substrateinterface import SubstrateInterface, Keypair
from peaq.sudo_extrinsic import funds
from tools.utils import get_all_events
from peaq.utils import get_block_height, get_block_hash
from peaq.utils import ExtrinsicBatch
from tools.utils import get_collators
from tools.constants import KP_GLOBAL_SUDO
from tools.runtime_upgrade import wait_until_block_height
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
        return batch.execute()


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
        return batch.execute()


def get_validators_info(substrate):
    validators = substrate.query('Session', 'Validators', [])
    return [validator.value for validator in validators]


def check_delegator_reward_event(substrate, kp, number):
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
        if kp.ss58_address in reward_info:
            print(f'Delegator reward event {kp.ss58_address} found, block height {block_height}, reward {reward_info[kp.ss58_address]}')
            continue
        else:
            print(f'Delegator reward {kp.ss58_address} event {block_height} not found')
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


def setup_delegators(substrate, kps, validators, number):
    # Delegate the first
    receipt = delegate_join_delegators(substrate, kps, validators[0], get_collator_stake(substrate, validators[0]))
    if number == 1:
        return
    print('Wait for one session')
    # [TODO] Let us skip this, only need to enable in Krest/Peaq docker env
    # batch = ExtrinsicBatch(substrate, KP_GLOBAL_SUDO)
    # batch.compose_sudo_call(
    #     'ParachainStaking',
    #     'force_new_round',
    #     {}
    # )
    # receipt = batch.execute()
    # if not receipt.is_success:
    #     print('Force new round failed')
    #     raise IOError('Force new round failed')

    wait_next_session(substrate, receipt.block_hash)

    # Delegate
    validators = validators[1:]
    for idx, validator in enumerate(validators[:number]):
        print(F'Setup delegators for {validator} start, {idx} / {len(validators)}')
        receipt = delegate_delegators(
            substrate,
            kps,
            validator,
            get_collator_stake(substrate, validator))
        print(f'Setup delegators for {validator} successfully, {idx} / {len(validators)}')
        # [TODO] Let us skip this, only need to enable in Krest/Peaq docker env
        # receipt = batch.execute()
        # if not receipt.is_success:
        #     print('Force new round failed')
        #     raise IOError('Force new round failed')
        wait_next_session(substrate, receipt.block_hash)


def check_delegator_number(substrate, kp, number):
    out = substrate.query('ParachainStaking', 'DelegatorState', [kp.ss58_address])

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


def main():
    parser = argparse.ArgumentParser(description='Setup the delegator')
    parser.add_argument('--number', type=int, required=True, help='Number of collators one delegator want to delegate')
    parser.add_argument('--url', type=str, required=True, help='websocket URL')

    args = parser.parse_args()
    substrate = SubstrateInterface(url=args.url)

    print('Wait until block height 1')
    wait_until_block_height(substrate, 1)
    validators = get_validators_info(substrate)
    if len(validators) == 0:
        print('No validators found')
        return
    if len(validators) < args.number:
        print(f'Number of validators {len(validators)} is less than {args.number}')
        return

    print(f'Number of validators are {len(validators)}')
    # [TODO] Let us skip this, only need to enable in Krest/Peaq docker env
    # batch = ExtrinsicBatch(substrate, KP_GLOBAL_SUDO)
    # batch.compose_sudo_call(
    #     'ParachainStaking',
    #     'force_new_round',
    #     {}
    # )
    # receipt = batch.execute()
    # if not receipt.is_success:
    #     print('Force new round failed')
    #     raise IOError('Force new round failed')

    kps = [Keypair.create_from_mnemonic('trumpet depth hidden success nominee twenty erode mixture pond bread easily cycle')]
    for i in range(10000):
        print('Setup delegators start {}'.format(i))
        setup_delegators(substrate, kps, validators, args.number)

        if not check_delegator_number(substrate, kps[0], args.number):
            print('Delegator number not found')
            raise IOError('Delegator number not found')

        # Wait and check whether the delegators there
        if not check_delegator_reward_event(substrate, kps[0], 24):
            print('Delegator reward event not found')
            raise IOError('Delegator reward event not found')

        # Leave the delegators
        batch = ExtrinsicBatch(substrate, kps[0])
        batch.compose_call('ParachainStaking', 'leave_delegators', {})
        receipt = batch.execute()
        if not receipt.is_success:
            print('Leave delegators failed')
            raise IOError('Leave delegators failed')

        if not check_delegator_number(substrate, kps[0], 0):
            print('Delegator number not found')
            raise IOError('Delegator number not found')

        print('Setup delegators successfully {}'.format(i))


# python3 tools/stress_delegator_multi_collators.py --number 8 --url wss://docker-test.peaq.network
if __name__ == '__main__':
    main()
