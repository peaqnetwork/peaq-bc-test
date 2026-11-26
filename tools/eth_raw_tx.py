"""Hand-built and hand-signed Ethereum transactions of the four types peaq accepts, for the 2603 EVM tests.

eth-account 0.9.0, the version web3 6.11.2 works with, cannot sign an EIP-7702 (type 4) transaction, and no
eth-account version signs with a high s on purpose. So the transaction is RLP-encoded here with `rlp` and
signed with eth_keys' native backend, whose ecdsa_raw_sign always returns the low s:
- legacy:  rlp([nonce, gasPrice, gas, to, value, data, v, r, s]), v = 35 + 2 * chainId + y_parity (EIP-155),
           or 27 + y_parity when chainId is None (an unprotected transaction);
- type 1:  0x01 || rlp([chainId, nonce, gasPrice, gas, to, value, data, accessList, y_parity, r, s]);
- type 2:  0x02 || rlp([chainId, nonce, maxPriorityFeePerGas, maxFeePerGas, gas, to, value, data, accessList,
           y_parity, r, s]);
- type 4:  0x04 || rlp([chainId, nonce, maxPriorityFeePerGas, maxFeePerGas, gas, to, value, data, accessList,
           authorizationList, y_parity, r, s]), each authorization [chainId, address, nonce, y_parity, r, s]
           signed over keccak(0x05 || rlp([chainId, address, nonce])).
A transaction is a dict with the keys of its type (see FIELDS) plus 'type'; addresses and data are bytes.
"""
import copy

import rlp
from eth_keys.backends.native.ecdsa import ecdsa_raw_recover, ecdsa_raw_sign
from eth_utils import keccak, to_checksum_address

SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

FIELDS = {
    0: ['nonce', 'gasPrice', 'gas', 'to', 'value', 'data'],
    1: ['chainId', 'nonce', 'gasPrice', 'gas', 'to', 'value', 'data', 'accessList'],
    2: ['chainId', 'nonce', 'maxPriorityFeePerGas', 'maxFeePerGas', 'gas', 'to', 'value', 'data', 'accessList'],
    4: ['chainId', 'nonce', 'maxPriorityFeePerGas', 'maxFeePerGas', 'gas', 'to', 'value', 'data', 'accessList',
        'authorizationList'],
}


def address_bytes(address):
    return bytes.fromhex(address[2:]) if isinstance(address, str) else address


def _payload(tx):
    return [tx[k] for k in FIELDS[tx['type']]]


def signing_hash(tx):
    if tx['type'] == 0:
        extra = [] if tx.get('chainId') is None else [tx['chainId'], 0, 0]  # EIP-155
        return keccak(rlp.encode(_payload(tx) + extra))
    return keccak(bytes([tx['type']]) + rlp.encode(_payload(tx)))


def sign(tx, private_key):
    """The transaction with its low-s signature, as {'tx', 'y_parity', 'r', 's'}."""
    y_parity, r, s = ecdsa_raw_sign(signing_hash(tx), private_key)
    return {'tx': tx, 'y_parity': y_parity, 'r': r, 's': s}


def with_high_s(signed):
    """The same signature with s replaced by n - s and the recovery id flipped: still valid ECDSA, but high s."""
    high = copy.deepcopy(signed)
    high['s'] = SECP256K1_N - signed['s']
    high['y_parity'] = 1 - signed['y_parity']
    return high


def encode(signed):
    """The raw transaction bytes eth_sendRawTransaction takes."""
    tx = signed['tx']
    if tx['type'] == 0:
        chain_id = tx.get('chainId')
        v = signed['y_parity'] + (27 if chain_id is None else 35 + 2 * chain_id)
        return rlp.encode(_payload(tx) + [v, signed['r'], signed['s']])
    return bytes([tx['type']]) + rlp.encode(_payload(tx) + [signed['y_parity'], signed['r'], signed['s']])


def tx_hash(signed):
    return '0x' + keccak(encode(signed)).hex()


def recover_sender(signed):
    """
    The sender address, recovered with eth_keys.backends.native.ecdsa.ecdsa_raw_recover, which checks
    neither that s is low nor anything else EIP-2 adds, so it also recovers the high-s version.
    """
    public_key = ecdsa_raw_recover(signing_hash(signed['tx']), (signed['y_parity'], signed['r'], signed['s']))
    return to_checksum_address(keccak(public_key)[-20:])


def sign_authorization(chain_id, address, nonce, private_key):
    """An EIP-7702 authorization tuple [chainId, address, nonce, y_parity, r, s] for authorizationList."""
    address = address_bytes(address)
    y_parity, r, s = ecdsa_raw_sign(keccak(b'\x05' + rlp.encode([chain_id, address, nonce])), private_key)
    return [chain_id, address, nonce, y_parity, r, s]


def deploy_code(runtime_code):
    """Init code that returns `runtime_code` as the contract's code: CODECOPY it to memory 0, RETURN it."""
    return bytes.fromhex(f'61{len(runtime_code):04x}80600c6000396000f3') + runtime_code
