from tests.evm_sc.base import SmartContractBehavior, log_func


class GasSCBehavior(SmartContractBehavior):
    def __init__(self, unittest, w3, kp_deployer):
        super().__init__(unittest, "ETH/gas", w3, kp_deployer)

    @log_func
    def deploy(self, deploy_args=None):
        super().deploy(deploy_args)

    def compose_all_args(self):
        self._args = {
            "pre": {
                "gas_branch": [],
            },
            "after": {
                "gas_branch": [],
            },
        }

    def get_fund_ss58_keys(self):
        """Get the ss58 keys for funding"""
        return [self._kp_deployer["substrate"]] + [
            kp["substrate"]
            for action_type in ["pre", "after"]
            for kp in self._args[action_type]["gas_branch"][:1]
        ]

    @log_func
    def gas_branch(self):
        contract = self._get_contract()

        tx_arg = self.compose_build_transaction_args(self._kp_deployer)
        tx_arg["gas"] = 300_000
        tx = contract.functions.checkGas().build_transaction(
            tx_arg,
        )
        tx_receipt = self.send_and_check_tx(tx, self._kp_deployer)

        # Check transaction status
        if tx_receipt["status"] != 1:
            raise Exception(f"Transaction failed with status: {tx_receipt['status']}")

        # Check if events were emitted
        if not tx_receipt.get('logs'):
            raise Exception(f"No events emitted - transaction may have failed silently")

        # Use create_filter with proper error handling
        event_filter = contract.events.Success.create_filter(fromBlock=tx_receipt['blockNumber'], toBlock=tx_receipt['blockNumber'])
        success_logs = event_filter.get_all_entries()
        if not success_logs:
            raise Exception(f"Success event not found in {len(tx_receipt['logs'])} emitted events")
        self._unittest.assertNotEqual(
            success_logs[0],
            None,
            "Event not found",
        )

        tx_arg = self.compose_build_transaction_args(self._kp_deployer)
        tx_arg["gas"] = 60_000
        tx = contract.functions.checkGas().build_transaction(
            tx_arg,
        )
        tx_receipt = self.send_and_check_tx(tx, self._kp_deployer)

        # Check transaction status
        if tx_receipt["status"] != 1:
            raise Exception(f"Transaction failed with status: {tx_receipt['status']}")

        # Check if events were emitted
        if not tx_receipt.get('logs'):
            raise Exception(f"No events emitted - transaction may have failed silently")

        # Use create_filter with proper error handling
        event_filter = contract.events.Fail.create_filter(fromBlock=tx_receipt['blockNumber'], toBlock=tx_receipt['blockNumber'])
        fail_logs = event_filter.get_all_entries()
        if not fail_logs:
            raise Exception(f"Fail event not found in {len(tx_receipt['logs'])} emitted events")
        self._unittest.assertNotEqual(
            fail_logs[0],
            None,
            "Event not found",
        )

        return None

    def migration_same_behavior(self, args):
        return {
            "gas_branch": self.gas_branch(*args["gas_branch"]),
        }
