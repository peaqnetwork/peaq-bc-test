"""
The checks the 2603 EVM tests (tests/evm_2603_test.py) make on raw JSON-RPC responses, kept free of network
imports so that tests/evm_2603_check_test.py can feed them hand-made responses. A response is the dict
web3's provider.make_request returns: {'jsonrpc', 'id', 'result'} or {'jsonrpc', 'id', 'error': {'code',
'message', 'data'?}}. The error strings are Frontier's (client/rpc/src/eth/format.rs, Geth::pool_error).
"""
from tools.eth_raw_tx import SECP256K1_N, recover_sender

# what eth_sendRawTransaction answers when the runtime's check_self_contained cannot recover a signer,
# which is what frame/ethereum's recover_signer returns for s > n/2
HIGH_S_ERROR = 'invalid sender'
GAS_CAP_ERROR = 'exceeds transaction gas limit cap'
EXHAUSTS_RESOURCES_ERROR = 'exceeds block gas limit'
NOT_CALLABLE_BY_CONTRACTS = 'Function not callable by smart contracts'


def error_message(response):
    return response.get('error', {}).get('message')


def check_high_s_version(high, sender):
    """AC-77, before sending: the outer signature has s > n/2 and still recovers to the sender."""
    assert high['s'] > SECP256K1_N // 2, f"s = {high['s']} is not above n/2"
    recovered = recover_sender(high)
    assert recovered == sender, f'the high-s signature recovers to {recovered}, not the sender {sender}'


def check_high_s_rejected(response):
    """AC-77: eth_sendRawTransaction refused the high-s transaction because its signature is invalid."""
    assert 'result' not in response, f"the high-s transaction was accepted as {response['result']}"
    assert error_message(response) == HIGH_S_ERROR, (
        f'the high-s transaction was refused for another reason: {response.get("error")}, '
        f'expected the message {HIGH_S_ERROR!r}')


def check_accepted(response):
    """AC-38 (unprotected legacy): eth_sendRawTransaction accepted the transaction."""
    assert 'result' in response, f'the transaction was refused: {response.get("error")}'


def check_not_refused_for_gas_cap(response):
    """
    AC-38 (gas = block gas limit - 1): not refused because of TransactionGasLimit. Accepted (it may stay
    pending) or refused with ExhaustsResources, when the PoV it reserves is over the block's, both pass.
    """
    if 'result' in response:
        return
    message = error_message(response)
    assert message != GAS_CAP_ERROR, f'refused by the transaction gas limit cap: {response["error"]}'
    assert message == EXHAUSTS_RESOURCES_ERROR, f'refused for an unexpected reason: {response["error"]}'


def check_not_callable_by_contracts(call_response, receipt):
    """
    AC-32: from an EOA with an EIP-7702 delegation, eth_call of the precompile reverted with Frontier's
    'Function not callable by smart contracts', and the same call sent as a transaction reverted on chain.
    """
    message = error_message(call_response)
    assert message is not None, f'eth_call did not revert: {call_response}'
    assert NOT_CALLABLE_BY_CONTRACTS in message, f'eth_call reverted for another reason: {message!r}'
    assert receipt['status'] == 0, f"the transaction did not revert: status {receipt['status']}"


def check_call_trace_logs(trace_response, receipt):
    """
    AC-34: debug_traceTransaction with callTracer and withLog returned one log, the same topics and data
    as the receipt's. An error response (for example Method not found on a node built without
    evm-tracing) fails the check instead of raising something else.
    """
    assert 'error' not in trace_response, f'debug_traceTransaction failed: {trace_response["error"]}'
    logs = trace_response['result'].get('logs')
    assert logs and len(logs) == 1, f'expected one log in the call trace, got {logs}'
    want = receipt['logs'][0]
    got = logs[0]
    assert [t.lower() for t in got['topics']] == [t.lower() for t in want['topics']], (
        f"trace topics {got['topics']} != receipt topics {want['topics']}")
    assert got['data'].lower() == want['data'].lower(), f"trace data {got['data']} != receipt data {want['data']}"
