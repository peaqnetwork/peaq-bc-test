from tests.evm_sc.base import SmartContractBehavior, log_func
import pytest


class ErrorHandlingSCBehavior(SmartContractBehavior):
    def __init__(self, unittest, w3, kp_deployer):
        super().__init__(unittest, "ETH/error.handling", w3, kp_deployer)

    @log_func
    def deploy(self, deploy_args=None):
        super().deploy(deploy_args)

    def compose_all_args(self):
        self._args = {
            "pre": {
                "error_handling": [],
            },
            "after": {
                "error_handling": [],
            },
        }

    def get_fund_ss58_keys(self):
        """Get the ss58 keys for funding"""
        return (
            [self._kp_deployer["substrate"]]
            + [
                kp["substrate"]
                for action_type in ["pre", "after"]
                for kp in self._args[action_type]["error_handling"][:1]
            ]
        )

    @log_func
    def error_handling(self):
        contract = self._get_contract()

        with pytest.raises(Exception):
            contract.functions.requirePositive(0).call(),

        self._unittest.assertEqual(
            contract.functions.requirePositive(1).call(),
            1,
        )

        tx = contract.functions.requirePositive(1).build_transaction(
            self.compose_build_transaction_args(self._kp_deployer)
        )
        self.send_and_check_tx(tx, self._kp_deployer)

        with pytest.raises(Exception):
            # While gas esitmation, it fail
            contract.functions.requirePositive(0).build_transaction(
                self.compose_build_transaction_args(self._kp_deployer)
            )

        with pytest.raises(Exception):
            contract.functions.forceRevert().build_transaction(
                self.compose_build_transaction_args(self._kp_deployer)
            )

        with pytest.raises(Exception):
            contract.functions.alwaysFailAssert().build_transaction(
                self.compose_build_transaction_args(self._kp_deployer)
            )

        return None

    def migration_same_behavior(self, args):
        return {
            "error_handling": self.error_handling(
                *args["error_handling"]
            ),
        }
