from tools.evm_precompiles import *
from tools.peaq_eth_utils import get_eth_info

if __name__ == '__main__':
    typehash = bytes(permit_typehash())
    domain = bytes(permit_domain())
    domain_separator = bytes(compute_domain_separator())
    print(f'TYPEHASH: {typehash.hex()}')
    print(f'DOMAIN: {domain.hex()}')
    print(f'SEPARATOR: {domain_separator.hex()}')

    eth_info = get_eth_info()
    owner = eth_info['eth']
    spender = eth_info['eth']
    permit = generate_permit(owner, spender, 1000, 0, 100)
    print(permit)
