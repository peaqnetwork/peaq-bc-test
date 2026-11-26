"""
Offline tests (no node) for tools/eth_raw_tx.py and the checks in tools/evm_2603_checks.py, including the red
checks of AC-32, AC-34, AC-38 and AC-77: each check must fail on the response it exists to catch. The
responses are copied from the PR-11 network runs where one could be produced there (the comment on each
says which); the one that cannot is built from Frontier's format string and says so. TRACE's topic is upper-cased
on purpose: check_call_trace_logs compares case-insensitively.
"""
import unittest

from eth_account import Account

from tools import eth_raw_tx as T
from tools.evm_2603_checks import (
    check_accepted, check_call_trace_logs, check_high_s_rejected, check_high_s_version,
    check_not_callable_by_contracts, check_not_refused_for_gas_cap)

KEY = bytes.fromhex('4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f362318')
SENDER = Account.from_key(KEY).address
TO = '0x' + '11' * 20


def error(message):
    return {'jsonrpc': '2.0', 'id': 1, 'error': {'code': -32603, 'message': message}}


# Responses below are the "error" objects (or results) printed by tests/evm_2603_test.py in the PR-11 network runs;
# the comment on each names the run (logs under evidence/pr11 of the upgrade report). Only the JSON-RPC id is changed.
ACCEPTED = {'jsonrpc': '2.0', 'id': 1, 'result': '0x' + 'ab' * 32}
# green3 2026-11-26, AC-77 against the collator (10044), legacy high-s; the RPC node (20044) answered the same
HIGH_S_REFUSED = error('invalid sender')
# green3 2026-11-26, AC-77 red check (2), unfunded sender
INSUFFICIENT_FUNDS = error('insufficient funds for gas * price + value')
# green3 2026-11-26, AC-38 gas = 72,000,000 - 1
EXHAUSTS_RESOURCES = error('exceeds block gas limit')
# peaq sets no TransactionGasLimit, so no network run can produce this one: it is Frontier's string,
# client/rpc/src/eth/format.rs (Geth::pool_error, TransactionGasLimitExceedsCap)
GAS_CAP_REFUSED = error('exceeds transaction gas limit cap')
# green3 2026-11-26, AC-38 red check, wrong chain id
WRONG_CHAIN_ID = error('invalid chain id')
# nooverride 2026-11-26: debug_traceTransaction on an RPC node with no tracing override wasm. The node has no
# evm-tracing feature of its own (only the runtime does), so it serves debug_* and the runtime refuses the trace
NO_TRACING_RUNTIME = error('DispatchError: Other("")')
# green3 2026-11-26, AC-32, eth_call of Batch.batchAll from the delegated EOA (data shortened to '0x')
NOT_CALLABLE = {'jsonrpc': '2.0', 'id': 1, 'error': {
    'code': -32603, 'message': 'VM Exception while processing transaction: revert Function not callable by smart contracts',
    'data': '0x'}}
# green3 2026-11-26, AC-32, the same eth_call from the plain EOA
PLAIN_CALL = {'jsonrpc': '2.0', 'id': 1, 'result': '0x'}
# green3 2026-11-26, AC-34 callTracer withLog (the emitter's LOG1); the receipt is built from the same topic and data
TOPIC = '0xda58d44b679018a1a273cdf2f63ba8b193f0a9e2f7cc08ba8ef0cd700cf79e58'
DATA = '0x' + '00' * 31 + '2a'
RECEIPT = {'status': 1, 'logs': [{'topics': [TOPIC], 'data': DATA}]}
TRACE = {'jsonrpc': '2.0', 'id': 1, 'result': {
    'from': '0xb52d94b0a0d130d60f704fb08d3b85fb46f236ff', 'gas': '0x13095', 'gasUsed': '0x560b', 'type': 'CALL',
    'to': '0x877ccf1d77052c63e638d9b5a0b594162e3777cf', 'input': '0x', 'output': '0x', 'value': '0x0',
    'logs': [{'address': '0x877ccf1d77052c63e638d9b5a0b594162e3777cf', 'topics': [TOPIC.upper().replace('0X', '0x')],
              'data': DATA}]}}


def legacy(chain_id):
    return {'type': 0, 'nonce': 3, 'gasPrice': 10 ** 9, 'gas': 21000, 'to': T.address_bytes(TO), 'value': 5,
            'data': b'', 'chainId': chain_id}


