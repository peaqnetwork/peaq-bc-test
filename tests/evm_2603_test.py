"""
EVM / Frontier behaviour that changed with polkadot-sdk stable2603 (Frontier 92fc798), on a local network:
- AC-31 EIP-7702 (type 4) transactions; AC-32 an EOA with a delegation calling the Batch (0x805) and
  XcmUtils (0x804) precompiles; AC-33 the EIP-7623 calldata floor; AC-38 unprotected legacy transactions
  and a gas limit just under the block's; AC-77 high-s signatures refused for all four transaction types;
- AC-34 EVM tracing; AC-35 the logs journal limits; AC-36 eth_blockNumber after an RPC node restart;
  AC-37 the log query limits.

Transactions are built and signed by tools/eth_raw_tx.py (eth-account 0.9.0 has no type 4), and the
responses are checked raw, with the functions in tools/evm_2603_checks.py.

Two endpoints: ETH_URL, the collator, for what the runtime decides (AC-31, 32, 33, 38), and RPC_NODE_URL, a
non-collator node started with --ethapi=debug,trace,txpool (run_pr11.sh starts one on the host), for what
the RPC node does itself (AC-34 to AC-37). AC-77 sends to both. Tests that need the RPC node skip when
nothing answers there. AC-36 also needs PR11_RPC_RESTART, a command that restarts that node; AC-37 needs a
chain higher than 2000 blocks and waits for one only when PR11_WAIT_FOR_HEIGHT is set.
"""
import json
import os
import subprocess
import threading
import time
import unittest

import pytest
import websocket
from eth_account import Account
from eth_utils import keccak, to_checksum_address
from peaq.eth import calculate_evm_account
from peaq.utils import ExtrinsicBatch
from substrateinterface import SubstrateInterface
from web3 import Web3

from tools import eth_raw_tx as T
from tools.constants import ETH_URL, KP_GLOBAL_SUDO, WS_URL
from tools.evm_2603_checks import (
    check_accepted, check_call_trace_logs, check_high_s_rejected, check_high_s_version,
    check_not_callable_by_contracts, check_not_refused_for_gas_cap)
from tools.peaq_eth_utils import get_contract
from tools.runtime_upgrade import wait_until_block_height
from tools.utils import batch_fund

RPC_NODE_URL = 'http://127.0.0.1:20044'
RPC_NODE_WS = 'ws://127.0.0.1:20044'
BATCH_ADDRESS = '0x0000000000000000000000000000000000000805'
XCMUTILS_ADDRESS = '0x0000000000000000000000000000000000000804'
DID_ADDRESS = '0x0000000000000000000000000000000000000800'
FUNDS = 10 ** 24

# Runtime code of the test contracts, hand-assembled (bc-test has no Solidity compiler):
RETURN_42 = bytes.fromhex('602a60005260206000f3')  # MSTORE(0, 42) RETURN(0, 32)
EMPTY_FALLBACK = bytes.fromhex('00')  # STOP
# calldata (n, size): n times LOG0(offset 0, size); the loop counter n and size stay on the stack
LOG0_LOOP = bytes.fromhex('600035' '602035' '5b' '81' '15' '6019' '57' '80' '6000' 'a0'
                          '90' '6001' '90' '03' '90' '6006' '56' '5b' '00')
LOG1_TOPIC = keccak(b'pr11 LOG1')
LOG1_ONE = bytes.fromhex('602a600052' '7f' + LOG1_TOPIC.hex() + '6020' '6000' 'a1' '00')  # LOG1(0, 32, topic) of 42


def rpc_node_up():
    try:
        return Web3(Web3.HTTPProvider(RPC_NODE_URL, request_kwargs={'timeout': 5})).eth.block_number >= 0
    except Exception:
        return False


