import sys
sys.path.append('./')

from tools.docker_utils import get_docker_service
import argparse
import os
import tempfile


def parse_args():
    parser = argparse.ArgumentParser(description='''
        Get the peer id of a node.
        For example:
            python3 get-peer-id.py --read in --key 936b9a39f181e8051f6c0f309008752db07db2c7d1bbd351beaacb43700793e8
            python3 get_peer_id.py --read docker --type peaq --target 0
            python3 get_peer_id.py --read docker --type relay
            python3 get_peer_id.py --read docker --type 3rd --target 0
    ''', formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('--read', required=True, choices=['docker', 'in'],
                        help='The read of node you want to get logs for')
    in_parser = parser.add_argument_group('in')
    in_parser.add_argument('--key', help='The node key, is needed in read, in')

    docker_parser = parser.add_argument_group('docker')
    docker_parser.add_argument('--type', choices=['peaq', 'relay', '3rd'],
                               help='The type of node you want to get logs for')
    docker_parser.add_argument('--target', default=0, help='The target index of node you want to get logs for')

    return parser.parse_args()


def read_peer_id_from_subkey(key):
    with tempfile.NamedTemporaryFile(dir='/tmp', delete=False) as tmp_file:
        tmp_file_path = tmp_file.name
        tmp_file.write(key.encode('utf-8'))

    cmd = f'subkey inspect-node-key --file {tmp_file_path}'
    peer_id = os.popen(cmd).read()
    os.remove(tmp_file_path)
    return peer_id


def get_peer_id_from_logs(chain_type, logs):
    if chain_type == 'para':
        filter_logs = [log for log in logs if 'Parachain' in log]
    elif chain_type == 'relay':
        filter_logs = [log for log in logs if 'Parachain' not in log]
    else:
        raise ValueError(f'Invalid chain type: {chain_type}')

    if len(filter_logs) == 0:
        return None
    return filter_logs[0].split('Local node identity is: ')[1].strip()


if __name__ == "__main__":
    args = parse_args()
    if args.read == 'in':
        peer_id = read_peer_id_from_subkey(args.key)
        print(f'Peer id: {peer_id}')
    elif args.read == 'docker':
        container = get_docker_service(args.type, args.target)
        container_name = container.name
        logs = container.logs().split('\n')
        peer_logs = [log for log in logs if 'Local node identity' in log]
        relay_peer = get_peer_id_from_logs('relay', peer_logs)
        para_peer = get_peer_id_from_logs('para', peer_logs)
        print(f'Found from Container: {container_name}')
        print(f'    Relay Peer id: {relay_peer}')
        print(f'    Parachain Peer id: {para_peer}')
