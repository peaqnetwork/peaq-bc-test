import sys
sys.path.append('./')


from substrateinterface import SubstrateInterface
from peaq.utils import get_block_height, get_block_hash
from peaq.utils import get_account_balance
from tools.utils import PARACHAIN_STAKING_POT
from tools.utils import get_existential_deposit
import argparse
# from collections import Counter
import pprint
pp = pprint.PrettyPrinter(indent=4)


def get_pervious_session_block(substrate):
    round_info = substrate.query(
        'ParachainStaking',
        'Round',
    )
    return (round_info['first'].value, round_info['length'].value, round_info['current'].value)


def traverse_single_blocks_and_check(substrate, session_height, round_length, session_idx):
    print(f'Check session block: {session_height}')
    print(f'Session idx: {session_idx}')

    check_data = {}
    end_block_height = session_height + round_length
    # We don't check the latest block because we also distirbute the rewrd at the new session block
    for i in range(session_height + 1, end_block_height):
        # print(f'get author in block height: {i}, session idx: {session_idx}')
        block_hash = get_block_hash(substrate, i)
        block_info = substrate.get_block(block_hash, include_author=True)
        # print(f'block author: {block_info["author"]}')
        # print(f'CollatorBlock: {result}')
        check_data[block_info['author']] = check_data.get(block_info["author"], 0) + 1
        result = substrate.query(
            module='ParachainStaking',
            storage_function='CollatorBlocks',
            params=[session_idx, block_info['author']],
            block_hash=block_hash,
        )
        if result != check_data[block_info["author"]]:
            raise IOError(f'    error: {block_info["author"]}: CollatorBlock: {result} v.s. {check_data.get(block_info["author"], 0)}')
    print(f'End block: {end_block_height}, session: {session_idx}, contributed collators length: {len(check_data.keys())}')


def travese_blocks_and_check(substrate, test_session_num):
    session_block_height, session_block_length, session_idx = get_pervious_session_block(substrate)

    for i in range(test_session_num):
        prev_session_block_height = session_block_height - session_block_length * (i + 1)
        if prev_session_block_height < 0:
            print(f'End traverse for prev {i}th session because of block height < 0')
            break
        print(f'Check session block: {prev_session_block_height}')
        traverse_single_blocks_and_check(substrate, prev_session_block_height, session_block_length, session_idx - i - 1)


def validator_check(substrate, test_session_num):
    check_data = {}
    session_block_height, session_block_length, session_idx = get_pervious_session_block(substrate)

    now_block_height = get_block_height(substrate)
    block_hash = get_block_hash(substrate, now_block_height)
    print(f'get author in block height: {now_block_height}')
    print(f'block hash: {block_hash}')

    validators = substrate.query(
        module='Session',
        storage_function='Validators',
        block_hash=block_hash,
    )

    check_data = {}
    for validator in validators:
        result = substrate.query(
            module='ParachainStaking',
            storage_function='CollatorBlock',
            params=[validator.value],
            block_hash=block_hash,
        )
        if result.value != 0:
            check_data[validator.value] = result.value
        else:
            print(f'{validator} not in CollatorBlock')

    pp.pprint(check_data)
    print(f'End block: {now_block_height}, total length: {len(check_data.keys())}')


def calculate_collator_block_info(substrate, session_height):
    session_block_hash = get_block_hash(substrate, session_height - 1)

    # Get the collator blocks
    validators = substrate.query(
        module='Session',
        storage_function='Validators',
        block_hash=session_block_hash,
    )
    collator_block_info = {}
    for validator in validators:
        result = substrate.query(
            module='ParachainStaking',
            storage_function='CollatorBlock',
            params=[validator.value],
            block_hash=session_block_hash,
        )
        collator_block_info[validator.value] = result.value

    # Remebmer to add the session block author
    session_block_hash = get_block_hash(substrate, session_height)
    block_author = substrate.get_block(session_block_hash, include_author=True)['author']
    collator_block_info[block_author] = collator_block_info.get(block_author, 0) + 1
    return collator_block_info


def get_staking_info(substrate, session_block_hash, collator_block_info):
    # Store all staking info
    staking_info = {}
    # import pdb
    # pdb.set_trace()
    for collator_addr, _ in collator_block_info.items():
        staking_out = substrate.query(
            module='ParachainStaking',
            storage_function='CandidatePool',
            params=[collator_addr],
            block_hash=session_block_hash,
        )
        staking_info[collator_addr] = staking_out
    return staking_info


