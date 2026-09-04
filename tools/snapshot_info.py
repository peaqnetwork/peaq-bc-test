from substrateinterface import SubstrateInterface
from peaq.utils import get_chain, get_block_hash, get_block_height
import argparse
from argparse import RawDescriptionHelpFormatter

'''
python3 tools/snapshot_info.py -r peaq --compare-versions --compare-with 108
'''

import pprint
pp = pprint.PrettyPrinter(indent=4)

ENDPOINTS = {
    'peaq-dev': 'wss://wss-async.agung.peaq.network',
    'krest': 'wss://wss-krest.peaq.network',
    'peaq': 'wss://mpfn1.peaq.network',
    'docker': 'wss://docker-test.peaq.network',
    'local-test': 'ws://localhost:10044',
}


STORAGE_SKIP_LIST = {
    'AddressUnification': 'all',
    'Assets': 'all',
    'AuraExt': 'all',
    'Authorship': 'all',
    'Balances': 'all',
    'Contracts': ['PristineCode', 'CodeStorage', 'OwnerInfoOf', 'ContractInfoOf', 'DeletionQueue'],
    'Council': ['ProposalCount', 'ProposalOf', 'Proposals', 'Voting'],
    'DmpQueue': ['CounterForOverweight', 'PageIndex', 'Pages'],
    'EVM': ['AccountCodes', 'AccountStorages', 'AccountCodesMetadata'],
    'Ethereum': 'all',
    'Multisig': 'all',
    # We should check out collators in the TopCandidates
    'ParachainStaking': [
        'CandidatePool', 'DelegatorState', 'LastDelegation', 'TopCandidates', 'TotalCollatorStake',
        'Unstaking'],
    'ParachainSystem': [
        'LastDmqMqcHead', 'LastRelayChainBlockNumber', 'RelayStateProof', 'RelevantMessagingState', 'ValidationData'],
    'PeaqStorage': 'all',
    'PeaqDid': 'all',
    'PeaqRbac': 'all',
    'RandomnessCollectiveFlip': 'all',
    'Session': 'all',
    'System': 'all',
    'Timestamp': 'all',
    'Treasury': 'all',
    'Vesting': 'all',
    'TransactionPayment': 'all',
}

SHEET_INTERESTED_LIST = {
    'InflationManager::InflationConfiguration',
    'InflationManager::InflationParameters',
    'InflationManager::CurrentYear',
    'InflationManager::DoRecalculationAt',
    'InflationManager::DoInitializeAt',
    'InflationManager::TotalIssuanceNum',
    'InflationManager::BlockRewards',
    'ParachainStaking::MaxSelectedCandidates',
    'ParachainStaking::Round',
    'ParachainStaking::CounterForCandidatePool',
    'ParachainStaking::MaxCollatorCandidateStake',
    'ParachainStaking::ForceNewRound',
    'StakingCoefficientRewardCalculator::CoefficientConfig',
    # Skip Zenlink protocol
    # Skip XcAssetConfig,
    # Skip PeaqMor
    'Balances::ExistentialDeposit',
    'Balances::MaxLocks',
    'Balances::MaxReserves',
    'Balances::MaxFreezes',
    # Skip Contracts
    'Treasury::ProposalBond',
    'Treasury::ProposalBondMinimum',
    'Treasury::ProposalBondMaximum',
    'Treasury::SpendPeriod',
    'Treasury::Burn',
    'Treasury::MaxApprovals',
    'Treasury::PayoutPeriod',
    'InflationManager::DefaultTotalIssuanceNum',
    'InflationManager::DefaultInflationConfiguration',
    'InflationManager::BoundedDataLen',
    'ParachainStaking::MinBlocksPerRound',
    'ParachainStaking::DefaultBlocksPerRound',
    'ParachainStaking::StakeDuration',
    'ParachainStaking::ExitQueueDelay',
    'ParachainStaking::MinCollators',
    'ParachainStaking::MinRequiredCollators',
    'ParachainStaking::MaxDelegationsPerRound',
    'ParachainStaking::MaxDelegatorsPerCollator',
    'ParachainStaking::MaxCollatorsPerDelegator',
    'ParachainStaking::MaxTopCandidates',
    'ParachainStaking::MinCollatorStake',
    'ParachainStaking::MinCollatorCandidateStake',
    'ParachainStaking::MinDelegation',
    'ParachainStaking::MinDelegatorStake',
    'ParachainStaking::MaxUnstakeRequests',
    'Assets::RemoveItemsLimit',
    'Assets::AssetDeposit',
    'Assets::AssetAccountDeposit',
    'Assets::MetadataDepositBase',
    'Assets::MetadataDepositPerByte',
    'Assets::ApprovalDeposit',
    'Assets::StringLimit',
    'Vesting::MinVestedTransfer',
    'Vesting::MaxVestingSchedules',
    'PeaqDid::BoundedDataLen',
    'PeaqDid::StorageDepositBase',
    'PeaqDid::StorageDepositPerByte',
    'Multisig::DepositBase',
    'Multisig::DepositFactor',
    'Multisig::MaxSignatories',
    'PeaqRbac::BoundedDataLen',
    'PeaqRbac::StorageDepositBase',
    'PeaqRbac::StorageDepositPerByte',
    'PeaqStorage::BoundedDataLen',
    'PeaqStorage::StorageDepositBase',
    'PeaqStorage::StorageDepositPerByte',
    'BlockReward::RewardDistributionConfigStorage',
}


