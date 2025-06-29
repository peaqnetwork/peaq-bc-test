from tools.constants import WS_URL, RELAYCHAIN_WS_URL
from peaq.utils import get_chain
from tools.constants import KP_GLOBAL_SUDO
from tools.restart import restart_parachain_launch
from tools.runtime_upgrade import wait_until_block_height
from tools.runtime_upgrade import fund_account
from tools.runtime_upgrade import do_runtime_upgrade_only
from tools.runtime_upgrade import fetch_runtime_upgrade_path_from_env
from tools.runtime_upgrade import fetch_collator_dict_from_env
from tools.collator_binary_utils import cleanup_collator
from tools.runtime_upgrade import do_runtime_upgrade
from substrateinterface import SubstrateInterface
from tools.xcm_setup import setup_hrmp_channel
from peaq.utils import get_account_balance


def is_runtime_upgrade_test():
    return fetch_runtime_upgrade_path_from_env() is not None


# Will raise error
def restart_with_setup():
    cleanup_collator()
    restart_parachain_launch()

    wait_until_block_height(SubstrateInterface(url=RELAYCHAIN_WS_URL), 1)
    # [TODO] Add the config because not all needed to setup
    setup_hrmp_channel(RELAYCHAIN_WS_URL)
    wait_until_block_height(SubstrateInterface(url=WS_URL), 1)
    if get_account_balance(SubstrateInterface(url=WS_URL), KP_GLOBAL_SUDO.ss58_address) < 0.5 * 10 ** 18:
        fund_account()


def start_runtime_upgrade_only():
    do_runtime_upgrade_only(fetch_runtime_upgrade_path_from_env())


# Will raise error
def restart_parachain_and_runtime_upgrade():
    restart_with_setup()
    if is_runtime_upgrade_test():
        collator_options = fetch_collator_dict_from_env()
        path = fetch_runtime_upgrade_path_from_env()
        do_runtime_upgrade(path, collator_options)


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
