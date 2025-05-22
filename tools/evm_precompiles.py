import sys
sys.path.append('.')

from tools.utils import get_peaq_chain_id
from web3 import Web3


def token_name_metadata(chainId):
    match chainId:
        case 2000:
            return 'Agung token'
        case 9990:
            return 'Agung token'
        case 2241:
            return 'Krest token'
        case 3330:
            return 'peaq token'
        case _:
            raise ValueError('Unknown ChainId')


def permit_typehash():
    """Sibling to peaq-network-node/precompiles/balances-erc20/src/eip2612.rs: const PERMIT_TYPEHASH"""
    return Web3.keccak(text='Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)')


def permit_domain():
    """Sibling to peaq-network-node/precompiles/balances-erc20/src/eip2612.rs: const PERMIT_DOMAIN"""
    return Web3.keccak(text='EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)')


def compute_domain_separator():
    """Sibling to peaq-network-node/precompiles/balances-erc20/src/eip2612.rs: fn compute_domain_separator"""
    # Be aware of ID=2000 when launching local network for testing
    chain_id = get_peaq_chain_id()

    name = Web3.keccak(text=token_name_metadata(chain_id))
    version = Web3.keccak(text='1')
    chain_id = int(chain_id).to_bytes(32, byteorder='big')
    address = int(809).to_bytes(32, byteorder='big')

    domain_separator_inner = permit_domain() + name + version + chain_id + address

    return Web3.keccak(domain_separator_inner)


def generate_permit(owner, spender, value, nonce, deadline):
    """Sibling to peaq-network-node/precompiles/balances-erc20/src/eip2612.rs: fn generate_permit"""
    owner = bytes.fromhex(owner[2:])
    spender = bytes.fromhex(spender[2:])
    value = bytes(value)
    nonce = bytes(nonce)
    deadline = bytes(deadline)

    permit_content = permit_typehash() + owner + spender + value + nonce + deadline
    permit_content = Web3.keccak(permit_content)

    pre_digest = bytes(25) + bytes(1) + bytes(compute_domain_separator()) + bytes(permit_content)
    return Web3.keccak(pre_digest)


def generate_permit2(owner, spender, value, nonce, deadline):
    """Test test test"""
    d_owner = bytes.fromhex(owner[2:])
    d_spender = bytes.fromhex(spender[2:])
    d_value = bytes(value)
    d_nonce = bytes(nonce)
    d_deadline = bytes(deadline)

    return dict(
        owner=d_owner,
        spender=d_spender,
        value=d_value,
        nonce=d_nonce,
        deadline=d_deadline,
        gas=1000000,
        gasPrice=1000000,
    )

    
