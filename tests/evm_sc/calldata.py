from tests.evm_sc.base import SmartContractBehavior, log_func
from eth_abi.abi import encode as encode_abi


class CalldataSCBehavior(SmartContractBehavior):
    def __init__(self, unittest, w3, kp_deployer):
        super().__init__(unittest, "ETH/calldata", w3, kp_deployer)

    @log_func
    def deploy(self, deploy_args=None):
        super().deploy(deploy_args)

    def compose_all_args(self):
        self._args = {
            "pre": {
                "batch_set": [],
                "handle": [],
                "router_call": [],
            },
            "after": {
                "batch_set": [],
                "handle": [],
                "router_call": [],
            },
        }

    def get_fund_ss58_keys(self):
        """Get the ss58 keys for funding"""
        return [self._kp_deployer["substrate"]] + [
            kp["substrate"]
            for action_type in ["pre", "after"]
            for kp in self._args[action_type]["batch_set"][:1]
        ] + [
            kp["substrate"]
            for action_type in ["pre", "after"]
            for kp in self._args[action_type]["handle"][:1]
        ] + [
            kp["substrate"]
            for action_type in ["pre", "after"]
            for kp in self._args[action_type]["router_call"][:1]
        ]

    @log_func
    def batch_set(self):
        contract = self._get_contract()

        tx = contract.functions.batchSet([10, 20, 30]).build_transaction(
            self.compose_build_transaction_args(self._kp_deployer)
        )
        tx_receipt = self.send_and_check_tx(tx, self._kp_deployer)
        block_idx = tx_receipt["blockNumber"]
        # get event
        event_filter = contract.events.BatchSet.create_filter(
            fromBlock=block_idx, toBlock=block_idx
        )
        event = event_filter.get_all_entries()[0]
        self._unittest.assertEqual(
            event["args"]["count"],
            3,
            "Event not found",
        )
        self._unittest.assertEqual(
            event["args"]["sum"],
            60,
            "Event not found",
        )
        return None

    @log_func
    def handle(self):
        contract = self._get_contract()

        encoded = encode_abi(["uint256", "address"], [1234, self._kp_deployer["kp"].ss58_address])

        tx = contract.functions.handle(encoded).build_transaction(
            self.compose_build_transaction_args(self._kp_deployer)
        )
        tx_receipt = self.send_and_check_tx(tx, self._kp_deployer)
        block_idx = tx_receipt["blockNumber"]
        # get event
        event_filter = contract.events.Decoded.create_filter(
            fromBlock=block_idx, toBlock=block_idx
        )
        event = event_filter.get_all_entries()[0]
        self._unittest.assertEqual(
            event["args"]["a"],
            1234,
            "Event not found",
        )
        self._unittest.assertEqual(
            event["args"]["b"],
            self._kp_deployer["kp"].ss58_address,
            "Event not found",
        )
        return None

    @log_func
    def router_call(self):
        contract = self._get_contract()
        inner = encode_abi(["uint256", "address"], [999, self._kp_deployer["kp"].ss58_address])
        outer = encode_abi(["string", "bytes"], ["handle", inner])

        tx = contract.functions.routerCall(outer).build_transaction(
            self.compose_build_transaction_args(self._kp_deployer)
        )
        tx_receipt = self.send_and_check_tx(tx, self._kp_deployer)
        block_idx = tx_receipt["blockNumber"]
        # get event
        event_filter = contract.events.Routed.create_filter(
            fromBlock=block_idx, toBlock=block_idx
        )
        event = event_filter.get_all_entries()[0]
        self._unittest.assertEqual(
            event["args"]["method"],
            "handle",
            "Event not found",
        )
        self._unittest.assertEqual(
            event["args"]["data"],
            inner,
            "Event not found",
        )
        return None

    def migration_same_behavior(self, args):
        return {
            "batch_set": self.batch_set(*args["batch_set"]),
            "handle": self.handle(*args["handle"]),
            "router_call": self.router_call(*args["router_call"]),
        }
