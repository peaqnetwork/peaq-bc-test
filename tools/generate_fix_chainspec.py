import json
import argparse
import os

BLOCK_CODE = '13'

WASM_FILE = '/home/jaypan/PublicSMB/peaq-node-wasm/peaq_dev_runtime.compact.compressed.wasm.peaq-dev.v0.0.100.success'
DEV_CHAINSPEC = '/home/jaypan/Work/peaq/parachain-launch/yoyo/dev-local-2000.json'


def args_parser():
    parser = argparse.ArgumentParser(description='''
Generate chainspec file with updated wasm code
python3 generate_fix_chainspec.py \
    --wasm /home/jaypan/PublicSMB/peaq-node-wasm/peaq_dev_runtime.compact.compressed.wasm.peaq-dev.v0.0.100.success \
    --chainspec /home/jaypan/Work/peaq/parachain-launch/yoyo/dev-local-2000.json \
    --block_code 13
    ''', formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('--wasm', type=str, help='Path to the wasm file')
    parser.add_argument('--chainspec', type=str, help='Path to the chainspec file')
    parser.add_argument('--block_code', type=str, help='Block code to update')
    return parser.parse_args()


if __name__ == '__main__':
    args = args_parser()

    if not os.path.exists(args.wasm):
        raise FileNotFoundError(f'Wasm file not found: {args.wasm}')
    if not os.path.exists(args.chainspec):
        raise FileNotFoundError(f'Chainspec file not found: {args.chainspec}')

    with open(args.chainspec, 'r') as f:
        chainspec = json.load(f)

    with open(args.wasm, 'rb', buffering=0) as f:
        data = f.read()
    chainspec['codeSubstitutes'] = {}
    chainspec['codeSubstitutes'] = {
        f'{args.block_code}': f'0x{data.hex()}'
    }

    with open(DEV_CHAINSPEC, 'w') as f:
        json.dump(chainspec, f, indent=2)