class Chain:
    """Raw JSON-RPC over one endpoint, plus the few transaction helpers the tests share."""

    def __init__(self, url):
        self.w3 = Web3(Web3.HTTPProvider(url, request_kwargs={'timeout': 120}))
        self.chain_id = self.w3.eth.chain_id

    def rpc(self, method, params):
        return self.w3.provider.make_request(method, params)

    def nonce(self, address):
        return self.w3.eth.get_transaction_count(address, 'pending')

    def tx(self, sender, tx_type=2, to=None, data=b'', gas=200_000, value=0, nonce=None, **extra):
        tx = {'type': tx_type, 'nonce': self.nonce(sender) if nonce is None else nonce, 'gas': gas,
              'to': T.address_bytes(to) if to else b'', 'value': value, 'data': data}
        price = self.w3.eth.gas_price
        if tx_type in (0, 1):
            tx['gasPrice'] = price
        else:
            tx['maxPriorityFeePerGas'], tx['maxFeePerGas'] = 0, 2 * price
        if tx_type != 0 or 'chainId' not in extra:
            tx['chainId'] = self.chain_id
        if tx_type != 0:
            tx['accessList'] = []
        tx.update(extra)
        return tx

    def send(self, signed):
        return self.rpc('eth_sendRawTransaction', ['0x' + T.encode(signed).hex()])

    def receipt(self, tx_hash):
        return self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)

    def send_ok(self, key, tx):
        response = self.send(T.sign(tx, key))
        assert 'result' in response, f'transaction refused: {response}'
        return self.receipt(response['result'])

    def deploy(self, key, sender, runtime_code):
        tx = self.tx(sender, data=T.deploy_code(runtime_code), gas=300_000)
        receipt = self.send_ok(key, tx)
        assert receipt['status'] == 1, f'deploy failed: {receipt}'
        return receipt['contractAddress']


def new_funded_accounts(count):
    accounts = [Account.create() for _ in range(count)]
    substrate = SubstrateInterface(url=WS_URL)
    batch = ExtrinsicBatch(substrate, KP_GLOBAL_SUDO)
    for a in accounts:
        batch_fund(batch, calculate_evm_account(a.address), FUNDS)
    receipt = batch.execute()
    assert receipt.is_success, f'funding failed: {receipt.error_message}'
    return [(bytes(a.key), a.address) for a in accounts]


def delegate(chain, key, address, target):
    """AC-31's type-4 transaction: `address` signs an authorization to `target` and sends it itself."""
    nonce = chain.nonce(address)
    # the sender is the authority, so its nonce is already +1 when the authorization is checked
    auth = T.sign_authorization(chain.chain_id, target, nonce + 1, key)
    tx = chain.tx(address, tx_type=4, to=address, gas=100_000, nonce=nonce, authorizationList=[auth])
    response = chain.send(T.sign(tx, key))
    return nonce, response


