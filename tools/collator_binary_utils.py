import sys
sys.path.append('./')

from tools.docker_utils import get_docker_service
import time
import subprocess
import os
import shutil
import sys


FORK_COLLATOR_PORT = 40044


def stop_collator_binary():
    command = "pkill -9 peaq-node"
    subprocess.run(
        command,
        shell=True,
        capture_output=True,
        executable="/bin/bash",
        text=True,
    )
    time.sleep(12)


def remove_chain_data(folder_path, is_keep_keystores):
    if os.path.realpath(folder_path) == os.path.realpath(os.path.expanduser('~')) or \
       os.path.realpath(folder_path) == os.path.realpath("/"):
        raise Exception(f"The folder path is too dangerous to remove, {os.path.realpath(folder_path)}")

    for root, dirs, files in os.walk(folder_path, topdown=True):
        filter_dirs = [d for d in dirs if not is_keep_keystores or d != "keystore"]
        found_keystore = dirs != filter_dirs
        for file in files:
            file_path = os.path.join(root, file)
            print(f'remove file: {file_path}')
            os.remove(file_path)

        for dir in filter_dirs:
            dir_path = os.path.join(root, dir)
            if not remove_chain_data(dir_path, is_keep_keystores):
                print(f'remove dir: {dir_path}')
                shutil.rmtree(dir_path)
            else:
                found_keystore = True
        return found_keystore


def wait_runtime_version_change(substrate, old_version):
    wait_time = 60 * 2
    for i in range(int(60 * (10 + 5) / wait_time)):
        time.sleep(wait_time)
        substrate.connect_websocket()
        current_version = substrate.get_block_runtime_version(substrate.get_block_hash())['specVersion']
        if current_version != old_version:
            return True

    return False


def check_collator_generate_node(substrate, prev_version):
    last_block = substrate.get_block_number()
    for i in range(20):
        time.sleep(12)
        substrate.connect_websocket()
        current_block = substrate.get_block_number()
        if current_block <= last_block:
            return True
        last_block = current_block
    return False


def get_parachain_chainspec_path(collator_dict):
    container = get_docker_service('peaq')
    chain_args = [arg for arg in container.args if '--chain' in arg]
    if len(chain_args) != 2:
        raise IOError(f"Cannot find chain_args, {chain_args}")
    return os.path.join(collator_dict['docker_composer_folder'], chain_args[0].split('=')[1])


def get_relaychain_chainspec_path(collator_dict):
    container = get_docker_service('peaq')
    chain_args = [arg for arg in container.args if '--chain' in arg]
    if len(chain_args) != 2:
        raise IOError(f"Cannot find chain_args, {chain_args}")
    return os.path.join(collator_dict['docker_composer_folder'], chain_args[1].split('=')[1])


def get_parachain_id():
    container = get_docker_service('peaq')
    parachain_id_arg = [arg for arg in container.args if '--parachain-id' in arg]
    if len(parachain_id_arg) != 1:
        raise IOError(f"Cannot find parachain id, {parachain_id_arg}")
    return parachain_id_arg[0].split('=')[1]


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


def get_peer_id():
    container = get_docker_service('peaq')
    logs = container.logs().split('\n')
    peer_logs = [log for log in logs if 'Local node identity' in log[:100]]
    para_peer = get_peer_id_from_logs('para', peer_logs)
    return para_peer


def get_parachain_bootnode():
    peer_id = get_peer_id()
    parachain_bootnode = f"/ip4/127.0.0.1/tcp/40336/p2p/{peer_id}"
    return parachain_bootnode


def wakeup_latest_collator(collator_dict):
    pid = os.fork()
    if pid != 0:
        return

    peaq_binary_path = collator_dict['collator_binary']
    collator_chain_data_folder = collator_dict['chain_data']
    parachain_id = get_parachain_id()
    parachain_bootnode = get_parachain_bootnode()
    parachain_config = get_parachain_chainspec_path(collator_dict)
    relaychain_config = get_relaychain_chainspec_path(collator_dict)

    command = f"""PYTHONUNBUFFERED=1  {peaq_binary_path} \
        --parachain-id {parachain_id} \
        --chain {parachain_config} \
        --port 50334 \
        --rpc-port {FORK_COLLATOR_PORT} \
        --ferdie \
        --collator \
        --base-path {collator_chain_data_folder} \
        --unsafe-rpc-external \
        --rpc-cors=all \
        --rpc-methods=Unsafe \
        --bootnodes {parachain_bootnode} \
        -- \
        --chain {relaychain_config} \
        --port 50345 \
        --rpc-port 30055 \
        --unsafe-rpc-external \
        --rpc-cors=all 2>&1 | tee {collator_chain_data_folder}/collator.log
    """

    subprocess.run(
        command,
        shell=True,
        capture_output=True,
        executable="/bin/bash",
        text=True,
    )
    sys.exit(0)


def monitor_runtime_and_wake_collator(substrate, old_version, collator_dict):
    pid = os.fork()
    if pid != 0:
        return

    try:
        # Only child process can run the below code
        found_version_change = wait_runtime_version_change(substrate, old_version)
    except Exception as e:
        print(f'Error: {e}')
        sys.exit(1)

    if not found_version_change:
        print(f'Cannot find the runtime version change from {old_version}')
        sys.exit(1)

    # [TODO] stop_second_docker_container()

    # Wake up the collator!!
    # [TODO] I'm not sure whether the old full node can work or not... if we cannot, we have to
    # 1. copy the chain data
    # 2. steal the node key
    # 3. stop the full node
    # 4. start the collator on 10044
    # below func fork the process again because we want to do double fork
    try:
        wakeup_latest_collator(collator_dict)
    except Exception as e:
        print(f'Error: {e}')
        sys.exit(1)
    sys.exit(0)


def cleanup_collator(is_keep_keystores=True):
    from tools.runtime_upgrade import fetch_collator_dict_from_env
    stop_collator_binary()
    collator_options = fetch_collator_dict_from_env()
    remove_chain_data(collator_options['chain_data'], is_keep_keystores)
