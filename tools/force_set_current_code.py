import sys
sys.path.append('./')

# import time
import os
from substrateinterface import SubstrateInterface
from tools.constants import KP_GLOBAL_SUDO, RELAYCHAIN_WS_URL
from peaq.utils import ExtrinsicBatch

import argparse


def args_parse():
    parser = argparse.ArgumentParser(description='''Force set current code for parachain
python3 force_set_current_code.py \
    --file /home/jaypan/PublicSMB/peaq-node-wasm/peaq_dev_runtime.compact.compressed.wasm.peaq-dev.v0.0.100.success \
    --para 2000
    ''', formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('--file', type=str, help='The file path of the code to be set')
    parser.add_argument('--para', type=int, help='The parachain id')
    args = parser.parse_args()
    return args


if __name__ == '__main__':

    args = args_parse()
    if not os.path.exists(args.file):
        print(f'File not found: {args.file}')
        sys.exit(1)

    substrate = SubstrateInterface(
        url=RELAYCHAIN_WS_URL,
        type_registry_preset='rococo'
    )

    block_num = substrate.get_block(None)['header']['number']

    with open(args.file, 'rb', buffering=0) as f:
        data = f.read()
    file_hash = f'0x{data.hex()}'

    batch = ExtrinsicBatch(substrate, KP_GLOBAL_SUDO)
    batch.compose_sudo_call(
        'Paras',
        'force_set_current_code',
        {'para': args.para, 'new_code': data}
    )
    receipt = batch.execute()
    print(f'receipt is success: {receipt.is_success}')

    # target_block_num = block_num + 10
    # batch = ExtrinsicBatch(substrate, KP_GLOBAL_SUDO)
    # batch.compose_sudo_call(
    #     'Paras',
    #     'force_schedule_code_upgrade',
    #     {'para': args.para, 'new_code': file_hash, 'relay_parent_number': target_block_num}
    # )
    # receipt = batch.execute()
    # print(f'receipt is success: {receipt.is_success}')
    # while True:
    #     block_num = substrate.get_block(None)['header']['number']
    #     print(f'current block number: {block_num} and wait for block_num: {target_block_num}')
    #     if block_num >= target_block_num:
    #         break
    #     time.sleep(6)
    # print('done')
