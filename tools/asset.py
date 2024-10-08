from peaq.utils import ExtrinsicBatch
from tools.utils import get_peaq_chain_id
from tools.constants import ACA_PD_CHAIN_ID
from peaq.utils import get_account_balance
from tools.constants import BLOCK_GENERATE_TIME
import time


PEAQ_PD_CHAIN_ID = get_peaq_chain_id()

XCM_VER = 'V4'  # So far not tested with V2!

ACA_ASSET_ID = {
    'peaq': '3',
    'para': '0',
}
ACA_ASSET_LOCATION = {
    'peaq': {
        XCM_VER: {
            'parents': '1',
            'interior': {'X1': [{'Parachain': ACA_PD_CHAIN_ID}]}
        }
    },
    'para': None
}

UNITS_PER_SECOND = 5 * 10 ** 5
ACA_METADATA = {
    'name': 'ACA',
    'symbol': 'ACA',
    'decimals': 18,
}


RELAY_ASSET_LOCATION = {
    'peaq': {
        XCM_VER: {
            'parents': '1',
            'interior': 'Here'
        }
    },
    'para': None,
}
RELAY_ASSET_ID = {
    'peaq': '1',
    'para': None,
}
RELAY_METADATA = {
    'name': 'Relay Token',
    'symbol': 'DOT',
    'decimals': 12,
}

PEAQ_ASSET_ID = {
    'peaq': '0',
    'para': '3',
}
PEAQ_ASSET_LOCATION = {
    'peaq': {
        XCM_VER: {
            'parents': '0',
            'interior': 'Here'
        }
    },
    'para': {
        XCM_VER: {
            'parents': '1',
            'interior': {'X1': [{'Parachain': PEAQ_PD_CHAIN_ID}]}
        }
    },
}
PEAQ_METADATA = {
    'name': 'Peaq Token',
    'symbol': 'AGUNG',
    'decimals': 18,
}


def batch_register_location(batch, asset_id, location):
    batch.compose_sudo_call(
        'XcAssetConfig',
        'register_asset_location',
        {
            'asset_location': location,
            'asset_id': asset_id
        }
    )


def batch_set_units_per_second(batch, location, units_per_second):
    batch.compose_sudo_call(
        'XcAssetConfig',
        'set_asset_units_per_second',
        {
            'asset_location': location,
            'units_per_second': units_per_second
        }
    )


def batch_create_asset(batch, addr_admin, asset_id, min_balance=100):
    batch.compose_call(
        'Assets',
        'create',
        {
            'id': asset_id,
            'admin': addr_admin,
            'min_balance': min_balance,
        }
    )


def batch_force_create_asset(batch, addr_admin, asset_id, min_balance=100):
    batch.compose_sudo_call(
        'Assets',
        'force_create',
        {
            'id': asset_id,
            'owner': addr_admin,
            'is_sufficient': True,
            'min_balance': min_balance,
        }
    )


def batch_set_metadata(batch, asset_id, name, symbol, decimals):
    batch.compose_call(
        'Assets',
        'set_metadata',
        {
            'id': asset_id,
            'name': name,
            'symbol': symbol,
            'decimals': decimals,
        }
    )


def batch_mint(batch, addr_src, asset_id, token_amount):
    batch.compose_call(
        'Assets',
        'mint',
        {
            'id': asset_id,
            'beneficiary': addr_src,
            'amount': token_amount,
        }
    )


class AlwaysTrueReceipt():
    def __init__(self, *args, **kwargs):
        pass

    def is_success(self):
        return True

    def error_message(self):
        return ''


# This function is only for ACA chain, now deprecated because we are no longer use ACA chain
def setup_aca_asset_if_not_exist(si_aca, kp_sudo, asset_id, location, metadata, min_balance=100):
    out = setup_asset_if_not_exist(si_aca, kp_sudo, asset_id, metadata, min_balance, True)
    if not out.is_success:
        return out

    out = setup_xc_register_if_not_exist(si_aca, kp_sudo, asset_id, location, UNITS_PER_SECOND)
    return out


