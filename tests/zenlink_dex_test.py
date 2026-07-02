import sys
import traceback
import unittest
import pytest

sys.path.append('./')

from peaq.sudo_extrinsic import funds
from substrateinterface import SubstrateInterface
from tools.constants import PARACHAIN_WS_URL, KP_GLOBAL_SUDO, URI_GLOBAL_SUDO
from tools.utils import show_test, show_title, show_subtitle, wait_for_event
from tools.utils import get_existential_deposit
from peaq.utils import ExtrinsicBatch, into_keypair
from peaq.utils import get_account_balance
from tools.currency import peaq, dot, aca
from tools.runtime_upgrade import wait_until_block_height
from tools.asset import setup_asset_if_not_exist
from tools.asset import ACA_METADATA
from tools.asset import RELAY_METADATA
from tools.asset import get_valid_asset_id, batch_mint
from tools.zenlink import compose_zdex_create_lppair, compose_zdex_lppair_params, compose_zdex_add_liquidity
from tools.zenlink import calc_deadline


# Technical constants
XCM_RTA_TO = 45  # timeout for xcm-rta
# Test parameter configurations
TOK_LIQUIDITY = 50  # generic amount of tokens
TOK_SWAP = 1  # generic amount of tokens
MORE_EXISTENTIAL_TOKENS = 10000

URI_MOON = '//Moon'
URI_MARS = '//Mars'


# [TODO] Need to move the setup (asset_resgiter/metadata here)
def relay_amount_w_fees(x):
    return x + dot(2.5)


def bifrost_amount_w_fees(x):
    return x + aca(1)


def compose_balances_transfer(batch, kp_beneficiary, amount):
    params = {
        'dest': kp_beneficiary.ss58_address,
        'value': str(amount),
    }
    batch.compose_call('Balances', 'transfer_keep_alive', params)


def compose_balances_setbalance(batch, who, amount):
    kp_who = into_keypair(who)
    params = {
        'who': kp_who.ss58_address,
        'new_free': str(amount),
        'new_reserved': '0',
    }
    batch.compose_sudo_call('Balances', 'force_set_balance', params)


def compose_zdex_swap_exact_for(batch, tok_idx, amount_in0=None, amount_in1=None):
    if amount_in1 is None and amount_in0 is not None:
        asset_0, asset_1 = compose_zdex_lppair_params(tok_idx)
        amount = amount_in0
    elif amount_in0 is None and amount_in1 is not None:
        asset_1, asset_0 = compose_zdex_lppair_params(tok_idx)
        amount = amount_in1
    else:
        raise AttributeError
    deadline = calc_deadline(batch.substrate)
    params = {
        'amount_in': str(amount),
        'amount_out_min': '0',
        'path': [asset_0, asset_1],
        'recipient': batch.keypair.ss58_address,
        'deadline': deadline,
    }
    batch.compose_call('ZenlinkProtocol', 'swap_exact_assets_for_assets', params)


def compose_zdex_swap_for_exact(batch, tok_idx, amount_out0=None, amount_out1=None,
                                amnt_in_max=100e18):
    if amount_out0 is None and amount_out1 is not None:
        asset_0, asset_1 = compose_zdex_lppair_params(tok_idx)
        amount = amount_out1
    elif amount_out1 is None and amount_out0 is not None:
        asset_1, asset_0 = compose_zdex_lppair_params(tok_idx)
        amount = amount_out0
    else:
        raise AttributeError
    deadline = calc_deadline(batch.substrate)
    params = {
        'amount_out': str(amount),
        'amount_in_max': str(amnt_in_max),
        'path': [asset_0, asset_1],
        'recipient': batch.keypair.ss58_address,
        'deadline': deadline,
    }
    batch.compose_call('ZenlinkProtocol', 'swap_assets_for_exact_assets', params)


