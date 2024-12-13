import pytest  # noqa: F401
import importlib
import sys
import tools.utils  # noqa: F401
from substrateinterface import SubstrateInterface
import os
import datetime
import json

old_submit_extrinsic = SubstrateInterface.submit_extrinsic
all_weight_fee_data = {}


def compose_extrinsic_name(call):
    module = call['call_module']
    function = call['call_function']
    extrinsic_name = f'{module}.{function}'
    if module != 'Utility' and function != 'batch_all':
        return extrinsic_name

    inner_names = [compose_extrinsic_name(call) for call in call['call_args'][0]['value']]
    extrinsic_name += f'({", ".join(inner_names)})'

    return extrinsic_name


def get_transaction_fee(substrate, extrinsic_idx, block_hash):
    events = substrate.get_events(block_hash)
    for event in events:
        if event.value['extrinsic_idx'] != extrinsic_idx:
            continue
        if event.value['module_id'] != 'TransactionPayment' or \
           event.value['event_id'] != 'TransactionFeePaid':
            continue
        return event['event'][1][1].value['actual_fee'] - event['event'][1][1].value['tip']


def get_transaction_weight(substrate, extrinsic_idx, block_hash):
    events = substrate.get_events(block_hash)

    for event in events:
        if event.value['extrinsic_idx'] != extrinsic_idx:
            continue
        if event.value['module_id'] != 'System' or \
           event.value['phase'] != 'ApplyExtrinsic' or \
           'dispatch_info' not in event.value['attributes']:
            continue
        # We didn't check event_id because it might be extrnisic error
        return event.value['attributes']['dispatch_info']['weight']['ref_time']


def monkey_submit_extrinsic_for_fee_weight(self, extrinsic, wait_for_inclusion, wait_for_finalization):
    receipt = old_submit_extrinsic(self, extrinsic, wait_for_inclusion, wait_for_finalization)

    block_hash = receipt.block_hash
    block = self.get_block(block_hash)
    for extrinsic in block['extrinsics']:
        if f'0x{extrinsic.extrinsic_hash.hex()}' != receipt.extrinsic_hash:
            continue
        name = compose_extrinsic_name(extrinsic.value['call'])
        fee = get_transaction_fee(self, receipt.extrinsic_idx, block_hash)
        weight = get_transaction_weight(self, receipt.extrinsic_idx, block_hash)
        if name in all_weight_fee_data:
            all_weight_fee_data[name].append({
                'fee': fee,
                'weight': weight
            })
        else:
            all_weight_fee_data[name] = [{
                'fee': fee,
                'weight': weight
            }]

        break
    else:
        raise Exception('Extrinsic not found in the block')

    return receipt


SubstrateInterface.submit_extrinsic = monkey_submit_extrinsic_for_fee_weight


def pytest_runtest_setup(item):
    # For the monkey patching to work, the module must be reloaded
    # Avoid the dependency on the module name
    if 'substrateinterface' in sys.modules:
        importlib.reload(sys.modules['substrateinterface'])
    if 'peaq.utils' in sys.modules:
        importlib.reload(sys.modules['peaq.utils'])


def process_weight_fee_data():
    summary_data = {}
    for extrinsic_name, data in all_weight_fee_data.items():
        summary_data[extrinsic_name] = {
            'fee': sum([d['fee'] for d in data]) / len(data),
            'weight': sum([d['weight'] for d in data]) / len(data),
            'len': len(data)
        }
    return summary_data


def pytest_sessionfinish(session, exitstatus):
    # get date by format "YYYY-MM-DD-HH-MM"
    now = datetime.datetime.now()
    date = now.strftime("%Y-%m-%d-%H-%M")

    folder = "reports"
    report_file = f"weight_fee_summary_{date}.json"

    if not os.path.exists(folder):
        os.makedirs(folder)

    report_path = os.path.join(folder, report_file)
    summary_data = process_weight_fee_data()
    with open(report_path, "w") as f:
        json.dump(summary_data, f, indent=4)

    print('')
    print(f"Weight/fee data saved to {report_path}")
