from tests.evm_sc.base import SmartContractBehavior
from tests.evm_utils import sign_and_submit_evm_transaction
from tools.peaq_eth_utils import TX_SUCCESS_STATUS
from tools.peaq_eth_utils import get_eth_info


class ERC20SmartContractBehavior(SmartContractBehavior):
    def __init__(self, w3, kp_deployer):
        super().__init__("ETH/ERC20", w3, kp_deployer)

    def _mint_tokens(self, mint_addr, token_num):
        """Mint tokens to the address"""
        contract = self._get_contract(self._w3, self._address, "ETH/ERC20/abi")
        tx = contract.functions.mint(mint_addr, token_num).build_transaction(
            {
                "from": self._kp_deployer['kp'].ss58_address,
                "nonce": self._w3.eth.get_transaction_count(
                    self._kp_deployer['kp'].ss58_address
                ),
                "chainId": self._eth_chain_id,
            }
        )
        receipt = sign_and_submit_evm_transaction(tx, self._w3, self._kp_deployer['kp'])
        self.assertEqual(
            receipt["status"], TX_SUCCESS_STATUS, "The transaction was not successful"
        )
        evm_balance = contract.functions.balanceOf(mint_addr).call()
        return {
            "mint_addr": evm_balance,
        }

    def compose_all_arg(self):
        self._args = {
            "pre": {
                "mint_and_transfer_tokens": [get_eth_info(), get_eth_info(), 10**15],
                "approval_and_send_tokens": [get_eth_info(), get_eth_info(), get_eth_info(), 10**15],
            },
            "after": {
                "mint_and_transfer_tokens": [get_eth_info(), get_eth_info(), 10**15],
                "approval_and_send_tokens": [get_eth_info(), get_eth_info(), get_eth_info(), 10**15],
            },
        }

    def get_fund_ss58_keys(self):
        """Get the ss58 keys for funding"""
        return (
            [self._kp_deployer["substrate"]]
            + [
                kp['substrate'] for action_type in ["pre", "after"]
                for kp in self._args[action_type]['mint_and_transfer_tokens'][:2]
            ]
            + [
                kp['substrate'] for action_type in ["pre", "after"]
                for kp in self._args[action_type]['approval_and_send_tokens'][:3]
            ]
        )

    def mint_and_transfer_tokens(self, kp_from, kp_to, token_num):
        self._mint_tokens(kp_from['kp'].ss58_address, 3 * token_num)
        contract = self._get_contract(self._w3, self._address, "ETH/ERC20/abi")
        tx = contract.functions.transfer(kp_to['kp'].ss58_address, token_num).build_transaction(
            {
                "from": self._kp_deployer['kp'].ss58_address,
                "nonce": self._w3.eth.get_transaction_count(self._kp_deployer['kp'].ss58_address),
                "chainId": self._eth_chain_id,
            }
        )
        tx.receipt = sign_and_submit_evm_transaction(tx, self._w3, self._kp_deployer['kp'])
        self.assertEqual(
            tx.receipt["status"],
            TX_SUCCESS_STATUS,
            "The transaction was not successful",
        )
        return {
            "transfer_tokens": {
                "from": contract.functions.balanceOf(kp_from['kp'].ss58_address).call(),
                "to": contract.functions.balanceOf(kp_to['kp'].ss58_address).call(),
            }
        }

    def approval_and_send_tokens(self, kp_from, kp_approval, kp_new, token_num):
        self._mint_tokens(kp_from['kp'].ss58_address, 3 * token_num)
        contract = self._get_contract(self._w3, self._address, "ETH/ERC20/abi")
        tx = contract.functions.approve(
            kp_approval['kp'].ss58_address, token_num
        ).build_transaction(
            {
                "from": kp_from['kp'].ss58_address,
                "nonce": self._w3.eth.get_transaction_count(kp_from['kp'].ss58_address),
                "chainId": self._eth_chain_id,
            }
        )
        tx.receipt = sign_and_submit_evm_transaction(tx, self._w3, kp_from['kp'])
        self.assertEqual(
            tx.receipt["status"],
            TX_SUCCESS_STATUS,
            "The transaction was not successful",
        )
        data = contract.functions.allowance(
            kp_from['kp'].ss58_address, kp_approval['kp'].ss58_address
        ).call()
        self.assertEqual(data, token_num, "The allowance is not correct")
        tx = contract.functions.transferFrom(
            kp_from['kp'].ss58_address, kp_new['kp'].ss58_address, token_num
        ).build_transaction(
            {
                "from": kp_approval['kp'].ss58_address,
                "nonce": self._w3.eth.get_transaction_count(kp_approval['kp'].ss58_address),
                "chainId": self._eth_chain_id,
            }
        )
        tx.receipt = sign_and_submit_evm_transaction(tx, self._w3, kp_approval['kp'])
        self.assertEqual(
            tx.receipt["status"],
            TX_SUCCESS_STATUS,
            "The transaction was not successful",
        )
        return {
            "approval_amount": contract.functions.allowance(
                kp_from['kp'].ss58_address, kp_approval['kp'].ss58_address
            ).call(),
            "new_balance": contract.functions.balanceOf(kp_new['kp'].ss58_address).call(),
        }

    def migration_same_behavior(self, args):
        return {
            "mint_and_transfer_tokens": self.transfer_tokens(
                **args["mint_and_transfer_tokens"]
            ),
            "approval_and_send_tokens": self.approval_and_send_tokens(
                **args["approval_and_send_tokens"]
            ),
        }