@pytest.mark.eth
class TestEvm2603Runtime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        wait_until_block_height(SubstrateInterface(url=WS_URL), 3)
        cls.chain = Chain(ETH_URL)

    def setUp(self):
        (self.key, self.addr), (self.key2, self.addr2) = new_funded_accounts(2)

    def test_ac31_eip7702_delegation_and_clear(self):
        c = self.chain
        target = c.deploy(self.key2, self.addr2, RETURN_42)
        nonce, response = delegate(c, self.key, self.addr, target)
        self.assertIn('result', response, f'eth_sendRawTransaction refused the type-4 transaction: {response}')
        receipt = c.receipt(response['result'])
        print('AC-31 type-4 receipt:', dict(receipt))
        self.assertEqual(receipt['status'], 1)
        self.assertEqual(int(receipt['type']), 4)
        code = bytes(c.w3.eth.get_code(self.addr))
        self.assertEqual(code, b'\xef\x01\x00' + T.address_bytes(target), f'eth_getCode: 0x{code.hex()}')
        self.assertEqual(c.nonce(self.addr), nonce + 2, 'the transaction and the authorization each add 1')
        result = c.rpc('eth_call', [{'to': self.addr, 'data': '0x'}, 'latest'])
        self.assertEqual(int(result['result'], 16), 42, f'eth_call of the delegated EOA: {result}')

        nonce, response = delegate(c, self.key, self.addr, '0x' + '00' * 20)
        self.assertIn('result', response, f'the clearing authorization was refused: {response}')
        self.assertEqual(c.receipt(response['result'])['status'], 1)
        self.assertEqual(bytes(c.w3.eth.get_code(self.addr)), b'', 'an authorization to 0x0 clears the code')

    def _precompile_calls(self):
        batch = get_contract(self.chain.w3, BATCH_ADDRESS, 'ETH/batch/abi')
        xcm = get_contract(self.chain.w3, XCMUTILS_ADDRESS, 'ETH/xcmutils/abi')
        return {
            'Batch.batchAll': (BATCH_ADDRESS, batch.encodeABI(fn_name='batchAll', args=[[], [], [], []])),
            'XcmUtils.xcmExecute': (XCMUTILS_ADDRESS, xcm.encodeABI(
                fn_name='xcmExecute', args=[self._xcm_execute_message(), 20_000_000_000])),
        }

    @staticmethod
    def _xcm_execute_message():
        """The message bridge_xcmutils_test sends: withdraw 1 PEAQ, deposit it to a new account."""
        si = SubstrateInterface(url=WS_URL)
        beneficiary = Account.create()
        message = {'V4': [[
            {'WithdrawAsset': [[{'id': {'parents': '0', 'interior': 'Here'}, 'fun': {'Fungible': 10 ** 18}}]]},
            {'DepositAsset': {'assets': {'Wild': {'AllCounted': 1}}, 'beneficiary': {
                'parents': '0', 'interior': {'X1': [{'AccountId32': {
                    'network': None, 'id': '0x' + keccak(beneficiary.key)[:32].hex()}}]}}}},
        ]]}
        call = si.compose_call(call_module='PolkadotXcm', call_function='execute', call_params={
            'message': message, 'max_weight': {'ref_time': 2 * 10 ** 21, 'proof_size': 10 ** 12}})
        return call['call_args']['message'].encode().data

    def _call_and_send(self, key, sender, to, data):
        # 3M gas: xcmExecute reserves its maxWeight as gas, so a revert is never for want of gas
        call = self.chain.rpc('eth_call', [{'from': sender, 'to': to, 'data': data, 'gas': hex(3_000_000)}, 'latest'])
        tx = self.chain.tx(sender, to=to, data=bytes.fromhex(data[2:]), gas=3_000_000)
        return call, self.chain.send_ok(key, tx)

    def test_ac32_delegated_eoa_cannot_call_batch_or_xcm_execute(self):
        target = self.chain.deploy(self.key2, self.addr2, RETURN_42)
        _, response = delegate(self.chain, self.key, self.addr, target)
        self.assertEqual(self.chain.receipt(response['result'])['status'], 1)
        for name, (to, data) in self._precompile_calls().items():
            with self.subTest(caller='delegated EOA', precompile=name):
                call, receipt = self._call_and_send(self.key, self.addr, to, data)
                print(f'AC-32 delegated EOA {name}: eth_call {call}, receipt status {receipt["status"]}')
                check_not_callable_by_contracts(call, receipt)
            with self.subTest(caller='plain EOA', precompile=name):
                call, receipt = self._call_and_send(self.key2, self.addr2, to, data)
                print(f'AC-32 plain EOA {name}: eth_call {call}, receipt status {receipt["status"]}')
                self.assertNotIn('error', call, f'eth_call from a plain EOA failed: {call}')
                self.assertEqual(receipt['status'], 1, f'the plain EOA call reverted: {receipt}')
                # red check: the "reverts" check applied to the plain EOA's results must fail
                with self.assertRaises(AssertionError):
                    check_not_callable_by_contracts(call, receipt)

    def test_ac33_calldata_floor(self):
        """Sends (a), (b) and (c) and prints all three results before any assertion, so that one run on the
        2503 node records the baseline of all three (a failed assertion would stop the test there)."""
        c = self.chain
        target = c.deploy(self.key2, self.addr2, EMPTY_FALLBACK)
        data = b'\xff' * 4096  # 4096 non-zero bytes: 4 tokens each under EIP-7623
        standard, floor = 21000 + 16 * 4096, 21000 + 40 * 4096
        nonce = c.nonce(self.addr)
        response_a = c.send(T.sign(c.tx(self.addr, to=target, data=data, gas=standard), self.key))
        print('AC-33 (a) gas = 21000 + 16 x 4096:', response_a)
        if 'result' in response_a:
            print('AC-33 (a) gasUsed:', c.receipt(response_a['result'])['gasUsed'])
        nonce_after_a = c.nonce(self.addr)
        receipt_b = c.send_ok(self.key, c.tx(self.addr, to=target, data=data, gas=floor))
        print('AC-33 (b) gas = 21000 + 40 x 4096: status', receipt_b['status'], 'gasUsed', receipt_b['gasUsed'])
        estimate = c.rpc('eth_estimateGas', [{'from': self.addr, 'to': target, 'data': '0x' + data.hex()}])
        print('AC-33 (c) eth_estimateGas:', estimate, 'floor', floor)

        self.assertEqual(response_a.get('error', {}).get('message'), 'intrinsic gas too low', response_a)
        self.assertEqual(nonce_after_a, nonce, 'the refused transaction changed the nonce')
        self.assertEqual(receipt_b['status'], 1)
        self.assertEqual(receipt_b['gasUsed'], floor)
        self.assertGreaterEqual(int(estimate['result'], 16), floor)

    def test_ac33_did_add_attribute_gas(self):
        """Not a pass/fail check: prints the gasUsed of a DID addAttribute with a 2 KB value (ASCII: the pallet
        refuses other bytes with AttributeNonAsciiProperty)."""
        did = get_contract(self.chain.w3, DID_ADDRESS, 'ETH/did/abi')
        data = did.encodeABI(fn_name='addAttribute', args=[self.addr, b'pr11-ac33', b'a' * 2048, 1000])
        print('AC-33 DID eth_call:', self.chain.rpc('eth_call', [{'from': self.addr, 'to': DID_ADDRESS, 'data': data,
                                                                  'gas': hex(2_000_000)}, 'latest']))
        receipt = self.chain.send_ok(self.key, self.chain.tx(self.addr, to=DID_ADDRESS,
                                                             data=bytes.fromhex(data[2:]), gas=2_000_000))
        print('AC-33 DID addAttribute 2 KB value: status', receipt['status'], 'gasUsed', receipt['gasUsed'])
        self.assertEqual(receipt['status'], 1)

    def test_ac38_unprotected_legacy_transaction(self):
        c = self.chain
        tx = c.tx(self.addr, tx_type=0, to=self.addr2, value=1, gas=21000, chainId=None)
        response = c.send(T.sign(tx, self.key))
        print('AC-38 unprotected legacy:', response)
        check_accepted(response)
        self.assertEqual(c.receipt(response['result'])['status'], 1)
        # red check: the same transaction with a wrong chain id is refused, so check_accepted fails
        wrong = c.tx(self.addr, tx_type=0, to=self.addr2, value=1, gas=21000, chainId=c.chain_id + 1)
        response = c.send(T.sign(wrong, self.key))
        print('AC-38 wrong chain id:', response)
        with self.assertRaises(AssertionError):
            check_accepted(response)

    def test_ac38_gas_limit_just_under_the_block_limit(self):
        c = self.chain
        block_gas_limit = c.w3.eth.get_block('latest')['gasLimit']
        tx = c.tx(self.addr, to=self.addr2, value=1, gas=block_gas_limit - 1)
        response = c.send(T.sign(tx, self.key))
        print(f'AC-38 gas = {block_gas_limit} - 1:', response)
        check_not_refused_for_gas_cap(response)
        if 'result' in response:
            try:
                print('AC-38 receipt:', dict(c.w3.eth.wait_for_transaction_receipt(response['result'], timeout=60)))
            except Exception as e:
                print('AC-38 no receipt within 60 s (pending):', e)


