import sys
sys.path.append('./')

from substrateinterface import SubstrateInterface
import datetime


if __name__ == '__main__':
    URL = 'ws://127.0.0.1:10044'
    substrate = SubstrateInterface(url=URL)

    now_block_num = substrate.get_block_number(None)
    block_hash = substrate.get_block_hash(now_block_num)
    block_info = substrate.get_block(block_hash, include_author=True)
    for extrinsic in block_info['extrinsics']:
        if extrinsic.value['call']['call_module'] != 'Timestamp':
            continue
        if extrinsic.value['call']['call_function'] != 'set':
            continue
        timestamp = extrinsic.value['call']['call_args'][0]['value']
        # Convert time stamp to human readable format
        human_readable_time = datetime.datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S')
        print(human_readable_time)
