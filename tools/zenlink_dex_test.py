import sys, traceback

sys.path.append('./')

from substrateinterface import SubstrateInterface, Keypair
from tools.utils import RELAYCHAIN_WS_URL, PARACHAIN_WS_URL, BIFROST_WS_URL, ExtrinsicBatch
from tools.utils import show_test, show_title, show_subtitle, wait_for_event, get_account_balance
from tools.currency import peaq, mpeaq, npeaq, dot, bnc


# Technical constants
PEAQ_PARACHAIN_ID = 2000
BIFROST_PARACHAIN_ID = 3000
XCM_VER = 'V3'  # So far not tested with V2!
XCM_RTA_TO = 45  # timeout for xcm-rta
DOT_IDX = 64 # u8 value for DOT-token (CurrencyId/TokenSymbol)
BNC_IDX = 129 # u8 value for BNC-token (CurrencyId/TokenSymbol)
# Test parameter configurations
BENEFICIARY = '//Dave'
TOK_LIQUIDITY = 20  # generic amount of tokens
TOK_SWAP = 5  # generic amount of tokens


def relay_amount_w_fees(x):
    return x + dot(2.5)


def bifrost_amount_w_fees(x):
    return x + bnc(1)


def compose_zdex_lppair_params(tok_idx, w_str=True):
    if w_str:
        chain_id = str(PEAQ_PARACHAIN_ID)
        zero = '0'
        two = '2'
        asset_idx = str(tok_idx)
    else:
        chain_id = PEAQ_PARACHAIN_ID
        zero = 0
        two = 2
        asset_idx = tok_idx
    asset0 = {
        'chain_id': chain_id,
        'asset_type': zero,
        'asset_index': zero,
    }
    asset1 = {
        'chain_id': chain_id,
        'asset_type': two,
        'asset_index': asset_idx,
    }
    return asset0, asset1


def calc_deadline(substrate):
    return substrate.get_block_number(None) + 10


def compose_balances_transfer(batch, kp_beneficiary, amount):
    params = {
        'dest': kp_beneficiary.ss58_address,
        'value': str(amount),
    }
    batch.compose_call('Balances', 'transfer', params)


# Composes a XCM Reserve-Transfer-Asset call to transfer DOT-tokens
# from relaychain to parachain
def compose_xcm_rta_relay2para(batch, kp_beneficiary, amount):
    dest = { XCM_VER: {
        'parents': '0',
        'interior': { 'X1': { 'Parachain': f'{PEAQ_PARACHAIN_ID}' }}
    }}
    beneficiary = { XCM_VER: {
        'parents': '0',
        'interior': { 'X1': { 'AccountId32': (None, kp_beneficiary.public_key) }}
    }}
    assets = { XCM_VER: [[{
        'id': { 'Concrete': { 'parents': '0', 'interior': 'Here' }},
        'fun': { 'Fungible': f'{amount}' }
        }]]}
    params = {
        'dest': dest,
        'beneficiary': beneficiary,
        'assets': assets,
        'fee_asset_item': '0'
    }
    batch.compose_call('XcmPallet', 'reserve_transfer_assets', params)


def compose_xtokens_transfer(batch, kp_beneficiary, amount):
    params = {
        'currency_id': { 'Native': 'BNC' },
        'amount': str(amount),
        'dest': { XCM_VER: {
            'parents': '1',
            'interior': { 'X2': [
                {'Parachain': f'{PEAQ_PARACHAIN_ID}'},
                {'AccountId32': (None, kp_beneficiary.public_key)}
                ]}
            }},
        'dest_weight_limit': 'Unlimited',
    }
    batch.compose_call('XTokens', 'transfer', params)


def compose_zdex_create_lppair(batch, tok_idx):
    asset_0, asset_1 = compose_zdex_lppair_params(tok_idx)
    params = {
        'asset_0': asset_0,
        'asset_1': asset_1,
    }
    batch.compose_sudo_call('ZenlinkProtocol', 'create_pair', params)


def compose_zdex_add_liquidity(batch, tok_idx, liquidity0, liquidity1):
    asset_0, asset_1 = compose_zdex_lppair_params(tok_idx)
    deadline = calc_deadline(batch.substrate)
    params = {
        'asset_0': asset_0,
        'asset_1': asset_1,
        'amount_0_desired': str(liquidity0),
        'amount_1_desired': str(liquidity1),
        'amount_0_min': '0',
        'amount_1_min': '0',
        'deadline': str(deadline),
    }
    batch.compose_call('ZenlinkProtocol', 'add_liquidity', params)