def caculate_total_staking(staking_info, collator_block_info):
    total_staking = 0
    for collator_addr, collator_stake_info in staking_info.items():
        block_generated_num = collator_block_info[collator_addr]
        total_staking += block_generated_num * collator_stake_info['stake'].value
        for delegator_info in collator_stake_info['delegators']:
            total_staking += block_generated_num * delegator_info['amount']
    return total_staking


def get_pot_balance(substrate, session_height):
    # Get pot balance
    prev_height = session_height - 1
    prev_block_hash = get_block_hash(substrate, prev_height)

    pot_transferable_balance = \
        get_account_balance(substrate, PARACHAIN_STAKING_POT, prev_block_hash) - \
        get_existential_deposit(substrate)
    return pot_transferable_balance


def get_reward_info(substrate, session_block_hash):
    # Get all the reward
    reward_info = {}
    for event in substrate.get_events(session_block_hash):
        if event.value['module_id'] != 'ParachainStaking' or \
           event.value['event_id'] != 'Rewarded':
            continue
        reward_info[event['event'][1][1][0].value] = event['event'][1][1][1].value
    return reward_info


def distribution_check(substrate, args):
    session_height = args.session
    session_block_hash = get_block_hash(substrate, session_height)

    collator_block_info = calculate_collator_block_info(substrate, session_height - 1)
    staking_info = get_staking_info(substrate, session_block_hash, collator_block_info)
    total_staking = caculate_total_staking(staking_info, collator_block_info)
    pot_transferable_balance = get_pot_balance(substrate, session_height)

    reward_info = get_reward_info(substrate, session_block_hash)

    # Check all collator reward in collators
    for collator_addr, info in staking_info.items():
        # Check collator
        block_generated_num = collator_block_info[collator_addr]
        if block_generated_num == 0:
            continue
        print(f'collator: {collator_addr}, block_generated_num: {block_generated_num}')
        print(f'collator: {collator_addr}, stake: {info["stake"].value}')
        print(f'collator: {collator_addr}, total_staking: {total_staking}')
        print(f'collator: {collator_addr}, pot_transferable_balance: {pot_transferable_balance}')
        collator_reward = float(block_generated_num * info['stake'].value) / float(total_staking) * pot_transferable_balance
        # amost equal
        if abs(collator_reward - reward_info[collator_addr]) > 0.0000001 * collator_reward:
            print(f'    error: collator: {collator_addr},'
                  f'reward: {collator_reward} v.s. {reward_info[collator_addr]}')

        # # Check delegators
        # for delegator in info['delegators']:
        #     delegator_reward = float(block_generated_num * delegator['amount']) / float(total_staking) * pot_transferable_balance
        #     if abs(delegator_reward - reward_info[delegator['owner']]) > 0.0000001 * delegator_reward:
        #         print(f'    error: delegator: {delegator["owner"]},'
        #               f'reward: {delegator_reward} v.s. {reward_info[delegator["owner"]]}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Get storage and constants from a Substrate chain')
    parser.add_argument('-r', '--runtime', type=str, required=True, help='Your runtime websocket endpoint')
    parser.add_argument('-s', '--session', type=int, required=False, help='session block blockheight, needed on traverse mode and distribution')
    parser.add_argument('--test-session-num', type=int, required=False, default=10, help='test session number')
    parser.add_argument(
        '-t', '--type', choices=['traverse', 'validator', 'distribution'], required=True,
        help='Specify the type, '
             'traverse: traverse check, from session block to now block,'
             'validator: check validator,'
             'distribution: check distribution')

    args = parser.parse_args()

    substrate = SubstrateInterface(
        url=args.runtime,
    )

    if args.type == 'traverse':
        test_session_num = args.test_session_num
        travese_blocks_and_check(substrate, test_session_num)
    elif args.type == 'validator':
        test_session_num = args.test_session_num
        validator_check(substrate, test_session_num)
    elif args.type == 'distribution':
        if args.session is None:
            print('Please specify session block blockheight')
            sys.exit(1)
        distribution_check(substrate, args)