def compose_zdex_remove_liquidity(batch, tok_idx, amount):
    asset_0, asset_1 = compose_zdex_lppair_params(tok_idx)
    deadline = calc_deadline(batch.substrate)
    params = {
        'asset_0': asset_0,
        'asset_1': asset_1,
        'liquidity': str(amount),
        'amount_0_min': '1',
        'amount_1_min': '1',
        'recipient': batch.keypair.ss58_address,
        'deadline': deadline,
    }
    batch.compose_call('ZenlinkProtocol', 'remove_liquidity', params)


def compose_bootstrap_create_call(batch, tok_idx, target0, target1, limit0, limit1):
    asset_0, asset_1 = compose_zdex_lppair_params(tok_idx)
    target_0 = str(target0)
    target_1 = str(target1)
    capacity_0 = str(target0*100)
    capacity_1 = str(target1*100)
    end = batch.substrate.get_block_number(None) + 500
    params = {
        'asset_0': asset_0,
        'asset_1': asset_1,
        'target_supply_0': target_0,
        'target_supply_1': target_1,
        'capacity_supply_0': capacity_0,
        'capacity_supply_1': capacity_1,
        'end': end,
        'rewards': [asset_0],
        'limits': [(asset_0, limit0), (asset_1, limit1)],
    }
    batch.compose_sudo_call('ZenlinkProtocol', 'bootstrap_create', params)


def compose_bootstrap_contribute_call(batch, tok_idx, amount0, amount1):
    assert amount0 == 0 or amount1 == 0
    asset_0, asset_1 = compose_zdex_lppair_params(tok_idx)
    deadline = calc_deadline(batch.substrate)
    params = {
        'asset_0': asset_0,
        'asset_1': asset_1,
        'amount_0_contribute': str(amount0),
        'amount_1_contribute': str(amount1),
        'deadline': deadline,
    }
    batch.compose_call('ZenlinkProtocol', 'bootstrap_contribute', params)


def compose_bootstrap_end_call(batch, tok_idx):
    asset_0, asset_1 = compose_zdex_lppair_params(tok_idx)
    params = {
        'asset_0': asset_0,
        'asset_1': asset_1,
    }
    batch.compose_call('ZenlinkProtocol', 'bootstrap_end', params)


def compose_call_bootstrap_update_end(batch, tok_idx):
    si = batch.substrate
    asset_0, asset_1 = compose_zdex_lppair_params(tok_idx)
    lpstatus = state_znlnkprot_lppair_status(si, tok_idx)
    target_0 = lpstatus['target_supply'][0]
    target_1 = lpstatus['target_supply'][1]
    capacity_0 = lpstatus['capacity_supply'][0]
    capacity_1 = lpstatus['capacity_supply'][1]
    query = si.query('ZenlinkProtocol', 'BootstrapLimits', [[asset_0, asset_1]])
    limit_0 = str(query[0][1])
    limit_1 = str(query[1][1])
    params = {
        'asset_0': asset_0,
        'asset_1': asset_1,
        'target_supply_0': target_0,
        'target_supply_1': target_1,
        'capacity_supply_0': capacity_0,
        'capacity_supply_1': capacity_1,
        'end': str(si.get_block_number(None)),
        'rewards': [asset_0],
        'limits': [(asset_0, limit_0), (asset_1, limit_1)],
    }
    batch.compose_sudo_call('ZenlinkProtocol', 'bootstrap_update', params)


def state_system_account(si_peaq, kp_user):
    query = si_peaq.query('System', 'Account', [kp_user.ss58_address])
    return int(query['data']['free'].value)


# [TODO] Need to extract
def state_token_assets_accounts(si_peaq, kp_user, token):
    params = [token, kp_user.ss58_address]
    query = si_peaq.query('Assets', 'Account', params)
    return int(query['balance'].value)


def state_znlnkprot_lppair_assetidx(si_peaq, tok_idx):
    asset0, asset1 = compose_zdex_lppair_params(tok_idx)
    query = si_peaq.query('ZenlinkProtocol', 'LiquidityPairs', [[asset0, asset1]])
    if query.value is None:
        return 0
    else:
        return int(query['asset_index'].value)


