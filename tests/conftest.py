import pytest  # noqa: F401
import importlib
import sys
import tools.utils  # noqa: F401
from tools.constants import DEFAULT_COLLATOR_PATH, DEFAULT_BINARY_CHAIN_PATH
from tools.constants import DEFAULT_DOCKER_COMPOSE_FOLDER
from tests.substrate_utils import monkey_submit_extrinsic_for_fee_weight
from tests.substrate_utils import generate_substrate_weight_fee_report
from tests.evm_utils import generate_evm_fee_report
from substrateinterface import SubstrateInterface

SubstrateInterface.submit_extrinsic = monkey_submit_extrinsic_for_fee_weight


def pytest_addoption(parser):
    parser.addoption(
        '--runtime-upgrade-path',
        type=str, default=None,
        help='Runtime upgrade path')

    parser.addoption(
        '--enable-collator-binary',
        action="store_true", default=False,
        help='Enable collator binary')
    parser.addoption(
        '--collator-binary',
        type=str, help='Collator binary path, only affect when enable collator binary',
        default=DEFAULT_COLLATOR_PATH)
    parser.addoption(
        '--chain-data',
        type=str, help='Collator\'s chain data path, only affect when enable collator binary',
        default=DEFAULT_BINARY_CHAIN_PATH)

    parser.addoption(
        '--docker-compose-folder',
        help='Docker compose folder',
        type=str, default=DEFAULT_DOCKER_COMPOSE_FOLDER,
    )


def setup_pytest_options_to_env(item):
    from tools.runtime_upgrade import set_enable_collator_dict_to_env
    set_enable_collator_dict_to_env(
        item.config.getoption('--enable-collator-binary'),
        item.config.getoption('--collator-binary'),
        item.config.getoption('--chain-data'),
        item.config.getoption('--docker-compose-folder')
    )


def setup_pytest_runtime_upgrade_path_to_env(item):
    from tools.runtime_upgrade import set_runtime_upgrade_path_to_env
    set_runtime_upgrade_path_to_env(item.config.getoption('--runtime-upgrade-path'))


def pytest_runtest_setup(item):
    # For the monkey patching to work, the module must be reloaded
    # Avoid the dependency on the module name
    if 'substrateinterface' in sys.modules:
        importlib.reload(sys.modules['substrateinterface'])
    if 'peaq.utils' in sys.modules:
        importlib.reload(sys.modules['peaq.utils'])

    setup_pytest_options_to_env(item)
    setup_pytest_runtime_upgrade_path_to_env(item)


def pytest_sessionfinish(session, exitstatus):
    generate_substrate_weight_fee_report()
    generate_evm_fee_report()
