from tests.evm_sc.base import SmartContractBehavior, log_func
from tools.peaq_eth_utils import get_eth_info
from web3 import Web3
import time


class CalldataHeavyTestBehavior(SmartContractBehavior):
    def __init__(self, unittest, w3, kp_deployer):
        super().__init__(unittest, "ETH/calldata_heavy", w3, kp_deployer)
        
        # Simple mock tokens
        self._mock_tokens = [
            "0x1111111111111111111111111111111111111111",
            "0x2222222222222222222222222222222222222222",
            "0x3333333333333333333333333333333333333333"
        ]

    @log_func
    def deploy(self, deploy_args=None):
        super().deploy(deploy_args)

    def compose_all_args(self):
        self._args = {
            "pre": {
                "router_swap_tests": [get_eth_info()],
                "multi_hop_tests": [get_eth_info()],
                "batch_operation_tests": [get_eth_info()],
                "long_calldata_tests": [get_eth_info()],
                "aggregator_tests": [get_eth_info()],
                "calldata_limits_tests": [],
            },
            "after": {
                "router_swap_tests": [get_eth_info()],
                "multi_hop_tests": [get_eth_info()],
                "batch_operation_tests": [get_eth_info()],
                "long_calldata_tests": [get_eth_info()],
                "aggregator_tests": [get_eth_info()],
                "calldata_limits_tests": [],
            },
        }

    def get_fund_ss58_keys(self):
        """Get the ss58 keys for funding"""
        return [self._kp_deployer["substrate"]] + [
            kp["substrate"]
            for action_type in ["pre", "after"]
            for test_type in ["router_swap_tests", "multi_hop_tests", "batch_operation_tests", 
                            "long_calldata_tests", "aggregator_tests"]
            for kp in self._args[action_type][test_type]
        ]

    def _generate_large_data(self, size_kb):
        """Generate simple test data"""
        return ("test_data_" * (size_kb * 50)).encode('utf-8')[:size_kb * 1024]

    def _create_swap_data(self, amount_in):
        """Create simple swap data"""
        return {
            'deadline': int(time.time()) + 3600,
            'amountIn': amount_in,
            'amountOutMinimum': int(amount_in * 0.9),
        }

    def _encode_path(self):
        """Simple path encoding"""
        return Web3.to_bytes(text="simple_path")

    @log_func
    def router_swap_tests(self, kp_caller):
        """Test router swap with multiple transactions"""
        contract = self._get_contract()
        
        # Main swap test
        swap_data = self._create_swap_data(Web3.to_wei(1, 'ether'))
        tx = contract.functions.exactInputSingle(
            swap_data['deadline'],
            swap_data['amountIn'], 
            swap_data['amountOutMinimum']
        ).build_transaction(self.compose_build_transaction_args(kp_caller))
        receipt = self.send_and_check_tx(tx, kp_caller)
        
        # Calldata analysis
        tx_data = self._w3.eth.get_transaction(receipt['transactionHash'])
        calldata_size = len(tx_data['input']) // 2 - 1
        
        # Multiple swaps with different amounts
        multi_swap_results = []
        for i in range(3):
            amount = Web3.to_wei(0.5 + i * 0.1, 'ether')
            swap_data_multi = self._create_swap_data(amount)
            
            tx_multi = contract.functions.exactInputSingle(
                swap_data_multi['deadline'],
                swap_data_multi['amountIn'],
                swap_data_multi['amountOutMinimum']
            ).build_transaction(self.compose_build_transaction_args(kp_caller))
            receipt_multi = self.send_and_check_tx(tx_multi, kp_caller)
            multi_swap_results.append(receipt_multi["status"] == 1)
        
        return {
            "single_swap_success": receipt["status"] == 1,
            "calldata_size_bytes": calldata_size,
            "gas_used": receipt.get("gasUsed", 0),
            "multi_swap_results": multi_swap_results,
            "all_multi_swaps_successful": all(multi_swap_results),
            "router_functionality_working": receipt["status"] == 1 and all(multi_swap_results)
        }

    @log_func
    def multi_hop_tests(self, kp_caller):
        """Test multi-hop swaps with different path lengths"""
        contract = self._get_contract()
        deadline = int(time.time()) + 3600
        
        # Short path test
        short_path = self._encode_path()
        tx_short = contract.functions.exactInput(
            short_path,
            deadline,
            Web3.to_wei(1, 'ether'),
            Web3.to_wei(0.9, 'ether')
        ).build_transaction(self.compose_build_transaction_args(kp_caller))
        receipt_short = self.send_and_check_tx(tx_short, kp_caller)
        
        # Long path test  
        long_path = Web3.to_bytes(text="long_path_data")
        tx_long = contract.functions.exactInput(
            long_path,
            deadline,
            Web3.to_wei(0.5, 'ether'),
            Web3.to_wei(0.4, 'ether')
        ).build_transaction(self.compose_build_transaction_args(kp_caller))
        receipt_long = self.send_and_check_tx(tx_long, kp_caller)
        
        return {
            "short_hop_success": receipt_short["status"] == 1,
            "short_hop_gas": receipt_short.get("gasUsed", 0),
            "short_path_length": len(short_path),
            "long_hop_success": receipt_long["status"] == 1,
            "long_hop_gas": receipt_long.get("gasUsed", 0),
            "long_path_length": len(long_path),
            "gas_scaling_reasonable": receipt_long.get("gasUsed", 0) > receipt_short.get("gasUsed", 0),
            "multi_hop_functional": receipt_short["status"] == 1 and receipt_long["status"] == 1
        }

    @log_func
    def batch_operation_tests(self, kp_caller):
        """Test batch operations with varying calldata sizes"""
        contract = self._get_contract()
        
        # Create batch operations with different sizes
        operations = [
            Web3.to_bytes(text="op1"),
            Web3.to_bytes(text="op2_longer_data"),
            Web3.to_bytes(text="op3_even_longer_operation_data"),
            Web3.to_bytes(text="op4_" + "x" * 50),
            Web3.to_bytes(text="op5_" + "x" * 100),
        ]
        
        # Execute batch operations
        tx_batch = contract.functions.batchOperations(operations).build_transaction(
            self.compose_build_transaction_args(kp_caller)
        )
        receipt_batch = self.send_and_check_tx(tx_batch, kp_caller)
        
        # Get calldata analysis
        tx_data = self._w3.eth.get_transaction(receipt_batch['transactionHash'])
        calldata_size = len(tx_data['input']) // 2 - 1
        
        return {
            "batch_success": receipt_batch["status"] == 1,
            "operation_count": len(operations),
            "calldata_size_bytes": calldata_size,
            "gas_used": receipt_batch.get("gasUsed", 0),
            "gas_per_operation": receipt_batch.get("gasUsed", 0) // len(operations),
            "batch_processing_efficient": calldata_size > 1000,
        }

    @log_func
    def long_calldata_tests(self, kp_caller):
        """Test long calldata processing"""
        contract = self._get_contract()
        
        # Generate test data chunks
        data1 = self._generate_large_data(1)  # 1KB
        data2 = self._generate_large_data(1)  # 1KB
        data3 = self._generate_large_data(1)  # 1KB
        
        # Process long calldata
        tx_long = contract.functions.processLongCalldata(
            data1, data2, data3
        ).build_transaction(self.compose_build_transaction_args(kp_caller))
        receipt_long = self.send_and_check_tx(tx_long, kp_caller)
        
        # Get contract result
        result = contract.functions.processLongCalldata(data1, data2, data3).call()
        data_hash, total_length = result[0], result[1]
        
        # Test nested data decoding
        nested_data = Web3.to_bytes(text="nested_test_data" * 20)  # ~340 bytes
        tx_nested = contract.functions.decodeNestedCalldata(nested_data).build_transaction(
            self.compose_build_transaction_args(kp_caller)
        )
        receipt_nested = self.send_and_check_tx(tx_nested, kp_caller)
        
        # Calldata analysis
        tx_data = self._w3.eth.get_transaction(receipt_long['transactionHash'])
        calldata_size = len(tx_data['input']) // 2 - 1
        
        return {
            "long_calldata_success": receipt_long["status"] == 1,
            "total_data_length": total_length,
            "calldata_size_bytes": calldata_size,
            "data_hash": Web3.to_hex(data_hash),
            "gas_used": receipt_long.get("gasUsed", 0),
            "nested_decoding_success": receipt_nested["status"] == 1,
            "nested_gas_used": receipt_nested.get("gasUsed", 0),
            "blob_like_processing_works": total_length > 5000,
        }

    @log_func
    def aggregator_tests(self, kp_caller):
        """Test aggregator functionality with multiple amounts"""
        contract = self._get_contract()
        
        # Test with multiple swap amounts  
        amounts = [
            Web3.to_wei(0.5, 'ether'), 
            Web3.to_wei(1.0, 'ether'), 
            Web3.to_wei(0.75, 'ether'), 
            Web3.to_wei(0.25, 'ether')
        ]
        
        # Execute aggregated swap
        tx_agg = contract.functions.aggregateSwaps(amounts).build_transaction(
            self.compose_build_transaction_args(kp_caller)
        )
        receipt_agg = self.send_and_check_tx(tx_agg, kp_caller)
        
        # Calldata analysis
        tx_data = self._w3.eth.get_transaction(receipt_agg['transactionHash'])
        calldata_size = len(tx_data['input']) // 2 - 1
        
        return {
            "aggregator_success": receipt_agg["status"] == 1,
            "total_swaps": len(amounts),
            "calldata_size_bytes": calldata_size,
            "gas_used": receipt_agg.get("gasUsed", 0),
            "aggregation_efficient": calldata_size > 500,
        }

    @log_func
    def calldata_limits_tests(self):
        """Test calldata size limits and edge cases"""
        contract = self._get_contract()
        
        # Test different calldata sizes
        small_data = self._generate_large_data(1)     # 1KB
        medium_data = self._generate_large_data(5)    # 5KB  
        large_data = self._generate_large_data(10)    # 10KB
        
        # Test calldata limits
        result = contract.functions.testCalldataLimits(
            small_data, medium_data, large_data
        ).call()
        
        small_ok, medium_ok, large_ok = result
        
        # Get calldata statistics
        stats = contract.functions.getCalldataStats().call()
        current_counter, total_stored, average_size = stats
        
        return {
            "small_calldata_ok": small_ok,
            "medium_calldata_ok": medium_ok,
            "large_calldata_ok": large_ok,
            "all_sizes_processed": small_ok and medium_ok and large_ok,
            "calldata_counter": current_counter,
            "total_stored": total_stored,
            "average_size": average_size,
            "size_handling_robust": small_ok and medium_ok,
        }


    def migration_same_behavior(self, args):
        """Execute all calldata-heavy test scenarios"""
        results = {}
        
        # Execute router swap tests
        if args["router_swap_tests"]:
            results["router_swap_tests"] = self.router_swap_tests(*args["router_swap_tests"])
        
        # Execute multi-hop tests
        if args["multi_hop_tests"]:
            results["multi_hop_tests"] = self.multi_hop_tests(*args["multi_hop_tests"])
        
        # Execute batch operation tests
        if args["batch_operation_tests"]:
            results["batch_operation_tests"] = self.batch_operation_tests(*args["batch_operation_tests"])
        
        # Execute long calldata tests
        if args["long_calldata_tests"]:
            results["long_calldata_tests"] = self.long_calldata_tests(*args["long_calldata_tests"])
        
        # Execute aggregator tests
        if args["aggregator_tests"]:
            results["aggregator_tests"] = self.aggregator_tests(*args["aggregator_tests"])
        
        # Execute calldata limits tests (no args needed)
        results["calldata_limits_tests"] = self.calldata_limits_tests()
        
        return results