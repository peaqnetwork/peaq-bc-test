from tests.evm_sc.base import SmartMultipleContractBehavior, log_func
from tools.peaq_eth_utils import deploy_contract, deploy_contract_with_args
import pytest


class ReentrySCBehavior(SmartMultipleContractBehavior):
    def __init__(self, unittest, w3, kp_deployer):
        super().__init__(
            unittest,
            {
                "simple": "ETH/reentry/simple",
                "attacker": "ETH/reentry/attacker",
            },
            w3,
            kp_deployer,
        )

    @log_func
    def deploy(self, deploy_args=None):
        simple_address = deploy_contract(
            self._w3,
            self._kp_deployer["kp"],
            self._eth_chain_id,
            self._abis["simple"],
            self._load_bytecode_by_key("simple"),
        )

        attacker_address = deploy_contract_with_args(
            self._w3,
            self._kp_deployer["kp"],
            self._eth_chain_id,
            self._abis["attacker"],
            self._load_bytecode_by_key("attacker"),
            [simple_address],
        )

        self._addresses = {
            "simple": simple_address,
            "attacker": attacker_address,
        }
        self._contracts = {
            "simple": self._get_contract_by_key("simple"),
            "attacker": self._get_contract_by_key("attacker"),
        }

        build_args = self.compose_build_transaction_args(self._kp_deployer)
        build_args["value"] = self._w3.to_wei(1, "ether")
        tx = self._contracts["simple"].functions.deposit().build_transaction(build_args)
        self.send_and_check_tx(tx, self._kp_deployer)

    def compose_all_args(self):
        self._args = {
            "pre": {
                "reentry_safe": [],
            },
            "after": {
                "reentry_safe": [],
            },
        }

    def get_fund_ss58_keys(self):
        """Get the ss58 keys for funding"""
        return [self._kp_deployer["substrate"]] + [
            kp["substrate"]
            for action_type in ["pre", "after"]
            for kp in self._args[action_type]["reentry_safe"][:1]
        ]

    @log_func
    def reentry_safe(self):
        with pytest.raises(Exception):
            self._contracts["attacker"].functions.attack().build_transaction(
                self.compose_build_transaction_args(self._kp_deployer)
            )
        remaining = self._contracts["simple"].functions.balance().call()
        self._unittest.assertEqual(
            remaining,
            self._w3.to_wei(1, "ether"),
        )
        return None

    def migration_same_behavior(self, args):
        return {
            "reentry_safe": self.reentry_safe(*args["reentry_safe"]),
        }
