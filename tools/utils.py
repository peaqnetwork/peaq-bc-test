import sys
import time
sys.path.append('./')

from dataclasses import dataclass
from substrateinterface import SubstrateInterface, Keypair
from substrateinterface.utils import hasher, ss58
from scalecodec.base import RuntimeConfiguration
from scalecodec.type_registry import load_type_registry_preset

from scalecodec.utils.ss58 import ss58_encode

# Monkey patch
from scalecodec.types import FixedLengthArray
from tools.monkey_patch_scale_info import process_encode as new_process_encode
FixedLengthArray.process_encode = new_process_encode

TOKEN_NUM_BASE = pow(10, 3)
TOKEN_NUM_BASE_DEV = pow(10, 18)
STANDALONE_WS_URL = 'ws://127.0.0.1:9944'
RELAYCHAIN_WS_URL = 'ws://127.0.0.1:9944'
RELAYCHAIN_ETH_URL = 'http://127.0.0.1:9933'
PARACHAIN_WS_URL = 'ws://127.0.0.1:9947'
PARACHAIN_ETH_URL = "http://127.0.0.1:9936"
# PARACHAIN_WS_URL = 'wss://wsspc1.agung.peaq.network'
# PARACHAIN_ETH_URL = "https://rpcpc1.agung.peaq.network"
# WS_URL = 'ws://127.0.0.1:9944'
# ETH_URL = "http://127.0.0.1:9933"
WS_URL = PARACHAIN_WS_URL
ETH_URL = PARACHAIN_ETH_URL
# WS_URL = 'ws://192.168.178.23:9944'
# ETH_URL = "http://192.168.178.23:9933"
# WS_URL = "wss://wss.test.peaq.network"
# ETH_URL = "https://erpc.test.peaq.network:443"
PEAQ_DEV_CHAIN_ID = 9999
AGUNG_CHAIN_ID = 9999
KREST_CHAIN_ID = 424242
PEAQ_CHAIN_ID = 424242

ETH_CHAIN_ID = PEAQ_DEV_CHAIN_ID

import pprint
pp = pprint.PrettyPrinter(indent=4)


SCALE_CODEC = {
    "Address": "MultiAddress",
    "LookupSource": "MultiAddress",
    "Account": {
        "nonce": "U256",
        "balance": "U256"
    },
    "Transaction": {
        "nonce": "U256",
        "action": "String",
        "gas_price": "u64",
        "gas_limit": "u64",
        "value": "U256",
        "input": "Vec<u8>",
        "signature": "Signature"
    },
    "Signature": {
        "v": "u64",
        "r": "H256",
        "s": "H256"
    }
}


def show_extrinsic(receipt, info_type):
    if receipt.is_success:
        print(f'🚀 {info_type}, Success: {receipt.get_extrinsic_identifier()}')
    else:
        print(f'💥 {info_type}, Extrinsic Failed: {receipt.error_message} {receipt.get_extrinsic_identifier()}')


def show_test(name, success, line=0):
    if success:
        print(f'✅ Test/{name}, Passed')
    else:
        if line != 0:
            print(f'🔥 Test/{name}, Failed in line {line}')
        else:
            print(f'🔥 Test/{name}, Failed')


def show_title(name):
    print(f'\n========== {name} ==========')


def calculate_multi_sig(kps, threshold):
    '''https://github.com/polkascan/py-scale-codec/blob/f063cfd47c836895886697e7d7112cbc4e7514b3/test/test_scale_types.py#L383'''

    addrs = [kp.ss58_address for kp in kps]
    RuntimeConfiguration().update_type_registry(load_type_registry_preset("legacy"))
    multi_account_id = RuntimeConfiguration().get_decoder_class("MultiAccountId")

    multi_sig_account = multi_account_id.create_from_account_list(addrs, threshold)
    print(multi_sig_account)
    return ss58_encode(multi_sig_account.value.replace('0x', ''), 42)


def deposit_money_to_multsig_wallet(substrate, kp_consumer, kp_provider, token_num):
    print('----- Consumer deposit money to multisig wallet')
    threshold = 2
    signators = [kp_consumer, kp_provider]
    multi_sig_addr = calculate_multi_sig(signators, threshold)
    call = substrate.compose_call(
        call_module='Balances',
        call_function='transfer',
        call_params={
            'dest': multi_sig_addr,
            'value': token_num * TOKEN_NUM_BASE
        })

    nonce = substrate.get_account_nonce(kp_consumer.ss58_address)
    extrinsic = substrate.create_signed_extrinsic(
        call=call,
        keypair=kp_consumer,
        era={'period': 64},
        nonce=nonce
    )

    receipt = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
    show_extrinsic(receipt, 'transfer')


