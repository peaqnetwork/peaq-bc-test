from tests.evm_sc.base import SmartContractBehavior, log_func
from tools.peaq_eth_utils import get_eth_info
from web3 import Web3


TOKEN_NUM = 10**15


class ERC1155SmartContractBehavior(SmartContractBehavior):
    def __init__(self, unittest, w3, kp_deployer):
        super().__init__(unittest, "ETH/erc1155.openzeppelin", w3, kp_deployer)

    @log_func
    def deploy(self, deploy_args=None):
        super().deploy(deploy_args)

    def compose_all_args(self):
        self._args = {
            "pre": {
                "mint_burn_exists": [get_eth_info()],
                "mint_burn_approval_for_all": [
                    get_eth_info(),
                    get_eth_info(),
                    get_eth_info(),
                ],
                "update_exists": [get_eth_info()],
            },
            "after": {
                "mint_burn_exists": [get_eth_info()],
                "mint_burn_approval_for_all": [
                    get_eth_info(),
                    get_eth_info(),
                    get_eth_info(),
                ],
                "update_exists": [get_eth_info()],
            },
        }

    def get_fund_ss58_keys(self):
        """Get the ss58 keys for funding"""
        return (
            [self._kp_deployer["substrate"]]
            + [
                kp["substrate"]
                for action_type in ["pre", "after"]
                for kp in self._args[action_type]["mint_burn_exists"][:1]
            ]
            + [
                kp["substrate"]
                for action_type in ["pre", "after"]
                for kp in self._args[action_type]["mint_burn_approval_for_all"][:3]
            ]
            + [
                kp["substrate"]
                for action_type in ["pre", "after"]
                for kp in self._args[action_type]["update_exists"][:1]
            ]
        )

    def _find_next_not_exist_id(self):
        contract = self._get_contract()
        token_id = 0
        while contract.functions.exists(token_id).call():
            token_id += 1
        return token_id

    @log_func
    def mint_burn_approval_for_all(self, kp_from, kp_operator, kp_to):
        contract = self._get_contract()
        new_token_id = self._find_next_not_exist_id()

        tx = self._batch_contract.functions.batchAll(
            [
                Web3.to_checksum_address(self._address),
                Web3.to_checksum_address(self._address),
            ],
            [0, 0],
            [
                contract.encodeABI(
                    fn_name="mintBatch",
                    args=[
                        kp_from["kp"].ss58_address,
                        [new_token_id, new_token_id + 1],
                        [TOKEN_NUM * 3, TOKEN_NUM * 4],
                        b"",
                    ],
                ),
                contract.encodeABI(
                    fn_name="burnBatch",
                    args=[
                        kp_from["kp"].ss58_address,
                        [new_token_id, new_token_id + 1],
                        [TOKEN_NUM, TOKEN_NUM],
                    ],
                ),
            ],
            [0, 0],
        ).build_transaction(self.compose_build_transaction_args(self._kp_deployer))
        self.send_and_check_tx(tx, self._kp_deployer)

        tx = contract.functions.setApprovalForAll(
            kp_operator["kp"].ss58_address, True
        ).build_transaction(self.compose_build_transaction_args(kp_from))
        self.send_and_check_tx(tx, kp_from)

        self._unittest.assertEqual(
            contract.functions.isApprovedForAll(
                kp_from["kp"].ss58_address, kp_operator["kp"].ss58_address
            ).call(),
            True,
            "The operator is not approved for all",
        )

        tx = self._batch_contract.functions.batchAll(
            [
                Web3.to_checksum_address(self._address),
                Web3.to_checksum_address(self._address),
            ],
            [0, 0],
            [
                contract.encodeABI(
                    fn_name="safeTransferFrom",
                    args=[
                        kp_from["kp"].ss58_address,
                        kp_to["kp"].ss58_address,
                        new_token_id,
                        TOKEN_NUM,
                        b"",
                    ],
                ),
                contract.encodeABI(
                    fn_name="safeTransferFrom",
                    args=[
                        kp_from["kp"].ss58_address,
                        kp_to["kp"].ss58_address,
                        new_token_id + 1,
                        TOKEN_NUM,
                        b"",
                    ],
                ),
            ],
            [0, 0],
        ).build_transaction(self.compose_build_transaction_args(kp_operator))
        self.send_and_check_tx(tx, kp_operator)

        self._unittest.assertEqual(
            contract.functions.uri(1000).call(),
            "https://game.example/api/item/{id}.json",
        )

        return {
            "mint_burn_approval_for_all": {
                "sender_token": contract.functions.balanceOfBatch(
                    [kp_from["kp"].ss58_address, kp_from["kp"].ss58_address],
                    [new_token_id, new_token_id + 1],
                ).call(),
                "operator_token": contract.functions.balanceOfBatch(
                    [kp_operator["kp"].ss58_address, kp_operator["kp"].ss58_address],
                    [new_token_id, new_token_id + 1],
                ).call(),
                "receiver_token": contract.functions.balanceOfBatch(
                    [kp_to["kp"].ss58_address, kp_to["kp"].ss58_address],
                    [new_token_id, new_token_id + 1],
                ).call(),
            }
        }

    @log_func
    def mint_burn_exists(self, kp_to):
        contract = self._get_contract()

        tx = self._batch_contract.functions.batchAll(
            [
                Web3.to_checksum_address(self._address),
                Web3.to_checksum_address(self._address),
            ],
            [0, 0],
            [
                contract.encodeABI(
                    fn_name="mintBatch",
                    args=[
                        kp_to["kp"].ss58_address,
                        [0, 1],
                        [TOKEN_NUM * 3, TOKEN_NUM * 4],
                        b"",
                    ],
                ),
                contract.encodeABI(
                    fn_name="burnBatch",
                    args=[
                        kp_to["kp"].ss58_address,
                        [0, 1],
                        [TOKEN_NUM, TOKEN_NUM],
                    ],
                ),
            ],
            [0, 0],
        ).build_transaction(self.compose_build_transaction_args(self._kp_deployer))
        self.send_and_check_tx(tx, self._kp_deployer)

        return {
            "mint_burn_exists": {
                "to_token": [
                    contract.functions.balanceOf(kp_to["kp"].ss58_address, 0).call(),
                    contract.functions.balanceOf(kp_to["kp"].ss58_address, 1).call(),
                ],
            }
        }

    @log_func
    def update_exists(self, kp_to):
        contract = self._get_contract()

        tx = contract.functions.updateBatch(
            self._kp_deployer["kp"].ss58_address,
            kp_to["kp"].ss58_address,
            [0, 1],
            [TOKEN_NUM * 3, TOKEN_NUM * 4],
        ).build_transaction(self.compose_build_transaction_args(self._kp_deployer))
        self.send_and_check_tx(tx, self._kp_deployer)

        return {
            "update_exists": {
                "to_token": [
                    contract.functions.balanceOf(kp_to["kp"].ss58_address, 0).call(),
                    contract.functions.balanceOf(kp_to["kp"].ss58_address, 1).call(),
                ],
            }
        }

    def migration_same_behavior(self, args):
        return {
            "mint_burn_exists": self.mint_burn_exists(*args["mint_burn_exists"]),
            "mint_burn_approval_for_all": self.mint_burn_approval_for_all(
                *args["mint_burn_approval_for_all"]
            ),
            "update_exists": self.update_exists(*args["update_exists"]),
        }
