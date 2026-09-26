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
# keccak of the DEPLOYED verifier runtime code, cross-checked on Base and OP mainnet:
# an on-chain contract only counts as "the verifier" if its code hashes to this
VERIFIER_RUNTIME_KECCAK = bytes.fromhex(
    "3cd725b6ba67b40b7979190c41a015e82cf21e098eb61832ba623f8538bab7fc")
# keccak of the 69-byte Arachnid proxy runtime; presence alone is not integrity
FACTORY_RUNTIME_KECCAK = bytes.fromhex(
    "2fa86add0aed31f33a762c9d88e807c475bd51d0f52bd0955754b2608f7e4989")

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


def verify_deployed(w3):
    """Confirm the code at the canonical address IS the audited verifier and works."""
    code = bytes(w3.eth.get_code(CANONICAL_ADDRESS))
    if keccak(code) != VERIFIER_RUNTIME_KECCAK:
        print(f"FAIL: runtime code at {CANONICAL_ADDRESS} does not match the "
              "pinned Daimo verifier hash (unexpected contract at this address)")
        return False
    out = bytes(w3.eth.call({"to": CANONICAL_ADDRESS, "data": "0x" + P256_VALID_VECTOR.hex()}))
    if out != VALID_OUTPUT:
        print(f"FAIL: valid vector returned {out.hex() or '(empty)'}")
        return False
    bad = bytearray(P256_VALID_VECTOR)
    bad[0] ^= 0x01
    out = bytes(w3.eth.call({"to": CANONICAL_ADDRESS, "data": "0x" + bad.hex()}))
    # The Daimo CONTRACT returns a 32-byte 0 for invalid input (verified against the
    # original on Base). Note this differs from the RIP-7212 PRECOMPILE, which returns
    # empty output; callers using `out.length == 32 && out[31] == 1` are unaffected.
    if out != b"\x00" * 32:
        print(f"FAIL: invalid vector returned {out.hex() or '(empty)'} (expected 32-byte 0)")
        return False
    print("verified: runtime hash pinned OK; valid vector -> 32-byte 1, invalid -> 32-byte 0")
    return True


def exit_via_recheck(w3, why):
    """Idempotency net: if a competing deploy landed first, that is success."""
    if w3.eth.get_code(CANONICAL_ADDRESS):
        print(f"{why}; verifier now present (deployed concurrently?) - verifying")
        sys.exit(0 if verify_deployed(w3) else 1)
    sys.exit(f"ABORT: {why} and verifier still absent")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rpc", required=True, help="EVM RPC endpoint of the target peaq network")
    ap.add_argument("--execute", action="store_true",
                    help="actually send the deployment tx (default: read-only dry run)")
    ap.add_argument("--key-env", default="DEPLOYER_KEY",
                    help="env var holding the deployer private key (default: DEPLOYER_KEY)")
    ap.add_argument("--expect-chain-id", type=int, default=None,
                    help="abort unless the RPC reports this chain id (guards against wrong --rpc)")
    ap.add_argument("--max-spend", type=float, default=5.0,
                    help="abort if gas_limit*gas_price exceeds this many native tokens (default 5)")
    args = ap.parse_args()

    w3 = Web3(Web3.HTTPProvider(args.rpc, request_kwargs={"timeout": 30}))
    chain_id = w3.eth.chain_id
    print(f"chain id {chain_id}, block #{w3.eth.block_number}")
    if args.expect_chain_id is not None and chain_id != args.expect_chain_id:
        sys.exit(f"ABORT: chain id {chain_id} != expected {args.expect_chain_id}")

    addr = compute_create2_address()
    if addr != CANONICAL_ADDRESS:
        sys.exit(f"ABORT: computed {addr} != canonical address (init code mismatch)")
    print(f"CREATE2 address check: {addr} == canonical OK")

    factory_code = bytes(w3.eth.get_code(CREATE2_FACTORY))
    if not factory_code:
        sys.exit(f"ABORT: CREATE2 factory {CREATE2_FACTORY} not deployed on this chain; "
                 "the canonical address cannot be reproduced here")
    if keccak(factory_code) != FACTORY_RUNTIME_KECCAK:
        sys.exit("ABORT: contract at the factory address is NOT the Arachnid proxy "
                 "(runtime hash mismatch); refusing to send funds to it")
    print(f"factory present and hash-verified: {CREATE2_FACTORY}")

    if w3.eth.get_code(CANONICAL_ADDRESS):
        print("verifier ALREADY deployed at the canonical address")
        sys.exit(0 if verify_deployed(w3) else 1)

    data = SALT + load_init_code()
    if not args.execute:
        print("DRY RUN: verifier not deployed yet; would send "
              f"{len(data)} bytes to the factory. Re-run with --execute to deploy.")
        return

    execute_deploy(w3, args, chain_id, data)


def execute_deploy(w3, args, chain_id, data):
    key = os.environ.get(args.key_env, "").strip()
    if not key:
        sys.exit(f"ABORT: --execute needs a private key in ${args.key_env}")
    acct = Account.from_key(key)
    print(f"deployer: {acct.address}, balance {w3.eth.get_balance(acct.address) / 10**18:.4f}")

    # Deliberately a legacy type-0 tx: peaq accepts them and every existing tool in
    # this repo uses gasPrice; do not mix in EIP-1559 fields.
    tx = {
        "from": acct.address,
        "to": CREATE2_FACTORY,
        "data": "0x" + data.hex(),
        "nonce": w3.eth.get_transaction_count(acct.address, "pending"),
        "chainId": chain_id,
        "gasPrice": w3.eth.gas_price,
    }
    try:
        tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.2)
    except Exception as e:
        exit_via_recheck(w3, f"gas estimation failed ({e})")
    max_spend_wei = tx["gas"] * tx["gasPrice"]
    print(f"max spend: {max_spend_wei / 10**18:.6f} native tokens "
          f"(gas {tx['gas']} x price {tx['gasPrice']})")
    if max_spend_wei > args.max_spend * 10**18:
        sys.exit(f"ABORT: max spend exceeds --max-spend {args.max_spend}; "
                 "raise the cap explicitly if this is intended")

    signed = acct.sign_transaction(tx)
    raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
    txh = w3.eth.send_raw_transaction(raw)
    print(f"sent {txh.hex()}, waiting...")
    rcpt = w3.eth.wait_for_transaction_receipt(txh, timeout=180)
    if rcpt.status != 1:
        exit_via_recheck(w3, f"deploy tx {txh.hex()} reverted")
    if not w3.eth.get_code(CANONICAL_ADDRESS):
        sys.exit("ABORT: tx succeeded but no code at the canonical address")
    print(f"deployed in block {rcpt.blockNumber}, tx {txh.hex()}")
    sys.exit(0 if verify_deployed(w3) else 1)


if __name__ == "__main__":
    main()
