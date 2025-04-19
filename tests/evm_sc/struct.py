from tests.evm_sc.base import SmartContractBehavior, log_func


class StructSCBehavior(SmartContractBehavior):
    def __init__(self, unittest, w3, kp_deployer):
        super().__init__(unittest, "ETH/struct", w3, kp_deployer)

    @log_func
    def deploy(self, deploy_args=None):
        super().deploy(deploy_args)

    def compose_all_args(self):
        self._args = {
            "pre": {
                "struct_abi": [],
            },
            "after": {
                "struct_abi": [],
            },
        }

    def get_fund_ss58_keys(self):
        """Get the ss58 keys for funding"""
        return (
            [self._kp_deployer["substrate"]]
            + [
                kp["substrate"]
                for action_type in ["pre", "after"]
                for kp in self._args[action_type]["struct_abi"][:1]
            ]
        )

    @log_func
    def struct_abi(self):
        contract = self._get_contract()

        result = contract.functions.getInfo().call()
        self._unittest.assertEqual(
            result,
            (1, self._kp_deployer["kp"].ss58_address, "test"),
        )

        result = contract.functions.getTuple().call()
        self._unittest.assertEqual(
            result,
            [1, self._kp_deployer["kp"].ss58_address, "test"],
        )

        return None

    def migration_same_behavior(self, args):
        return {
            "struct_abi": self.struct_abi(
                *args["struct_abi"]
            ),
        }
