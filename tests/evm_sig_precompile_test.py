import unittest
import pytest

from web3 import Web3
from substrateinterface import Keypair, KeypairType
from tools.constants import ETH_URL


# P256VERIFY (RIP-7212, secp256r1) -- standard address 0x100.
P256VERIFY_ADDRESS = '0x0000000000000000000000000000000000000100'
# Ed25519 verify -- peaq-specific address 0x403 (Ed25519 has no ecosystem address standard).
ED25519_ADDRESS = '0x0000000000000000000000000000000000000403'

# Both precompiles share ONE output convention (RIP-7212 style):
# valid   -> 32 bytes, big-endian 1
# invalid -> empty output (and the call itself succeeds; it never reverts)
VALID_OUTPUT = (b'\x00' * 31) + b'\x01'

# Official RIP-7212 test vectors (msg_hash(32) || r(32) || s(32) || pub_x(32) || pub_y(32)).
P256_VALID_1 = bytes.fromhex(
    'b5a77e7a90aa14e0bf5f337f06f597148676424fae26e175c6e5621c34351955'
    '289f319789da424845c9eac935245fcddd805950e2f02506d09be7e411199556'
    'd262144475b1fa46ad85250728c600c53dfd10f8b3f4adf140e27241aec3c2da'
    '3a81046703fccf468b48b145f939efdbb96c3786db712b3113bb2488ef286cdc'
    'ef8afe82d200a5bb36b5462166e8ce77f2d831a52ef2135b2af188110beaefb1')
P256_VALID_2 = bytes.fromhex(
    '4cee90eb86eaa050036147a12d49004b6b9c72bd725d39d4785011fe190f0b4d'
    'a73bd4903f0ce3b639bbbf6e8e80d16931ff4bcf5993d58468e8fb19086e8cac'
    '36dbcd03009df8c59286b162af3bd7fcc0450c9aa81be5d10d312af6c66b1d60'
    '4aebd3099c618202fcfe16ae7770b0c49ab5eadf74b754204a3bb6060e44eff3'
    '7618b065f9832de4ca6ca971a7a1adc826d0f7c00181a5fb2ddf79ae00b4e10e')
# P256_VALID_2 with its first byte flipped (4c -> 3c): wrong message hash -> invalid.
P256_INVALID = bytes.fromhex(
    '3cee90eb86eaa050036147a12d49004b6b9c72bd725d39d4785011fe190f0b4d'
    'a73bd4903f0ce3b639bbbf6e8e80d16931ff4bcf5993d58468e8fb19086e8cac'
    '36dbcd03009df8c59286b162af3bd7fcc0450c9aa81be5d10d312af6c66b1d60'
    '4aebd3099c618202fcfe16ae7770b0c49ab5eadf74b754204a3bb6060e44eff3'
    '7618b065f9832de4ca6ca971a7a1adc826d0f7c00181a5fb2ddf79ae00b4e10e')
P256_TOO_SHORT = bytes.fromhex('4cee90eb86eaa050036147a12d49004b6a')

# Guard against transcription mistakes in the vectors above.
assert len(P256_VALID_1) == 160
assert len(P256_VALID_2) == 160
assert len(P256_INVALID) == 160

# RFC 8032 "TEST 1" secret seed; standard, well-known ed25519 test key.
ED25519_TEST_SEED = '0x9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60'


@pytest.mark.eth
class TestSigVerifyPrecompiles(unittest.TestCase):
    def setUp(self):
        self.w3 = Web3(Web3.HTTPProvider(ETH_URL))

    def _call_precompile(self, address, data):
        # eth_call = read-only staticcall; these precompiles are pure verifiers.
        return bytes(self.w3.eth.call({
            'to': Web3.to_checksum_address(address),
            'data': '0x' + data.hex(),
        }))

    # --- P256VERIFY (0x100) ---

    def test_p256_valid_signatures(self):
        for i, vector in enumerate([P256_VALID_1, P256_VALID_2]):
            out = self._call_precompile(P256VERIFY_ADDRESS, vector)
            self.assertEqual(out, VALID_OUTPUT, f'valid P256 vector {i} did not verify')

    def test_p256_invalid_signature_returns_empty(self):
        out = self._call_precompile(P256VERIFY_ADDRESS, P256_INVALID)
        self.assertEqual(out, b'', 'invalid P256 signature must return empty output')

    def test_p256_wrong_length_returns_empty(self):
        out = self._call_precompile(P256VERIFY_ADDRESS, P256_TOO_SHORT)
        self.assertEqual(out, b'', 'short P256 input must return empty output')

    # --- Ed25519 (0x403) ---

    def _ed25519_signed_input(self, message):
        # input = message(32) || public_key(32) || signature(64)
        kp = Keypair.create_from_seed(ED25519_TEST_SEED, crypto_type=KeypairType.ED25519)
        signature = kp.sign(message)
        return message + kp.public_key + signature

    def test_ed25519_valid_signature(self):
        message = b'abcdefghijklmnopqrstuvwxyz123456'  # 32 bytes
        data = self._ed25519_signed_input(message)
        self.assertEqual(len(data), 128)
        out = self._call_precompile(ED25519_ADDRESS, data)
        self.assertEqual(out, VALID_OUTPUT, 'valid ed25519 signature did not verify')

    def test_ed25519_tampered_message_returns_empty(self):
        message = b'abcdefghijklmnopqrstuvwxyz123456'
        data = bytearray(self._ed25519_signed_input(message))
        data[0] ^= 0x01  # flip one bit of the message
        out = self._call_precompile(ED25519_ADDRESS, bytes(data))
        self.assertEqual(out, b'', 'tampered ed25519 message must return empty output')

    def test_ed25519_wrong_length_returns_empty(self):
        message = b'abcdefghijklmnopqrstuvwxyz123456'
        data = self._ed25519_signed_input(message)
        # exactly 128 bytes is required: both truncated and oversized input are invalid
        for bad in [data[:-1], data + b'\x00', b'']:
            out = self._call_precompile(ED25519_ADDRESS, bad)
            self.assertEqual(out, b'', f'ed25519 input of length {len(bad)} must return empty output')
