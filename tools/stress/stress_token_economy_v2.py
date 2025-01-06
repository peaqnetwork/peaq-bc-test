import sys
sys.path.append('./')


from substrateinterface import SubstrateInterface
from peaq.utils import get_block_hash
from peaq.utils import get_account_balance
from tools.utils import PARACHAIN_STAKING_POT
from tools.utils import get_existential_deposit
from decimal import Decimal
import argparse
# from collections import Counter
import pprint
pp = pprint.PrettyPrinter(indent=4)

DEBUG = False

COLLATOR_POT = '5EYCAe5cKPAoFh2HnQQvpKqRYZGqBpaA87u4Zzw89qPE58is'
PERCISION_ERROR = 0.000001


def get_pervious_session_block(substrate, test_session_num):
    out = []
    now_block_hash = substrate.get_block_hash()
    round_info = substrate.query(
        'ParachainStaking',
        'Round',
        block_hash=now_block_hash,
    )
    if round_info['first'].value == 0:
        print('End traverse because of first round')
        raise IOError('End traverse because of first round')

    new_session_height = round_info['first'].value
    block_hash = get_block_hash(substrate, round_info['first'].value - 1)
    for i in range(test_session_num):
        round_info = substrate.query(
            'ParachainStaking',
            'Round',
            block_hash=block_hash,
        )
        if round_info['first'].value == 0:
            print(f'End traverse for prev {i}th session because of first round')
            break
        print(f'first: {round_info["first"].value},'
              f'length: {new_session_height - round_info["first"].value}',
              f'current: {round_info["current"].value}')

        out.append((round_info['first'].value, new_session_height - round_info['first'].value, round_info['current'].value))
        new_session_height = round_info['first'].value
        block_hash = get_block_hash(substrate, round_info['first'].value - 1)
    return out


def traverse_single_blocks_and_check(substrate, session_height, round_length, session_idx):
    print(f'Check session block: {session_height}, session idx: {session_idx}, round length: {round_length}')

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
        if i % 100 == 0:
            print(f'during block: {i}, author: {block_info["author"]}, checked')
        if result != check_data[block_info["author"]]:
            raise IOError(f'    error: {block_info["author"]}: CollatorBlock: {result} v.s. {check_data.get(block_info["author"], 0)}')
    print(f'End block: {end_block_height}, session: {session_idx}, contributed collators length: {len(check_data.keys())}')


def travese_blocks_and_check(substrate, test_session_num):
    session_infos = get_pervious_session_block(substrate, test_session_num)

    for prev_session_block_height, session_block_length, session_idx in session_infos:
        print(f'Check session block: {prev_session_block_height}')
        traverse_single_blocks_and_check(substrate, prev_session_block_height, session_block_length, session_idx)


def check_single_session_collators(substrate, session_height, round_length, session_idx):
    block_hash = get_block_hash(substrate, session_height)
    now_collators = substrate.query(
        module='Session',
        storage_function='Validators',
        block_hash=block_hash,
    )
    now_collator_set = set(now_collators.value)

    end_block_height = session_height + round_length
    block_hash = get_block_hash(substrate, end_block_height - 1)
    all_colators_info = substrate.query_map(
        module='ParachainStaking',
        storage_function='CollatorBlocks',
        params=[session_idx],
        block_hash=block_hash,
        start_key=None,
        page_size=1000,
    )
    collators_block_set = set([addr.value for addr, _ in all_colators_info.records])
    if not collators_block_set.issubset(now_collator_set):
        for collator in collators_block_set:
            if collator not in now_collator_set:
                print(f'    error: collator: {collator} not in session block')
        raise IOError(f'    error: collators in session block: {now_collator_set} v.s. collators in collator block: {collators_block_set}')


def collator_check(substrate, test_session_num):
    session_infos = get_pervious_session_block(substrate, test_session_num)

    for prev_session_block_height, session_block_length, session_idx in session_infos:
        print(f'Check session block: {prev_session_block_height}')
        check_single_session_collators(substrate, prev_session_block_height, session_block_length, session_idx)


def calculate_block_reward(substrate, block_height):
    now_block_hash = get_block_hash(substrate, block_height)
    tx_fee = get_all_deposits_to_pot(substrate, now_block_hash)
    print(f'block: {block_height}, tx fee: {tx_fee/10**18}')
    return tx_fee


def get_all_distribution_to_collator_delegator_in_block(substrate, block_hash):
    events = substrate.get_events(block_hash=block_hash)

    distribution = Decimal(0)
    for event in events:
        if event.value['module_id'] != 'ParachainStaking' or event.value['event_id'] != 'Rewarded':
            continue
        distribution += Decimal(event.value['event']['attributes'][1])
    return distribution