def query_storage(substrate, module, storage_function):
    try:
        result = substrate.query(
            module=module,
            storage_function=storage_function,
        )
        print(f'Querying data: {module}::{storage_function}: {result.value}')
        return result.value
    except ValueError:
        pass

    start_key = None
    batch_size = 1000
    out = {}
    while True:
        result = substrate.query_map(
            module=module,
            storage_function=storage_function,
            start_key=start_key,
            page_size=batch_size,
        )
        for k, v in result.records:
            key_str = str(getattr(k, 'value', k))
            out[key_str] = v.value
        if len(result.records) < batch_size:
            break
        start_key = result.last_key
    print(f'Querying map: {module}::{storage_function}: v.value')
    return out


def query_constant(substrate, module, storage_function):
    result = substrate.get_constant(
        module,
        storage_function,
    )

    if f'{module}::{storage_function}' in SHEET_INTERESTED_LIST:
        print(f'Show me the constant: {module}::{storage_function}: {result.value}')
    print(f'Querying constant: {module}::{storage_function}: {result.value}')
    return result.value


def is_storage_ignore(module, storage_function):
    if module not in STORAGE_SKIP_LIST:
        return False
    if STORAGE_SKIP_LIST[module] == 'all':
        return True
    if storage_function in STORAGE_SKIP_LIST[module]:
        return True
    return False


def count_variants(pallet_field):
    """Helper to count variants in pallet fields"""
    if not pallet_field:
        return 0
    return len(pallet_field.get('type', {}).get('def', {}).get('variant', {}).get('variants', []))


def count_storage_entries(storage_field):
    """Helper to count storage entries"""
    if not storage_field:
        return 0
    return len(storage_field.get('entries', []))


def extract_pallet_info(pallet):
    """Extract information from a single pallet"""
    return {
        'index': pallet.get('index', 0),
        'has_storage': bool(pallet.get('storage')),
        'has_calls': bool(pallet.get('calls')),
        'has_events': bool(pallet.get('event')),
        'has_errors': bool(pallet.get('error')),
        'num_constants': len(pallet.get('constants', [])),
        'num_storage_entries': count_storage_entries(pallet.get('storage')),
        'num_calls': count_variants(pallet.get('calls')),
        'num_events': count_variants(pallet.get('event')),
        'num_errors': count_variants(pallet.get('error')),
    }


def iterate_pallets(metadata):
    """Helper function to iterate through pallets in metadata"""
    return metadata.value[1]['V14']['pallets']


def get_module_versions(metadata):
    """Extract module information from metadata for comparison"""
    modules = {}
    for pallet in iterate_pallets(metadata):
        modules[pallet['name']] = extract_pallet_info(pallet)
    return modules


