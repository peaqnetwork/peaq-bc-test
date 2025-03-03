import sys
sys.path.append('./')

import argparse
from substrateinterface import SubstrateInterface
from decimal import Decimal


def get_all_evm_tip_in_block(substrate, block_hash):
    block = substrate.get_block(block_hash)
    events = substrate.get_events(block_hash=block_hash)

    evm_all_tip = Decimal(0)
    evm_count = 0
    for idx, tx in enumerate(block['extrinsics']):
        if idx < 2:
            continue
        if tx.value['call']['call_module'] != 'Ethereum':
            continue
        evm_tip = Decimal(0)
        related_events = [
            event.value
            for event in events if 'extrinsic_idx' in event.value and event.value['extrinsic_idx'] == idx]
        if related_events[0]['module_id'] != 'Balances' or related_events[0]['event_id'] != 'Withdraw':
            raise IOError(f'    error: first event is not withdraw, {block_hash}, {idx}, {events[0]}')
        evm_tip = Decimal(related_events[0]['event']['attributes']['amount'])

        for event in related_events[1:]:
            if event['module_id'] != 'Balances' or event['event_id'] != 'Deposit':
                continue
            evm_tip -= Decimal(event['event']['attributes']['amount'])
        if evm_tip < 0:
            raise IOError(f'    error: evm_tip < 0, {evm_tip}, {block_hash}, {idx}')
        # print(f' tx tip found: {block_hash}-{idx}: fee {evm_tip}')
        evm_all_tip += evm_tip
        evm_count += 1
    return {
        'tip': evm_all_tip,
        'count': evm_count
    }


def get_all_evm_tx_fee_in_block(substrate, block_hash):
    block = substrate.get_block(block_hash)
    events = substrate.get_events(block_hash=block_hash)

    evm_total_tx_fee = Decimal(0)
    evm_count = 0
    for idx, tx in enumerate(block['extrinsics']):
        if idx < 2:
            continue
        if tx.value['call']['call_module'] != 'Ethereum':
            continue
        evm_tx_fee = Decimal(0)
        related_events = [
            event.value
            for event in events if 'extrinsic_idx' in event.value and event.value['extrinsic_idx'] == idx]
        if related_events[0]['module_id'] != 'Balances' or related_events[0]['event_id'] != 'Withdraw':
            raise IOError(f'    error: first event is not withdraw, {block_hash}, {idx}, {events[0]}')

        for event in related_events[1:]:
            if event['module_id'] != 'Balances' or event['event_id'] != 'Deposit':
                continue
            evm_tx_fee += Decimal(event['event']['attributes']['amount'])
        # print(f' tx fee found: {block_hash}-{idx}: fee {evm_tx_fee}')
        evm_total_tx_fee += evm_tx_fee
        evm_count += 1
    return {
        'fee': evm_total_tx_fee,
        'count': evm_count
    }


def get_all_evm_fee_tip_in_block(substrate, block_hash):
    fee = get_all_evm_tx_fee_in_block(substrate, block_hash)
    tip = get_all_evm_tip_in_block(substrate, block_hash)
    if fee['count'] != tip['count']:
        raise IOError(f'    error: fee count != tip count, {fee["count"]}, {tip["count"]}, {block_hash}')

    return {
        'fee': fee['fee'],
        'tip': tip['tip'],
        'count': fee['count']
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Fetch EVM tx fee')
    parser.add_argument('-r', '--runtime', type=str, required=True, help='Your runtime websocket endpoint')
    parser.add_argument('-p', '--period', type=int, required=True, help='Time period (seconds) to fetch')
    args = parser.parse_args()

    substrate = SubstrateInterface(
        url=args.runtime,
    )
    now_block_number = substrate.get_block_number(None)
    out = {
        'fee': Decimal(0),
        'tip': Decimal(0),
        'count': 0
    }
    for block_idx in range(int(args.period / 6)):
        block_hash = substrate.get_block_hash(now_block_number - block_idx)
        # print(f'block idx: {now_block_number - block_idx}, block hash: {block_hash}')
        data = get_all_evm_fee_tip_in_block(substrate, block_hash)
        print(f'remain: {int(args.period / 6) - block_idx}: block idx: {now_block_number - block_idx}: '
              f'fee: {data["fee"] / 10**18}, tip: {data["tip"] / 10**18}, count: {data["count"]}')

        out['fee'] += data['fee']
        out['tip'] += data['tip']
        out['count'] += data['count']
    print('======================')
    print(f'fee: {out["fee"] / 10**18}, tip: {out["tip"] / 10**18}, count: {out["count"]}')
