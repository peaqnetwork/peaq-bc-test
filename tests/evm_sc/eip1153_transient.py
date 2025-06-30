from tests.evm_sc.base import SmartContractBehavior, log_func
from tools.peaq_eth_utils import get_eth_info


class EIP1153TransientTestBehavior(SmartContractBehavior):
    def __init__(self, unittest, w3, kp_deployer):
        super().__init__(unittest, "ETH/eip1153_transient", w3, kp_deployer)

    @log_func
    def deploy(self, deploy_args=None):
        super().deploy(deploy_args)

    def compose_all_args(self):
        self._args = {
            "pre": {
                "transient_storage_tests": [get_eth_info()],
            },
            "after": {
                "transient_storage_tests": [get_eth_info()],
            },
        }

    def get_fund_ss58_keys(self):
        return [self._kp_deployer["substrate"]] + [
            kp["substrate"]
            for action_type in ["pre", "after"]
            for test_type in ["transient_storage_tests"]
            for kp in self._args[action_type][test_type]
        ]

    @log_func
    def transient_storage_tests(self, kp_caller):
        """Test EIP-1153 transient storage TLOAD/TSTORE"""
        contract = self._get_contract()

        # Test 1: Basic TSTORE/TLOAD
        test_value = 12345
        tx1 = contract.functions.testBasicTransient(test_value).build_transaction(
            self.compose_build_transaction_args(kp_caller)
        )
        receipt1 = self.send_and_check_tx(tx1, kp_caller)

        # Get result from call
        result1 = contract.functions.testBasicTransient(test_value).call()

        # Test 2: Transient isolation between calls
        tx2 = contract.functions.testTransientIsolation().build_transaction(
            self.compose_build_transaction_args(kp_caller)
        )
        receipt2 = self.send_and_check_tx(tx2, kp_caller)

        result2 = contract.functions.testTransientIsolation().call()

        # Test 3: Transient vs regular storage
        tx3 = contract.functions.testTransientVsRegular(test_value).build_transaction(
            self.compose_build_transaction_args(kp_caller)
        )
        receipt3 = self.send_and_check_tx(tx3, kp_caller)

        result3 = contract.functions.testTransientVsRegular(test_value).call()

        # Test 4: Multiple transient slots
        tx4 = contract.functions.testMultipleSlots().build_transaction(
            self.compose_build_transaction_args(kp_caller)
        )
        receipt4 = self.send_and_check_tx(tx4, kp_caller)

        result4 = contract.functions.testMultipleSlots().call()

        # Test 5: Transient in loops
        tx5 = contract.functions.testTransientLoop(5).build_transaction(
            self.compose_build_transaction_args(kp_caller)
        )
        receipt5 = self.send_and_check_tx(tx5, kp_caller)

        result5 = contract.functions.testTransientLoop(5).call()

        return {
            "all_tests_passed": all([
                receipt1["status"] == 1,
                receipt2["status"] == 1,
                receipt3["status"] == 1,
                receipt4["status"] == 1,
                receipt5["status"] == 1
            ]),
            "basic_transient_success": receipt1["status"] == 1 and result1 == test_value,
            "isolation_success": receipt2["status"] == 1 and result2,
            "vs_regular_success": receipt3["status"] == 1 and result3,
            "multiple_slots_success": receipt4["status"] == 1 and result4,
            "loop_success": receipt5["status"] == 1 and result5 == 10,  # 0+1+2+3+4 = 10
            "tload_tstore_working": result1 == test_value,
            "total_gas_used": sum([
                receipt1.get("gasUsed", 0),
                receipt2.get("gasUsed", 0),
                receipt3.get("gasUsed", 0),
                receipt4.get("gasUsed", 0),
                receipt5.get("gasUsed", 0),
            ])
        }

    def migration_same_behavior(self, args):
        """Execute transient storage tests"""
        results = {}

        if args["transient_storage_tests"]:
            results["transient_storage_tests"] = self.transient_storage_tests(*args["transient_storage_tests"])

        return results