def find_runtime_version_block(substrate, target_version):
    """Find the last block of a specific runtime version using binary search"""
    low = 1
    high = get_block_height(substrate)

    if target_version < 1:
        return None

    # Binary search for the highest block with target version
    result = None
    while low <= high:
        mid = (low + high) // 2
        block_hash = get_block_hash(substrate, mid)
        try:
            version = substrate.get_block_runtime_version(block_hash)['specVersion']
            if version == target_version:
                result = mid
                low = mid + 1  # Look for higher blocks with same version
            elif version < target_version:
                low = mid + 1
            else:
                high = mid - 1
        except Exception as e:
            print(f"Error getting version at block {mid}: {e}")
            high = mid - 1

    return result


def get_metadata_at_block(substrate, block_number):
    """Get metadata at a specific block"""
    if block_number is None:
        return None

    block_hash = get_block_hash(substrate, block_number)
    try:
        # Get the metadata at specific block
        return substrate.get_block_metadata(block_hash)
    except Exception as e:
        print(f"Error getting metadata at block {block_number}: {e}")
        return None


def compare_field_values(current_info, prev_info, field_mappings):
    """Compare field values and return differences"""
    differences = []
    for field_key, display_name in field_mappings.items():
        if current_info[field_key] != prev_info[field_key]:
            differences.append(f"{display_name}: {prev_info[field_key]} → {current_info[field_key]}")
    return differences


def compare_module_info(current_info, prev_info):
    """Compare two module info dictionaries and return differences"""
    # Define field mappings for numeric comparisons
    numeric_fields = {
        'index': 'index',
        'num_calls': 'calls',
        'num_storage_entries': 'storage',
        'num_events': 'events',
        'num_errors': 'errors',
        'num_constants': 'constants'
    }

    # Define field mappings for capability comparisons
    capability_fields = {
        'has_storage': 'storage',
        'has_calls': 'calls',
        'has_events': 'events',
        'has_errors': 'errors'
    }

    differences = compare_field_values(current_info, prev_info, numeric_fields)
    caps_changed = compare_field_values(current_info, prev_info, capability_fields)

    return differences, caps_changed


def compare_module_versions(current_modules, previous_modules):
    """Compare module information and identify changes"""
    if not previous_modules:
        return {
            'updated': [],
            'added': list(current_modules.keys()),
            'removed': [],
            'details': {}
        }

    changes = {
        'updated': [],
        'added': [],
        'removed': [],
        'details': {}
    }

    # Check for updated and new modules
    for module, info in current_modules.items():
        if module in previous_modules:
            prev_info = previous_modules[module]
            differences, caps_changed = compare_module_info(info, prev_info)

            if differences or caps_changed:
                changes['updated'].append(module)
                changes['details'][module] = {
                    'changes': differences,
                    'capability_changes': caps_changed
                }
        else:
            changes['added'].append(module)

    # Check for removed modules
    for module in previous_modules:
        if module not in current_modules:
            changes['removed'].append(module)

    return changes


def get_all_storage(substrate, metadata, out, interested_out):
    for pallet in iterate_pallets(metadata):
        if not pallet['storage']:
            continue

        out[pallet['name']] = {}
        for entry in pallet['storage']['entries']:
            if is_storage_ignore(pallet['name'], entry['name']):
                out[pallet['name']][entry['name']] = 'ignored'
                continue
            data = query_storage(substrate, pallet['name'], entry['name'])
            if f'{pallet["name"]}::{entry["name"]}' in interested_out:
                interested_out[f'{pallet["name"]}::{entry["name"]}'] = data

            out[pallet['name']][entry['name']] = data

    return out


def get_all_constants(substrate, metadata, out, interested_out):
    for pallet in iterate_pallets(metadata):
        if not pallet['constants']:
            continue

        out[pallet['name']] = {}
        for entry in pallet['constants']:
            data = query_constant(substrate, pallet['name'], entry['name'])
            if f'{pallet["name"]}::{entry["name"]}' in SHEET_INTERESTED_LIST:
                interested_out[f'{pallet["name"]}::{entry["name"]}'] = data
            out[pallet['name']][entry['name']] = data

    return out


def get_constants_from_metadata(substrate, metadata):
    """Extract constants directly from metadata using unified decoder"""
    constants = {}
    for pallet in iterate_pallets(metadata):
        if not pallet['constants']:
            continue

        for entry in pallet['constants']:
            key = f"{pallet['name']}::{entry['name']}"
            constants[key] = decode_constant_value(substrate, pallet['name'], entry, metadata)

    return constants