def state_znlnkprot_lppair_status(si_peaq, tok_idx):
    asset0, asset1 = compose_zdex_lppair_params(tok_idx)
    query = si_peaq.query('ZenlinkProtocol', 'PairStatuses', [[asset0, asset1]])
    if isinstance(query.value, dict):
        if 'Trading' in query.value.keys():
            return query.value['Trading']
        elif 'Bootstrap' in query.value.keys():
            return query.value['Bootstrap']
        else:
            raise KeyError
    else:
        return query.value


def wait_n_check_swap_event(substrate, min_tokens, block_idx_prev):
    event = wait_for_event(
        substrate, 'ZenlinkProtocol', 'AssetSwap', timeout=XCM_RTA_TO, block_idx_prev=block_idx_prev)
    assert event is not None
    assert event['attributes'][3][1] > min_tokens


def create_pair_n_swap_test(si_peaq, asset_id):
    """
    This test is about creating directly a liquidity-pair with the
    Zenlink-DEX-Protocol and using its swap-function (no bootstrap).
    This test also tests some of Zenlink-Protocol RPC methods.
    """
    show_subtitle('create_pair_n_swap_test')

    user_bene = URI_MOON
    bob = URI_MARS

    kp_para_sudo = into_keypair(KP_GLOBAL_SUDO)
    kp_beneficiary = into_keypair(user_bene)
    kp_para_bob = into_keypair(bob)

    bt_para_sudo = ExtrinsicBatch(si_peaq, kp_para_sudo)
    bt_para_bob = ExtrinsicBatch(si_peaq, kp_para_bob)
    bt_para_bene = ExtrinsicBatch(si_peaq, kp_beneficiary)

    # Setup the accounts
    relay_token = 10 ** 23
    bt_sudo = ExtrinsicBatch(si_peaq, KP_GLOBAL_SUDO)
    batch_mint(bt_sudo, into_keypair('//Alice').ss58_address, asset_id, relay_token)
    batch_mint(bt_sudo, into_keypair(user_bene).ss58_address, asset_id, relay_token)
    receipt = bt_sudo.execute_n_clear()
    assert receipt.is_success

    # Check that DOT tokens for liquidity have been transfered succesfully
    dot_liquidity = state_token_assets_accounts(si_peaq, kp_para_sudo, asset_id)
    # Remove the existing liquidity from the account
    dot_liquidity = dot_liquidity - MORE_EXISTENTIAL_TOKENS
    assert dot_liquidity >= dot(TOK_LIQUIDITY)
    # Check that beneficiary has DOT and PEAQ tokens available
    dot_balance = state_token_assets_accounts(si_peaq, kp_beneficiary, asset_id)
    assert dot_balance > dot(TOK_SWAP)

    # 1.) Create a liquidity pair and add liquidity on pallet Zenlink-Protocol
    compose_zdex_create_lppair(bt_para_sudo, asset_id)
    # Check different amounts of liquidity!!!
    compose_zdex_add_liquidity(bt_para_sudo, asset_id, dot_liquidity, dot_liquidity)
    # Reset user1's account to very low amount, to test payment in local currency
    # force pay the fee by other currency
    compose_balances_setbalance(
        bt_para_sudo, user_bene, get_existential_deposit(si_peaq) + 1000)
    receipt = bt_para_sudo.execute_n_clear()
    print(f'create_pair_n_swap_test: receipt: {receipt.error_message}')
    assert receipt.is_success

    # Check that liquidity pool is filled with DOT-tokens
    lpstatus = state_znlnkprot_lppair_status(si_peaq, asset_id)
    assert lpstatus['total_supply'] >= dot(TOK_LIQUIDITY)

    # Check that RPC functionality is working on this created lp-pair.
    asset0, asset1 = compose_zdex_lppair_params(asset_id, False)
    bl_hsh = si_peaq.get_block_hash(None)
    data = si_peaq.rpc_request(
        'zenlinkProtocol_getPairByAssetId',
        [asset0, asset1, bl_hsh])
    assert not data['result'] is None

    # 2.) Swap liquidity pair on Zenlink-DEX
    block_idx_peaq = si_peaq.get_block_number(None)
    compose_zdex_swap_exact_for(bt_para_bene, asset_id, amount_in1=dot(TOK_SWAP))
    receipt = bt_para_bene.execute_n_clear()
    assert receipt.is_success
    wait_n_check_swap_event(si_peaq, dot(TOK_SWAP), block_idx_peaq)

    block_idx_peaq = si_peaq.get_block_number(None)
    compose_zdex_swap_exact_for(bt_para_bob, asset_id, amount_in0=peaq(TOK_SWAP))
    receipt = bt_para_bob.execute_n_clear()
    assert receipt.is_success
    wait_n_check_swap_event(si_peaq, dot(TOK_SWAP), block_idx_peaq)

    # 3.) Remove some liquidity
    compose_zdex_remove_liquidity(bt_para_sudo, asset_id, int(dot_liquidity / 4))
    receipt = bt_para_sudo.execute_n_clear()
    assert receipt.is_success

    show_test('create_pair_n_swap_test', True)


