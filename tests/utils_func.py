import os

from tools.utils import WS_URL
from peaq.utils import get_chain
from tools.restart import restart_parachain_launch
from tools.runtime_upgrade import do_runtime_upgrade
from tools.runtime_upgrade import wait_until_block_height
from substrateinterface import SubstrateInterface


def is_runtime_upgrade_test():
    return os.environ.get('RUNTIME_UPGRADE_PATH') is not None


def get_runtime_upgrade_path():
    return os.environ.get('RUNTIME_UPGRADE_PATH')


# Will raise error
def restart_parachain_and_runtime_upgrade():
    restart_parachain_launch()
    wait_until_block_height(SubstrateInterface(url=WS_URL), 1)
    substrate = SubstrateInterface(url=WS_URL)
    old_version = substrate.get_block_runtime_version(substrate.get_block_hash())['specVersion']
    if is_runtime_upgrade_test():
        path = get_runtime_upgrade_path()
        do_runtime_upgrade(path)
        new_version = substrate.get_block_runtime_version(substrate.get_block_hash())['specVersion']
        if old_version == new_version:
            raise Exception(f'Runtime upgrade failed. old_version: {old_version}, new_version: {new_version}')


def is_not_dev_chain():
    ws = SubstrateInterface(url=WS_URL)
    chain_name = get_chain(ws)
    print(f'chain_name: {chain_name}')
    return chain_name not in ['peaq-dev', 'peaq-dev-fork']


def is_krest_related_chain():
    ws = SubstrateInterface(url=WS_URL)
    chain_name = get_chain(ws)
    return chain_name in ['krest-network', 'krest-network-fork']


def is_local_new_chain():
    substrate = SubstrateInterface(url=WS_URL)
    chain_spec = get_chain(substrate)

    return 'peaq-dev-fork' != chain_spec and \
        'krest-network-fork' != chain_spec and \
        'peaq-network-fork' != chain_spec