def send_service_request(substrate, kp_consumer, kp_provider, token_num):
    print('----- Consumer sends the serviice requested to peaq-transaction')
    nonce = substrate.get_account_nonce(kp_consumer.ss58_address)
    call = substrate.compose_call(
        call_module='PeaqTransaction',
        call_function='service_requested',
        call_params={
            'provider': kp_provider.ss58_address,
            'token_deposited': token_num * TOKEN_NUM_BASE
        })

    extrinsic = substrate.create_signed_extrinsic(
        call=call,
        keypair=kp_consumer,
        era={'period': 64},
        nonce=nonce
    )

    receipt = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
    show_extrinsic(receipt, 'service_requested')


def send_spent_token_from_multisig_wallet(substrate, kp_consumer, kp_provider, token_num, threshold):
    print('----- Provider asks the spent token')
    payload = substrate.compose_call(
        call_module='Balances',
        call_function='transfer',
        call_params={
            'dest': kp_provider.ss58_address,
            'value': token_num * TOKEN_NUM_BASE
        })

    nonce = substrate.get_account_nonce(kp_provider.ss58_address)

    as_multi_call = substrate.compose_call(
        call_module='MultiSig',
        call_function='as_multi',
        call_params={
            'threshold': threshold,
            'other_signatories': [kp_consumer.ss58_address],
            'maybe_timepoint': None,
            'call': str(payload.data),
            'store_call': True,
            'max_weight': {'ref_time': 1000000000},
        })

    extrinsic = substrate.create_signed_extrinsic(
        call=as_multi_call,
        keypair=kp_provider,
        era={'period': 64},
        nonce=nonce
    )

    receipt = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
    show_extrinsic(receipt, 'as_multi')
    info = receipt.get_extrinsic_identifier().split('-')
    return {
        'tx_hash': receipt.extrinsic_hash,
        'timepoint': {'height': int(info[0]), 'index': int(info[1])},
        'call_hash': f'0x{payload.call_hash.hex()}',
    }


# [TODO] Can be extract function
def send_refund_token_from_multisig_wallet(substrate, kp_consumer, kp_provider, token_num, threshold):
    print('----- Provider asks the refund token')
    payload = substrate.compose_call(
        call_module='Balances',
        call_function='transfer',
        call_params={
            'dest': kp_consumer.ss58_address,
            'value': token_num * TOKEN_NUM_BASE
        })

    nonce = substrate.get_account_nonce(kp_provider.ss58_address)

    as_multi_call = substrate.compose_call(
        call_module='MultiSig',
        call_function='as_multi',
        call_params={
            'threshold': threshold,
            'other_signatories': [kp_consumer.ss58_address],
            'maybe_timepoint': None,
            'call': str(payload.data),
            'store_call': True,
            'max_weight': {'ref_time': 1000000000},
        })

    extrinsic = substrate.create_signed_extrinsic(
        call=as_multi_call,
        keypair=kp_provider,
        era={'period': 64},
        nonce=nonce
    )

    receipt = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
    show_extrinsic(receipt, 'as_multi')
    info = receipt.get_extrinsic_identifier().split('-')
    return {
        'tx_hash': receipt.extrinsic_hash,
        'timepoint': {'height': int(info[0]), 'index': int(info[1])},
        'call_hash': f'0x{payload.call_hash.hex()}'
    }


# [TODO] Can be extract function
def send_spent_token_service_delievered(
        substrate, kp_consumer, kp_provider, token_num, tx_hash, timepoint, call_hash):

    print('----- Provider send the spent service delivered')
    nonce = substrate.get_account_nonce(kp_provider.ss58_address)
    call = substrate.compose_call(
        call_module='PeaqTransaction',
        call_function='service_delivered',
        call_params={
            'consumer': kp_provider.ss58_address,
            'token_num': token_num,
            'tx_hash': tx_hash,
            'time_point': timepoint,
            'call_hash': call_hash,
        })

    extrinsic = substrate.create_signed_extrinsic(
        call=call,
        keypair=kp_provider,
        era={'period': 64},
        nonce=nonce
    )

    receipt = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
    show_extrinsic(receipt, 'service_delivered')