def count_zdex_swap_events(receipt):
    """數某筆 extrinsic 觸發的 ZenlinkProtocol.AssetSwap 事件數(含 fee-payment 的 swap)。"""
    n = 0
    for ev in receipt.triggered_events:
        val = ev.value
        inner = val.get('event', val)
        if inner.get('module_id') == 'ZenlinkProtocol' and inner.get('event_id') == 'AssetSwap':
            n += 1
    return n


def payment_local_currency_single_swap_test(si_peaq, asset_id):
    """
    回歸測試 fix#2(runtime/common payment.rs can_withdraw_fee):
    使用者 native 不足、以 local currency(asset_id)付手續費時,fee-payment 只能觸發「一次」
    Zenlink swap。修復前 can_withdraw_fee 在 validate 階段也 swap 一次 → 共兩次(double-swap,
    且 validate 有副作用)。本測試用一筆「非-swap」extrinsic(system.remark)隔離出 fee-payment
    的 swap,斷言剛好一次。
    前置:asset_id/native 的 Zenlink pool 已存在且有流動性(可先跑 create_pair_n_swap_test)。
    """
    show_subtitle('payment_local_currency_single_swap_test')
    user = URI_MOON
    kp_sudo = into_keypair(KP_GLOBAL_SUDO)
    kp_user = into_keypair(user)

    # user 要有足夠 local token 付費、但 native 幾乎為 0 → 強制以 local currency 付費。
    bt_sudo = ExtrinsicBatch(si_peaq, kp_sudo)
    batch_mint(bt_sudo, kp_user.ss58_address, asset_id, 10 ** 20)
    compose_balances_setbalance(bt_sudo, user, get_existential_deposit(si_peaq) + 1000)
    assert bt_sudo.execute_n_clear().is_success

    asset_before = state_token_assets_accounts(si_peaq, kp_user, asset_id)

    # 送一筆非-swap extrinsic;手續費只能用 local currency 付(觸發 fee-payment swap)。
    bt_user = ExtrinsicBatch(si_peaq, kp_user)
    bt_user.compose_call('System', 'remark', {'remark': '0x00'})
    receipt = bt_user.execute_n_clear()
    assert receipt.is_success, \
        f'fee-in-local-currency remark failed: {receipt.error_message}'

    # 核心斷言:fee-payment 只 swap 一次(修復前 double-swap 會是 2)。
    swaps = count_zdex_swap_events(receipt)
    assert swaps == 1, \
        f'expected exactly 1 fee-payment swap, got {swaps} (double-swap regression!)'

    # 次要:local token 確實被扣(有付費)。
    asset_after = state_token_assets_accounts(si_peaq, kp_user, asset_id)
    assert asset_after < asset_before, \
        'fee should be paid in local currency (asset balance must drop)'

    show_test('payment_local_currency_single_swap_test', True)


