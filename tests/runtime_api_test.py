"""API-1: stable2503 runtime-API bump.

Verifies the runtime APIs that are new / version-bumped by the 110->112
upgrade are actually EXPORTED and CALLABLE at spec 112 (single-core
lookahead). Covers the gap left by debug_traceCall (which was already
exercised by the tracing tests): GetCoreSelectorApi and the reworked
GenesisBuilder API, plus the Core API version bump (4 -> 5).

Called via raw ``state_call`` because substrate-interface's runtime-call
type registry does not know these newer stable2503 APIs; ``state_call``
only succeeds when the runtime actually exports the method and it runs
without trapping, so a non-error SCALE result proves "callable".
"""
import unittest

import pytest
from substrateinterface import SubstrateInterface

from tools.constants import PARACHAIN_WS_URL
from peaq.utils import get_chain
from tools.utils import get_modified_chain_spec

# Well-known Substrate Core runtime-API trait hash; its version is >= 5 from
# polkadot-sdk stable2503 onward (was 4 at v1.7.2 / spec 110).
CORE_API_HASH = '0xdf6acb689907609b'
MIN_CORE_API_VERSION = 5

# Minimum specVersion per chain after the stable2503 upgrade (peaq->112,
# peaq-dev/krest->108). -fork chains resolve to their base name.
MIN_SPEC_VERSION = {
    'peaq-network': 112,
    'peaq-dev': 108,
    'krest-network': 108,
}


def state_call(substrate, method, data='0x'):
    """Invoke a runtime API by name via raw state_call; return the hex result."""
    resp = substrate.rpc_request('state_call', [method, data])
    return resp.get('result')


@pytest.mark.substrate
class TestRuntimeApi(unittest.TestCase):
    def setUp(self):
        self.substrate = SubstrateInterface(url=PARACHAIN_WS_URL)

    def test_get_core_selector_api(self):
        # GetCoreSelectorApi_core_selector() -> (CoreSelector(u8), ClaimQueueOffset(u8))
        result = state_call(self.substrate, 'GetCoreSelectorApi_core_selector')
        self.assertIsNotNone(result, 'GetCoreSelectorApi.core_selector not callable')
        raw = bytes.fromhex(result[2:])
        # Two u8 newtypes -> exactly 2 bytes; value rotates per block so we
        # only assert the shape, not a fixed value.
        self.assertEqual(
            len(raw), 2,
            f'expected 2-byte (CoreSelector, ClaimQueueOffset), got {result}')

    def test_genesis_builder_api(self):
        # GenesisBuilder_preset_names() -> Vec<PresetId> (SCALE compact-len prefixed)
        names = state_call(self.substrate, 'GenesisBuilder_preset_names')
        self.assertIsNotNone(names, 'GenesisBuilder.preset_names not callable')
        self.assertGreaterEqual(
            len(bytes.fromhex(names[2:])), 1,
            'preset_names must return at least a SCALE length byte')
        # GenesisBuilder_get_preset(Option<PresetId>::None) -> Option<Vec<u8>>.
        # 0x00 == encoded None argument; a non-error result proves callable.
        preset = state_call(self.substrate, 'GenesisBuilder_get_preset', '0x00')
        self.assertIsNotNone(preset, 'GenesisBuilder.get_preset(None) not callable')

    def test_core_api_version_at_least_5(self):
        # Durable invariant: the stable2503 upgrade brought a per-chain minimum
        # specVersion and Core API >= 5, and neither regresses on later
        # upgrades. (peaq->112, peaq-dev/krest->108; -fork resolves to base.)
        version = self.substrate.get_block_runtime_version(
            self.substrate.get_chain_head())
        chain_spec = get_modified_chain_spec(get_chain(self.substrate))
        min_spec = MIN_SPEC_VERSION[chain_spec]
        self.assertGreaterEqual(
            version.get('specVersion'), min_spec,
            f'{chain_spec}: specVersion {version.get("specVersion")} < {min_spec}')
        apis = dict(version.get('apis', []))
        core_version = apis.get(CORE_API_HASH)
        self.assertIsNotNone(core_version, 'Core runtime API not found')
        self.assertGreaterEqual(
            core_version, MIN_CORE_API_VERSION,
            f'Core API must be >= v{MIN_CORE_API_VERSION} at stable2503+, '
            f'got {core_version}')


if __name__ == '__main__':
    unittest.main()