# [TODO] Can be extract function
def send_refund_token_service_delievered(
        substrate, kp_consumer, kp_provider, token_num, tx_hash, timepoint, call_hash):

    print('----- Provider send the refund service delivered')
    nonce = substrate.get_account_nonce(kp_provider.ss58_address)
    call = substrate.compose_call(
        call_module='PeaqTransaction',
        call_function='service_delivered',
        call_params={
            'consumer': kp_consumer.ss58_address,
            'token_num': token_num,
            'tx_hash': tx_hash,
            'time_point': timepoint,
            'call_hash': call_hash,
        })

    extrinsic = substrate.create_signed_extrinsic(
        call=call,
        keypair=kp_provider,
        era={'period': 64},
        nonce=nonce
    )

    receipt = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
    show_extrinsic(receipt, 'service_delivered')


def _approve_token(substrate, kp_sign, other_signatories, threshold, info):
    nonce = substrate.get_account_nonce(kp_sign.ss58_address)

    as_multi_call = substrate.compose_call(
        call_module='MultiSig',
        call_function='approve_as_multi',
        call_params={
            'threshold': threshold,
            'other_signatories': other_signatories,
            'maybe_timepoint': info['timepoint'],
            'call_hash': info['call_hash'],
            'max_weight': {'ref_time': 1000000000},
        })

    extrinsic = substrate.create_signed_extrinsic(
        call=as_multi_call,
        keypair=kp_sign,
        era={'period': 64},
        nonce=nonce
    )

    receipt = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
    show_extrinsic(receipt, 'approve_as_multi')


def approve_spent_token(substrate, kp_consumer, provider_addr, threshold, spent_info):
    print('--- User approve spent token')
    _approve_token(substrate, kp_consumer, [provider_addr], threshold, spent_info)


def approve_refund_token(substrate, kp_consumer, provider_addr, threshold, refund_info):
    print('--- User approve refund token')
    _approve_token(substrate, kp_consumer, [provider_addr], threshold, refund_info)


def transfer(substrate, kp_src, kp_dst_addr, token_num):
    return transfer_with_tip(substrate, kp_src, kp_dst_addr, token_num, 0)


def transfer_with_tip(substrate, kp_src, kp_dst_addr, token_num, tip, token_base=0):
    if not token_base:
        token_base = TOKEN_NUM_BASE

    nonce = substrate.get_account_nonce(kp_src.ss58_address)

    call = substrate.compose_call(
        call_module='Balances',
        call_function='transfer',
        call_params={
            'dest': kp_dst_addr,
            'value': token_num * token_base
        })

    extrinsic = substrate.create_signed_extrinsic(
        call=call,
        keypair=kp_src,
        era={'period': 64},
        tip=tip * token_base,
        nonce=nonce
    )

    receipt = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
    show_extrinsic(receipt, 'transfer')
    if not receipt.is_success:
        print(substrate.get_events(receipt.block_hash))
        raise IOError
    return receipt


def calculate_evm_account(addr):
    evm_addr = b'evm:' + bytes.fromhex(addr[2:].upper())
    hash_key = hasher.blake2_256(evm_addr)
    return ss58.ss58_encode(hash_key)


def calculate_evm_addr(addr):
    return '0x' + ss58.ss58_decode(addr)[:40]


def fund(substrate, kp_dst, token_num):
    kp_sudo = Keypair.create_from_uri('//Alice')

    payload = substrate.compose_call(
        call_module='Balances',
        call_function='set_balance',
        call_params={
            'who': kp_dst.ss58_address,
            'new_free': token_num * TOKEN_NUM_BASE,
            'new_reserved': 0
        }
    )

    call = substrate.compose_call(
        call_module='Sudo',
        call_function='sudo',
        call_params={
            'call': payload.value,
        }
    )

    extrinsic = substrate.create_signed_extrinsic(
        call=call,
        keypair=kp_sudo
    )
    receipt = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
    show_extrinsic(receipt, 'fund')


# TODO Rmeove
def get_account_balance(substrate, addr):
    result = substrate.query("System", "Account", [addr])
    return int(result['data']['free'].value)


def get_account_balance_locked(substrate, addr):
    result = substrate.query("System", "Account", [addr])
    return int(result['data']['misc_frozen'].value)