def state_lp_asset_balance(si_peaq, kp_user, tok_idx):
    """讀使用者持有的 LP pallet-assets 餘額(帳戶被 reap 時 query 回 None → 視為 0)。"""
    lp_idx = state_znlnkprot_lppair_assetidx(si_peaq, tok_idx)
    q = si_peaq.query('Assets', 'Account', [lp_idx, kp_user.ss58_address])
    return 0 if q.value is None else int(q['balance'].value)


def lp_reap_on_remove_liquidity_test(si_peaq, asset_id):
    """
    回歸測試 fix#1(runtime/common wrapper.rs 非原生 withdraw 用 Expendable):
    使用者移除「全部自有」LP → ZenlinkProtocol.remove_liquidity →
    ZenlinkMultiAssets::withdraw(LP) → local_withdraw → PeaqMultiCurrenciesWrapper::withdraw
    (非原生) → Assets::burn_from。LP token 是有 min_balance 的 pallet-assets 資產,燒到 0 需 reap。
    修復前 Preservation::Protect 會卡 min_balance 底線 → FundsUnavailable → remove_liquidity 失敗;
    修復後 Expendable 可 reap → 成功。全程單鏈(remove_liquidity 同步執行,不涉 XCM)。
    前置:asset_id/native 的 pair 已存在且有流動性(先跑 create_pair_n_swap_test)。
    """
    show_subtitle('lp_reap_on_remove_liquidity_test')
    user = URI_MARS
    kp_sudo = into_keypair(KP_GLOBAL_SUDO)
    kp_user = into_keypair(user)

    # user 需有 token + native 才能加流動性;pair 已存在,故 user 非首位 LP(無 MINIMUM_LIQUIDITY 鎖)。
    dot_liq = dot(TOK_LIQUIDITY)
    peaq_liq = peaq(TOK_LIQUIDITY)
    bt_sudo = ExtrinsicBatch(si_peaq, kp_sudo)
    batch_mint(bt_sudo, kp_user.ss58_address, asset_id, dot_liq * 2)
    compose_balances_setbalance(bt_sudo, user, peaq_liq * 2)
    assert bt_sudo.execute_n_clear().is_success

    # user 加流動性 → 取得「自己完全持有」的 LP。
    bt_add = ExtrinsicBatch(si_peaq, kp_user)
    compose_zdex_add_liquidity(bt_add, asset_id, peaq_liq, dot_liq)
    assert bt_add.execute_n_clear().is_success
    lp_before = state_lp_asset_balance(si_peaq, kp_user, asset_id)
    assert lp_before > 0, 'user should hold LP after add_liquidity'

    # 移除「全部自有」LP → withdraw 燒 LP 到 0 → 需 Expendable。
    bt_rm = ExtrinsicBatch(si_peaq, kp_user)
    compose_zdex_remove_liquidity(bt_rm, asset_id, lp_before)
    receipt = bt_rm.execute_n_clear()

    # 核心斷言:修復後可 reap → 成功(修壞 Protect 會 FundsUnavailable)。
    assert receipt.is_success, \
        f'remove full LP failed (Protect regression?): {receipt.error_message}'

    # LP 帳戶被 reap 到 0(< min_balance → query None)。
    lp_after = state_lp_asset_balance(si_peaq, kp_user, asset_id)
    assert lp_after == 0, f'expected LP account reaped to 0, got {lp_after}'

    show_test('lp_reap_on_remove_liquidity_test', True)