def decode_constant_value(substrate, pallet_name, entry, metadata):
    """Unified constant value decoder with fallback strategies"""
    # Primary: Use substrate interface with metadata
    try:
        constant = substrate.get_constant(pallet_name, entry['name'], metadata=metadata)
        if constant:
            return constant.value

        # Secondary: Scale codec decoding if substrate interface fails
        from scalecodec import ScaleBytes
        from scalecodec.base import RuntimeConfiguration

        type_id = entry.get('type')
        raw_value = entry.get('value')

        if raw_value and type_id is not None:
            runtime_config = RuntimeConfiguration()
            runtime_config.update_type_registry(metadata.portable_registry)

            obj = runtime_config.create_scale_object(
                type_id=type_id,
                data=ScaleBytes(raw_value),
                metadata=metadata
            )

            if obj:
                return obj.decode()

    except Exception:
        pass

    # Fallback: Return raw value
    return entry.get('value')


def normalize_value(val):
    """Convert various value formats to comparable forms"""
    try:
        if isinstance(val, str) and val.startswith('0x'):
            hex_str = val[2:]
            if len(hex_str) % 2 == 1:
                hex_str = '0' + hex_str
            bytes_val = bytes.fromhex(hex_str)
            return int.from_bytes(bytes_val, byteorder='little')
        elif isinstance(val, str) and len(val) == 1:
            return ord(val)
        elif isinstance(val, bytes):
            return int.from_bytes(val, byteorder='little')
    except Exception:
        pass

    return val


def perform_runtime_comparison(substrate, metadata, current_runtime_version, target_version, interested_out):
    """Perform the complete runtime comparison and return results"""
    print_progress("Comparing runtime versions...")
    print(f"Current runtime version: {current_runtime_version}")
    print(f"Comparing with version: {target_version}")

    # Get current module versions
    current_module_versions = get_module_versions(metadata)

    # Find target runtime block
    previous_block = find_runtime_version_block(substrate, target_version)

    if not previous_block:
        return {
            'module_versions': {
                'current': current_module_versions,
                'note': f'Runtime version {target_version} not found'
            },
            'constants_changes': None
        }

    print(f"Found target runtime at block {previous_block}")

    # Get previous metadata and versions
    previous_metadata = get_metadata_at_block(substrate, previous_block)

    if not previous_metadata:
        return {
            'module_versions': {
                'current': current_module_versions,
                'error': 'Could not retrieve target runtime metadata'
            },
            'constants_changes': None
        }

    previous_module_versions = get_module_versions(previous_metadata)
    version_changes = compare_module_versions(current_module_versions, previous_module_versions)

    # Get constants from both versions
    print_progress("Comparing constants and storage values...")
    current_constants = get_constants_from_metadata(substrate, metadata)
    previous_constants = get_constants_from_metadata(substrate, previous_metadata)

    # Filter to only interested items (constants only, not storage)
    current_interested = {k: v for k, v in current_constants.items() if k in SHEET_INTERESTED_LIST}
    previous_interested = {k: v for k, v in previous_constants.items() if k in SHEET_INTERESTED_LIST}

    # Compare constants
    constants_changes = compare_constants_and_storage(current_interested, previous_interested)

    version_comparison_data = {
        'current': current_module_versions,
        'previous': previous_module_versions,
        'previous_runtime_version': target_version,
        'previous_runtime_block': previous_block,
        'changes': version_changes
    }

    return {
        'module_versions': version_comparison_data,
        'constants_changes': constants_changes
    }


def compare_constants_and_storage(current_data, previous_data):
    """Compare constants and storage values between versions"""
    changes = {
        'constants': {
            'updated': [],
            'added': [],
            'removed': []
        }
    }

    # Only compare items in SHEET_INTERESTED_LIST
    for key in SHEET_INTERESTED_LIST:
        current_val = current_data.get(key)
        previous_val = previous_data.get(key)

        # Normalize values for comparison and display
        current_normalized = normalize_value(current_val)
        previous_normalized = normalize_value(previous_val)

        if current_normalized != previous_normalized:
            if previous_val is None:
                changes['constants']['added'].append({
                    'key': key,
                    'value': current_normalized
                })
            elif current_val is None:
                changes['constants']['removed'].append({
                    'key': key,
                    'value': previous_normalized
                })
            else:
                changes['constants']['updated'].append({
                    'key': key,
                    'old': previous_normalized,
                    'new': current_normalized
                })

    return changes