def check_and_fund_account(substrate, addr, min_bal, req_bal):
    if get_account_balance(substrate, addr.ss58_address) < min_bal:
        print("Since sufficinet balance is not available in account: ", addr.ss58_address)
        print("account will be fund with an amount equalt to :", req_bal)
        fund(substrate, addr, req_bal)
        print("account balance after funding: ", get_account_balance(substrate, addr.ss58_address))


def show_account(substrate, addr, out_str):
    result = substrate.query("System", "Account", [addr])
    print(f'{addr} {out_str}: {result["data"]["free"]}')
    return int(result['data']['free'].value)


@dataclass
class ExtrinsicBatch:
    """
    ExtrinsicBatch class for simple creation of extrinsic-batch to be executed.

    When initialising, pass either an existing SubstrateInterface/WS-URL and
    optional Keypair/URI, or use the defaults. The ExtrinsicBatch is designed
    to be used on one chain (relaychain/parachain), because the usage of one
    SubstrateInterface. It is also designed for one user to execute the batch,
    because the Utility pallet does not varying users unfortunately.

    Example 1:    ex_stack = ExtrinsicStack(substrate, kp_src)
    Example 2:    ex_stack = ExtrinsicStack(WS_URL, '//Bob')
    Example 3:    ex_stack = ExtrinsicStack()
    """
    substrate: SubstrateInterface
    kp_default: Keypair
    batch: list

    def __init__(self, substrate_or_url=WS_URL, keypair_or_uri='//Alice'):
        self.substrate = _into_substrate(substrate_or_url)
        self.kp_default = _into_keypair(keypair_or_uri)
        self.batch = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self

    def __str__(self):
        return 'ExtrinsicBatch@{}, batch: {}'.format(self.substrate, self.batch)

    def compose_call(self, module, extrinsic, params):
        """Composes and appends an extrinsic call to this stack"""
        self.batch.append(compose_call(
            self.substrate, module, extrinsic, params))

    def compose_sudo_call(self, module, extrinsic, params):
        """Composes a sudo-user extrinsic call and adds it this stack"""
        self.batch.append(compose_sudo_call(
            self.substrate, module, extrinsic, params))

    def execute(self, wait_for_finalization=False, alt_keypair=None) -> str:
        """Executes the extrinsic-stack"""
        if not self.batch:
            return ''
        if alt_keypair is None:
            alt_keypair = self.kp_default
        return execute_extrinsic_batch(
            self.substrate, alt_keypair, self.batch, wait_for_finalization)

    def execute_n_clear(self, alt_keypair=None, wait_for_finalization=False) -> str:
        """Combination of execute() and clear()"""
        if alt_keypair is None:
            alt_keypair = self.kp_default
        bl_hash = self.execute(wait_for_finalization, alt_keypair)
        self.clear()
        return bl_hash

    def clear(self):
        """Clears the current extrinsic-stack"""
        self.batch = []

    def clone(self, keypair_or_uri=None):
        """Creates a duplicate, by using the same SubstrateInterface"""
        if keypair_or_uri is None:
            keypair_or_uri = self.kp_default
        return ExtrinsicBatch(self.substrate, keypair_or_uri)


def compose_call(substrate, module, extrinsic, params):
    """
    Composes a substrate-extrinsic-call on any module
    Example:
      module = 'Rbac'
      extrinsic = 'add_role'
      params = {'role_id': entity_id, 'name': name }
    """
    return substrate.compose_call(
        call_module=module,
        call_function=extrinsic,
        call_params=params
    )


def compose_sudo_call(substrate, module, extrinsic, params):
    """
    Composes a substrate-sudo-extrinsic-call on any module
    Parameters same as in compose_call, see above
    """
    payload = compose_call(substrate, module, extrinsic, params)
    return compose_call(substrate, 'Sudo', 'sudo', {'call': payload.value})


def execute_extrinsic_batch(substrate, kp_src, batch,
                            wait_for_finalization=False) -> str:
    """
    Executes a extrinsic-stack/batch-call on substrate
    Parameters:
      substrate:  SubstrateInterface
      kp_src:     Keypair
      batch:      list[compose_call(), compose_call(), ...]
    """
    # Wrap payload into a utility batch cal
    call = substrate.compose_call(
        call_module='Utility',
        call_function='batch_all',
        call_params={
            'calls': batch,
        })

    nonce = substrate.get_account_nonce(kp_src.ss58_address)
    extrinsic = substrate.create_signed_extrinsic(
        call=call,
        keypair=kp_src,
        era={'period': 64},
        nonce=nonce
    )

    receipt = substrate.submit_extrinsic(
        extrinsic, wait_for_inclusion=True,
        wait_for_finalization=wait_for_finalization)
    if len(batch) == 1:
        description = generate_call_description(batch[0])
    else:
        description = generate_batch_description(batch)
    show_extrinsic(receipt, description)

    if not receipt.is_success:
        print(substrate.get_events(receipt.block_hash))
        raise IOError
    else:
        return receipt.block_hash


