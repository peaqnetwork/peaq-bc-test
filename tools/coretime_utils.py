#!/usr/bin/env python3

from substrateinterface import SubstrateInterface
from tools.constants import PARACHAIN_WS_URL, RELAYCHAIN_WS_URL, KP_GLOBAL_SUDO, CORETIME_CORES, CORETIME_DURATION, PARACHAIN_CORE_MAP
from peaq.utils import ExtrinsicBatch


def get_parachain_id(parachain_url=PARACHAIN_WS_URL):
    """Get the parachain ID from the parachain instance"""
    substrate = SubstrateInterface(url=parachain_url)

    # Query parachain ID
    para_id = substrate.query(
        module='ParachainInfo',
        storage_function='ParachainId'
    )

    return para_id.value if para_id else None


def check_coretime_assigned(substrate, cores):
    """Check if coretime is already assigned by querying coreDescriptor"""
    assigned_cores = []
    for core in range(cores):
        try:
            # Query the CoretimeAssignmentProvider.CoreDescriptors storage
            result = substrate.query(
                module='CoretimeAssignmentProvider',
                storage_function='CoreDescriptors',
                params=[core]
            )

            # If result has value, core is assigned
            if result and result.value:
                assigned_cores.append(core)
        except Exception:
            # If query fails, assume core is not assigned
            continue

    return assigned_cores


def setup_coretime(parachain_id, cores=None, duration=CORETIME_DURATION, raise_on_exists=False, relay_url=RELAYCHAIN_WS_URL, start_core=0):
    """Setup coretime for parachain using sudo with ExtrinsicBatch for multiple cores

    Args:
        parachain_id: The parachain ID to assign cores to
        cores: Number of cores to assign (auto-determined from parachain ID if None)
        duration: Duration for coretime assignment
        raise_on_exists: If True, raise exception if coretime already assigned
        relay_url: Relay chain URL for sudo operations
        start_core: Starting core index (default 0)

    Returns:
        int: Number of cores assigned, or 0 on failure
    """
    if parachain_id is None:
        print("Skipping coretime setup: no parachain ID")
        return 0

    # Determine core count based on parachain ID if not specified
    if cores is None:
        cores = PARACHAIN_CORE_MAP.get(parachain_id, CORETIME_CORES)
        print(f"Auto-determined {cores} cores for parachain {parachain_id}")

    # Connect to relay chain for sudo operations with rococo type registry
    substrate = SubstrateInterface(url=relay_url, type_registry_preset='rococo')

    # Check if any cores in our range are already assigned
    end_core = start_core + cores
    assigned_cores = check_coretime_assigned(substrate, end_core)
    cores_to_assign = [c for c in range(start_core, end_core) if c not in assigned_cores]

    if not cores_to_assign:
        if raise_on_exists:
            raise ValueError(f"All cores {start_core}-{end_core-1} already assigned. Aborting to prevent duplicate assignment.")
        else:
            print(f"All cores {start_core}-{end_core-1} already assigned. Skipping setup.")
            return 0

    # Get current block number
    current_block = substrate.get_block_number(None)

    # Prepare the assignment - (CoreAssignment, duration) tuple
    assignment = [({"Task": parachain_id}, duration)]

    # Use ExtrinsicBatch for sudo call
    batch = ExtrinsicBatch(substrate, KP_GLOBAL_SUDO)

    # Add assignCore calls for cores that need assignment
    for core in cores_to_assign:
        batch.compose_sudo_call(
            'Coretime',
            'assign_core',
            {
                'core': core,
                'begin': current_block,
                'assignment': assignment,
                'end_hint': None
            }
        )

    # Execute all assignCore calls in a single batch
    receipt = batch.execute()

    if receipt.is_success:
        print(f"Successfully assigned coretime for parachain {parachain_id}")
        print(f"  Cores: {cores_to_assign}, Begin block: {current_block}, Duration: {duration}")
        return len(cores_to_assign)
    else:
        print(f"Coretime assignment failed: {receipt.error_message}")
        return 0
