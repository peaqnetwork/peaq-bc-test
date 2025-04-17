from tests.evm_sc.base import SmartContractBehavior, log_func
from tools.peaq_eth_utils import get_eth_info
from web3 import Web3


TOKEN_NUM = 10**15


class ERC20SmartContractBehavior(SmartContractBehavior):
    def __init__(self, unittest, w3, kp_deployer):
        super().__init__(unittest, "ETH/erc20.openzeppelin", w3, kp_deployer)

    @log_func
    def deploy(self, deploy_args=None):
        super().deploy(deploy_args)

    def _mint_tokens(self, mint_addr, token_num):
        """Mint tokens to the address"""
        contract = self._get_contract()
        tx = contract.functions.mint(mint_addr, token_num).build_transaction(
            self.compose_build_transaction_args(self._kp_deployer)
        )
        self.send_and_check_tx(tx, self._kp_deployer)
        evm_balance = contract.functions.balanceOf(mint_addr).call()
        return {
            "mint_addr": evm_balance,
        }

    def compose_all_args(self):
        self._args = {
            "pre": {
                "mint_burn_transfer_tokens": [get_eth_info(), get_eth_info()],
                "approval_and_send_tokens": [
                    get_eth_info(),
                    get_eth_info(),
                    get_eth_info()
                ],
            },
            "after": {
                "mint_burn_transfer_tokens": [get_eth_info(), get_eth_info()],
                "approval_and_send_tokens": [
                    get_eth_info(),
                    get_eth_info(),
                    get_eth_info(),
                ],
            },
        }

    def get_fund_ss58_keys(self):
        """Get the ss58 keys for funding"""
        return (
            [self._kp_deployer["substrate"]]
            + [
                kp["substrate"]
                for action_type in ["pre", "after"]
                for kp in self._args[action_type]["mint_burn_transfer_tokens"][:2]
            ]
            + [
                kp["substrate"]
                for action_type in ["pre", "after"]
                for kp in self._args[action_type]["approval_and_send_tokens"][:3]
            ]
        )

    @log_func
    def mint_burn_transfer_tokens(self, kp_from, kp_to):
        contract = self._get_contract()

        tx = self._batch_contract.functions.batchAll(
            [
                Web3.to_checksum_address(self._address),
                Web3.to_checksum_address(self._address),
            ],
            [0, 0],
            [
                contract.encodeABI(
                    fn_name="mint", args=[kp_from["kp"].ss58_address, 3 * TOKEN_NUM]
                ),
                contract.encodeABI(
                    fn_name="burn", args=[kp_from["kp"].ss58_address, TOKEN_NUM]
                ),
            ],
            [0, 0],
        ).build_transaction(self.compose_build_transaction_args(self._kp_deployer))
        self.send_and_check_tx(tx, self._kp_deployer)

        tx = contract.functions.transfer(
            kp_to["kp"].ss58_address, TOKEN_NUM
        ).build_transaction(self.compose_build_transaction_args(kp_from))
        self.send_and_check_tx(tx, kp_from)

        return {
            "mint_burn_transfer_tokens": {
                "from": contract.functions.balanceOf(kp_from["kp"].ss58_address).call(),
                "to": contract.functions.balanceOf(kp_to["kp"].ss58_address).call(),
            }
        }

    @log_func
    def approval_and_send_tokens(self, kp_from, kp_approval, kp_new):
        self._mint_tokens(kp_from["kp"].ss58_address, 3 * TOKEN_NUM)
        contract = self._get_contract()

        tx = contract.functions.approve(
            kp_approval["kp"].ss58_address, TOKEN_NUM
        ).build_transaction(self.compose_build_transaction_args(kp_from))
        self.send_and_check_tx(tx, kp_from)

        tx = contract.functions.transferFrom(
            kp_from["kp"].ss58_address, kp_new["kp"].ss58_address, TOKEN_NUM
        ).build_transaction(self.compose_build_transaction_args(kp_approval))
        self.send_and_check_tx(tx, kp_approval)

        return {
            "approval_amount": contract.functions.allowance(
                kp_from["kp"].ss58_address, kp_approval["kp"].ss58_address
            ).call(),
            "new_balance": contract.functions.balanceOf(
                kp_new["kp"].ss58_address
            ).call(),
        }

    def migration_same_behavior(self, args):
        return {
            "mint_burn_transfer_tokens": self.mint_burn_transfer_tokens(
                *args["mint_burn_transfer_tokens"]
            ),
            "approval_and_send_tokens": self.approval_and_send_tokens(
                *args["approval_and_send_tokens"]
            ),
        }
