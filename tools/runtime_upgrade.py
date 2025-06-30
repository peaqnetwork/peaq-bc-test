import sys
sys.path.append('./')
import os
import time
import importlib

from peaq.utils import ExtrinsicBatch
from tools.monkey.monkey_reorg_batch import monkey_execute_extrinsic_batch
ExtrinsicBatch._execute_extrinsic_batch = monkey_execute_extrinsic_batch

from substrateinterface import SubstrateInterface, Keypair
from tools.constants import WS_URL, KP_GLOBAL_SUDO, RELAYCHAIN_WS_URL, KP_COLLATOR
from peaq.sudo_extrinsic import funds
from peaq.utils import show_extrinsic, get_block_height
from substrateinterface.utils.hasher import blake2_256
from peaq.utils import wait_for_n_blocks
from tools.restart import restart_parachain_launch
from peaq.utils import get_account_balance
from tools.constants import BLOCK_GENERATE_TIME
from tools.constants import DEFAULT_COLLATOR_PATH, DEFAULT_BINARY_CHAIN_PATH
from tools.constants import DEFAULT_DOCKER_COMPOSE_FOLDER
from tools.constants import DEFAULT_COLLATOR_DICT
from tools.xcm_setup import setup_hrmp_channel
from tools.collator_binary_utils import wakeup_latest_collator
from tools.collator_binary_utils import copy_all_chain_data
from tools.collator_binary_utils import get_docker_info
from tools.collator_binary_utils import stop_peaq_docker_container
from tools.collator_binary_utils import stop_collator_binary
from tools.collator_binary_utils import get_docker_volume_path
from tools.utils import show_title
import argparse

import pprint
pp = pprint.PrettyPrinter(indent=4)


def set_runtime_upgrade_path_to_env(runtime_path):
    if not runtime_path:
        print(f'use the default runtime path: {os.environ.get("RUNTIME_UPGRADE_PATH")}')
        return
    os.environ['RUNTIME_UPGRADE_PATH'] = runtime_path


def fetch_runtime_upgrade_path_from_env():
    return os.environ.get('RUNTIME_UPGRADE_PATH')


def set_enable_collator_dict_to_env(enable_collator_binary, collator_binary, chain_data, docker_compose_folder):
    os.environ['TEST_ENABLE_COLLATOR_BINARY'] = str(enable_collator_binary)
    if enable_collator_binary:
        os.environ['TEST_COLLATOR_BINARY'] = collator_binary
        os.environ['TEST_CHAIN_DATA'] = chain_data
        os.environ['TEST_DOCKER_COMPOSE_FOLDER'] = docker_compose_folder
    else:
        os.environ['TEST_COLLATOR_BINARY'] = ''
        os.environ['TEST_CHAIN_DATA'] = ''
        os.environ['TEST_DOCKER_COMPOSE_FOLDER'] = ''


def fetch_collator_dict_from_env():
    # Fetch the environment variables
    enable_collator_dict = DEFAULT_COLLATOR_DICT.copy()
    enable_collator_dict['enable_collator_binary'] = os.environ.get('TEST_ENABLE_COLLATOR_BINARY') == 'True'
    enable_collator_dict['collator_binary'] = os.environ.get('TEST_COLLATOR_BINARY')
    enable_collator_dict['chain_data'] = os.environ.get('TEST_CHAIN_DATA')
    enable_collator_dict['docker_compose_folder'] = os.environ.get('TEST_DOCKER_COMPOSE_FOLDER')
    return enable_collator_dict


def send_upgrade_call(substrate, kp_sudo, wasm_file):
    with open(wasm_file, 'rb', buffering=0) as f:
        data = f.read()
    file_hash = f'0x{blake2_256(data).hex()}'
    print(f'File hash: {file_hash}')
    batch = ExtrinsicBatch(substrate, kp_sudo)
    batch.compose_sudo_call(
        'ParachainSystem',
        'authorize_upgrade',
        {'code_hash': file_hash, 'check_version': True}
    )
    batch.compose_sudo_call(
        'ParachainSystem',
        'enact_authorized_upgrade',
        {'code': data}
    )
    return batch.execute()


def wait_until_block_height(substrate, block_height):
    current_block = get_block_height(substrate)
    block_num = block_height - current_block + 1
    wait_for_n_blocks(substrate, block_num)


def wait_relay_upgrade_block(url=RELAYCHAIN_WS_URL):
    relay_substrate = SubstrateInterface(url, type_registry_preset='rococo')
    result = relay_substrate.query(
        'Paras',
        'UpcomingUpgrades',
    )
    if not result.value:
        print('No upgrade scheduled')
        return

    print('Upcoming upgrade:')
    wait_until_block_height(relay_substrate, int(result.value[0][1]))