@pytest.mark.eth
class TestEvm2603HighS(unittest.TestCase):
    """AC-77, on the collator and on the RPC node."""

    def _check_all_types(self, url):
        c = Chain(url)
        (key, sender), (auth_key, _) = new_funded_accounts(2)
        target = c.deploy(key, sender, RETURN_42)
        authorization = [T.sign_authorization(c.chain_id, target, 0, auth_key)]
        kinds = {'legacy': {'tx_type': 0}, 'EIP-2930': {'tx_type': 1}, 'EIP-1559': {'tx_type': 2},
                 'EIP-7702': {'tx_type': 4, 'authorizationList': authorization}}
        for name, kind in kinds.items():
            with self.subTest(url=url, type=name):
                low = T.sign(c.tx(sender, to=target, gas=100_000, **kind), key)
                high = T.with_high_s(low)
                check_high_s_version(high, sender)
                before = c.nonce(sender)
                response = c.send(high)
                print(f'AC-77 {url} {name} high-s:', json.dumps(response))
                check_high_s_rejected(response)
                self.assertEqual(c.nonce(sender), before, 'the pending nonce moved after the high-s transaction')
                response = c.send(low)
                self.assertIn('result', response, f'the low-s transaction was refused: {response}')
                receipt = c.receipt(response['result'])
                self.assertEqual(receipt['status'], 1)
                self.assertEqual(receipt['from'], sender)
                # red check (1): an accepted transaction's response fails check_high_s_rejected
                with self.assertRaises(AssertionError):
                    check_high_s_rejected(response)
        with self.subTest(url=url, type='red check (2): insufficient funds'):
            poor = Account.create()
            response = c.send(T.sign(c.tx(poor.address, to=target, gas=100_000), bytes(poor.key)))
            print(f'AC-77 {url} unfunded sender:', json.dumps(response))
            self.assertIn('error', response)
            with self.assertRaises(AssertionError):
                check_high_s_rejected(response)

    def test_ac77_high_s_refused_by_the_collator(self):
        wait_until_block_height(SubstrateInterface(url=WS_URL), 3)
        self._check_all_types(ETH_URL)

    def test_ac77_high_s_refused_by_the_rpc_node(self):
        if not rpc_node_up():
            self.skipTest(f'no RPC node at {RPC_NODE_URL}')
        self._check_all_types(RPC_NODE_URL)