TYPED = {
    1: {'type': 1, 'chainId': 9990, 'nonce': 3, 'gasPrice': 10 ** 9, 'gas': 21000, 'to': T.address_bytes(TO),
        'value': 5, 'data': b'\x01\x02', 'accessList': []},
    2: {'type': 2, 'chainId': 9990, 'nonce': 3, 'maxPriorityFeePerGas': 1, 'maxFeePerGas': 10 ** 9, 'gas': 21000,
        'to': T.address_bytes(TO), 'value': 5, 'data': b'\x01\x02', 'accessList': []},
}


def eth_account_dict(tx):
    d = {k: v for k, v in tx.items() if k != 'type' and v is not None}
    d['to'] = TO
    if tx['type']:
        d['type'] = tx['type']
    return d


class TestEthRawTx(unittest.TestCase):
    def test_encoding_matches_eth_account(self):
        """For the types eth-account 0.9.0 can sign, the raw bytes are the same as its."""
        for name, tx in [('legacy, EIP-155', legacy(9990)), ('legacy, unprotected', legacy(None)),
                         ('EIP-2930', TYPED[1]), ('EIP-1559', TYPED[2])]:
            with self.subTest(name):
                want = Account.sign_transaction(eth_account_dict(tx), KEY).rawTransaction
                self.assertEqual(T.encode(T.sign(tx, KEY)), bytes(want))

    def test_high_s_version_recovers_to_the_sender(self):
        """AC-77 offline: s > n/2, and ecdsa_raw_recover (recover_sender) still gives the sender."""
        for name, tx in [('legacy', legacy(9990)), ('EIP-2930', TYPED[1]), ('EIP-1559', TYPED[2]),
                         ('EIP-7702', dict(TYPED[2], type=4, authorizationList=[T.sign_authorization(9990, TO, 0, KEY)]))]:
            with self.subTest(name):
                low = T.sign(tx, KEY)
                high = T.with_high_s(low)
                check_high_s_version(high, SENDER)
                self.assertEqual(T.recover_sender(low), SENDER)
                self.assertNotEqual(T.encode(high), T.encode(low))
                with self.assertRaises(AssertionError):
                    check_high_s_version(low, SENDER)  # the low-s original is not a high-s version

    def test_authorization_stays_low_s(self):
        auth = T.sign_authorization(9990, TO, 0, KEY)
        self.assertLessEqual(auth[5], T.SECP256K1_N // 2)


class TestEvm2603Checks(unittest.TestCase):
    def test_high_s_rejected(self):
        check_high_s_rejected(HIGH_S_REFUSED)
        for name, response in [('accepted', ACCEPTED), ('insufficient funds', INSUFFICIENT_FUNDS),
                               ('wrong chain id', WRONG_CHAIN_ID)]:
            with self.subTest(name), self.assertRaises(AssertionError):
                check_high_s_rejected(response)

    def test_not_refused_for_gas_cap(self):
        check_not_refused_for_gas_cap(ACCEPTED)
        check_not_refused_for_gas_cap(EXHAUSTS_RESOURCES)
        for name, response in [('gas cap', GAS_CAP_REFUSED), ('insufficient funds', INSUFFICIENT_FUNDS)]:
            with self.subTest(name), self.assertRaises(AssertionError):
                check_not_refused_for_gas_cap(response)

    def test_accepted(self):
        check_accepted(ACCEPTED)
        with self.assertRaises(AssertionError):
            check_accepted(WRONG_CHAIN_ID)

    def test_not_callable_by_contracts(self):
        check_not_callable_by_contracts(NOT_CALLABLE, {'status': 0})
        for name, call, receipt in [('plain EOA', PLAIN_CALL, {'status': 1}),
                                    ('eth_call reverted, tx did not', NOT_CALLABLE, {'status': 1}),
                                    ('reverted for another reason', error('VM Exception: revert out of gas'), {'status': 0})]:
            with self.subTest(name), self.assertRaises(AssertionError):
                check_not_callable_by_contracts(call, receipt)

    def test_call_trace_logs(self):
        check_call_trace_logs(TRACE, RECEIPT)
        other = {'result': {'logs': [{'topics': [TOPIC], 'data': '0x' + '00' * 32}]}}
        for name, trace in [('no tracing runtime', NO_TRACING_RUNTIME), ('no logs', {'result': {'type': 'CALL'}}),
                            ('other data', other)]:
            with self.subTest(name), self.assertRaises(AssertionError):
                check_call_trace_logs(trace, RECEIPT)