def bootstrap_pair_n_swap_test(si_peaq, asset_id):
    """
    This test as about the Zenlink-DEX-Protocol bootstrap functionality.
    """
    show_subtitle('bootstrap_pair_n_swap_test')

    tok_limit = 5
    assert TOK_LIQUIDITY / 2 > tok_limit

    cont = URI_MOON
    user = URI_MARS

    kp_sudo = into_keypair(KP_GLOBAL_SUDO)
    kp_cont = into_keypair(cont)
    kp_user = into_keypair(user)

    bt_peaq_sudo = ExtrinsicBatch(si_peaq, kp_sudo)
    bt_peaq_cont = ExtrinsicBatch(si_peaq, kp_cont)
    bt_peaq_user = ExtrinsicBatch(si_peaq, kp_user)

    def ed_recal(val):
        # Use the 10 ** 18 for remote parachain's token because of the ED increase
        return int(val * 10 ** 18)

    # Transfer tokens from parachain to our chain
    amount = bifrost_amount_w_fees(ed_recal(TOK_LIQUIDITY)) // 2
    bt_sudo = ExtrinsicBatch(si_peaq, KP_GLOBAL_SUDO)
    batch_mint(bt_sudo, into_keypair(URI_GLOBAL_SUDO).ss58_address, asset_id, amount)
    batch_mint(bt_sudo, into_keypair(cont).ss58_address, asset_id, amount)
    batch_mint(bt_sudo, into_keypair(user).ss58_address, asset_id, bifrost_amount_w_fees(ed_recal(TOK_SWAP)))
    receipt = bt_sudo.execute_n_clear()
    assert receipt.is_success

    # 1.) Create bootstrap-liquidity-pair & start contributing
    compose_bootstrap_create_call(bt_peaq_sudo, asset_id,
                                  peaq(TOK_LIQUIDITY), ed_recal(TOK_LIQUIDITY),
                                  peaq(tok_limit), ed_recal(tok_limit))
    compose_bootstrap_contribute_call(bt_peaq_sudo, asset_id,
                                      peaq(TOK_LIQUIDITY/2), 0)
    compose_bootstrap_contribute_call(bt_peaq_sudo, asset_id,
                                      0, ed_recal(TOK_LIQUIDITY/2))
    receipt = bt_peaq_sudo.execute_n_clear()
    assert receipt.is_success

    # Check that bootstrap-liquidity-pair has been created
    lpstatus = state_znlnkprot_lppair_status(si_peaq, asset_id)
    assert lpstatus['target_supply'][0] == peaq(TOK_LIQUIDITY)
    assert lpstatus['target_supply'][1] == ed_recal(TOK_LIQUIDITY)
    assert lpstatus['capacity_supply'][0] == peaq(TOK_LIQUIDITY) * 100
    assert lpstatus['capacity_supply'][1] == ed_recal(TOK_LIQUIDITY) * 100
    assert lpstatus['accumulated_supply'][0] == peaq(TOK_LIQUIDITY/2)
    assert lpstatus['accumulated_supply'][1] == ed_recal(TOK_LIQUIDITY/2)

    # 2.) Contribute to bootstrap-liquidity-pair until goal is reached
    compose_bootstrap_contribute_call(bt_peaq_cont, asset_id,
                                      peaq(TOK_LIQUIDITY/2), 0)
    compose_bootstrap_contribute_call(bt_peaq_cont, asset_id,
                                      0, ed_recal(TOK_LIQUIDITY/2))
    receipt = bt_peaq_cont.execute_n_clear()
    assert receipt.is_success

    # Check that bootstrap-liquidity-pair has been created
    lpstatus = state_znlnkprot_lppair_status(si_peaq, asset_id)
    assert lpstatus['accumulated_supply'][0] == peaq(TOK_LIQUIDITY)
    assert lpstatus['accumulated_supply'][1] == ed_recal(TOK_LIQUIDITY)

    # 3.) Pool should be filled up (both targets are reached). now end bootstrap
    block_idx_peaq = si_peaq.get_block_number(None)
    compose_call_bootstrap_update_end(bt_peaq_sudo, asset_id)
    compose_bootstrap_end_call(bt_peaq_sudo, asset_id)
    receipt = bt_peaq_sudo.execute_n_clear()
    assert receipt.is_success
    wait_for_event(si_peaq, 'ZenlinkProtocol', 'BootstrapEnd', block_idx_prev=block_idx_peaq)

    # 4.) User swaps tokens by using the created pool
    block_idx_peaq = si_peaq.get_block_number(None)
    balance = get_account_balance(si_peaq, kp_user.ss58_address)
    compose_zdex_swap_exact_for(bt_peaq_user, asset_id, amount_in1=ed_recal(TOK_SWAP))
    receipt = bt_peaq_user.execute_n_clear()
    assert receipt.is_success
    wait_n_check_swap_event(si_peaq, 1, block_idx_peaq)

    # Check that pool has been fully created after goal was reached
    lpstatus = state_znlnkprot_lppair_status(si_peaq, asset_id)
    assert 'total_supply' in lpstatus.keys()  # means it is a true liquidity-pair
    assert lpstatus['total_supply'] > 0

    # Check tokens have been swaped and transfered to user's account
    new_balance = get_account_balance(si_peaq, kp_user.ss58_address)
    assert new_balance > balance

    show_test('bootstrap_pair_n_swap_test', True)