def upgrade(runtime_path):
    substrate = SubstrateInterface(url=WS_URL)
    wait_for_n_blocks(substrate, 1)

    print(f'Global Sudo: {KP_GLOBAL_SUDO.ss58_address}')
    receipt = send_upgrade_call(substrate, KP_GLOBAL_SUDO, runtime_path)
    show_extrinsic(receipt, 'upgrade?')
    if not receipt.is_success:
        raise IOError('Cannot upgrade')
    wait_relay_upgrade_block()


def fund_sudo_account():
    substrate = SubstrateInterface(url=WS_URL)

    kps = [Keypair.create_from_mnemonic(
        "crane scheme tourist cigar exact asthma culture lamp bacon give wish certain"),
        KP_COLLATOR
    ]
    for kp in kps:
        balance = get_account_balance(substrate, kp.ss58_address)
        if get_account_balance(substrate, kp.ss58_address) > 1 * 10 ** 18:
            print(f'Funding account {kp.ss58_address}')
            batch = ExtrinsicBatch(substrate, kp)
            batch.compose_call(
                'Balances',
                'transfer_keep_alive',
                {
                    'dest': KP_GLOBAL_SUDO.ss58_address,
                    'value': 3 * 10 ** 18,
                }
            )
            receipt = batch.execute()
            if not receipt.is_success:
                print('Cannot transfer account')
                raise IOError(receipt.error_message)
        if get_account_balance(substrate, KP_GLOBAL_SUDO.ss58_address) < 0.5 * 10 ** 18:
            print(f'Funding account {KP_GLOBAL_SUDO.ss58_address}')
            break
        else:
            print(f'Account {KP_GLOBAL_SUDO.ss58_address} not have enough balance '
                  f'becaues {kp.ss58_address} balance is {balance}')
    if get_account_balance(substrate, KP_GLOBAL_SUDO.ss58_address) < 0.5 * 10 ** 18:
        raise IOError('Sudo user still dont have enough balance')


def fund_all_retated_accounts():
    substrate = SubstrateInterface(url=WS_URL)

    accounts = [
        '5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY',
        '5GNJqTPyNqANBkUVMN1LPPrxXnFouWXoe2wNSmmEoLctxiZY',
        '5FHneW46xGXgs5mUiveU4sbTyGBzmstUspZC92UhjJM694ty',
        '5HpG9w8EBLe5XCrbczpwq5TSXvedjrBGCwqxK1iQ7qUsSWFc',
        '5FLSigC9HGRKVhB9FiEo4Y3koPsNmBmLJbpXg2mp1hXcS59Y',
        '5DAAnrj7VHTznn2AWBemMuyBwZWs6FNFjdyVXUeYum3PTXFy',
        '5HGjWAeFDfFCWPsjFQdVV2Msvz2XtMktvgocEZcCj68kUMaw',
        '5CiPPseXPECbkjWCa6MnjNokrgYjMqmKndv2rSnekmSK2DjL',
    ]
    account_balances = [get_account_balance(substrate, a) for a in accounts]
    receipt = funds(substrate, KP_GLOBAL_SUDO, accounts, max(account_balances) + 302231 * 10 ** 18)
    if not receipt.is_success:
        print('Cannot fund the sudo account')
        print(receipt.error_message)


def fund_account():
    print('update the info')
    substrate = SubstrateInterface(url=WS_URL)

    fund_sudo_account()
    fund_all_retated_accounts()

    balance = get_account_balance(substrate, KP_GLOBAL_SUDO.ss58_address)
    if balance < 1 * 10 ** 18:
        raise IOError('Sudo user still dont have enough balance')


# [TODO] Will need to remove after precompile runtime upgrade
# Fix from dev 0.0.12 to 0.0.16
def update_xcm_default_version(substrate):
    batch = ExtrinsicBatch(substrate, KP_GLOBAL_SUDO)
    batch.compose_sudo_call(
        'PolkadotXcm',
        'force_default_xcm_version',
        {
            'maybe_xcm_version': 4,
        }
    )
    batch.execute()


# Please check that...
def remove_asset_id(substrate):
    batch = ExtrinsicBatch(substrate, KP_GLOBAL_SUDO)
    batch.compose_sudo_call(
        'XcAssetConfig',
        'remove_asset',
        {
            'asset_id': 1,
        }
    )
    batch.compose_sudo_call(
        'Assets',
        'start_destroy',
        {'id': 1}
    )
    batch.compose_call(
        'Assets',
        'finish_destroy',
        {'id': 1}
    )

    batch.execute()