def calculate_pot_balance(substrate, block_height):
    prev_block_hash = get_block_hash(substrate, block_height - 1)

    prev_block_pot_balance = get_account_balance(substrate, PARACHAIN_STAKING_POT, prev_block_hash)
    now_block_hash = get_block_hash(substrate, block_height)
    now_block_pot_balance = get_account_balance(substrate, PARACHAIN_STAKING_POT, now_block_hash)
    print(f'block: {block_height}, pot balance: {now_block_pot_balance/10**18}, prev pot balance: {prev_block_pot_balance/10**18}')
    distribution = get_all_distribution_to_collator_delegator_in_block(substrate, now_block_hash)
    return Decimal(now_block_pot_balance) - Decimal(prev_block_pot_balance) + Decimal(distribution)


def block_check(substrate, test_num):
    now_block_height = substrate.get_block_number(None)
    for block_height in range(now_block_height - test_num, now_block_height):
        cal_block_reward = calculate_block_reward(substrate, block_height)
        pot_balance = calculate_pot_balance(substrate, block_height)
        print(f'block: {block_height}, reward: {cal_block_reward/10**18}, pot balance: {pot_balance/10**18}')
        print(f'error: {(cal_block_reward - pot_balance) / 10**18}')
        if (cal_block_reward - pot_balance) > Decimal(PERCISION_ERROR) * cal_block_reward:
            raise IOError(f'    error: block: {block_height}, reward: {cal_block_reward}, pot balance: {pot_balance}')


def calculate_collator_block_info(substrate, session_height, round_length, session_idx):
    session_block_hash = get_block_hash(substrate, session_height + round_length - 1)

    collator_blocks = substrate.query_map(
        module='ParachainStaking',
        storage_function='CollatorBlocks',
        params=[session_idx],
        block_hash=session_block_hash,
        start_key=None,
        page_size=1000,
    )
    collator_blocks = {addr.value: info.value for addr, info in collator_blocks.records}

    # Remebmer to add the session block author
    session_block_hash = get_block_hash(substrate, session_height + round_length)
    block_author = substrate.get_block(session_block_hash, include_author=True)['author']
    collator_blocks[block_author] = collator_blocks.get(block_author, 0) + 1
    return collator_blocks


def get_snapshot_info(substrate, session_block_hash, session_idx):
    snapshot = substrate.query_map(
        module='ParachainStaking',
        storage_function='AtStake',
        params=[session_idx],
        block_hash=session_block_hash,
        start_key=None,
        page_size=1000,
    )
    return {addr.value: info.value for addr, info in snapshot.records}


def calculate_total_staking_ratio(staking_info, collator_block_info):
    total_staking_num = caculate_total_staking_num(staking_info, collator_block_info)
    total_staking_ratio = {}

    for collator_addr, collator_stake_info in staking_info.items():
        staking_ratio = {}
        if collator_addr not in collator_block_info:
            continue
        block_generated_num = Decimal(collator_block_info[collator_addr])
        commission = Decimal(collator_stake_info['commission']) / Decimal(10 ** 6)

        staking_ratio[collator_addr] = \
            block_generated_num * Decimal(collator_stake_info['stake']) / total_staking_num \
            + sum([
                block_generated_num * commission * Decimal(delegator_info['amount']) / total_staking_num
                for delegator_info in collator_stake_info['delegators']
            ])
        for delegator_info in collator_stake_info['delegators']:
            staking_ratio[delegator_info['owner']] = \
                block_generated_num * (1 - commission) * Decimal(delegator_info['amount']) / total_staking_num
        total_staking_ratio[collator_addr] = staking_ratio

    return total_staking_ratio


def caculate_total_staking_num(staking_info, collator_block_info):
    total_staking_num = Decimal(0)
    for collator_addr, collator_stake_info in staking_info.items():
        if collator_addr not in collator_block_info:
            continue
        block_generated_num = collator_block_info[collator_addr]
        total_staking_num += Decimal(block_generated_num) * Decimal(collator_stake_info['stake'])
        for delegator_info in collator_stake_info['delegators']:
            total_staking_num += Decimal(block_generated_num) * Decimal(delegator_info['amount'])
    return total_staking_num


def get_block_reward(substrate, block_hash):

    reward_info = substrate.query(
        module='InflationManager',
        storage_function='BlockRewards',
        block_hash=block_hash,
    )
    return reward_info.value


def get_reward_config_info(substrate, session_block_hash):
    reward_config = substrate.query(
        module='BlockReward',
        storage_function='RewardDistributionConfigStorage',
        block_hash=session_block_hash,
    )
    return (Decimal(reward_config['collators_delegators_percent'].decode()) / 10 ** 7) / 100


