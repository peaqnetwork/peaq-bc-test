from tools.deploy_p256_verifier import (
    CANONICAL_ADDRESS,
    CREATE2_FACTORY,
    INITCODE_KECCAK,
    SALT,
    compute_create2_address,
    load_init_code,
)


def test_salt_is_zero():
    assert SALT == b"\x00" * 32


def test_initcode_integrity():
    # init code extracted from Daimo's Base (8453) forge broadcast record;
    # its keccak is pinned so silent tampering of the .hex file fails loudly
    from eth_utils import keccak
    init = load_init_code()
    assert len(init) == 3565
    assert keccak(init) == INITCODE_KECCAK


def test_create2_address_matches_canonical():
    # address = keccak(0xff ++ factory ++ salt ++ keccak(init))[12:]
    addr = compute_create2_address()
    assert addr == CANONICAL_ADDRESS
    assert CANONICAL_ADDRESS == "0xc2b78104907F722DABAc4C69f826a522B2754De4"


def test_factory_is_arachnid_proxy():
    assert CREATE2_FACTORY == "0x4e59b44847b379578588920cA78FbF26c0B4956C"
