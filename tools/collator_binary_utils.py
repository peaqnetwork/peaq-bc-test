import sys
sys.path.append('./')

from tools.docker_utils import get_docker_service
from python_on_whales import docker
from tools.constants import COLLATOR_STOP_WAIT_TIME, COLLATOR_START_WAIT_TIME
from tools.constants import FORK_COLLATOR_PORT, PARACHAIN_PORT, RELAYCHAIN_PORT, RPC_PORT
import time
import subprocess
import os
import shutil
import sys
import getpass


def stop_collator_binary():
    """
    Stops any running peaq-node binary collator processes.

    Uses pkill to forcefully terminate all peaq-node processes
    and waits for cleanup to complete.
    """
    command = "pkill -9 peaq-node"
    subprocess.run(
        command,
        shell=True,
        capture_output=True,
        executable="/bin/bash",
        text=True,
    )
    time.sleep(COLLATOR_STOP_WAIT_TIME)


def remove_chain_data(folder_path, is_keep_keystores):
    """
    Recursively removes chain data while optionally preserving keystores.

    Args:
        folder_path: Path to the chain data directory
        is_keep_keystores: If True, preserves keystore directories

    Returns:
        bool: True if keystores were found and preserved

    Raises:
        Exception: If attempting to remove dangerous system paths
    """
    if os.path.realpath(folder_path) == os.path.realpath(os.path.expanduser('~')) or \
       os.path.realpath(folder_path) == os.path.realpath("/"):
        raise Exception(f"The folder path is too dangerous to remove, {os.path.realpath(folder_path)}")

    for root, dirs, files in os.walk(folder_path, topdown=True):
        non_keystore_dirs = [d for d in dirs if not is_keep_keystores or d != "keystore"]
        found_keystore = dirs != non_keystore_dirs
        for file in files:
            file_path = os.path.join(root, file)
            print(f'remove file: {file_path}')
            os.remove(file_path)

        for dir in non_keystore_dirs:
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
    """
    Extracts configuration information from running docker collator.

    Args:
        collator_dict: Collator configuration dictionary

    Returns:
        dict: Docker configuration including parachain ID, peer ID,
              node key, and chainspec paths
    """
    return {
        'parachain_id': get_parachain_id(),
        'parachain_bootnode': get_parachain_bootnode(),
        'peer_id': get_peer_id(),
        'node_key': get_node_key(),
        'parachain_chainspec': get_parachain_chainspec_path(collator_dict),
        'relaychain_chainspec': get_relaychain_chainspec_path(collator_dict),
    }


def stop_peaq_docker_container():
    """
    Stops and removes the peaq docker container.

    Gracefully stops the container and forcefully removes it
    to ensure clean shutdown.
    """
    containers = []
    try:
        containers = [get_docker_service('peaq', 0)]
    except Exception as e:
        print(f'Error: {e}')

    for container in containers:
        print(f'Stopping container {container.name}...')
        container.stop()
        docker.container.remove(container.name, force=True)


def build_parachain_args(collator_dict, docker_info):
    """Build command line arguments for parachain collator."""
    collator_chain_data_folder = collator_dict['chain_data']
    parachain_config = os.path.join(
        collator_dict['docker_compose_folder'],
        os.path.basename(docker_info['parachain_chainspec']))

    return [
        f'--base-path {collator_chain_data_folder}',
        f'--chain {parachain_config}',
        '--rpc-external',
        '--rpc-cors=all',
        '--name=binary-collator',
        '--collator',
        '--rpc-methods unsafe',
        '--execution wasm',
        '--state-pruning archive',
        f'--node-key {docker_info["node_key"]}',
        f'--parachain-id {docker_info["parachain_id"]}',
        f'--port {PARACHAIN_PORT}',
        f'--rpc-port {FORK_COLLATOR_PORT}',
    ]


def build_relaychain_args(collator_dict, docker_info):
    """Build command line arguments for relaychain connection."""
    relaychain_config = os.path.join(
        collator_dict['docker_compose_folder'],
        os.path.basename(docker_info['relaychain_chainspec']))

    return [
        f'--chain {relaychain_config}',
        f'--port {RELAYCHAIN_PORT}',
        f'--rpc-port {RPC_PORT}',
        '--unsafe-rpc-external',
        '--rpc-cors=all',
    ]


def start_collator_process(binary_path, args, log_path):
    """Start the collator binary process with given arguments."""
    command = f"""PYTHONUNBUFFERED=1 \
        {binary_path} \
        {' '.join(args)}
    """

    with open(log_path, 'w') as logfile:
        subprocess.Popen(
            command,
            stdout=logfile, stderr=logfile,
            shell=True,
            executable="/bin/bash",
            text=True,
            start_new_session=True,
        )


def wakeup_latest_collator(collator_dict, docker_info):
    """
    Starts the binary collator with configuration from docker container.

    Args:
        collator_dict: Dictionary containing binary collator configuration
        docker_info: Information extracted from docker container
    """
    peaq_binary_path = collator_dict['collator_binary']
    collator_chain_data_folder = collator_dict['chain_data']

    # Build command arguments
    parachain_args = build_parachain_args(collator_dict, docker_info)
    relaychain_args = build_relaychain_args(collator_dict, docker_info)

    # Combine with separator and add validator key
    run_args = ['--ferdie'] + parachain_args + ['--'] + relaychain_args

    # Start the collator process
    log_path = f'{collator_chain_data_folder}/collator.log'
    start_collator_process(peaq_binary_path, run_args, log_path)

    print('Wait for the collator to start...')
    time.sleep(COLLATOR_START_WAIT_TIME)


def get_docker_volume_path():
    docker_container = get_docker_service('peaq', 0)
    return docker_container.mounts[0].source


def copy_all_chain_data(collator_dict, volume_path=None):
    """
    Copies chain data from docker volume to binary collator location.

    Args:
        collator_dict: Collator configuration with target paths
        volume_path: Source docker volume path (auto-detected if None)

    Creates the target directory and copies all chain state data
    while ensuring proper file ownership for the current user.
    """
    if volume_path is None:
        volume_path = get_docker_volume_path()

    os.makedirs(collator_dict['chain_data'], exist_ok=True)
    cmd = f"sudo find {volume_path}/ -mindepth 1 -maxdepth 1 -exec cp -r {{}} {collator_dict['chain_data']}/ \\;"
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
    """
    Cleans up binary collator processes and chain data.

    Args:
        is_keep_keystores: If True, preserves keystore files

    Stops any running binary collator and removes its chain data
    based on environment configuration.
    """
    from tools.runtime_upgrade import fetch_collator_dict_from_env
    stop_collator_binary()
    collator_options = fetch_collator_dict_from_env()
    remove_chain_data(collator_options['chain_data'], is_keep_keystores)