def execute_call(substrate: SubstrateInterface, kp_src: Keypair, call,
                 wait_for_finalization=False) -> str:
    """Executes a single extrinsic call on substrate"""
    nonce = substrate.get_account_nonce(kp_src.ss58_address)
    extrinsic = substrate.create_signed_extrinsic(
        call=call,
        keypair=kp_src,
        era={'period': 64},
        nonce=nonce)

    receipt = substrate.submit_extrinsic(
        extrinsic, wait_for_inclusion=True,
        wait_for_finalization=wait_for_finalization)
    description = generate_call_description(call)
    show_extrinsic(receipt, description)

    if not receipt.is_success:
        print(substrate.get_events(receipt.block_hash))
        raise IOError
    else:
        return receipt.block_hash


def generate_call_description(call):
    """Generates a description for an arbitrary extrinsic call"""
    # print(type(call), call)
    # assert type(call) == "scalecodec.types.GenericCall"
    module = call.call_module.name
    function = call.call_function.name
    if module == 'Sudo':
        # I don't like this solution, but unfortunately I was not able to access
        # call.call_args in that way to extract the module and function of the payload.
        desc = call.__str__().split('{')[3]
        desc = desc.split("'")
        submodule = desc[3]
        subfunction = desc[7]
        return f'{module}.{function}({submodule}.{subfunction})'
    else:
        return f'{module}.{function}'


def generate_batch_description(batch):
    """Generates a description for an extrinsic batch"""
    desc = []
    for b in batch:
        desc.append(f'{generate_call_description(b)}')
    desc = ', '.join(desc)
    desc = f'Batch[ {desc} ]'

def _into_keypair(keypair_or_uri) -> Keypair:
    """Takes either a Keypair, or transforms a given uri into one"""
    if isinstance(keypair_or_uri, str):
        return Keypair.create_from_uri(keypair_or_uri)
    elif isinstance(keypair_or_uri, Keypair):
        return keypair_or_uri
    else:
        raise TypeError


def _into_substrate(substrate_or_url) -> SubstrateInterface:
    """Takes a SubstrateInterface, or takes into one by given url"""
    if isinstance(substrate_or_url, str):
        return SubstrateInterface(substrate_or_url)
    elif isinstance(substrate_or_url, SubstrateInterface):
        return substrate_or_url
    else:
        raise TypeError


def wait_for_event(substrate, module, event, attributes={}, timeout=30):
    """
    Waits for an certain event and returns it if found, and None if not.
    Method stops after given timeout and returns also None.
    Parameters:
    - module:       name of the module to filter
    - event:        name of the event to filter
    - attributes:   dict with attributes and expected values to filter
    """
    stime = time.time()
    cur_bl = None
    nxt_bl = substrate.get_block_hash()
    while not (time.time() - stime) > timeout:
        if nxt_bl != cur_bl:
            cur_bl = nxt_bl
            events = substrate.get_events(cur_bl)
            for e in events:
                if _is_it_this_event(e, module, event, attributes):
                    time.sleep(1) # To make sure everything has been processed
                    return e.value['event']
        time.sleep(1)
        nxt_bl = substrate.get_block_hash()
    return None


def _is_it_this_event(e_obj, module, event, attributes) -> bool:
    module_id = e_obj.value['event']['module_id']
    event_id = e_obj.value['event']['event_id']
    attrib_id = e_obj.value['event']['attributes']
    if module_id == module and event_id == event:
        if attributes:
            for key in attributes.keys():
                if not key in attrib_id.keys():
                    raise KeyError
                if attrib_id[key] != attributes[key]:
                    return False
            return True
        else:
            return True
    else:
        return False


def wait_for_n_blocks(substrate, n=1):
    """Waits until the next block has been created"""
    hash = substrate.get_block_hash()
    past = 0
    while past < n:
        next_hash = substrate.get_block_hash()
        if hash == next_hash:
            time.sleep(1)
        else:
            hash = next_hash
            past = past + 1

