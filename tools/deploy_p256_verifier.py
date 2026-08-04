"""Deploy Daimo's audited P256Verifier to its canonical cross-chain address.

The contract (github.com/daimo-eth/p256-verifier, Veridise-audited) lives at the
same CREATE2 address on Ethereum, OP, Base and Arbitrum:

    0xc2b78104907F722DABAc4C69f826a522B2754De4

This script reproduces that deployment on a peaq network: it sends the exact
init code Daimo used (extracted from their Base forge-broadcast record) to the
Arachnid deterministic-deployment proxy with salt 0, which yields the same
address on any chain where that factory exists.

Default mode is a read-only dry run. Pass --execute plus a funded key (via the
environment variable named by --key-env, never argv) to actually deploy.
Idempotent: if the verifier is already deployed it verifies and exits 0.
"""
import argparse
import os
import sys

from eth_account import Account
from eth_utils import keccak, to_checksum_address
from web3 import Web3

CREATE2_FACTORY = "0x4e59b44847b379578588920cA78FbF26c0B4956C"
CANONICAL_ADDRESS = "0xc2b78104907F722DABAc4C69f826a522B2754De4"
SALT = b"\x00" * 32
# keccak of the 3,565-byte init code; pins p256_verifier_initcode.hex against tampering
INITCODE_KECCAK = bytes.fromhex(
    "3257821cc41f91063996667ce8ccb18b2ef28210b0e35376a36d6d47f3aea33a")

# Official RIP-7212 test vector (msg_hash || r || s || pub_x || pub_y); output must be 32-byte 1
P256_VALID_VECTOR = bytes.fromhex(
    'b5a77e7a90aa14e0bf5f337f06f597148676424fae26e175c6e5621c34351955'
    '289f319789da424845c9eac935245fcddd805950e2f02506d09be7e411199556'
    'd262144475b1fa46ad85250728c600c53dfd10f8b3f4adf140e27241aec3c2da'
    '3a81046703fccf468b48b145f939efdbb96c3786db712b3113bb2488ef286cdc'
    'ef8afe82d200a5bb36b5462166e8ce77f2d831a52ef2135b2af188110beaefb1')
VALID_OUTPUT = (b"\x00" * 31) + b"\x01"


def load_init_code():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "p256_verifier_initcode.hex")
    with open(path) as f:
        init = bytes.fromhex(f.read().strip())
    if keccak(init) != INITCODE_KECCAK:
        raise RuntimeError("init code file does not match pinned keccak hash; refusing to use it")
    return init


def compute_create2_address():
    factory = bytes.fromhex(CREATE2_FACTORY[2:])
    return to_checksum_address(
        keccak(b"\xff" + factory + SALT + keccak(load_init_code()))[12:])


def verify_onchain(w3):
    """Call the deployed verifier with the official RIP-7212 vector."""
    out = bytes(w3.eth.call({"to": CANONICAL_ADDRESS, "data": "0x" + P256_VALID_VECTOR.hex()}))
    if out != VALID_OUTPUT:
        print(f"FAIL: valid vector returned {out.hex() or '(empty)'}")
        return False
    bad = bytearray(P256_VALID_VECTOR)
    bad[0] ^= 0x01
    out = bytes(w3.eth.call({"to": CANONICAL_ADDRESS, "data": "0x" + bad.hex()}))
    if out != b"":
        print(f"FAIL: invalid vector returned {out.hex()} (expected empty)")
        return False
    print("verified: RIP-7212 valid vector -> 0x..01, invalid vector -> empty")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rpc", required=True, help="EVM RPC endpoint of the target peaq network")
    ap.add_argument("--execute", action="store_true",
                    help="actually send the deployment tx (default: read-only dry run)")
    ap.add_argument("--key-env", default="DEPLOYER_KEY",
                    help="env var holding the deployer private key (default: DEPLOYER_KEY)")
    args = ap.parse_args()

    w3 = Web3(Web3.HTTPProvider(args.rpc, request_kwargs={"timeout": 30}))
    print(f"chain id {w3.eth.chain_id}, block #{w3.eth.block_number}")

    addr = compute_create2_address()
    assert addr == CANONICAL_ADDRESS, f"computed {addr} != canonical (init code mismatch)"
    print(f"CREATE2 address check: {addr} == canonical OK")

    if not w3.eth.get_code(CREATE2_FACTORY):
        sys.exit(f"ABORT: CREATE2 factory {CREATE2_FACTORY} not deployed on this chain; "
                 "the canonical address cannot be reproduced here")
    print(f"factory present: {CREATE2_FACTORY}")

    if w3.eth.get_code(CANONICAL_ADDRESS):
        print("verifier ALREADY deployed at the canonical address")
        sys.exit(0 if verify_onchain(w3) else 1)

    data = SALT + load_init_code()
    if not args.execute:
        print("DRY RUN: verifier not deployed yet; would send "
              f"{len(data)} bytes to the factory. Re-run with --execute to deploy.")
        return

    key = os.environ.get(args.key_env)
    if not key:
        sys.exit(f"ABORT: --execute needs a private key in ${args.key_env}")
    acct = Account.from_key(key)
    print(f"deployer: {acct.address}, balance {w3.eth.get_balance(acct.address) / 10**18:.4f}")

    tx = {
        "from": acct.address,
        "to": CREATE2_FACTORY,
        "data": "0x" + data.hex(),
        "nonce": w3.eth.get_transaction_count(acct.address),
        "chainId": w3.eth.chain_id,
        "gasPrice": w3.eth.gas_price,
    }
    tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.2)
    print(f"sending deploy tx (gas limit {tx['gas']})...")
    txh = w3.eth.send_raw_transaction(acct.sign_transaction(tx).rawTransaction)
    rcpt = w3.eth.wait_for_transaction_receipt(txh, timeout=180)
    if rcpt.status != 1:
        sys.exit(f"ABORT: deploy tx {txh.hex()} reverted")
    if not w3.eth.get_code(CANONICAL_ADDRESS):
        sys.exit("ABORT: tx succeeded but no code at the canonical address")
    print(f"deployed in block {rcpt.blockNumber}, tx {txh.hex()}")
    sys.exit(0 if verify_onchain(w3) else 1)


if __name__ == "__main__":
    main()