def save_outputs(out, interested_out, args, substrate):
    """Save outputs to files if requested"""
    pp.pprint(out)

    if args.folder:
        filepath = f'{args.folder}/{args.runtime}.{substrate.runtime_version}'
        with open(filepath, 'w') as f:
            f.write(pp.pformat(out))

    pp.pprint(interested_out)

    if args.sheet:
        filepath = f'{args.folder}/{args.runtime}.{substrate.runtime_version}.sheet'
        with open(filepath, 'w') as f:
            keys = list(interested_out.keys())
            keys = sorted(keys)
            for k in keys:
                f.write(f'{k}-{interested_out[k]}\n')
        print(f'Wrote to {filepath}')


def print_progress(message, level="info"):
    """Centralized progress printing with optional levels"""
    icons = {
        "info": "🔍",
        "success": "✅",
        "warning": "⚠️",
        "error": "❌",
        "data": "📊"
    }
    icon = icons.get(level, "")
    if icon:
        print(f"{icon} {message}")
    else:
        print(message)


def _display_header(version_comparison_data, current_runtime_version):
    """Display comparison summary header"""
    print(f"\n{'='*80}")
    print_progress("RUNTIME VERSION COMPARISON SUMMARY", "data")
    print(f"{'='*80}")
    print(f"Current Runtime Version: {current_runtime_version}")
    print(f"Compared with Version: {version_comparison_data['previous_runtime_version']}")
    print(f"Compared Version Block: {version_comparison_data['previous_runtime_block']}")
    print(f"{'='*80}")


def _display_updated_modules(version_changes):
    """Display updated modules section"""
    if not version_changes['updated']:
        return

    print(f"\n✏️  Updated modules ({len(version_changes['updated'])} modules):")
    for module in version_changes['updated']:
        print(f"   📦 {module}:")
        details = version_changes['details'][module]
        if details['changes']:
            for change in details['changes']:
                print(f"      • {change}")
        if details['capability_changes']:
            print("      Capability changes:")
            for change in details['capability_changes']:
                print(f"      • {change}")


def _display_module_changes(version_changes):
    """Display module structure changes"""
    print("\n📦 MODULE STRUCTURE CHANGES:")
    print("-" * 40)

    _display_updated_modules(version_changes)

    if version_changes['added']:
        print(f"\n➕ Added modules ({len(version_changes['added'])} modules):")
        for module in version_changes['added']:
            print(f"   • {module}")

    if version_changes['removed']:
        print(f"\n➖ Removed modules ({len(version_changes['removed'])} modules):")
        for module in version_changes['removed']:
            print(f"   • {module}")

    if not any([version_changes['updated'], version_changes['added'], version_changes['removed']]):
        print_progress("No module structure changes detected", "success")


def _display_constants_changes(constants_comparison_data):
    """Display constants and storage changes"""
    if not constants_comparison_data:
        return

    print("\n💾 CONSTANTS & STORAGE VALUE CHANGES:")
    print("-" * 40)

    const_changes = constants_comparison_data['constants']
    has_const_changes = False

    if const_changes['updated']:
        has_const_changes = True
        print(f"\n✏️  Updated values ({len(const_changes['updated'])} items):")
        for item in const_changes['updated']:
            print(f"\n   📝 {item['key']}:")
            print(f"      Old: {item['old']}")
            print(f"      New: {item['new']}")

    if const_changes['added']:
        has_const_changes = True
        print(f"\n➕ Added values ({len(const_changes['added'])} items):")
        for item in const_changes['added']:
            print(f"   • {item['key']}: {item['value']}")

    if const_changes['removed']:
        has_const_changes = True
        print(f"\n➖ Removed values ({len(const_changes['removed'])} items):")
        for item in const_changes['removed']:
            print(f"   • {item['key']}: {item['value']}")

    if not has_const_changes:
        print_progress("No constants or storage value changes detected", "success")


