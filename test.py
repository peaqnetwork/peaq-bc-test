from tools.pallet_assets_test import pallet_assets_test
from tools.two_address_substrate_with_extrinsic import pallet_multisig_test
from tools.two_address_substrate_with_extrinsic import pallet_transaction_test
from tools.two_address_substrate_with_extrinsic import pallet_did_test
from tools.two_address_evm_contract_with_extrinsic import evm_extrinsic_test
from tools.two_address_evm_contract_with_rpc import evm_rpc_test


if __name__ == '__main__':
    pallet_multisig_test()
    pallet_transaction_test()
    pallet_did_test()
    pallet_assets_test()
    evm_rpc_test()
    evm_extrinsic_test()