def get_all_tip_reward_in_block(substrate, block_hash):
    block = substrate.get_block(block_hash)
    events = substrate.get_events(block_hash=block_hash)

    tx_fee = Decimal(0)
    for idx, tx in enumerate(block['extrinsics']):
        if idx < 2:
            continue
        related_events = [
            event.value
            for event in events if 'extrinsic_idx' in event.value and event.value['extrinsic_idx'] == idx]
        if related_events[0]['module_id'] != 'Balances' or related_events[0]['event_id'] != 'Withdraw':
            raise IOError(f'    error: first event is not withdraw, {block_hash}, {idx}, {events[0]}')
        deposit_event = related_events[0]
        deposit_user = deposit_event['event']['attributes']['who']
        deposit_value = Decimal(deposit_event['event']['attributes']['amount'])

        for event in related_events[1:]:
            if event['module_id'] != 'Balances' or event['event_id'] != 'Deposit':
                continue
            if deposit_user != event['event']['attributes']['who']:
                continue
            deposit_value -= Decimal(event['event']['attributes']['amount'])
        if deposit_value < 0:
            raise IOError(f'    error: deposit_value < 0, {deposit_value}, {deposit_user}, {block_hash}, {idx}')
        print(f' tx found: {block_hash}-{idx}: fee {deposit_value}')
        tx_fee += deposit_value
    return tx_fee


def get_all_tx_fee_in_block(substrate, block_hash):
    deposit = 0
    block_reward = True
    for event in substrate.get_events(block_hash=block_hash):
        if event.value['module_id'] != 'Balances' or event.value['event_id'] != 'Deposit':
            continue
        if event.value['event']['attributes']['who'] != COLLATOR_POT:
            continue
        if block_reward:
            block_reward = False
            print(f'block_reward found: {block_hash}, {event.value["event"]["attributes"]["amount"] / 10 ** 18}')
        else:
            print(f'fee found: {block_hash}, {event.value["event"]["attributes"]["amount"] / 10 ** 18}')
        deposit += Decimal(event.value['event']['attributes']['amount'])
    print(f'block: {block_hash}, deposit: {deposit}')
    return deposit


def get_all_transaction_fee_in_block(substrate, block_hash):
    tip = get_all_tip_reward_in_block(substrate, block_hash)
    tx_fee = get_all_tx_fee_in_block(substrate, block_hash)
    return tip + tx_fee


def get_all_deposits_to_pot(substrate, block_hash):
    deposit = 0
    block_reward = True
    for event in substrate.get_events(block_hash=block_hash):
        if event.value['module_id'] != 'Balances' or event.value['event_id'] != 'Deposit':
            continue
        if event.value['event']['attributes']['who'] != COLLATOR_POT:
            continue
        if block_reward:
            block_reward = False
            print(f'block_reward found: {block_hash}, {event.value["event"]["attributes"]["amount"] / 10 ** 18}')
        else:
            print(f'fee found: {block_hash}, {event.value["event"]["attributes"]["amount"] / 10 ** 18}')
        deposit += Decimal(event.value['event']['attributes']['amount'])
    print(f'block: {block_hash}, deposit: {deposit}')
    return deposit


def get_total_session_rewards(substrate, session_height, round_length):
    # Now we are using the event in block to get the block + transaction reward
    # [TODO] However, we should check EVM/Blockreward/Substrate fee's stress tool

    deposit = Decimal(0)
    # We don include the latest block because we also distribute the reward at the new session block
    for block_idx in range(session_height, session_height + round_length):
        if block_idx % 100 == 0:
            print(f'get tx fee in block: {block_idx}')
        block_hash = get_block_hash(substrate, block_idx)
        this_deposit = get_all_deposits_to_pot(substrate, block_hash)
        deposit += this_deposit
        if DEBUG:
            print(f'block: {block_idx}, tx fee: {this_deposit / 10 ** 18}')
    print(f'total deposit: {deposit}')

    return deposit


def get_pot_balance(substrate, session_height, round_length):
    # Get pot balance
    prev_height = session_height + round_length - 1
    prev_block_hash = get_block_hash(substrate, prev_height)

    pot_transferable_balance = \
        get_account_balance(substrate, PARACHAIN_STAKING_POT, prev_block_hash) - \
        get_existential_deposit(substrate)

    return pot_transferable_balance


def get_reward_info(substrate, payout_session_height, round_length):
    all_reward_info = {}
    collator_addr = None
    for block_idx in range(payout_session_height, payout_session_height + round_length):
        reward_info = {}
        block_hash = get_block_hash(substrate, block_idx)
        for event in substrate.get_events(block_hash):
            if event.value['module_id'] != 'ParachainStaking' or \
               event.value['event_id'] != 'Rewarded':
                continue
            if collator_addr is None:
                collator_addr = event['event'][1][1][0].value
            reward_info[event['event'][1][1][0].value] = Decimal(event['event'][1][1][1].value)
        if not reward_info:
            break
        all_reward_info[block_idx] = {
            'reward': reward_info,
            'collator': collator_addr,
        }
        collator_addr = None
    return all_reward_info


