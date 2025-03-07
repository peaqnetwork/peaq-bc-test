import sys
import time
sys.path.append('.')

from peaq import utils as PeaqUtils
PeaqUtils.DEBUG = True

from tools.constants import PARACHAIN_WS_URL, TOKEN_NUM_BASE, KP_GLOBAL_SUDO
from substrateinterface import SubstrateInterface
from substrateinterface import Keypair
from peaq.utils import get_account_balance, show_extrinsic
from peaq.sudo_extrinsic import fund
from peaq.eth import calculate_evm_addr
from peaq.utils import calculate_multi_sig

# Monkey patch
from scalecodec.types import FixedLengthArray
from tools.monkey.monkey_patch_scale_info import process_encode as new_process_encode
from tools.payload import user_extrinsic_send
FixedLengthArray.process_encode = new_process_encode

from tools.monkey.monkey_3rd_substrate_interface import monkey_submit_extrinsic
SubstrateInterface.submit_extrinsic = monkey_submit_extrinsic

from peaq.utils import ExtrinsicBatch
from tools.monkey.monkey_reorg_batch import monkey_execute_extrinsic_batch
ExtrinsicBatch._execute_extrinsic_batch = monkey_execute_extrinsic_batch

PARACHAIN_STAKING_POT = '5EYCAe5cKPAoFh2HnQQvpKqRYZGqBpaA87u4Zzw89qPE58is'


import pprint
pp = pprint.PrettyPrinter(indent=4)


def get_parachain_id(substrate):
    result = substrate.query(
        'ParachainInfo',
        'ParachainId',
    )
    return result.value


def show_test(name, success, line=0):
    if success:
        print(f'✅ Test/{name}, Passed')
    else:
        if line != 0:
            print(f'🔥 Test/{name}, Failed in line {line}')
        else:
            print(f'🔥 Test/{name}, Failed')


def get_peaq_chain_id():
    return get_parachain_id(SubstrateInterface(url=PARACHAIN_WS_URL))


def show_title(name):
    print(f'========== {name} ==========')


def show_subtitle(name):
    print(f'----- {name} -----')


@user_extrinsic_send
def deposit_money_to_multsig_wallet(substrate, kp_consumer, kp_provider, token_num):
    print('----- Consumer deposit money to multisig wallet')
    threshold = 2
    signators = [kp_consumer, kp_provider]
    multi_sig_addr = calculate_multi_sig(signators, threshold)
    return substrate.compose_call(
        call_module='Balances',
        call_function='transfer_keep_alive',
        call_params={
            'dest': multi_sig_addr,
            'value': token_num * TOKEN_NUM_BASE
        })


@user_extrinsic_send
def send_service_request(substrate, kp_consumer, kp_provider, token_num):
    print('----- Consumer sends the serviice requested to peaq-transaction')
    return substrate.compose_call(
        call_module='PeaqTransaction',
        call_function='service_requested',
        call_params={
            'provider': kp_provider.ss58_address,
            'token_deposited': token_num * TOKEN_NUM_BASE
        })


