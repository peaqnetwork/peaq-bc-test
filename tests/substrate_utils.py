import tools.utils  # noqa: F401
from substrateinterface import SubstrateInterface
import os
import datetime
import json
from tools.constants import PARACHAIN_WS_URL

old_submit_extrinsic = SubstrateInterface.submit_extrinsic
substrate_all_weight_fee_data = {}


def compose_extrinsic_name(call):
    module = call['call_module']
    function = call['call_function']
    extrinsic_name = f'{module}.{function}'
    if module == 'Sudo' and function == 'sudo':
        inner_call = call['call_args'][0]['value']
        composed_inner_name = compose_extrinsic_name(inner_call)
        return f'[Sudo.sudo.{composed_inner_name}]'
    if module != 'Utility' and function != 'batch_all':
        return extrinsic_name

    inner_names = [compose_extrinsic_name(call) for call in call['call_args'][0]['value']]
    extrinsic_name += f'({",".join(inner_names)})'

    return extrinsic_name


def get_transaction_fee(substrate, extrinsic_idx, block_hash):
    events = substrate.get_events(block_hash)
    for event in events:
        if event.value['extrinsic_idx'] != extrinsic_idx:
            continue
        if event.value['module_id'] != 'TransactionPayment' or \
           event.value['event_id'] != 'TransactionFeePaid':
            continue
        return event['event'][1][1].value['actual_fee'], event['event'][1][1].value['tip']


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
    if self.url != PARACHAIN_WS_URL:
        return receipt

    block_hash = receipt.block_hash
    block = self.get_block(block_hash)
    for extrinsic in block['extrinsics']:
        if f'0x{extrinsic.extrinsic_hash.hex()}' != receipt.extrinsic_hash:
            continue
        name = compose_extrinsic_name(extrinsic.value['call'])
        fee, tip = get_transaction_fee(self, receipt.extrinsic_idx, block_hash)
        weight = get_transaction_weight(self, receipt.extrinsic_idx, block_hash)
        if name not in substrate_all_weight_fee_data:
            substrate_all_weight_fee_data[name] = []

        substrate_all_weight_fee_data[name].append({
            'fee': fee,
            'tip': tip,
            'weight': weight
        })

        break
    else:
        raise Exception('Extrinsic not found in the block')

    return receipt


def generate_substrate_weight_fee_report():
    # get date by format "YYYY-MM-DD-HH-MM"
    now = datetime.datetime.now()
    date = now.strftime("%Y-%m-%d-%H-%M")

    folder = "reports"
    report_file = f"substrate_weight_fee_summary_{date}.json"

    if not os.path.exists(folder):
        os.makedirs(folder)

    report_path = os.path.join(folder, report_file)
    summary_data = process_weight_fee_data()
    with open(report_path, "w") as f:
        json.dump(summary_data, f, indent=4)

    print('')
    print(f"Weight/fee data saved to {report_path}")


def process_weight_fee_data():
    summary_data = {}
    for extrinsic_name, data in substrate_all_weight_fee_data.items():
        summary_data[extrinsic_name] = {
            'fee': sum([d['fee'] for d in data]) / len(data),
            'weight': sum([d['weight'] for d in data]) / len(data),
            'tip': sum([d['tip'] for d in data]) / len(data),
            'len': len(data)
        }
    return summary_data