def calculate_reward(total_session_reward, snapshot_info, collator_block_info):
    total_reward_info = {}
    total_staking_ratio = calculate_total_staking_ratio(snapshot_info, collator_block_info)
    for collator_addr, ratio_info in total_staking_ratio.items():
        reward_info = {}
        for addr, ratio in ratio_info.items():
            reward_info[addr] = ratio * total_session_reward
        total_reward_info[collator_addr] = reward_info
    return total_reward_info


def check_reward(total_session_reward, distributed_reward_info, calculated_reward_info):
    distribute_reward = 0
    for block_idx, block_reward_info in distributed_reward_info.items():
        reward_info = block_reward_info['reward']
        for addr, reward in reward_info.items():
            distribute_reward += reward
    if abs(distribute_reward - total_session_reward) > Decimal(0.0001) * total_session_reward:
        print(f' error: {(distribute_reward - total_session_reward) / total_session_reward}')
        raise IOError(
            f'    error: distribute_reward: {distribute_reward} v.s. total_session_reward: {total_session_reward}')

    for block_idx, block_reward_info in distributed_reward_info.items():
        collator_addr = block_reward_info['collator']
        reward_info = block_reward_info['reward']
        for addr, reward in reward_info.items():
            if abs(reward - calculated_reward_info[collator_addr][addr]) > Decimal(0.0001) * reward:
                raise IOError(f'    error: block_idx: {block_idx},'
                              f'reward: {reward} v.s. {calculated_reward_info[collator_addr][addr]}')


def check_single_session_distribution(substrate, session_height, round_length, session_idx):
    print(f'Check session block: {session_height}, session idx: {session_idx}, round length: {round_length}')
    session_block_hash = get_block_hash(substrate, session_height)

    collator_block_info = calculate_collator_block_info(substrate, session_height, round_length, session_idx)
    if DEBUG:
        print('collator_block_info')
        pp.pprint(collator_block_info)
    if round_length != sum(collator_block_info.values()):
        raise IOError(f'    error: round_length: {round_length} v.s. collator block length: {sum(collator_block_info.values())}')

    # Because we might change, we have to use the snapshot data
    # [TODO] We have to test the snapshot data
    snapshot_info = get_snapshot_info(substrate, session_block_hash, session_idx)
    if DEBUG:
        print('snapshot_info')
        pp.pprint(snapshot_info)

    # [TODO] Check totalIssuance
    # Caculate the pot balance
    # [TODO] We have to test the pot balance
    total_session_reward = get_total_session_rewards(substrate, session_height, round_length)
    # {blockheight: {collator: reward, delegator1: reward, delegator2: reward}}
    distributed_reward_info = get_reward_info(substrate, session_height + round_length, round_length)
    if DEBUG:
        print('distributed_reward_info')
        pp.pprint(distributed_reward_info)

    if len(distributed_reward_info.keys()) != len(collator_block_info.keys()):
        raise IOError(
            f'    error: collator length: {len(collator_block_info.keys())} '
            f'v.s. distributed reward length: {len(distributed_reward_info.keys())}')

    calculated_reward_info = calculate_reward(total_session_reward, snapshot_info, collator_block_info)
    check_reward(total_session_reward, distributed_reward_info, calculated_reward_info)


def distribution_check(substrate, test_session_num):
    session_infos = get_pervious_session_block(substrate, test_session_num)

    for prev_session_block_height, session_block_length, session_idx in session_infos:
        print(f'Check session block: {prev_session_block_height}')
        check_single_session_distribution(substrate, prev_session_block_height, session_block_length, session_idx)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Get storage and constants from a Substrate chain')
    parser.add_argument('-r', '--runtime', type=str, required=True, help='Your runtime websocket endpoint')
    parser.add_argument('-s', '--session', type=int, required=False, help='session block blockheight, needed on traverse mode and distribution')
    parser.add_argument('--test-session-num', type=int, required=False, default=10, help='test session number')
    parser.add_argument(
        '-t', '--type', choices=['traverse', 'collator', 'distribution', 'block'], required=True,
        help='Specify the type, '
             'traverse: traverse check, from session block to now block,'
             'collator: check collator,'
             'block: check block reward,'
             'distribution: check distribution')

    args = parser.parse_args()

    substrate = SubstrateInterface(
        url=args.runtime,
    )
    test_session_num = args.test_session_num

    if args.type == 'traverse':
        travese_blocks_and_check(substrate, test_session_num)
    elif args.type == 'collator':
        collator_check(substrate, test_session_num)
    elif args.type == 'block':
        block_check(substrate, test_session_num)
    elif args.type == 'distribution':
        distribution_check(substrate, test_session_num)