def display_comparison_summary(version_comparison_data, constants_comparison_data, current_runtime_version):
    """Display the comparison summary at the end"""
    if not version_comparison_data:
        return

    version_changes = version_comparison_data['changes']
    _display_header(version_comparison_data, current_runtime_version)
    _display_module_changes(version_changes)
    _display_constants_changes(constants_comparison_data)
    print(f"\n{'='*80}\n")


def setup_argument_parser():
    """Setup and configure command line argument parser"""
    parser = argparse.ArgumentParser(
        formatter_class=RawDescriptionHelpFormatter,
        description='''
        Get storage and constants from a Substrate chain
        python3 snapshot_info.py -r peaq-dev --sheet
        '''
    )
    parser.add_argument(
        '-r', '--runtime', type=str, required=True,
        help='Your runtime websocket endpoint. however,'
             'some keys will automatically convert it to the correct endpoint: e.g.'
             f'{pp.pformat(ENDPOINTS)}')
    parser.add_argument(
        '-s', '--storage', type=bool, default=False,
        help='The storage function to query'
    )
    parser.add_argument(
        '-f', '--folder', type=str, default='tools/snapshot',
        help='The output folder to write the data to'
    )
    parser.add_argument(
        '--sheet', default=False,
        action="store_true",
        help='The output folder to sheet format'
    )
    parser.add_argument(
        '--compare-versions', default=False,
        action="store_true",
        help='Compare module versions with previous runtime version'
    )
    parser.add_argument(
        '--compare-with', type=int,
        help='Specific runtime version to compare with (default: previous version)'
    )
    return parser


def setup_substrate_connection(args):
    """Setup substrate connection and return substrate interface and metadata"""
    runtime = args.runtime
    if args.runtime in ENDPOINTS:
        runtime = ENDPOINTS[args.runtime]

    substrate = SubstrateInterface(url=runtime)
    metadata = substrate.get_metadata()

    return substrate, metadata


def collect_baseline_data(substrate, metadata):
    """Collect baseline storage and constants data"""
    current_runtime_version = substrate.runtime_version
    out = {
        'chain': {
            'name': get_chain(substrate),
            'version': current_runtime_version,
        },
        'constants': {},
        'storage': {},
    }

    interested_out = {k: None for k in SHEET_INTERESTED_LIST}
    get_all_storage(substrate, metadata, out['storage'], interested_out)
    get_all_constants(substrate, metadata, out['constants'], interested_out)

    return out, interested_out, current_runtime_version


def determine_comparison_target(args, current_runtime_version):
    """Determine which runtime version to compare with"""
    if args.compare_with:
        target_version = args.compare_with
        if target_version >= current_runtime_version:
            print_progress(f"Cannot compare with version {target_version} (current version is {current_runtime_version})", "warning")
            return None
        return target_version
    else:
        return current_runtime_version - 1


def handle_version_comparison(args, substrate, metadata, current_runtime_version, interested_out, out):
    """Handle runtime version comparison if requested"""
    if not args.compare_versions:
        return None, None

    target_version = determine_comparison_target(args, current_runtime_version)
    if not target_version:
        return None, None

    comparison_results = perform_runtime_comparison(
        substrate, metadata, current_runtime_version, target_version, interested_out
    )

    version_comparison_data = comparison_results['module_versions']
    constants_comparison_data = comparison_results['constants_changes']

    out['module_versions'] = version_comparison_data
    if constants_comparison_data:
        out['constants_changes'] = constants_comparison_data

    return version_comparison_data, constants_comparison_data


def main():
    """Main execution function"""
    parser = setup_argument_parser()
    args = parser.parse_args()

    substrate, metadata = setup_substrate_connection(args)
    out, interested_out, current_runtime_version = collect_baseline_data(substrate, metadata)

    version_comparison_data, constants_comparison_data = handle_version_comparison(
        args, substrate, metadata, current_runtime_version, interested_out, out
    )

    save_outputs(out, interested_out, args, substrate)

    if args.compare_versions:
        display_comparison_summary(version_comparison_data, constants_comparison_data, current_runtime_version)


if __name__ == '__main__':
    main()
