#!/usr/bin/env python3

import sys
sys.path.append('.')

from tools.constants import CORETIME_CORES, CORETIME_DURATION
from tools.coretime_utils import get_parachain_id, setup_coretime
import argparse


def main():
    parser = argparse.ArgumentParser(description='Setup coretime for parachain')
    parser.add_argument('--cores', type=int, default=CORETIME_CORES, help=f'Number of cores to assign (default: {CORETIME_CORES})')
    parser.add_argument('--duration', type=int, default=CORETIME_DURATION, help=f'Duration for coretime assignment (default: {CORETIME_DURATION})')
    parser.add_argument('--relay-url', type=str, default='ws://127.0.0.1:9944', help='Relay chain URL (default: ws://127.0.0.1:9944)')
    parser.add_argument('--parachain-url', type=str, default='ws://127.0.0.1:10044', help='Parachain URL for ID detection (default: ws://127.0.0.1:10044)')
    parser.add_argument('--start-core', type=int, default=0, help='Starting core index (default: 0)')
    
    args = parser.parse_args()
    
    # Always auto-detect parachain ID
    parachain_id = get_parachain_id(args.parachain_url)
    if not parachain_id:
        print("❌ Failed to get parachain ID")
        sys.exit(1)
    
    print(f"Setting up coretime for parachain {parachain_id}")
    
    # Call setup_coretime with raise_on_exists=True for the tool
    cores_assigned = setup_coretime(
        parachain_id=parachain_id,
        cores=args.cores,
        duration=args.duration,
        raise_on_exists=True,  # Tool should raise error if already exists
        relay_url=args.relay_url,
        start_core=args.start_core
    )
    
    if cores_assigned == 0:
        print("❌ No cores were assigned")
        sys.exit(1)
    else:
        print(f"✅ Successfully assigned {cores_assigned} cores")


if __name__ == '__main__':
    main()