def zenlink_empty_lp_swap_test(si_peaq, asset_id):
    """
    Maryna encountered an issue while testing Zenlink, where one users swaps all available tokens
    of one currency, and then another user tries again to swap the same tokens. Kept this test
    situation to keep track of Zenlink's response on that.
    """
    show_subtitle('zenlink_empty_lp_swap_test')

    usr1 = URI_MOON
    usr2 = URI_MARS

    bt_sudo = ExtrinsicBatch(si_peaq, KP_GLOBAL_SUDO)
    bt_usr1 = ExtrinsicBatch(si_peaq, usr1)
    bt_usr2 = ExtrinsicBatch(si_peaq, usr2)

    # Setup until step 6.
    batch = ExtrinsicBatch(si_peaq, KP_GLOBAL_SUDO)
    batch_mint(batch, into_keypair(usr1).ss58_address, asset_id, dot(500000))
    receipt = batch.execute_n_clear()
    assert receipt.is_success

    compose_zdex_create_lppair(bt_sudo, asset_id)
    compose_balances_setbalance(bt_sudo, usr1, peaq(30000))
    compose_balances_setbalance(bt_sudo, usr2, peaq(20000))
    receipt = bt_sudo.execute_n_clear()
    assert receipt.is_success

    # 7.
    compose_zdex_add_liquidity(bt_usr1, asset_id, peaq(10000), dot(10000))
    receipt = bt_usr1.execute_n_clear()
    assert receipt.is_success

    # 8 #less then existential deposit
    compose_zdex_swap_for_exact(bt_usr2, asset_id, amount_out1=dot(10000) - 10, amnt_in_max=10 ** 25)
    receipt = bt_usr2.execute_n_clear()
    assert not receipt.is_success

    # 9. will get 8xx dot tokens
    compose_zdex_swap_exact_for(bt_usr2, asset_id, amount_in0=peaq(1))
    receipt = bt_usr2.execute_n_clear()
    assert receipt.is_success

    dot_balance = state_token_assets_accounts(si_peaq, bt_usr2.keypair, asset_id)
    assert dot_balance > 0

    # 10. #error, overflow
    compose_zdex_swap_for_exact(bt_usr2, asset_id, amount_out1=dot(10000), amnt_in_max=10 ** 25)
    receipt = bt_usr2.execute_n_clear()
    assert not receipt.is_success

    # 11. add liquility again
    compose_zdex_add_liquidity(bt_usr1, asset_id, peaq(10), 1)
    receipt = bt_usr1.execute_n_clear()
    assert receipt.is_success


