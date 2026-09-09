"""API-1: runtime-API surface across SDK upgrades.

Verifies that the runtime APIs added or version-bumped by an upgrade are
actually EXPORTED and CALLABLE, covering the gap left by debug_traceCall
(already exercised by the tracing tests). Currently: RelayParentOffsetApi,
the reworked GenesisBuilder API, and the Core API version floor.

stable2503 (110 -> 112) introduced GetCoreSelectorApi; stable2603
(112 -> 114) removed it again, moving core selection to the node, and
added RelayParentOffsetApi in its place.

Called via raw ``state_call`` because substrate-interface's runtime-call
type registry does not know these APIs; ``state_call`` only succeeds when
the runtime actually exports the method and it runs without trapping, so a
non-error SCALE result proves "callable".
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

# Minimum specVersion per chain after the stable2603 upgrade (peaq->114,
# peaq-dev->110). -fork chains resolve to their base name. krest was dropped
# from the node in the stable2603 port, so it has no entry.
MIN_SPEC_VERSION = {
    'peaq-network': 114,
    'peaq-dev': 110,
}


def state_call(substrate, method, data='0x'):
    """Invoke a runtime API by name via raw state_call; return the hex result."""
    resp = substrate.rpc_request('state_call', [method, data])
    return resp.get('result')


@pytest.mark.substrate
class TestRuntimeApi(unittest.TestCase):
    def setUp(self):
        self.substrate = SubstrateInterface(url=PARACHAIN_WS_URL)

    def test_relay_parent_offset_api(self):
        # stable2603 removed GetCoreSelectorApi -- core selection moved to the
        # node, which writes it into a digest the runtime only validates -- and
        # added RelayParentOffsetApi in its place.
        result = state_call(self.substrate, 'RelayParentOffsetApi_relay_parent_offset')
        self.assertIsNotNone(result, 'RelayParentOffsetApi.relay_parent_offset not callable')
        raw = bytes.fromhex(result[2:])
        self.assertEqual(len(raw), 4, f'expected a 4-byte u32, got {result}')
        offset = int.from_bytes(raw, 'little')
        # The runtime pins Config::RelayParentOffset and this API to one
        # constant; parachain_system::on_initialize asserts they agree and
        # halts the chain when they do not. peaq ships 0.
        self.assertEqual(offset, 0, f'expected RelayParentOffset 0, got {offset}')

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
        # Durable invariant: each upgrade raises a per-chain minimum
        # specVersion and Core API >= 5, and neither regresses on later
        # upgrades. (stable2603: peaq->114, peaq-dev->110; -fork resolves to
        # base.)
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