# TODO, Depreciated
def send_spent_token_from_multisig_wallet(substrate, kp_consumer, kp_provider, token_num, threshold):
    print('----- Provider asks the spent token')
    payload = substrate.compose_call(
        call_module='Balances',
        call_function='transfer_keep_alive',
        call_params={
            'dest': kp_provider.ss58_address,
            'value': token_num * TOKEN_NUM_BASE
        })

    nonce = substrate.get_account_nonce(kp_provider.ss58_address)

    as_multi_call = substrate.compose_call(
        call_module='Multisig',
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

    receipt = substrate.submit_extrinsic(extrinsic, wait_for_finalization=True)
    show_extrinsic(receipt, 'as_multi')
    info = receipt.get_extrinsic_identifier().split('-')
    return {
        'tx_hash': receipt.extrinsic_hash,
        'timepoint': {'height': int(info[0]), 'index': int(info[1])},
        'call_hash': f'0x{payload.call_hash.hex()}',
    }


# TODO, Depreciated
def send_refund_token_from_multisig_wallet(substrate, kp_consumer, kp_provider, token_num, threshold):
    print('----- Provider asks the refund token')
    payload = substrate.compose_call(
        call_module='Balances',
        call_function='transfer_keep_alive',
        call_params={
            'dest': kp_consumer.ss58_address,
            'value': token_num * TOKEN_NUM_BASE
        })

    nonce = substrate.get_account_nonce(kp_provider.ss58_address)

    as_multi_call = substrate.compose_call(
        call_module='Multisig',
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

    receipt = substrate.submit_extrinsic(extrinsic, wait_for_finalization=True)
    show_extrinsic(receipt, 'as_multi')
    info = receipt.get_extrinsic_identifier().split('-')
    return {
        'tx_hash': receipt.extrinsic_hash,
        'timepoint': {'height': int(info[0]), 'index': int(info[1])},
        'call_hash': f'0x{payload.call_hash.hex()}'
    }


# TODO, Depreciated
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

    receipt = substrate.submit_extrinsic(extrinsic, wait_for_finalization=True)
    show_extrinsic(receipt, 'service_delivered')


# TODO, Depreciated
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

    receipt = substrate.submit_extrinsic(extrinsic, wait_for_finalization=True)
    show_extrinsic(receipt, 'service_delivered')


# TODO, Depreciated
@user_extrinsic_send
def _approve_token(substrate, kp_sign, other_signatories, threshold, info):
    return substrate.compose_call(
        call_module='Multisig',
        call_function='approve_as_multi',
        call_params={
            'threshold': threshold,
            'other_signatories': other_signatories,
            'maybe_timepoint': info['timepoint'],
            'call_hash': info['call_hash'],
            'max_weight': {'ref_time': 1000000000},
        })


# TODO, Depreciated
def approve_spent_token(substrate, kp_consumer, provider_addr, threshold, spent_info):
    print('--- User approve spent token')
    _approve_token(substrate, kp_consumer, [provider_addr], threshold, spent_info)


# TODO, Depreciated
def approve_refund_token(substrate, kp_consumer, provider_addr, threshold, refund_info):
    print('--- User approve refund token')
    _approve_token(substrate, kp_consumer, [provider_addr], threshold, refund_info)


def get_account_balance_locked(substrate, addr):
    result = substrate.query('System', 'Account', [addr])
    return int(result['data']['frozen'].value)


def check_and_fund_account(substrate, addr, min_bal, req_bal):
    if get_account_balance(substrate, addr.ss58_address) < min_bal:
        print('Since sufficinet balance is not available in account: ', addr.ss58_address)
        print('account will be fund with an amount equalt to :', req_bal)
        fund(substrate, addr, req_bal)
        print('account balance after funding: ', get_account_balance(substrate, addr.ss58_address))


def show_account(substrate, addr, out_str):
    result = get_account_balance(substrate, addr)
    print(f'{addr} {out_str}: {result}')
    return result


def set_block_reward_configuration(substrate, data):
    batch = ExtrinsicBatch(substrate, KP_GLOBAL_SUDO)
    batch.compose_sudo_call(
        'BlockReward',
        'set_configuration',
        {
            'reward_distro_params': {
                'treasury_percent': data['treasury_percent'],
                'depin_incentivization_percent': data['depin_incentivization_percent'],
                'collators_delegators_percent': data['collators_delegators_percent'],
                'depin_staking_percent': data['depin_staking_percent'],
                'coretime_percent': data['coretime_percent'],
                'subsidization_pool_percent': data['subsidization_pool_percent'],
            }
        }
    )
    return batch.execute()


def send_proposal(substrate, kp_src, kp_dst, threshold, payload, timepoint=None):
    batch = ExtrinsicBatch(substrate, kp_src)
    batch.compose_call(
        'Multisig',
        'as_multi',
        {
            'threshold': threshold,
            'other_signatories': [kp_dst.ss58_address],
            'maybe_timepoint': timepoint,
            'call': payload.value,
            'max_weight': {'ref_time': 1000000000, 'proof_size': 1000000},
        }
    )
    return batch.execute()


def get_as_multi_extrinsic_id(receipt):
    info = receipt.get_extrinsic_identifier().split('-')
    return {'height': int(info[0]), 'index': int(info[1])}


def send_approval(substrate, kp_src, kps, threshold, payload, timepoint):
    batch = ExtrinsicBatch(substrate, kp_src)
    batch.compose_call(
        'Multisig',
        'approve_as_multi',
        {
            'threshold': threshold,
            'other_signatories': [kp.ss58_address for kp in kps],
            'maybe_timepoint': timepoint,
            'call_hash': f'0x{payload.call_hash.hex()}',
            'max_weight': {'ref_time': 1000000000, 'proof_size': 1000000},
        }
    )
    return batch.execute()


def get_collators(substrate, key):
    return substrate.query(
           module='ParachainStaking',
           storage_function='CandidatePool',
           params=[key.ss58_address]
    )


def exist_pallet(substrate, pallet_name):
    return substrate.get_block_metadata(decode=True).get_metadata_pallet(pallet_name)


def _check_event_in_previous_blocks(substrate, module, event, attributes, block_idx_prev):
    now_block = substrate.get_block_number(None)
    for bl_idx in range(block_idx_prev, now_block + 1):
        block_hash = substrate.get_block_hash(bl_idx)
        events = substrate.get_events(block_hash)
        for e in events:
            if _is_it_this_event(e, module, event, attributes):
                return e.value['event']
    return None


def _check_event_in_future_blocks(substrate, module, event, attributes, timeout):
    stime = time.time()
    cur_bl = None
    nxt_bl = substrate.get_block_hash()
    while not (time.time() - stime) > timeout:
        if nxt_bl != cur_bl:
            cur_bl = nxt_bl
            events = substrate.get_events(cur_bl)
            for e in events:
                if _is_it_this_event(e, module, event, attributes):
                    time.sleep(1)  # To make sure everything has been processed
                    return e.value['event']
        time.sleep(1)
        nxt_bl = substrate.get_block_hash()
    return None


def wait_for_event(substrate, module, event, attributes={}, timeout=30, block_idx_prev=0):
    """
    Waits for an certain event and returns it if found, and None if not.
    Method stops after given timeout and returns also None.
    Parameters:
    - module:       name of the module to filter
    - event:        name of the event to filter
    - attributes:   dict with attributes and expected values to filter
    """

    if not block_idx_prev:
        block_idx_prev = substrate.get_block_number(None)

    out = _check_event_in_previous_blocks(substrate, module, event, attributes, block_idx_prev)
    if out:
        return out
    out = _check_event_in_future_blocks(substrate, module, event, attributes, timeout)
    return out


def _is_it_this_event(e_obj, module, event, attributes) -> bool:
    module_id = e_obj.value['event']['module_id']
    event_id = e_obj.value['event']['event_id']
    attrib_id = e_obj.value['event']['attributes']
    if module_id == module and event_id == event:
        print(f'attributes: {attrib_id}')
        if attributes:
            for key in attributes.keys():
                if key not in attrib_id.keys():
                    raise KeyError
                if attrib_id[key] != attributes[key]:
                    return False
            return True
        else:
            return True
    else:
        return False


def get_event(substrate, block_hash, pallet, event_name):
    for event in substrate.get_events(block_hash):
        if event.value['module_id'] != pallet or \
           event.value['event_id'] != event_name:
            continue
        return event['event']
    return None


def get_all_events(substrate, block_hash, pallet, event_name):
    return [
        event['event']
        for event in substrate.get_events(block_hash)
        if event.value['module_id'] == pallet and event.value['event_id'] == event_name
    ]


def batch_fund(batch, kp_or_addr, amount):
    addr = kp_or_addr
    if isinstance(kp_or_addr, Keypair):
        addr = kp_or_addr.ss58_address
    batch.compose_sudo_call('Balances', 'force_set_balance', {
        'who': addr,
        'new_free': amount,
        'new_reserved': 0
    })


def get_existential_deposit(substrate):
    result = substrate.get_constant(
        'Balances',
        'ExistentialDeposit',
    )
    return result.value


def get_modified_chain_spec(chain_spec):
    if 'peaq-dev-fork' == chain_spec:
        return 'peaq-dev'
    if 'krest-network-fork' == chain_spec:
        return 'krest-network'
    if 'peaq-network-fork' == chain_spec:
        return 'peaq-network'
    return chain_spec


def get_balance_reserve_value(substrate, account, key):
    hex_key = f'0x{key.encode("utf-8").hex()}'

    reserve_value = substrate.query(
        'Balances',
        'Reserves',
        params=[account]
    )
    for item in reserve_value.value:
        if item['id'] == hex_key:
            return item['amount']
    return 0


def get_events_impl(substrate, block_hash, pallet, event_name, tx_id):
    events = []
    for event in substrate.get_events(block_hash):
        if event.value['module_id'] != pallet or \
                event.value['event_id'] != event_name:
            continue
        if event.value['extrinsic_idx'] != tx_id:
            continue

        events.append(event['event'])
    return events


def get_withdraw_events(substrate, block_hash, tx_id):
    events = get_events_impl(substrate, block_hash, 'Balances', 'Withdraw', tx_id)
    return [{
        'addr': str(event[1][1]['who']),
        'value': event[1][1]['amount'].value
    } for event in events]


def get_deposit_events(substrate, block_hash, tx_id):
    events = get_events_impl(substrate, block_hash, 'Balances', 'Deposit', tx_id)
    return [{
        'addr': str(event[1][1]['who']),
        'value': event[1][1]['amount'].value
    } for event in events]


if __name__ == '__main__':
    data = '5F1e2nuSgxwWZiL9jTxv3jrMQHeHHhuwP7oDmU87SMp1Ncxv'
    print(calculate_evm_addr(data))
