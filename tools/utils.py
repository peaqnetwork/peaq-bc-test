import sys
import time
sys.path.append('.')

from substrateinterface import Keypair
from peaq.utils import get_account_balance, show_extrinsic
from peaq.sudo_extrinsic import fund
from peaq.eth import calculate_evm_addr
from peaq.utils import calculate_multi_sig
from peaq.utils import get_chain

# Monkey patch
from scalecodec.types import FixedLengthArray
from tools.monkey_patch_scale_info import process_encode as new_process_encode
from tools.payload import sudo_call_compose, sudo_extrinsic_send, user_extrinsic_send
FixedLengthArray.process_encode = new_process_encode

TOKEN_NUM_BASE = pow(10, 3)
TOKEN_NUM_BASE_DEV = pow(10, 18)
RELAYCHAIN_WS_URL = 'ws://127.0.0.1:9944'
STANDALONE_WS_URL = 'ws://127.0.0.1:9944'

PARACHAIN_WS_URL = 'ws://127.0.0.1:10044'
BIFROST_WS_URL = 'ws://127.0.0.1:10144'
RELAYCHAIN_ETH_URL = 'http://127.0.0.1:9933'
PARACHAIN_ETH_URL = 'http://127.0.0.1:10033'
BIFROST_ETH_URL = 'http://127.0.0.1:10133'
# PARACHAIN_WS_URL = 'wss://wsspc1.agung.peaq.network'
# PARACHAIN_ETH_URL = 'https://rpcpc1.agung.peaq.network'
# WS_URL = 'ws://127.0.0.1:9944'
# ETH_URL = 'http://127.0.0.1:9933'
WS_URL = PARACHAIN_WS_URL
ETH_URL = PARACHAIN_ETH_URL
# WS_URL = 'ws://192.168.178.23:9944'
# ETH_URL = 'http://192.168.178.23:9933'
# WS_URL = 'wss://wss.test.peaq.network'
# ETH_URL = 'https://erpc.test.peaq.network:443'

URI_GLOBAL_SUDO = '//Alice'
KP_GLOBAL_SUDO = Keypair.create_from_uri(URI_GLOBAL_SUDO)
KP_COLLATOR = Keypair.create_from_uri('//Ferdie')
PEAQ_PD_CHAIN_ID = 2000
BIFROST_PD_CHAIN_ID = 3000


import pprint
pp = pprint.PrettyPrinter(indent=4)


def show_test(name, success, line=0):
    if success:
        print(f'✅ Test/{name}, Passed')
    else:
        if line != 0:
            print(f'🔥 Test/{name}, Failed in line {line}')
        else:
            print(f'🔥 Test/{name}, Failed')


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
        call_function='transfer',
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
        call_function='transfer',
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

    receipt = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
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
        call_function='transfer',
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

    receipt = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
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

    receipt = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
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

    receipt = substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
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
    return int(result['data']['misc_frozen'].value)


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


# [TODO] Use the batch
@sudo_extrinsic_send(sudo_keypair=KP_GLOBAL_SUDO)
@sudo_call_compose(sudo_keypair=KP_GLOBAL_SUDO)
def set_max_currency_supply(substrate, max_currency_supply):
    return substrate.compose_call(
        call_module='BlockReward',
        call_function='set_max_currency_supply',
        call_params={
            'limit': max_currency_supply
        }
    )


@sudo_extrinsic_send(sudo_keypair=KP_GLOBAL_SUDO)
@sudo_call_compose(sudo_keypair=KP_GLOBAL_SUDO)
def set_block_reward_configuration(substrate, data):
    return substrate.compose_call(
        call_module='BlockReward',
        call_function='set_configuration',
        call_params={
            'reward_distro_params': {
                'treasury_percent': data['treasury_percent'],
                'dapps_percent': data['dapps_percent'],
                'collators_percent': data['collators_percent'],
                'lp_percent': data['lp_percent'],
                'machines_percent': data['machines_percent'],
                'parachain_lease_fund_percent': data['parachain_lease_fund_percent'],
            }
        }
    )


@sudo_extrinsic_send(sudo_keypair=KP_GLOBAL_SUDO)
@sudo_call_compose(sudo_keypair=KP_GLOBAL_SUDO)
def setup_block_reward(substrate, block_reward):
    return substrate.compose_call(
        call_module='BlockReward',
        call_function='set_block_issue_reward',
        call_params={
            'block_reward': block_reward
        }
    )


@user_extrinsic_send
def send_proposal(substrate, kp_src, kp_dst, threshold, payload, timepoint=None):
    return substrate.compose_call(
        call_module='Multisig',
        call_function='as_multi',
        call_params={
            'threshold': threshold,
            'other_signatories': [kp_dst.ss58_address],
            'maybe_timepoint': timepoint,
            'call': payload.value,
            'max_weight': {'ref_time': 1000000000, 'proof_size': 1000000},
        })


def get_as_multi_extrinsic_id(receipt):
    info = receipt.get_extrinsic_identifier().split('-')
    return {'height': int(info[0]), 'index': int(info[1])}


@user_extrinsic_send
def send_approval(substrate, kp_src, kps, threshold, payload, timepoint):
    return substrate.compose_call(
        call_module='Multisig',
        call_function='approve_as_multi',
        call_params={
            'threshold': threshold,
            'other_signatories': [kp.ss58_address for kp in kps],
            'maybe_timepoint': timepoint,
            'call_hash': f'0x{payload.call_hash.hex()}',
            'max_weight': {'ref_time': 1000000000, 'proof_size': 1000000},
        })


def get_collators(substrate, key):
    return substrate.query(
           module='ParachainStaking',
           storage_function='CandidatePool',
           params=[key.ss58_address]
    )


def exist_pallet(substrate, pallet_name):
    return substrate.get_block_metadata(decode=True).get_metadata_pallet(pallet_name)


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
                    time.sleep(1)  # To make sure everything has been processed
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
                if key not in attrib_id.keys():
                    raise KeyError
                if attrib_id[key] != attributes[key]:
                    return False
            return True
        else:
            return True
    else:
        return False


def get_relay_chain_token(substrate):
    chain_name = get_chain(substrate)
    if chain_name == 'agung-network' or chain_name == 'agung-network-fork':
        return 'DOT'
    elif chain_name == 'krest' or chain_name == 'krest-network-fork':
        return 'KSM'
    elif chain_name == 'peaq':
        return 'DOT'
    raise IOError(f'Unknown chain name: {chain_name}')


if __name__ == '__main__':
    data = '5F1e2nuSgxwWZiL9jTxv3jrMQHeHHhuwP7oDmU87SMp1Ncxv'
    print(calculate_evm_addr(data))