def do_runtime_upgrade_only(wasm_path, collator_dict=DEFAULT_COLLATOR_DICT):
    if not os.path.exists(wasm_path):
        raise IOError(f'Runtime not found: {wasm_path}')

    docker_volume_path = get_docker_volume_path()
    docker_info = get_docker_info(collator_dict)

    wait_until_block_height(SubstrateInterface(url=RELAYCHAIN_WS_URL), 1)
    wait_until_block_height(SubstrateInterface(url=WS_URL), 1)
    substrate = SubstrateInterface(url=WS_URL)
    old_version = substrate.get_block_runtime_version(substrate.get_block_hash())['specVersion']

    upgrade(wasm_path)
    try:
        wait_for_n_blocks(substrate, 15, timeout=15*12)
    except Exception as e:
        print(f'Error: {e}')
        if not collator_dict['enable_collator_binary']:
            raise e
        if 'runtime requires function imports' not in str(e) and 'Timeout waiting for blocks' not in str(e):
            raise e

    if collator_dict['enable_collator_binary']:
        copy_all_chain_data(collator_dict, docker_volume_path)
        print(f'docker info: {docker_info}')
        stop_collator_binary()
        stop_peaq_docker_container()
        wakeup_latest_collator(collator_dict, docker_info)

        substrate = SubstrateInterface(url=WS_URL)
        substrate.connect_websocket()
        wait_for_n_blocks(substrate, 3)

    # Cannot move in front of the upgrade because V4 only exists in 1.7.2

    new_version = substrate.get_block_runtime_version(substrate.get_block_hash())['specVersion']
    if old_version == new_version:
        raise IOError(f'Runtime ugprade fails: {old_version} == {new_version}')
    print(f'Upgrade from {old_version} to the {new_version}')


def setup_actions():
    wait_until_block_height(SubstrateInterface(url=RELAYCHAIN_WS_URL), 1)
    setup_hrmp_channel(RELAYCHAIN_WS_URL)

    wait_until_block_height(SubstrateInterface(url=WS_URL), 1)
    substrate = SubstrateInterface(url=WS_URL)

    if get_account_balance(substrate, KP_GLOBAL_SUDO.ss58_address) < 0.5 * 10 ** 18:
        print(f'Funding account {KP_GLOBAL_SUDO.ss58_address}')
        fund_account()

    # Remove the asset id 1: relay chain
    # Because of the zenlink's test_create_pair_swap should only use asset 1
    remove_asset_id(substrate)
    update_xcm_default_version(substrate)


def do_runtime_upgrade(wasm_path, collator_dict=DEFAULT_COLLATOR_DICT):
    setup_actions()
    do_runtime_upgrade_only(wasm_path, collator_dict)


def main():
    parser = argparse.ArgumentParser(description='Upgrade the runtime, env: RUNTIME_UPGRADE_PATH')
    parser.add_argument('--runtime-upgrade-path', type=str, help='Your runtime poisiton')
    parser.add_argument('-d', '--docker-restart', type=bool, default=False, help='Restart the docker container')

    # Three options for the collator binary
    #    1. Enable the collator binary: enable-collator-binary
    #    2. Collator binary path: collator-binary: collator-binary
    #    3. Chain data path: chain-data: chain-data
    parser.add_argument(
        '--enable-collator-binary', action="store_true", default=False, help='Enable collator binary')
    parser.add_argument(
        '--collator-binary',
        type=str, help='Collator binary path, only affect when enable collator binary',
        default=DEFAULT_COLLATOR_PATH)
    parser.add_argument(
        '--chain-data',
        type=str, help='Collator\'s chain data path, only affect when enable collator binary',
        default=DEFAULT_BINARY_CHAIN_PATH)
    parser.add_argument(
        '--docker-compose-folder',
        help='Docker compose folder',
        type=str, default=DEFAULT_DOCKER_COMPOSE_FOLDER)

    args = parser.parse_args()
    runtime_path = args.runtime_upgrade_path
    runtime_env = os.environ.get('RUNTIME_UPGRADE_PATH')

    if not runtime_env and not runtime_path:
        raise IOError('Runtime path is required')
    if runtime_env:
        print(f'Use runtime env {runtime_env} to overide the runtime path {runtime_path}')
        runtime_path = runtime_env

    set_enable_collator_dict_to_env(
        args.enable_collator_binary,
        args.collator_binary,
        args.chain_data,
        args.docker_compose_folder
    )
    set_runtime_upgrade_path_to_env(runtime_path)

    if args.docker_restart:
        restart_parachain_launch()

    substrate = SubstrateInterface(url=WS_URL)
    old_version = substrate.get_block_runtime_version(substrate.get_block_hash())['specVersion']

    do_runtime_upgrade(runtime_path, fetch_collator_dict_from_env())
    print('Done but wait 30s')
    time.sleep(BLOCK_GENERATE_TIME * 5)

    substrate = SubstrateInterface(url=WS_URL)
    new_version = substrate.get_block_runtime_version(substrate.get_block_hash())['specVersion']
    if old_version == new_version:
        raise Exception(f'Runtime upgrade failed. old_version: {old_version}, new_version: {new_version}')


if __name__ == '__main__':
    show_title('Runtime upgrade')
    # For the monkey patching to work, the module must be reloaded
    # Avoid the dependency on the module name
    if 'substrateinterface' in sys.modules:
        importlib.reload(sys.modules['substrateinterface'])
    if 'peaq.utils' in sys.modules:
        importlib.reload(sys.modules['peaq.utils'])

    main()
