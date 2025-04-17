from tests.evm_sc.base import SmartContractBehavior, log_func
from tests.evm_utils import sign_and_submit_evm_transaction
from tools.peaq_eth_utils import TX_SUCCESS_STATUS
from tools.peaq_eth_utils import get_eth_info


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
            {
                "from": self._kp_deployer["kp"].ss58_address,
                "nonce": self._w3.eth.get_transaction_count(
                    self._kp_deployer["kp"].ss58_address
                ),
                "chainId": self._eth_chain_id,
            }
        )
        receipt = sign_and_submit_evm_transaction(tx, self._w3, self._kp_deployer["kp"])
        self._unittest.assertEqual(
            receipt["status"], TX_SUCCESS_STATUS, "The transaction was not successful"
        )
        evm_balance = contract.functions.balanceOf(mint_addr).call()
        return {
            "mint_addr": evm_balance,
        }

    def compose_all_args(self):
        self._args = {
            "pre": {
                "mint_and_transfer_tokens": [get_eth_info(), get_eth_info(), 10**15],
                "approval_and_send_tokens": [
                    get_eth_info(),
                    get_eth_info(),
                    get_eth_info(),
                    10**15,
                ],
            },
            "after": {
                "mint_and_transfer_tokens": [get_eth_info(), get_eth_info(), 10**15],
                "approval_and_send_tokens": [
                    get_eth_info(),
                    get_eth_info(),
                    get_eth_info(),
                    10**15,
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
                for kp in self._args[action_type]["mint_and_transfer_tokens"][:2]
            ]
            + [
                kp["substrate"]
                for action_type in ["pre", "after"]
                for kp in self._args[action_type]["approval_and_send_tokens"][:3]
            ]
        )

    @log_func
    def mint_and_transfer_tokens(self, kp_from, kp_to, token_num):
        self._mint_tokens(kp_from["kp"].ss58_address, 3 * token_num)
        contract = self._get_contract()
        # TODO Let me move to the batch func...
        tx = contract.functions.transfer(
            kp_to["kp"].ss58_address, token_num
        ).build_transaction(
            {
                "from": kp_from["kp"].ss58_address,
                "nonce": self._w3.eth.get_transaction_count(
                    kp_from["kp"].ss58_address
                ),
                "chainId": self._eth_chain_id,
            }
        )
        tx_receipt = sign_and_submit_evm_transaction(
            tx, self._w3, kp_from["kp"]
        )
        self._unittest.assertEqual(
            tx_receipt["status"],
            TX_SUCCESS_STATUS,
            "The transaction was not successful",
        )
        return {
            "mint_and_transfer_tokens": {
                "from": contract.functions.balanceOf(kp_from["kp"].ss58_address).call(),
                "to": contract.functions.balanceOf(kp_to["kp"].ss58_address).call(),
            }
        }

    @log_func
    def approval_and_send_tokens(self, kp_from, kp_approval, kp_new, token_num):
        self._mint_tokens(kp_from["kp"].ss58_address, 3 * token_num)
        contract = self._get_contract()
        # TODO Let me move to the batch func...
        tx = contract.functions.approve(
            kp_approval["kp"].ss58_address, token_num
        ).build_transaction(
            {
                "from": kp_from["kp"].ss58_address,
                "nonce": self._w3.eth.get_transaction_count(kp_from["kp"].ss58_address),
                "chainId": self._eth_chain_id,
            }
        )
        tx_receipt = sign_and_submit_evm_transaction(tx, self._w3, kp_from["kp"])
        self._unittest.assertEqual(
            tx_receipt["status"],
            TX_SUCCESS_STATUS,
            "The transaction was not successful",
        )
        tx = contract.functions.transferFrom(
            kp_from["kp"].ss58_address, kp_new["kp"].ss58_address, token_num
        ).build_transaction(
            {
                "from": kp_approval["kp"].ss58_address,
                "nonce": self._w3.eth.get_transaction_count(
                    kp_approval["kp"].ss58_address
                ),
                "chainId": self._eth_chain_id,
            }
        )
        tx_receipt = sign_and_submit_evm_transaction(tx, self._w3, kp_approval["kp"])
        self._unittest.assertEqual(
            tx_receipt["status"],
            TX_SUCCESS_STATUS,
            "The transaction was not successful",
        )
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
            "mint_and_transfer_tokens": self.mint_and_transfer_tokens(
                *args["mint_and_transfer_tokens"]
            ),
            "approval_and_send_tokens": self.approval_and_send_tokens(
                *args["approval_and_send_tokens"]
            ),
        }
