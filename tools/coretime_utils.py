# Coretime helpers for local relay/parachain test networks.
#
# Reconstructed implementation: the original file was referenced by
# tools/restart.py, tools/setup_coretime.py and tests/test_evm_event_only.py
# but was never committed. Call semantics recovered from those call sites;
# the relay-side extrinsic shape follows the relay runtime's `Coretime`
# pallet: assign_core(core: u16, begin, assignment: Vec<(CoreAssignment,
# PartsOf57600)>, end_hint), root origin allowed.
from substrateinterface import SubstrateInterface
from peaq.utils import ExtrinsicBatch
from tools.constants import KP_GLOBAL_SUDO, PARACHAIN_WS_URL, RELAYCHAIN_WS_URL
from tools.constants import CORETIME_CORES, CORETIME_DURATION, PARACHAIN_CORE_MAP


def get_parachain_id(ws_url=PARACHAIN_WS_URL):
    """Return the parachain's on-chain id (parachainInfo.parachainId), or None."""
    try:
        substrate = SubstrateInterface(url=ws_url)
        return substrate.query('ParachainInfo', 'ParachainId').value
    except Exception as err:
        print(f'Warning: cannot read parachain id from {ws_url}: {err}')
        return None


def _cores_assigned_to(relay, parachain_id):
    """Count relay cores whose descriptor currently serves `parachain_id`."""
    count = 0
    try:
        for _, descriptor in relay.query_map('CoretimeAssignmentProvider', 'CoreDescriptors'):
            if descriptor is None:
                continue
            if f"'Task': {parachain_id}" in str(descriptor.value):
                count += 1
    except Exception:
        # Storage shape differs between relay versions; treat as unknown.
        return 0
    return count


def setup_coretime(parachain_id, cores=None, duration=CORETIME_DURATION,
                   raise_on_exists=False, relay_url=RELAYCHAIN_WS_URL, start_core=0):
    """Assign relay coretime cores to `parachain_id` via sudo on a test relay.

    Returns the number of cores assigned (or already serving the parachain).
    With raise_on_exists=True an existing assignment raises instead of being
    treated as success. Only meaningful against a local/test relay where the
    global sudo key is root; never run this against a live network.
    """
    if cores is None:
        cores = PARACHAIN_CORE_MAP.get(parachain_id, CORETIME_CORES)

    relay = SubstrateInterface(url=relay_url)
    existing = _cores_assigned_to(relay, parachain_id)
    if existing:
        if raise_on_exists:
            raise RuntimeError(
                f'parachain {parachain_id} already has {existing} core(s) assigned')
        print(f'Coretime already set up for {parachain_id} ({existing} cores); skipping')
        return existing

    batch = ExtrinsicBatch(relay, KP_GLOBAL_SUDO)
    for i in range(cores):
        batch.compose_sudo_call('Coretime', 'assign_core', {
            'core': start_core + i,
            'begin': 0,
            'assignment': [({'Task': parachain_id}, duration)],
            'end_hint': None,
        })
    receipt = batch.execute()
    if not receipt:
        print(f'Warning: coretime assignment submission failed for {parachain_id}')
        return 0
    return cores
