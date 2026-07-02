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

from substrateinterface import SubstrateInterface

from tools.constants import PARACHAIN_WS_URL

# Well-known Substrate Core runtime-API trait hash; its version is 5 at
# polkadot-sdk stable2503 (was 4 at v1.7.2 / spec 110).
CORE_API_HASH = '0xdf6acb689907609b'
EXPECTED_CORE_API_VERSION = 5


def state_call(substrate, method, data='0x'):
    """Invoke a runtime API by name via raw state_call; return the hex result."""
    resp = substrate.rpc_request('state_call', [method, data])
    return resp.get('result')


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

    def test_core_api_version_bumped_to_5(self):
        version = self.substrate.get_block_runtime_version(
            self.substrate.get_chain_head())
        self.assertEqual(version.get('specVersion'), 112)
        apis = dict(version.get('apis', []))
        self.assertEqual(
            apis.get(CORE_API_HASH), EXPECTED_CORE_API_VERSION,
            f'Core API must be v{EXPECTED_CORE_API_VERSION} at stable2503, '
            f'got {apis.get(CORE_API_HASH)}')


if __name__ == '__main__':
    unittest.main()
