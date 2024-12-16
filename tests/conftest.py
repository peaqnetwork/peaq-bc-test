import pytest  # noqa: F401
import importlib
import sys
import tools.utils  # noqa: F401
from tests.substrate_utils import monkey_submit_extrinsic_for_fee_weight
from tests.substrate_utils import generate_substrate_weight_fee_report
from tests.evm_utils import generate_evm_fee_report
from substrateinterface import SubstrateInterface

SubstrateInterface.submit_extrinsic = monkey_submit_extrinsic_for_fee_weight


def pytest_runtest_setup(item):
    # For the monkey patching to work, the module must be reloaded
    # Avoid the dependency on the module name
    if 'substrateinterface' in sys.modules:
        importlib.reload(sys.modules['substrateinterface'])
    if 'peaq.utils' in sys.modules:
        importlib.reload(sys.modules['peaq.utils'])


def pytest_sessionfinish(session, exitstatus):
    generate_substrate_weight_fee_report()
    generate_evm_fee_report()