def setup_asset_if_not_exist(si_peaq, kp_sudo, asset_id, metadata, min_balance=100, is_sufficient=False):
    resp = si_peaq.query("Assets", "Asset", [asset_id])
    if resp.value:
        return AlwaysTrueReceipt()

    batch = ExtrinsicBatch(si_peaq, kp_sudo)
    if is_sufficient:
        batch_force_create_asset(batch, kp_sudo.ss58_address,
                                 asset_id, min_balance)
    else:
        batch_create_asset(batch, kp_sudo.ss58_address, asset_id, min_balance)
    batch_set_metadata(batch, asset_id,
                       metadata['name'], metadata['symbol'], metadata['decimals'])
    return batch.execute()


def setup_xc_register_if_not_exist(si_peaq, kp_sudo, asset_id, location, units_per_second):
    resp = si_peaq.query("XcAssetConfig", "AssetIdToLocation", [asset_id])
    if resp.value:
        return AlwaysTrueReceipt()
    batch = ExtrinsicBatch(si_peaq, kp_sudo)
    batch_register_location(batch, asset_id, location)
    batch_set_units_per_second(batch, location, units_per_second)
    return batch.execute()


def get_valid_asset_id(conn):
    for i in range(30, 130):
        asset = conn.query("Assets", "Asset", [convert_enum_to_asset_id({'Token': i})])
        if asset.value:
            continue
        else:
            return convert_enum_to_asset_id({'Token': i})


def get_asset_balance(conn, addr, asset_id, block_hash):
    if block_hash:
        print("block_hash", block_hash)
        return conn.query("Assets", "Account", [asset_id, addr], block_hash)
    return conn.query("Assets", "Account", [asset_id, addr])


def get_tokens_account_from_pallet_assets(substrate, addr, asset_id, block_hash=None):
    resp = get_asset_balance(substrate, addr, asset_id, block_hash)
    if not resp.value:
        return 0
    return resp.value['balance']


# Only for other chain (aca), but now we are use the peaq chain to test XCM
def get_tokens_account_from_pallet_tokens(substrate, addr, asset_id, block_hash=None):
    if not block_hash:
        resp = substrate.query("Tokens", "Accounts", [addr, asset_id], block_hash)
    else:
        resp = substrate.query("Tokens", "Accounts", [addr, asset_id])
    if not resp.value:
        return 0
    return resp.value['free']


def get_balance_account_from_pallet_balance(substrate, addr, _, block_hash=None):
    return get_account_balance(substrate, addr, block_hash)


def wait_for_account_asset_change_wrap(substrate, addr, asset_id, prev_token, block_num, func):
    block_hash = substrate.get_block_hash(block_num)
    if not prev_token:
        prev_token = func(substrate, addr, asset_id, block_hash)

    # go to check preivous setting
    now_block = substrate.get_block_number(None)
    for i in range(block_num, now_block + 1):
        block_hash = substrate.get_block_hash(i)
        now_token = func(substrate, addr, asset_id, block_hash)
        if now_token != prev_token:
            print(f"Account {addr} balance {prev_token} changed to {now_token} on peaq at block {i}")
            return now_token

    # Check next
    count = 0
    now_block = substrate.get_block_number(None)
    while func(substrate, addr, asset_id) == prev_token and count < 10:
        time.sleep(BLOCK_GENERATE_TIME)
        now_block = substrate.get_block_number(None)
        count += 1
    now_token = func(substrate, addr, asset_id)
    if now_token == prev_token:
        raise IOError(f"Account {addr} balance {prev_token} not changed on peaq")
    print(f"Account {addr} balance {prev_token} changed to {now_token} on peaq at block {now_block}")
    return now_token


def convert_enum_to_asset_id(enum_info):
    TOKEN_MASK = 0xFFFFFFFF
    if 'Token' in enum_info.keys():
        return enum_info['Token']
    elif 'LPToken' in enum_info.keys():
        return ((enum_info['LPToken'][0] & TOKEN_MASK) << 32) + enum_info['LPToken'][1] + (1 << 60)
    else:
        raise ValueError(f'Invalid enum_info: {enum_info}')
