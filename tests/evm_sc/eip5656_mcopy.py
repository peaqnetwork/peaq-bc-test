from tests.evm_sc.base import SmartContractBehavior, log_func
from tools.peaq_eth_utils import get_eth_info
import random


class EIP5656MCOPYTestBehavior(SmartContractBehavior):
    def __init__(self, unittest, w3, kp_deployer):
        super().__init__(unittest, "ETH/eip5656_mcopy", w3, kp_deployer)

    @log_func
    def deploy(self, deploy_args=None):
        super().deploy(deploy_args)

    def compose_all_args(self):
        self._args = {
            "pre": {
                "mcopy_basic_tests": [get_eth_info()],
                "mcopy_gas_tests": [get_eth_info()],
                "mcopy_edge_cases": [get_eth_info()],
            },
            "after": {
                "mcopy_basic_tests": [get_eth_info()],
                "mcopy_gas_tests": [get_eth_info()],
                "mcopy_edge_cases": [get_eth_info()],
            },
        }

    def get_fund_ss58_keys(self):
        return [self._kp_deployer["substrate"]] + [
            kp["substrate"]
            for action_type in ["pre", "after"]
            for test_type in ["mcopy_basic_tests", "mcopy_gas_tests", "mcopy_edge_cases"]
            for kp in self._args[action_type][test_type]
        ]

    def _generate_test_data(self, size_bytes):
        """Generate test data of specified size"""
        return bytes([random.randint(0, 255) for _ in range(size_bytes)])

    @log_func
    def mcopy_basic_tests(self, kp_caller):
        """Test basic MCOPY functionality"""
        contract = self._get_contract()

        # Test 1: Basic MCOPY with small data
        test_data = b"Hello, MCOPY world! This is a test of EIP-5656."
        tx1 = contract.functions.testBasicMCOPY(test_data).build_transaction(
            self.compose_build_transaction_args(kp_caller)
        )
        receipt1 = self.send_and_check_tx(tx1, kp_caller)

        # Get result
        result1 = contract.functions.testBasicMCOPY(test_data).call()
        copied_data, is_identical = result1

        # Test 2: MCOPY with different sizes
        tx2 = contract.functions.testMCOPYSizes().build_transaction(
            self.compose_build_transaction_args(kp_caller)
        )
        receipt2 = self.send_and_check_tx(tx2, kp_caller)

        result2 = contract.functions.testMCOPYSizes().call()
        size_test_results = result2

        # Test 3: Large data copy
        large_data = self._generate_test_data(512)
        tx3 = contract.functions.testMCOPYLarge(len(large_data)).build_transaction(
            self.compose_build_transaction_args(kp_caller)
        )
        receipt3 = self.send_and_check_tx(tx3, kp_caller)

        result3 = contract.functions.testMCOPYLarge(len(large_data)).call()
        large_copy_success, data_hash = result3

        return {
            "basic_mcopy_success": receipt1["status"] == 1 and is_identical,
            "copied_data_length": len(copied_data),
            "original_data_length": len(test_data),
            "data_integrity_preserved": is_identical,
            "size_tests_passed": all(size_test_results),
            "size_test_results": size_test_results,
            "large_copy_success": receipt3["status"] == 1 and large_copy_success,
            "large_data_hash": data_hash,
            "total_gas_used": sum([
                receipt1.get("gasUsed", 0),
                receipt2.get("gasUsed", 0),
                receipt3.get("gasUsed", 0)
            ]),
            "mcopy_functional": receipt1["status"] == 1 and receipt2["status"] == 1 and receipt3["status"] == 1
        }

    @log_func
    def mcopy_gas_tests(self, kp_caller):
        """Test MCOPY gas efficiency compared to manual copying"""
        contract = self._get_contract()

        # Test gas comparison with different data sizes
        test_sizes = [64, 128, 256, 512]
        gas_results = []

        for size in test_sizes:
            test_data = self._generate_test_data(size)

            # Test MCOPY vs manual copy
            tx = contract.functions.testMCOPYGasComparison(test_data).build_transaction(
                self.compose_build_transaction_args(kp_caller)
            )
            receipt = self.send_and_check_tx(tx, kp_caller)

            # Get gas estimates
            gas_estimate = contract.functions.getMCOPYGasEstimate(test_data).call()
            mcopy_gas, manual_gas = gas_estimate

            gas_results.append({
                "size": size,
                "transaction_gas": receipt.get("gasUsed", 0),
                "mcopy_estimate": mcopy_gas,
                "manual_estimate": manual_gas,
                "gas_savings": manual_gas - mcopy_gas if manual_gas > mcopy_gas else 0,
                "efficiency_ratio": mcopy_gas / manual_gas if manual_gas > 0 else 1.0
            })

        # Calculate average efficiency
        avg_efficiency = sum(r["efficiency_ratio"] for r in gas_results) / len(gas_results)
        total_savings = sum(r["gas_savings"] for r in gas_results)

        return {
            "gas_test_results": gas_results,
            "average_efficiency_ratio": avg_efficiency,
            "total_gas_savings": total_savings,
            "mcopy_more_efficient": avg_efficiency < 1.0,
            "all_tests_successful": all(r["transaction_gas"] > 0 for r in gas_results),
            "gas_optimization_working": total_savings > 0
        }

    @log_func
    def mcopy_edge_cases(self, kp_caller):
        """Test MCOPY edge cases and boundary conditions"""
        contract = self._get_contract()

        # Test 1: Zero-length copy
        tx1 = contract.functions.testMCOPYZeroLength().build_transaction(
            self.compose_build_transaction_args(kp_caller)
        )
        receipt1 = self.send_and_check_tx(tx1, kp_caller)

        result1 = contract.functions.testMCOPYZeroLength().call()
        zero_length_success = result1

        # Test 2: Overlapping memory regions
        tx2 = contract.functions.testMCOPYOverlap().build_transaction(
            self.compose_build_transaction_args(kp_caller)
        )
        receipt2 = self.send_and_check_tx(tx2, kp_caller)

        result2 = contract.functions.testMCOPYOverlap().call()
        overlap_success = result2

        # Test 3: Edge case with exact 32-byte boundaries
        boundary_data = self._generate_test_data(32)  # Exactly 32 bytes
        tx3 = contract.functions.testBasicMCOPY(boundary_data).build_transaction(
            self.compose_build_transaction_args(kp_caller)
        )
        receipt3 = self.send_and_check_tx(tx3, kp_caller)

        result3 = contract.functions.testBasicMCOPY(boundary_data).call()
        boundary_copied, boundary_identical = result3

        # Test 4: Odd-sized data (not word-aligned)
        odd_data = self._generate_test_data(33)  # 33 bytes (not word-aligned)
        tx4 = contract.functions.testBasicMCOPY(odd_data).build_transaction(
            self.compose_build_transaction_args(kp_caller)
        )
        receipt4 = self.send_and_check_tx(tx4, kp_caller)

        result4 = contract.functions.testBasicMCOPY(odd_data).call()
        odd_copied, odd_identical = result4

        return {
            "zero_length_handled": receipt1["status"] == 1 and zero_length_success,
            "overlap_handled": receipt2["status"] == 1 and overlap_success,
            "boundary_copy_success": receipt3["status"] == 1 and boundary_identical,
            "odd_size_copy_success": receipt4["status"] == 1 and odd_identical,
            "boundary_data_length": len(boundary_copied),
            "odd_data_length": len(odd_copied),
            "all_edge_cases_passed": all([
                receipt1["status"] == 1 and zero_length_success,
                receipt2["status"] == 1 and overlap_success,
                receipt3["status"] == 1 and boundary_identical,
                receipt4["status"] == 1 and odd_identical
            ]),
            "total_edge_case_gas": sum([
                receipt1.get("gasUsed", 0),
                receipt2.get("gasUsed", 0),
                receipt3.get("gasUsed", 0),
                receipt4.get("gasUsed", 0)
            ]),
            "mcopy_robust": all([zero_length_success, overlap_success, boundary_identical, odd_identical])
        }

    def migration_same_behavior(self, args):
        """Execute all MCOPY test scenarios"""
        results = {}

        if args["mcopy_basic_tests"]:
            results["mcopy_basic_tests"] = self.mcopy_basic_tests(*args["mcopy_basic_tests"])

        if args["mcopy_gas_tests"]:
            results["mcopy_gas_tests"] = self.mcopy_gas_tests(*args["mcopy_gas_tests"])

        if args["mcopy_edge_cases"]:
            results["mcopy_edge_cases"] = self.mcopy_edge_cases(*args["mcopy_edge_cases"])

        return results
