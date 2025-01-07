import sys
sys.path.append('./')

import argparse
from substrateinterface import SubstrateInterface
from peaq.utils import get_block_hash
from peaq.utils import get_block_height


def get_runtime_version(substrate, block_number):
    block_hash = get_block_hash(substrate, block_number)
    return substrate.get_block_runtime_version(block_hash)['specVersion']


def find_first_occurrence(substrate, version):
    # Binary search for the block number,
    low = 1
    high = get_block_height(substrate)
    result = 0
    while low < high:
        mid = (low + high) // 2
        value = get_runtime_version(substrate, mid)
        # 0: equal, 1: mid > version, -1: mid < version
        if value == version:
            result = mid
            high = mid - 1
            print(f'Found runtime version {version} at block number {mid}')
        elif value < version:
            print(f'Runtime version {version} is already reached at block number {mid}')
            low = mid + 1
        else:
            high = mid - 1
            print(f'Runtime version {version} is not reached yet at block number {mid}')
    return result + 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Get storage and constants from a Substrate chain')
    parser.add_argument('-r', '--runtime', type=str, required=True, help='Your runtime websocket endpoint')
    parser.add_argument('-v', '--version', type=int, required=True, help='The runtime version you want to check')
    args = parser.parse_args()

    substrate = SubstrateInterface(
        url=args.runtime,
    )

    runtime_version = args.version
    print(f'Block number for runtime version {runtime_version}: {find_first_occurrence(substrate, runtime_version)}')