@pytest.mark.eth
class TestEvm2603RpcNode(unittest.TestCase):
    """AC-34 to AC-37, on the RPC node."""

    @classmethod
    def setUpClass(cls):
        if not rpc_node_up():
            raise unittest.SkipTest(f'no RPC node at {RPC_NODE_URL}')
        cls.chain = Chain(RPC_NODE_URL)
        (cls.key, cls.addr), = new_funded_accounts(1)

    def _emit_log1(self, emitter):
        return self.chain.send_ok(self.key, self.chain.tx(self.addr, to=emitter, gas=100_000))

    def test_ac34_call_tracer_with_log(self):
        emitter = self.chain.deploy(self.key, self.addr, LOG1_ONE)
        receipt = self._emit_log1(emitter)
        trace = self.chain.rpc('debug_traceTransaction', [receipt['transactionHash'].hex(), {
            'tracer': 'callTracer', 'tracerConfig': {'withLog': True}}])
        print('AC-34 callTracer withLog:', json.dumps(trace))
        receipt_json = json.loads(Web3.to_json(receipt))
        check_call_trace_logs(trace, receipt_json)

    def test_ac34_trace_latest_is_the_best_block(self):
        """debug_traceBlockByNumber("latest") traces the block eth_getBlockByNumber("latest") returns, or the next."""
        substrate = SubstrateInterface(url=RPC_NODE_WS)
        emitter = self.chain.deploy(self.key, self.addr, LOG1_ONE)
        for _ in range(5):
            receipt = self._emit_log1(emitter)
            block = receipt['blockNumber']
            if substrate.get_block_number(substrate.get_chain_head()) != block:
                continue  # the next block is already out; try again with a new transaction
            trace = self.chain.rpc('debug_traceBlockByNumber', ['latest', {'tracer': 'callTracer'}])
            eth_latest = self.chain.w3.eth.get_block('latest')['number']
            hashes = [t.get('txHash') for t in trace.get('result', [])]
            print(f'AC-34 latest: tx in #{block}, eth latest #{eth_latest}, trace of latest has {hashes}')
            if receipt['transactionHash'].hex() not in hashes:
                continue  # a block came out between the receipt and the trace
            self.assertLessEqual(abs(eth_latest - block), 1)
            return
        self.fail('never caught the block with the transaction as the best block')

    def test_ac34_trace_block_from_an_earlier_runtime(self):
        """Traces an EVM block made by an earlier runtime version, through that version's override wasm."""
        substrate = SubstrateInterface(url=RPC_NODE_WS)
        current = substrate.get_block_runtime_version(None)['specVersion']
        latest = self.chain.w3.eth.block_number
        for number in range(1, latest + 1):
            count = int(self.chain.rpc('eth_getBlockTransactionCountByNumber', [hex(number)])['result'], 16)
            if count == 0:
                continue
            spec = substrate.rpc_request('state_getRuntimeVersion', [substrate.get_block_hash(number)])['result']
            if spec['specVersion'] >= current:
                break
            trace = self.chain.rpc('debug_traceBlockByNumber', [hex(number), {'tracer': 'callTracer'}])
            print(f'AC-34 block #{number} (spec {spec["specVersion"]}, now {current}):', json.dumps(trace))
            self.assertNotIn('error', trace)
            self.assertEqual(len(trace['result']), count)
            return
        self.skipTest('no EVM transaction from an earlier runtime version on this chain')

    def _subscribe_logs(self, address):
        ws = websocket.create_connection(RPC_NODE_WS, timeout=30)
        ws.send(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'eth_subscribe',
                            'params': ['logs', {'address': address}]}))
        return ws, json.loads(ws.recv())['result']

    @staticmethod
    def _read_subscription(ws):
        """Reads the connection on its own thread from before the transaction is sent, as a client would: a reader
        that only starts after the receipt leaves the node's buffers full (sc-rpc's BoundedVecDeque of 16 for the
        logs subscription, plus the connection's message buffer, 64 by default), and the node then drops the
        subscription for that reason, not for the journal. Returns the state dict and a stop function, which sends
        eth_unsubscribe, waits up to 10 s for its reply and stops the thread."""
        state = {'received': 0, 'unsubscribe': 'no reply within 10 s', 'stop': False}

        def run():
            ws.settimeout(1)
            while not state['stop']:
                try:
                    message = json.loads(ws.recv())
                except websocket.WebSocketTimeoutException:
                    continue
                except (websocket.WebSocketConnectionClosedException, ConnectionError) as e:
                    state['unsubscribe'] = f'connection closed: {e!r}'
                    return
                if message.get('method') == 'eth_subscription':
                    state['received'] += 1
                elif message.get('id') == 2:
                    state['unsubscribe'] = message
                    return

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

        def stop(sub):
            try:
                ws.send(json.dumps({'jsonrpc': '2.0', 'id': 2, 'method': 'eth_unsubscribe', 'params': [sub]}))
            except (websocket.WebSocketConnectionClosedException, ConnectionError) as e:
                state['unsubscribe'] = f'connection closed: {e!r}'
            thread.join(10)
            state['stop'] = True
            thread.join(2)
        return state, stop

    def _journal_case(self, emitter, count, size):
        c = self.chain
        ws, sub = self._subscribe_logs(emitter)
        state, stop = self._read_subscription(ws)
        filter_id = c.rpc('eth_newFilter', [{'address': emitter}])['result']
        data = count.to_bytes(32, 'big') + size.to_bytes(32, 'big')
        estimate = int(c.rpc('eth_estimateGas', [{'from': self.addr, 'to': emitter, 'data': '0x' + data.hex()}])
                       ['result'], 16)
        receipt = c.send_ok(self.key, c.tx(self.addr, to=emitter, data=data, gas=estimate))
        time.sleep(30)
        stop(sub)
        ws.close()
        received, unsubscribe = state['received'], state['unsubscribe']
        changes = c.rpc('eth_getFilterChanges', [filter_id])
        again = c.rpc('eth_getFilterChanges', [filter_id])
        result = {
            'logs': count, 'size': size, 'status': receipt['status'], 'gasUsed': receipt['gasUsed'],
            'block': receipt['blockNumber'], 'received': received, 'unsubscribe': unsubscribe,
            # eth_unsubscribe answers true only for a subscription that is still open
            'subscribed': isinstance(unsubscribe, dict) and unsubscribe.get('result') is True,
            'changes': len(changes['result']) if 'result' in changes else changes['error']['message'],
            'again': len(again['result']) if 'result' in again else again['error']['message'],
        }
        print('AC-35', json.dumps(result))
        return result

    def test_ac35_logs_journal_limits(self):
        """A measurement: prints each case, then checks which cases close the subscription and the filter.

        Frontier 92fc798 (client/rpc/src/logs_journal.rs, append_block_logs) marks a block's journal entry
        incomplete when its logs exceed 10,000 or when the retained bytes exceed 4 MiB, and it counts the
        bytes as size_of::<LogsJournalEntry>() + Vec capacity x size_of::<Log>() + topics and data capacity.
        size_of::<Log>() is 296 on x86_64 (my inference from the field list), and the Vec doubles: at log
        8,193 its capacity becomes 16,384, and 16,384 x 296 is over 4 MiB. So the expected boundaries are
        8,192 / 8,193 LOG0 and 126 / 127 logs of 32 KiB, not AC-35's 10,000 and 4 MiB; the case list
        brackets both.

        What closes the subscription for the journal: the node sends none of that block's logs (received 0) and
        eth_unsubscribe then answers false. A complete block's logs do start arriving. But sc-rpc drops a logs
        subscription by itself when one block has more matching logs than its buffers hold (the connection's
        message buffer, 64 by default, then a BoundedVecDeque of 16): measured 2026-11-26, 100 LOG0 gave 64 logs
        and a closed subscription on default settings, and 8,192 LOG0 gave 127 with the buffer at 20,000. So for
        8,192 LOG0 and 126 x 32 KiB the check is received > 0 and the filter returning every log; only 50 LOG0,
        which fits the default buffers, must arrive in full with the subscription still open. 100 LOG0 is printed,
        not checked.
        """
        emitter = self.chain.deploy(self.key, self.addr, LOG0_LOOP)
        kib = 1024
        cases = {name: self._journal_case(emitter, count, size) for name, (count, size) in {
            '50 LOG0': (50, 0), '100 LOG0 (printed only)': (100, 0), '8,192 LOG0': (8_192, 0),
            '8,193 LOG0': (8_193, 0), '9,999 LOG0': (9_999, 0), '10,000 LOG0': (10_000, 0),
            '10,001 LOG0': (10_001, 0), '126 x 32 KiB': (126, 32 * kib),
            '127 x 32 KiB (4 MiB - 32 KiB)': (127, 32 * kib), '129 x 32 KiB (over 4 MiB)': (129, 32 * kib),
        }.items()}
        for name in ['8,193 LOG0', '9,999 LOG0', '10,000 LOG0', '10,001 LOG0', '127 x 32 KiB (4 MiB - 32 KiB)',
                     '129 x 32 KiB (over 4 MiB)']:
            with self.subTest(name):
                r = cases[name]
                self.assertEqual(r['status'], 1)
                self.assertEqual(r['received'], 0, f'{name}: logs of an incomplete entry were sent')
                self.assertFalse(r['subscribed'], f'{name}: the subscription is still open')
                self.assertIn('recreate the filter', str(r['changes']))
                self.assertRegex(str(r['again']), r'Filter id .* does not exist')
        for name, logs in [('8,192 LOG0', 8_192), ('126 x 32 KiB', 126)]:
            with self.subTest(name):
                r = cases[name]
                self.assertEqual(r['status'], 1)
                self.assertGreater(r['received'], 0, f'{name}: no log arrived, the entry was marked incomplete')
                self.assertEqual(r['changes'], logs)
        r = cases['50 LOG0']
        self.assertEqual(r['status'], 1)
        self.assertTrue(r['subscribed'], '50 LOG0: the subscription was closed')
        self.assertEqual(r['received'], 50)
        self.assertEqual(r['changes'], 50)

    def test_ac36_eth_block_number_after_restart(self):
        """A measurement: restarts the RPC node, samples once a second for 60 s, checks seconds 30 to 60."""
        restart = os.environ.get('PR11_RPC_RESTART')
        if not restart:
            self.skipTest('PR11_RPC_RESTART is not set')
        before = self.chain.w3.eth.block_number
        subprocess.run([restart], check=True)
        samples, t0 = [], time.time()
        for second in range(60):
            time.sleep(max(0, t0 + second - time.time()))
            try:
                eth = int(self.chain.rpc('eth_blockNumber', [])['result'], 16)
                header = int(self.chain.rpc('chain_getHeader', [])['result']['number'], 16)
                samples.append((second, eth, header))
            except Exception as e:
                samples.append((second, None, type(e).__name__))
        print('AC-36 eth_blockNumber before the restart:', before)
        for s in samples:
            print('AC-36', s)
        valid = [(t, e, h) for t, e, h in samples if e is not None]
        lags = [h - e for _, e, h in valid]
        went_back = any(b[1] < a[1] for a, b in zip(valid, valid[1:])) or any(e < before for _, e, _ in valid)
        print(f'AC-36 max lag {max(lags) if lags else None}, went back {went_back}')
        late = [s for s in samples if 30 <= s[0] < 60]
        self.assertTrue(all(e is not None for _, e, _ in late), f'no answer in seconds 30 to 60: {late}')
        # a node that stopped following the chain has no lag either: the last sample must be near the collator's best
        collator_best = int(Chain(ETH_URL).rpc('chain_getHeader', [])['result']['number'], 16)
        print('AC-36 collator best after the samples:', collator_best)
        self.assertGreaterEqual(late[-1][2], collator_best - 2, f'the RPC node is not following the chain: {late[-1]}')
        self.assertTrue(all(abs(h - e) <= 1 for _, e, h in late), f'lag above 1 in seconds 30 to 60: {late}')

    def test_ac37_log_query_limits(self):
        c = self.chain
        wanted = int(os.environ.get('PR11_WAIT_FOR_HEIGHT', '0'))
        while c.w3.eth.block_number < wanted:
            time.sleep(60)
        latest = c.w3.eth.block_number
        if latest <= 2000:
            self.skipTest(f'the chain is at #{latest}, AC-37 needs more than 2000 blocks')
        emitter = c.deploy(self.key, self.addr, LOG1_ONE)
        block = self._emit_log1(emitter)['blockNumber']
        latest = c.w3.eth.block_number
        other = '0x' + keccak(b'pr11 other topic').hex()
        topic0 = '0x' + LOG1_TOPIC.hex()
        queries = [
            ('eth_getLogs range 1025', 'error', 'eth_getLogs',
             {'address': emitter, 'fromBlock': hex(latest - 1025), 'toBlock': hex(latest)}),
            ('eth_getLogs range 1024', 'result', 'eth_getLogs',
             {'address': emitter, 'fromBlock': hex(latest - 1024), 'toBlock': hex(latest)}),
            ('eth_newFilter from latest - 2000', 'error', 'eth_newFilter', {'fromBlock': hex(latest - 2000)}),
            ('5 topics', 'error', 'eth_getLogs',
             {'address': emitter, 'fromBlock': hex(block), 'toBlock': hex(block), 'topics': [topic0] * 5}),
            ('1025 addresses', 'error', 'eth_getLogs',
             {'address': [to_checksum_address(i.to_bytes(20, 'big')) for i in range(1, 1026)],
              'fromBlock': hex(block), 'toBlock': hex(block)}),
        ]
        for name, outcome, method, params in queries:
            with self.subTest(name):
                response = c.rpc(method, [params])
                print(f'AC-37 {name}:', json.dumps(response)[:300])
                self.assertIn(outcome, response)
        with self.subTest('topic[1] given, the log has topic0 only'):
            params = {'address': emitter, 'fromBlock': hex(block), 'toBlock': hex(block)}
            only_topic0 = c.rpc('eth_getLogs', [dict(params, topics=[topic0])])
            both = c.rpc('eth_getLogs', [dict(params, topics=[topic0, other])])
            print('AC-37 topic0 only:', len(only_topic0['result']), 'topic0 and topic1:', both)
            self.assertEqual(len(only_topic0['result']), 1, 'the log itself is there')
            self.assertEqual(both['result'], [])
