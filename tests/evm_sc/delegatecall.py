from tests.evm_sc.base import SmartMultipleContractBehavior, log_func
from tools.peaq_eth_utils import deploy_contract, deploy_contract_with_args


class DelegateCallSCBehavior(SmartMultipleContractBehavior):
    def __init__(self, unittest, w3, kp_deployer):
        self._delegatecall_num = 100
        super().__init__(
            unittest,
            {
                "logic": "ETH/delegatorcall/logic",
                "proxy": "ETH/delegatorcall/proxy",
            },
            w3,
            kp_deployer,
        )

    @log_func
    def deploy(self, deploy_args=None):
        logic_address = deploy_contract(
            self._w3,
            self._kp_deployer["kp"],
            self._eth_chain_id,
            self._abis["logic"],
            self._load_bytecode_by_key("logic"),
        )

        proxy_address = deploy_contract_with_args(
            self._w3,
            self._kp_deployer["kp"],
            self._eth_chain_id,
            self._abis["logic"],
            self._load_bytecode_by_key("proxy"),
            [logic_address, 2],
        )

        self._addresses = {
            "logic": logic_address,
            "proxy": proxy_address,
        }
        self._contracts = {
            "logic": self._get_contract_by_key("logic"),
            "proxy": self._get_contract_by_key("proxy"),
        }

        tx = (
            self._contracts["logic"]
            .functions.setNum(2)
            .build_transaction(
                self.compose_build_transaction_args(self._kp_deployer)
            )
        )
        self.send_and_check_tx(tx, self._kp_deployer)

    def compose_all_args(self):
        self._args = {
            "pre": {
                "delegatecall": [],
            },
            "after": {
                "delegatecall": [],
            },
        }

    def get_fund_ss58_keys(self):
        """Get the ss58 keys for funding"""
        return [self._kp_deployer["substrate"]] + [
            kp["substrate"]
            for action_type in ["pre", "after"]
            for kp in self._args[action_type]["delegatecall"][:1]
        ]

    @log_func
    def delegatecall(self):
        self._delegatecall_num += 1

        num = self._contracts["logic"].functions.num().call()
        self._unittest.assertEqual(num, 2, "The number is not the same as expected: 2")

        tx = (
            self._contracts["proxy"]
            .functions.delegateSetNum(self._contracts["logic"].address, self._delegatecall_num)
            .build_transaction(
                self.compose_build_transaction_args(self._kp_deployer)
            )
        )
        self.send_and_check_tx(tx, self._kp_deployer)

        num = self._contracts["logic"].functions.num().call()
        self._unittest.assertEqual(num, 2, "The number is not the same as expected: 5")
        num = self._contracts["proxy"].functions.num().call()
        self._unittest.assertEqual(
            num, self._delegatecall_num,
            f"The number is not the same as expected: {self._delegatecall_num}")
        return None

    def migration_same_behavior(self, args):
        return {
            "delegatecall": self.delegatecall(*args["delegatecall"]),
        }
