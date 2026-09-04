#!/usr/bin/env python3
"""Pinned historical eth_call/estimateGas probe (RPC-1 QA gap).

After a runtime upgrade (e.g. spec 110 -> 112) the node must still serve
read RPCs pinned at PRE-upgrade blocks: the client resolves the
EthereumRuntimeRPCApi version *at that block* and calls into the OLD wasm.
This probe exercises exactly that path: eth_call / eth_estimateGas /
eth_getBalance / eth_getStorageAt / eth_getCode with an explicit historical
block parameter, plus the same set at latest for comparison.

Usage (local upgraded chain or agung right after the real upgrade):
  PYTHONUNBUFFERED=1 python3 tools/historical_call_probe.py \
      --eth-url http://127.0.0.1:10044 --ws-url ws://127.0.0.1:10044 \
      [--pre-block N] [--contract 0x.. --data 0x..] [--account 0x..]

Without --pre-block it auto-detects the upgrade boundary by binary-searching
specVersion over the chain history and probes the LAST pre-upgrade block.
Exit code 0 = all PASS, 1 = any FAIL (a FAIL means the node cannot serve
that RPC pinned at a pre-upgrade block — the exact regression this guards).
"""
import argparse
import sys

from substrateinterface import SubstrateInterface
from web3 import Web3

DEAD_BEEF = '0x000000000000000000000000000000000000dEaD'


def spec_at(si, number):
    block_hash = si.get_block_hash(number)
    return si.rpc_request('state_getRuntimeVersion', [block_hash])['result']['specVersion']


def find_last_pre_upgrade_block(si):
    """Binary-search the first block whose specVersion differs from block 1's."""
    head = si.get_block()['header']['number']
    spec_lo, spec_hi = spec_at(si, 1), spec_at(si, head)
    if spec_lo == spec_hi:
        return None, spec_lo, spec_hi
    lo, hi = 1, head  # invariant: spec(lo)==spec_lo, spec(hi)!=spec_lo
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if spec_at(si, mid) == spec_lo:
            lo = mid
        else:
            hi = mid
    return lo, spec_lo, spec_hi


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--eth-url', required=True)
    ap.add_argument('--ws-url', help='substrate ws url; needed unless --pre-block given')
    ap.add_argument('--pre-block', type=int, help='a block number known to be pre-upgrade')
    ap.add_argument('--account', default=DEAD_BEEF, help='eth address for balance/call probes')
    ap.add_argument('--contract', help='optional contract address for a real eth_call')
    ap.add_argument('--data', default='0x', help='calldata for --contract (e.g. balanceOf(...))')
    args = ap.parse_args()

    w3 = Web3(Web3.HTTPProvider(args.eth_url))
    acct = Web3.to_checksum_address(args.account)

    pre = args.pre_block
    if pre is None:
        if not args.ws_url:
            ap.error('need --pre-block or --ws-url (for auto-detect)')
        si = SubstrateInterface(url=args.ws_url)
        pre, spec_old, spec_new = find_last_pre_upgrade_block(si)
        if pre is None:
            print(f'[!] no upgrade boundary found (specVersion {spec_old} across whole chain) '
                  f'— this chain has no pre-upgrade history; nothing to probe')
            return 1
        print(f'[i] upgrade boundary auto-detected: last pre-upgrade block #{pre} '
              f'(spec {spec_old} -> {spec_new})')

    latest = w3.eth.block_number
    print(f'[i] probing pinned block #{pre} vs latest #{latest}\n')

    results = []

    def check(name, fn):
        try:
            value = fn()
            results.append((name, 'PASS', repr(value)[:60]))
        except Exception as exc:  # any RPC failure IS the finding this probe exists for
            results.append((name, 'FAIL', f'{type(exc).__name__}: {exc}'[:110]))

    for label, blk in (('@pre', pre), ('@latest', 'latest')):
        check(f'eth_getBalance      {label}', lambda b=blk: w3.eth.get_balance(acct, block_identifier=b))
        check(f'eth_getCode         {label}', lambda b=blk: w3.eth.get_code(acct, block_identifier=b))
        check(f'eth_getStorageAt    {label}', lambda b=blk: w3.eth.get_storage_at(acct, 0, block_identifier=b))
        # exercises EthereumRuntimeRPCApi::call against that block's (old) wasm
        check(f'eth_call (EOA)      {label}', lambda b=blk: w3.eth.call(
            {'from': acct, 'to': acct, 'value': 0}, block_identifier=b))
        check(f'eth_estimateGas     {label}', lambda b=blk: w3.eth.estimate_gas(
            {'from': acct, 'to': acct, 'value': 0}, block_identifier=b))
        if args.contract:
            check(f'eth_call (contract) {label}', lambda b=blk: w3.eth.call(
                {'to': Web3.to_checksum_address(args.contract), 'data': args.data},
                block_identifier=b))

    width = max(len(n) for n, _, _ in results)
    failed = 0
    for name, status, detail in results:
        mark = '✅' if status == 'PASS' else '❌'
        failed += status == 'FAIL'
        print(f'{mark} {name.ljust(width)}  {status}  {detail}')
    print(f'\n{len(results) - failed}/{len(results)} passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
