from tests.evm_sc.base import SmartContractBehavior, log_func
from web3 import Web3


class EventSCBehavior(SmartContractBehavior):
    def __init__(self, unittest, w3, kp_deployer):
        super().__init__(unittest, "ETH/event", w3, kp_deployer)

    @log_func
    def deploy(self, deploy_args=None):
        super().deploy(deploy_args)

    def compose_all_args(self):
        self._args = {
            "pre": {
                "trigger_event": [],
            },
            "after": {
                "trigger_event": [],
            },
        }

    def get_fund_ss58_keys(self):
        """Get the ss58 keys for funding"""
        return [self._kp_deployer["substrate"]] + [
            kp["substrate"]
            for action_type in ["pre", "after"]
            for kp in self._args[action_type]["trigger_event"][:1]
        ]

    @log_func
    def trigger_event(self):
        contract = self._get_contract()

        tx = contract.functions.triggerAll().build_transaction(
            self.compose_build_transaction_args(self._kp_deployer)
        )
        tx_receipt = self.send_and_check_tx(tx, self._kp_deployer)
        block_idx = tx_receipt["blockNumber"]

        events = contract.events.Event0.create_filter(
            fromBlock=block_idx, toBlock=block_idx
        )
        event = events.get_all_entries()[0]
        self._unittest.assertEqual(event["args"], {})

        events = contract.events.Event1.create_filter(
            fromBlock=block_idx, toBlock=block_idx
        )
        event = events.get_all_entries()[0]
        self._unittest.assertEqual(event["args"]["a"], 1)

        events = contract.events.Event2.create_filter(
            fromBlock=block_idx, toBlock=block_idx
        )
        event = events.get_all_entries()[0]
        self._unittest.assertEqual(event["args"]["a"], 2)
        self._unittest.assertEqual(
            event["args"]["b"], self._kp_deployer["kp"].ss58_address
        )

        events = contract.events.Event3.create_filter(
            fromBlock=block_idx, toBlock=block_idx
        )
        event = events.get_all_entries()[0]
        self._unittest.assertEqual(event["args"]["a"], 3)
        self._unittest.assertEqual(
            event["args"]["b"], self._kp_deployer["kp"].ss58_address
        )
        self._unittest.assertEqual(event["args"]["c"], "hello")

        events = contract.events.Event4.create_filter(
            fromBlock=block_idx, toBlock=block_idx
        )
        event = events.get_all_entries()[0]
        self._unittest.assertEqual(event["args"]["a"], 4)
        self._unittest.assertEqual(
            event["args"]["b"], self._kp_deployer["kp"].ss58_address
        )
        self._unittest.assertEqual(event["args"]["c"], "world")
        self._unittest.assertEqual(event["args"]["d"], True)

        events = contract.events.EventIndex1.create_filter(
            fromBlock=block_idx, toBlock=block_idx
        )
        event = events.get_all_entries()[0]
        self._unittest.assertEqual(event["args"]["a"], 11)
        self._unittest.assertEqual(
            event["args"]["b"], self._kp_deployer["kp"].ss58_address
        )
        self._unittest.assertEqual(event["args"]["c"], "moon")
        self._unittest.assertEqual(event["args"]["d"], False)

        events = contract.events.EventIndex2.create_filter(
            fromBlock=block_idx, toBlock=block_idx
        )
        event = events.get_all_entries()[0]
        self._unittest.assertEqual(event["args"]["a"], 22)
        self._unittest.assertEqual(
            event["args"]["b"], self._kp_deployer["kp"].ss58_address
        )
        self._unittest.assertEqual(event["args"]["c"], "mars")
        self._unittest.assertEqual(event["args"]["d"], True)

        events = contract.events.EventIndex3.create_filter(
            fromBlock=block_idx, toBlock=block_idx
        )
        event = events.get_all_entries()[0]
        self._unittest.assertEqual(event["args"]["a"], 33)
        self._unittest.assertEqual(
            event["args"]["b"], self._kp_deployer["kp"].ss58_address
        )
        self._unittest.assertEqual(
            f'0x{event["args"]["c"].hex()}', Web3.keccak(text="earth").hex()
        )
        self._unittest.assertEqual(event["args"]["d"], False)

        return None

    def migration_same_behavior(self, args):
        return {
            "trigger_event": self.trigger_event(*args["trigger_event"]),
        }
