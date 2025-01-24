from tools.constants import WS_URL, RELAYCHAIN_WS_URL
from peaq.utils import get_chain
from tools.restart import restart_parachain_launch
from tools.runtime_upgrade import wait_until_block_height
from tools.runtime_upgrade import fetch_runtime_upgrade_path_from_env
from tools.runtime_upgrade import fetch_collator_dict_from_env
from tools.collator_binary_utils import cleanup_collator
from tools.runtime_upgrade import do_runtime_upgrade
from substrateinterface import SubstrateInterface
from tools.xcm_setup import setup_hrmp_channel


def is_runtime_upgrade_test():
    return fetch_runtime_upgrade_path_from_env() is not None


# Will raise error
def restart_parachain_and_runtime_upgrade():
    collator_options = fetch_collator_dict_from_env()
    cleanup_collator()
    restart_parachain_launch()

    wait_until_block_height(SubstrateInterface(url=RELAYCHAIN_WS_URL), 1)
    setup_hrmp_channel(RELAYCHAIN_WS_URL)
    wait_until_block_height(SubstrateInterface(url=WS_URL), 1)
    substrate = SubstrateInterface(url=WS_URL)
    old_version = substrate.get_block_runtime_version(substrate.get_block_hash())['specVersion']
    if is_runtime_upgrade_test():
        path = fetch_runtime_upgrade_path_from_env()
        do_runtime_upgrade(path, collator_options)
        new_version = substrate.get_block_runtime_version(substrate.get_block_hash())['specVersion']
        if old_version == new_version:
            raise Exception(f'Runtime upgrade failed. old_version: {old_version}, new_version: {new_version}')


def is_not_dev_chain():
    ws = SubstrateInterface(url=WS_URL)
    chain_name = get_chain(ws)
    return chain_name not in ['peaq-dev', 'peaq-dev-fork']


def is_not_peaq_chain():
    ws = SubstrateInterface(url=WS_URL)
    chain_name = get_chain(ws)
    return chain_name not in ['peaq-network', 'peaq-network-fork']


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
