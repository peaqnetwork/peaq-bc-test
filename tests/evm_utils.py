from tools import peaq_eth_utils as PeaqEthUtils
from eth_utils import function_abi_to_4byte_selector
import os
import json
import datetime
from tools.constants import PARACHAIN_ETH_URL

evm_all_fee_data = {}
func_selector_dict = {}


def load_all_function(folder, abi):
    function_dict = {}
    for item in abi:
        if item["type"] != "function":
            continue
        selector = f'0x{function_abi_to_4byte_selector(item).hex()}'
        function_dict[selector] = f'{folder}.{item["name"]}'
    return function_dict


def load_all_abi():
    # traverse ETH/*/abi files
    folders = os.listdir("ETH")
    for folder in folders:
        if folder == ".pytest_cache":
            continue
        with open(os.path.join('ETH', folder, 'abi')) as f:
            abi = json.load(f)
        for k, v in load_all_function(folder, abi).items():
            func_selector_dict[k] = v


def compose_batch_function_name(w3, input_data):
    batch_abi = json.load(open('ETH/batch/abi'))

    batch = w3.eth.contract(address='0x0000000000000000000000000000000000000805', abi=batch_abi)
    func_name, args = batch.decode_function_input(input_data)
    inner_func_names = []
    for call_data in args['callData']:
        function_selector = "0x" + call_data.hex()[:8]
        if function_selector not in func_selector_dict:
            inner_func_names.append(f'Unknown.{function_selector}')
        else:
            inner_func_names.append(func_selector_dict[function_selector])
    return f"({','.join(inner_func_names)})"


def compose_function_name(w3, tx):
    if 'data' not in tx:
        return 'Transfer'
    input_data = tx['data']
    function_selector = input_data[:10]
    if function_selector not in func_selector_dict:
        return f'Unknown.{function_selector}'

    name = func_selector_dict[function_selector]
    if name.startswith('batch'):
        inner_name = compose_batch_function_name(w3, input_data)
        name += inner_name

    return name


def sign_and_submit_evm_transaction(tx, w3, signer):
    receipt = PeaqEthUtils.sign_and_submit_evm_transaction(tx, w3, signer)
    gas_used = receipt['gasUsed']
    effective_gas_price = receipt['effectiveGasPrice']

    if w3.provider.endpoint_uri != PARACHAIN_ETH_URL:
        return receipt

    if not func_selector_dict:
        load_all_abi()

    name = compose_function_name(w3, tx)
    fee = int(w3.from_wei(gas_used * effective_gas_price, 'wei'))
    if name not in evm_all_fee_data:
        evm_all_fee_data[name] = []
    evm_all_fee_data[name].append({
        'fee': fee,
    })

    return receipt


def generate_evm_fee_report():
    # get date by format "YYYY-MM-DD-HH-MM"
    now = datetime.datetime.now()
    date = now.strftime("%Y-%m-%d-%H-%M")

    folder = "reports"
    report_file = f"evm_fee_summary_{date}.json"

    if not os.path.exists(folder):
        os.makedirs(folder)

    report_path = os.path.join(folder, report_file)
    summary_data = process_fee_data()
    with open(report_path, "w") as f:
        json.dump(summary_data, f, indent=4)

    print('')
    print(f"EVM fee data saved to {report_path}")


def process_fee_data():
    summary_data = {}
    for extrinsic_name, data in evm_all_fee_data.items():
        summary_data[extrinsic_name] = {
            'fee': sum([d['fee'] for d in data]) / len(data),
            'len': len(data)
        }
    return summary_data
