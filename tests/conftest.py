import pytest  # noqa: F401
import importlib
import sys
import tools.utils  # noqa: F401


def pytest_runtest_setup(item):
    # For the monkey patching to work, the module must be reloaded
    # Avoid the dependency on the module name
    if 'substrateinterface' in sys.modules:
        importlib.reload(sys.modules['substrateinterface'])
    if 'peaq.utils' in sys.modules:
        importlib.reload(sys.modules['peaq.utils'])
