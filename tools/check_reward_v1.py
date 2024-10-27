import sys
sys.path.append('./')


from substrateinterface import SubstrateInterface
from peaq.utils import get_block_height, get_block_hash
import argparse
from collections import Counter
from tools.utils import get_all_events
from peaq.utils import get_account_balance
import pprint
pp = pprint.PrettyPrinter(indent=4)


POT_ADDR = '5EYCAe5cKPAoFh2HnQQvpKqRYZGqBpaA87u4Zzw89qPE58is'
ALLOW_ERROR_PERCENTAGE = 1e-6


def get_current_collator(substrate, num=80):
    now_block_height = get_block_height(substrate)
    collators = []
    for i in range(num):
        print(f'get author in block height: {now_block_height - i}')
        block_hash = get_block_hash(substrate, now_block_height - i)
        block_info = substrate.get_block(block_hash, include_author=True)
        collators.append(block_info['author'])
    return Counter(collators)


def get_session_validator(substrate):
    session_info = substrate.query(
        module='Session',
        storage_function='Validators',
        params=[],
    )
    return set(session_info.value)


# Only for the token economy V1
# flake8: noqa: C901
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Get storage and constants from a Substrate chain')
    parser.add_argument('-r', '--runtime', type=str, required=True, help='Your runtime websocket endpoint')
    parser.add_argument('-n', '--num', type=int, default=5, help='Number of blocks to check')
    parser.add_argument('-p', '--percentage', type=int, required=True, help='Collator Delegator rate')
    parser.add_argument('-c', '--coefficient', type=int, required=True, help='Collator/Delegator coefficient')

    args = parser.parse_args()

    if args.percentage < 0 or args.percentage > 100:
        raise ValueError(f'Percentage should be between 0 and 100, but got {args.percentage}')

    substrate = SubstrateInterface(
        url=args.runtime,
    )

    target_block_num = args.num
    now_block_height = get_block_height(substrate)
    now_block_hash = get_block_hash(substrate, now_block_height)
    if now_block_height < target_block_num:
        raise ValueError(f'Block height is {now_block_height}, less than target block number {target_block_num}')

    # get collator/delegator issuance number
    total_reward = substrate.query(
        module='InflationManager',
        storage_function='BlockRewards',
        params=[],
    )
    collator_delegator_issuance = total_reward.value * args.percentage / 100

    for block_height in range(now_block_height - target_block_num, now_block_height):
        print(f'Block height: {block_height}')
        # get block data
        block_hash = get_block_hash(substrate, block_height)
        previous_block_hash = get_block_hash(substrate, block_height - 1)
        block_author = substrate.get_block(block_hash, include_author=True)['author']
        print(f'block hash: {block_hash}, previous block hash: {previous_block_hash} block author: {block_author}')

        pot = get_account_balance(substrate, POT_ADDR, previous_block_hash)

        # Get staking info
        staking_info = {}
        info = substrate.query(
            module='ParachainStaking',
            storage_function='CandidatePool',
            params=[block_author],
            block_hash=block_hash,
        )
        staking_info[block_author] = info.value
        staking_info[block_author]['delegators'] = {
            delegator['owner']: delegator['amount']
            for delegator in info.value['delegators']
        }
        print(f'staking info: {staking_info}')

        # get block reward
        result = get_all_events(
            substrate,
            block_hash,
            'ParachainStaking', 'Rewarded')
        reward_info = {
            event.value['attributes'][0]: event.value['attributes'][1]
            for event in result
        }
        print(f'Block height: {block_height}, block author: {block_author}, reward info: {reward_info}, staking info: {staking_info}, pot: {pot}')

        # Check total
        total_reward = sum(reward_info.values())
        # Note float comparing
        if float(abs(total_reward - pot)) / pot > ALLOW_ERROR_PERCENTAGE:
            raise ValueError(f'Total reward is not equal to collator/delegator issuance {collator_delegator_issuance}, got {total_reward}')

        denominator = args.coefficient * \
            staking_info[block_author]['stake'] + \
            sum(staking_info[block_author]['delegators'].values())
        # Calculate the collator reward
        real_collator_reward = reward_info[block_author]
        target_collator_reward = collator_delegator_issuance * \
            float(args.coefficient) * staking_info[block_author]['stake'] / denominator
        if float(abs(real_collator_reward - target_collator_reward)) / target_collator_reward > ALLOW_ERROR_PERCENTAGE:
            raise ValueError(f'Collator reward is not equal to target reward {target_collator_reward}, got {real_collator_reward}')
        # Calculate the delegator reward
        for addr, value in reward_info.items():
            if addr == block_author:
                continue
            real_delegator_reward = value
            target_delegator_reward = collator_delegator_issuance * \
                float(staking_info[block_author]['delegators'][addr]) / denominator
            if float(abs(real_delegator_reward - target_delegator_reward)) / target_delegator_reward > ALLOW_ERROR_PERCENTAGE:
                raise ValueError(f'Delegator reward is not equal to target reward {target_delegator_reward}, got {real_delegator_reward}')
