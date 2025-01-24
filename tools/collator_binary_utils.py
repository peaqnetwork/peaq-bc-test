import sys
sys.path.append('./')

from tools.docker_utils import get_docker_service
from python_on_whales import docker
import time
import subprocess
import os
import shutil
import sys
import getpass


FORK_COLLATOR_PORT = 10044


def stop_collator_binary():
    command = "sudo pkill -9 peaq-node"
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


def get_parachain_chainspec_path(collator_dict):
    container = get_docker_service('peaq')
    chain_args = [arg for arg in container.args if '--chain' in arg]
    if len(chain_args) != 2:
        raise IOError(f"Cannot find chain_args, {chain_args}")
    return os.path.join(collator_dict['docker_compose_folder'], chain_args[0].split('=')[1])


def get_relaychain_chainspec_path(collator_dict):
    container = get_docker_service('peaq')
    chain_args = [arg for arg in container.args if '--chain' in arg]
    if len(chain_args) != 2:
        raise IOError(f"Cannot find chain_args, {chain_args}")
    return os.path.join(collator_dict['docker_compose_folder'], chain_args[1].split('=')[1])


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


def get_node_key():
    container = get_docker_service('peaq')
    node_key = [arg for arg in container.args if '--node-key' in arg]
    if len(node_key) != 1:
        raise IOError(f"Cannot find node key, {node_key}")
    return node_key[0].split('=')[1]


def get_docker_info(collator_dict):
    return {
        'parachain_id': get_parachain_id(),
        'parachain_bootnode': get_parachain_bootnode(),
        'peer_id': get_peer_id(),
        'node_key': get_node_key(),
        'parachain_chainspec': get_parachain_chainspec_path(collator_dict),
        'relaychain_chainspec': get_relaychain_chainspec_path(collator_dict),
    }


def stop_peaq_docker_container():
    containers = [get_docker_service('peaq', 0), get_docker_service('peaq', 1)]
    for container in containers:
        container.stop()
        docker.container.remove(container.name, force=True)


def wakeup_latest_collator(collator_dict, docker_info):
    peaq_binary_path = collator_dict['collator_binary']
    collator_chain_data_folder = collator_dict['chain_data']
    parachain_id = docker_info['parachain_id']
    parachain_config = os.path.join(
        collator_dict['docker_compose_folder'],
        os.path.basename(docker_info['parachain_chainspec']))
    relaychain_config = os.path.join(
        collator_dict['docker_compose_folder'],
        os.path.basename(docker_info['relaychain_chainspec']))
    node_key = docker_info['node_key']

    run_args = [
        f'--base-path {collator_chain_data_folder}',
        f'--chain {parachain_config}',
        '--rpc-external',
        '--rpc-cors=all',
        '--name=binary-collator',
        '--collator',
        '--rpc-methods unsafe',
        '--execution wasm',
        '--state-pruning archive',
        f'--node-key {node_key}',
        f'--parachain-id {parachain_id}',
        '--port 40333',
        f'--rpc-port {FORK_COLLATOR_PORT}',
        '--',
        f'--chain {relaychain_config}',
        '--port 50345',
        '--rpc-port 30055',
        '--unsafe-rpc-external',
        '--rpc-cors=all',
    ]

    # [TODO] Add --ferdie there...
    run_args = ['--ferdie'] + run_args
    command = f"""PYTHONUNBUFFERED=1 \
        {peaq_binary_path} \
        {' '.join(run_args)} 2>&1 | tee {collator_chain_data_folder}/collator.log
    """

    subprocess.Popen(
        command,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        shell=True,
        executable="/bin/bash",
        text=True,
    )

    print(f'Wait for the collator to start...')
    time.sleep(120)


def _get_docker_volume_path():
    docker_container = get_docker_service('peaq')
    return docker_container.mounts[0].source


def copy_all_chain_data(collator_dict):
    volume_path = _get_docker_volume_path()

    for folder in ['chains', 'polkadot']:
        cmd = f"sudo cp -r {volume_path}/{folder} {collator_dict['chain_data']}/"
        subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            executable="/bin/bash",
            text=True,
        )

    user = getpass.getuser()
    group = user
    subprocess.run(
        f"sudo chown -R {user}:{group} {collator_dict['chain_data']}",
        shell=True,
        capture_output=True,
        executable="/bin/bash",
        text=True,
    )


def cleanup_collator(is_keep_keystores=True):
    from tools.runtime_upgrade import fetch_collator_dict_from_env
    stop_collator_binary()
    collator_options = fetch_collator_dict_from_env()
    remove_chain_data(collator_options['chain_data'], is_keep_keystores)
