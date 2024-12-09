from substrateinterface import SubstrateInterface
from peaq.utils import get_chain
import argparse
from argparse import RawDescriptionHelpFormatter


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
            try:
                out[str(k.value)] = v.value
            except AttributeError:
                out[str(k)] = v.value
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


def get_all_storage(substrate, metadata, out, interested_out):
    for pallet in metadata.value[1]['V14']['pallets']:
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
    for pallet in metadata.value[1]['V14']['pallets']:
        if not pallet['constants']:
            continue

        out[pallet['name']] = {}
        for entry in pallet['constants']:
            data = query_constant(substrate, pallet['name'], entry['name'])
            if f'{pallet["name"]}::{entry["name"]}' in SHEET_INTERESTED_LIST:
                interested_out[f'{pallet["name"]}::{entry["name"]}'] = data
            out[pallet['name']][entry['name']] = data

    return out


if __name__ == '__main__':
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

    args = parser.parse_args()
    runtime = args.runtime
    if args.runtime in ENDPOINTS:
        runtime = ENDPOINTS[args.runtime]

    substrate = SubstrateInterface(
        url=runtime,
    )
    metadata = substrate.get_metadata()
    out = {
        'chain': {
            'name': get_chain(substrate),
            'version': substrate.runtime_version,
        },
        'constants': {},
        'storage': {},
    }

    interested_out = {k: None for k in SHEET_INTERESTED_LIST}
    get_all_storage(substrate, metadata, out['storage'], interested_out)
    get_all_constants(substrate, metadata, out['constants'], interested_out)

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