@pytest.mark.substrate
class TestZenlinkDex(unittest.TestCase):
    def setUp(self):
        wait_until_block_height(SubstrateInterface(url=PARACHAIN_WS_URL), 1)
        show_title('Zenlink-DEX-Protocol Test')
        self.si_peaq = SubstrateInterface(url=PARACHAIN_WS_URL)
        funds(self.si_peaq, KP_GLOBAL_SUDO,
              [into_keypair(URI_MOON).ss58_address, into_keypair(URI_MARS).ss58_address],
              100000 * 10 ** 18)

    @pytest.mark.xcm
    def test_create_pair_swap(self):
        show_title('Zenlink-DEX-Protocol create pair swap Test')
        try:
            si_peaq = SubstrateInterface(url=PARACHAIN_WS_URL)
            # [TODO] It can only be asset 1...
            asset_id = 1
            setup_asset_if_not_exist(si_peaq, KP_GLOBAL_SUDO, asset_id, RELAY_METADATA)
            create_pair_n_swap_test(si_peaq, asset_id)

        except Exception:
            ex_type, ex_val, ex_tb = sys.exc_info()
            tb = traceback.TracebackException(ex_type, ex_val, ex_tb)
            show_test(tb.stack[-1].name, False, tb.stack[-1].lineno)
            raise

    @pytest.mark.xcm
    def test_payment_local_currency_single_swap(self):
        show_title('Zenlink-DEX fee-in-local-currency single-swap Test')
        try:
            si_peaq = SubstrateInterface(url=PARACHAIN_WS_URL)
            asset_id = 1
            setup_asset_if_not_exist(si_peaq, KP_GLOBAL_SUDO, asset_id, RELAY_METADATA)
            # 建 pool + 流動性(避開 flaky create_pair_n_swap_test / wait_n_check_swap_event)。
            kp_sudo = into_keypair(KP_GLOBAL_SUDO)
            bt = ExtrinsicBatch(si_peaq, kp_sudo)
            batch_mint(bt, kp_sudo.ss58_address, asset_id, dot(TOK_LIQUIDITY) * 4)
            assert bt.execute_n_clear().is_success
            if not state_znlnkprot_lppair_status(si_peaq, asset_id):
                bt2 = ExtrinsicBatch(si_peaq, kp_sudo)
                compose_zdex_create_lppair(bt2, asset_id)
                assert bt2.execute_n_clear().is_success
            bt3 = ExtrinsicBatch(si_peaq, kp_sudo)
            compose_zdex_add_liquidity(bt3, asset_id, peaq(TOK_LIQUIDITY), dot(TOK_LIQUIDITY))
            assert bt3.execute_n_clear().is_success
            payment_local_currency_single_swap_test(si_peaq, asset_id)
            lp_reap_on_remove_liquidity_test(si_peaq, asset_id)

        except Exception:
            ex_type, ex_val, ex_tb = sys.exc_info()
            tb = traceback.TracebackException(ex_type, ex_val, ex_tb)
            show_test(tb.stack[-1].name, False, tb.stack[-1].lineno)
            raise

    @pytest.mark.xcm
    def test_booststrap(self):
        show_title('Zenlink-DEX-Protocol boostrap Test')
        try:
            si_peaq = SubstrateInterface(url=PARACHAIN_WS_URL)
            asset_id = get_valid_asset_id(si_peaq)
            setup_asset_if_not_exist(si_peaq, KP_GLOBAL_SUDO, asset_id, ACA_METADATA)

            bootstrap_pair_n_swap_test(si_peaq, asset_id)

        except Exception:
            ex_type, ex_val, ex_tb = sys.exc_info()
            tb = traceback.TracebackException(ex_type, ex_val, ex_tb)
            show_test(tb.stack[-1].name, False, tb.stack[-1].lineno)
            raise

    @pytest.mark.xcm
    def test_empty_lp_swap(self):
        show_title('Zenlink-DEX-Protocol empty lp swap Test')
        try:
            si_peaq = SubstrateInterface(url=PARACHAIN_WS_URL)
            asset_id = get_valid_asset_id(si_peaq)
            setup_asset_if_not_exist(si_peaq, KP_GLOBAL_SUDO, asset_id, RELAY_METADATA, 100)

            zenlink_empty_lp_swap_test(si_peaq, asset_id)

        except Exception:
            ex_type, ex_val, ex_tb = sys.exc_info()
            tb = traceback.TracebackException(ex_type, ex_val, ex_tb)
            show_test(tb.stack[-1].name, False, tb.stack[-1].lineno)
            raise