def compose_zdex_swap_lppair(batch, tok_idx, amount1, amount0=0):
    assert amount0 == 0 or amount1 == 0
    if amount1 > 0:
        asset_0, asset_1 = compose_zdex_lppair_params(tok_idx)
        amount = amount1
    else:
        asset_1, asset_0 = compose_zdex_lppair_params(tok_idx)
        amount = amount0
    deadline = calc_deadline(batch.substrate)
    params = {
        'amount_in': str(amount),
        'amount_out_min': '0',
        'path': [asset_1, asset_0],
        'recipient': batch.kp_default.ss58_address,
        'deadline': deadline,
    }
    batch.compose_call('ZenlinkProtocol', 'swap_exact_assets_for_assets', params)


def compose_zdex_remove_liquidity(batch, tok_idx, amount):
    asset_0, asset_1 = compose_zdex_lppair_params(tok_idx)
    deadline = calc_deadline(batch.substrate)
    params = {
        'asset_0': asset_0,
        'asset_1': asset_1,
        'liquidity': str(amount),
        'amount_0_min': '1',
        'amount_1_min': '1',
        'recipient': batch.kp_default.ss58_address,
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


def state_tokens_accounts(si_peaq, kp_user, token):
    params = [kp_user.ss58_address, {'Token': token}]
    query = si_peaq.query('Tokens', 'Accounts', params)
    return int(query['free'].value)


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


def wait_n_check_event(substrate, module, event, attributes=None):
    event = wait_for_event(substrate, module, event,
                           attributes=attributes,
                           timeout=XCM_RTA_TO)
    assert not event is None


def wait_n_check_token_deposit(substrate, kp_beneficiary, token):
    attributes = {
        'currency_id': {'Token': token},
        'who': kp_beneficiary.ss58_address
    }
    wait_n_check_event(substrate, 'Tokens', 'Deposited', attributes)


def wait_n_check_swap_event(substrate, min_tokens):
    event = wait_for_event(substrate, 'ZenlinkProtocol', 'AssetSwap', timeout=XCM_RTA_TO)
    assert not event is None
    assert event['attributes'][3][1] > min_tokens


def wait_check_bootstrap_created(substrate):
    event = wait_for_event(substrate, 'ZenlinkProtocol', '')


def currency_transfer_test(si_relay, si_peaq, si_bifrost):
    """
    This test is about transfering foreign currencies from relaychain
    and another parachain to our local parachain.
    """
    show_subtitle('currency_transfer_test')

    kp_beneficiary = Keypair.create_from_uri(BENEFICIARY)
    kp_peaq_sudo = Keypair.create_from_uri('//Alice')
    kp_bob = Keypair.create_from_uri('//Bob')  # Bob exists everywhere

    bat_relay = ExtrinsicBatch(si_relay, kp_bob)
    bat_bifrost = ExtrinsicBatch(si_bifrost, kp_bob)
    bat_peaq = ExtrinsicBatch(si_peaq, kp_bob)

    # Check balance of beneficiary in dependency of test setup
    bat_peaq_sudo = ExtrinsicBatch(si_peaq, kp_peaq_sudo)
    bat_peaq_sudo.compose_sudo_call('Balances', 'set_balance', {
        'who': kp_beneficiary.ss58_address,
        'new_free': '500',
        'new_reserved': '0',
    })
    bat_peaq_sudo.execute_n_clear()

    # 1.) Transfer tokens from relaychain to peaq-parachain
    # Tokens to the sudo, to test if he can add liquidity
    compose_xcm_rta_relay2para(bat_relay, kp_peaq_sudo,
                               relay_amount_w_fees(dot(TOK_LIQUIDITY)))
    # Tokens to the user, to test if he can swap them
    compose_xcm_rta_relay2para(bat_relay, kp_beneficiary,
                               relay_amount_w_fees(dot(TOK_SWAP + 200)))
    bat_relay.execute_n_clear()
    wait_n_check_token_deposit(si_peaq, kp_beneficiary, 'DOT')

    # 2.) Transfer tokens from bifrost-parachain to peaq-parachain
    # Tokens to the sudo, to test if he can add liquidity
    compose_xtokens_transfer(bat_bifrost, kp_peaq_sudo,
                             bifrost_amount_w_fees(bnc(TOK_LIQUIDITY/2)))
    # Tokens to the user, to test if he can swap them
    compose_xtokens_transfer(bat_bifrost, kp_beneficiary,
                             bifrost_amount_w_fees(bnc(TOK_SWAP + 100)))
    # Tokens to some additional bootstrap contributer
    compose_xtokens_transfer(bat_bifrost, kp_bob,
                             bifrost_amount_w_fees(bnc(TOK_LIQUIDITY/2)))
    bat_bifrost.execute_n_clear()
    wait_n_check_token_deposit(si_peaq, kp_beneficiary, 'BNC')

    show_test('currency_transfer_test', True)


def create_pair_n_swap_test(si_peaq):
    """
    This test is about creating directly a liquidity-pair with the
    Zenlink-DEX-Protocol and using its swap-function (no bootstrap).
    This test also tests some of Zenlink-Protocol RPC methods.
    """
    show_subtitle('create_pair_n_swap_test')

    kp_beneficiary = Keypair.create_from_uri(BENEFICIARY)
    kp_para_sudo = Keypair.create_from_uri('//Alice')
    kp_para_bob = Keypair.create_from_uri('//Bob')
    
    bat_para_sudo = ExtrinsicBatch(si_peaq, kp_para_sudo)
    bat_para_bob = ExtrinsicBatch(si_peaq, kp_para_bob)
    bat_para_bene = ExtrinsicBatch(si_peaq, kp_beneficiary)

    # Check that DOT tokens for liquidity have been transfered succesfully
    dot_liquidity = state_tokens_accounts(si_peaq, kp_para_sudo, 'DOT')
    assert dot_liquidity > dot(TOK_LIQUIDITY)
    # Check that beneficiary has DOT and PEAQ tokens available
    dot_balance = state_tokens_accounts(si_peaq, kp_beneficiary, 'DOT')
    assert dot_balance > dot(TOK_SWAP)
    peaq_balance = get_account_balance(si_peaq, kp_beneficiary.ss58_address)
    assert peaq_balance < npeaq(1000)

    # 1.) Create a liquidity pair and add liquidity on pallet Zenlink-Protocol
    compose_zdex_create_lppair(bat_para_sudo, DOT_IDX)
    # Check different amounts of liquidity!!!
    compose_zdex_add_liquidity(bat_para_sudo, DOT_IDX, dot_liquidity, dot_liquidity)
    bat_para_sudo.execute_n_clear()

    # Check that liquidity pool is filled with DOT-tokens
    lpstatus = state_znlnkprot_lppair_status(si_peaq, DOT_IDX)
    assert lpstatus['total_supply'] >= dot(TOK_LIQUIDITY)

    # Check that RPC functionality is working on this created lp-pair.
    asset0, asset1 = compose_zdex_lppair_params(DOT_IDX, False)
    data = si_peaq.rpc_request(
        'zenlinkProtocol_getPairByAssetId',
        [asset0, asset1])
    assert not data['result'] is None
    
    # 2.) Swap liquidity pair on Zenlink-DEX
    # TODO: Finish RPC-check about amount_in.
    # est_amnt_in = si_peaq.rpc_request(
    #     'zenlinkProtocol_getAmountInPrice',
    #     [npeaq(200), [asset0, asset1]])
    # swap_amnt = dot_balance - est_amnt_in
    compose_zdex_swap_lppair(bat_para_bene, DOT_IDX, dot(TOK_SWAP))
    bat_para_bene.execute_n_clear()
    wait_n_check_swap_event(si_peaq, dot(TOK_SWAP*0.4))

    compose_zdex_swap_lppair(bat_para_bob, DOT_IDX, 0, peaq(TOK_SWAP))
    bat_para_bob.execute_n_clear()
    wait_n_check_swap_event(si_peaq, dot(TOK_SWAP*0.4))

    # 3.) Remove some liquidity
    compose_zdex_remove_liquidity(bat_para_sudo, DOT_IDX, int(dot_liquidity / 4))
    bat_para_sudo.execute_n_clear()
    
    show_test('create_pair_n_swap_test', True)


def bootstrap_pair_n_swap_test(si_peaq):
    """
    This test as about the Zenlink-DEX-Protocol bootstrap functionality.
    """
    show_subtitle('bootstrap_pair_n_swap_test')

    tok_limit = 5
    assert TOK_LIQUIDITY / 2 > tok_limit

    kp_sudo = Keypair.create_from_uri('//Alice')
    kp_cont = Keypair.create_from_uri('//Bob')
    kp_user = Keypair.create_from_uri(BENEFICIARY)

    bat_peaq_sudo = ExtrinsicBatch(si_peaq, kp_sudo)
    bat_peaq_cont = ExtrinsicBatch(si_peaq, kp_cont)
    bat_peaq_user = ExtrinsicBatch(si_peaq, kp_user)

    # 1.) Create bootstrap-liquidity-pair & start contributing
    compose_bootstrap_create_call(bat_peaq_sudo, BNC_IDX,
                                  peaq(TOK_LIQUIDITY), bnc(TOK_LIQUIDITY),
                                  peaq(tok_limit), bnc(tok_limit))
    compose_bootstrap_contribute_call(bat_peaq_sudo, BNC_IDX,
                                      peaq(TOK_LIQUIDITY/2), 0)
    compose_bootstrap_contribute_call(bat_peaq_sudo, BNC_IDX,
                                      0, bnc(TOK_LIQUIDITY/2))
    bat_peaq_sudo.execute_n_clear()

    # Check that bootstrap-liquidity-pair has been created
    lpstatus = state_znlnkprot_lppair_status(si_peaq, BNC_IDX)
    assert lpstatus['target_supply'][0] == peaq(TOK_LIQUIDITY)
    assert lpstatus['target_supply'][1] == bnc(TOK_LIQUIDITY)
    assert lpstatus['capacity_supply'][0] == peaq(TOK_LIQUIDITY) * 100
    assert lpstatus['capacity_supply'][1] == bnc(TOK_LIQUIDITY) * 100
    assert lpstatus['accumulated_supply'][0] == peaq(TOK_LIQUIDITY/2)
    assert lpstatus['accumulated_supply'][1] == bnc(TOK_LIQUIDITY/2)

    # 2.) Contribute to bootstrap-liquidity-pair until goal is reached
    compose_bootstrap_contribute_call(bat_peaq_cont, BNC_IDX,
                                      peaq(TOK_LIQUIDITY/2), 0)
    compose_bootstrap_contribute_call(bat_peaq_cont, BNC_IDX,
                                      0, bnc(TOK_LIQUIDITY/2))
    bat_peaq_cont.execute_n_clear()

    # Check that bootstrap-liquidity-pair has been created
    lpstatus = state_znlnkprot_lppair_status(si_peaq, BNC_IDX)
    assert lpstatus['accumulated_supply'][0] == peaq(TOK_LIQUIDITY)
    assert lpstatus['accumulated_supply'][1] == bnc(TOK_LIQUIDITY)

    # 3.) Pool should be filled up (both targets are reached). now end bootstrap
    compose_call_bootstrap_update_end(bat_peaq_sudo, BNC_IDX)
    compose_bootstrap_end_call(bat_peaq_sudo, BNC_IDX)
    bat_peaq_sudo.execute_n_clear()
    wait_for_event(si_peaq, 'ZenlinkProtocol', 'BootstrapEnd')

    # 4.) User swaps tokens by using the created pool
    balance = get_account_balance(si_peaq, kp_user.ss58_address)
    compose_zdex_swap_lppair(bat_peaq_user, BNC_IDX, bnc(TOK_SWAP))
    bat_peaq_user.execute_n_clear()
    wait_n_check_swap_event(si_peaq, 1)

    # Check that pool has been fully created after goal was reached
    lpstatus = state_znlnkprot_lppair_status(si_peaq, BNC_IDX)
    assert 'total_supply' in lpstatus.keys()  # means it is a true liquidity-pair
    assert lpstatus['total_supply'] > 0

    # Check tokens have been swaped and transfered to user's account
    new_balance  = get_account_balance(si_peaq, kp_user.ss58_address)
    assert new_balance > balance

    show_test('bootstrap_pair_n_swap_test', True)


def zenlink_dex_test():
    show_title('Zenlink-DEX-Protocol Test')
    try:
        with SubstrateInterface(url=RELAYCHAIN_WS_URL) as si_relay:
            with SubstrateInterface(url=PARACHAIN_WS_URL) as si_peaq:
                with SubstrateInterface(url=BIFROST_WS_URL) as si_bifrost:
                    # Order of tests is important (they're structured)
                    # 1.) currency_transfer_test for proper balances
                    currency_transfer_test(si_relay, si_peaq, si_bifrost)
                    # 2.) all zenlink-specific tests
                    create_pair_n_swap_test(si_peaq)
                    bootstrap_pair_n_swap_test(si_peaq)

    except ConnectionRefusedError:
        print("⚠️  No local Substrate node(s) running, \
            check for a running peaq-node and a running bifrost-node first")
        sys.exit()

    except AssertionError:
        ex_type, ex_val, ex_tb = sys.exc_info()
        tb = traceback.TracebackException(ex_type, ex_val, ex_tb)
        show_test(tb.stack[-1].name, False, tb.stack[-1].lineno)
