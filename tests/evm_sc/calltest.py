from tests.evm_sc.base import SmartMultipleContractBehavior, log_func
from tools.peaq_eth_utils import deploy_contract, deploy_contract_with_args, get_eth_info
from web3 import Web3


class CallTestSCBehavior(SmartMultipleContractBehavior):
    def __init__(self, unittest, w3, kp_deployer):
        super().__init__(
            unittest,
            {
                "target": "ETH/calltest/target",
                "caller": "ETH/calltest",
            },
            w3,
            kp_deployer,
        )
        
        # Test values for different scenarios
        self._test_values = {
            "call_value": 100,
            "delegatecall_value": 200,
            "staticcall_value": 300,
            "revert_value": 999,
        }

    @log_func
    def deploy(self, deploy_args=None):
        # Deploy target contract first
        target_address = deploy_contract(
            self._w3,
            self._kp_deployer["kp"],
            self._eth_chain_id,
            self._abis["target"],
            self._load_bytecode_by_key("target"),
        )

        # Deploy caller contract with target address
        caller_address = deploy_contract_with_args(
            self._w3,
            self._kp_deployer["kp"],
            self._eth_chain_id,
            self._abis["caller"],
            self._load_bytecode_by_key("caller"),
            [target_address],
        )

        self._addresses = {
            "target": target_address,
            "caller": caller_address,
        }
        
        self._contracts = {
            "target": self._get_contract_by_key("target"),
            "caller": self._get_contract_by_key("caller"),
        }

    def compose_all_args(self):
        self._args = {
            "pre": {
                "call_tests": [get_eth_info()],
                "delegatecall_tests": [get_eth_info()],
                "staticcall_tests": [],
                "context_tests": [get_eth_info()],
                "fallback_tests": [get_eth_info()],
            },
            "after": {
                "call_tests": [get_eth_info()],
                "delegatecall_tests": [get_eth_info()],
                "staticcall_tests": [],
                "context_tests": [get_eth_info()],
                "fallback_tests": [get_eth_info()],
            },
        }

    def get_fund_ss58_keys(self):
        """Get the ss58 keys for funding"""
        return [self._kp_deployer["substrate"]] + [
            kp["substrate"]
            for action_type in ["pre", "after"]
            for test_type in ["call_tests", "delegatecall_tests", "context_tests", "fallback_tests"]
            for kp in self._args[action_type][test_type]
        ]

    @log_func
    def call_tests(self, kp_caller):
        """Test regular call functionality and context preservation"""
        caller_contract = self._contracts["caller"]
        target_contract = self._contracts["target"]
        
        # Test regular call
        tx = caller_contract.functions.testCall(
            self._test_values["call_value"]
        ).build_transaction(self.compose_build_transaction_args(kp_caller))
        
        receipt = self.send_and_check_tx(tx, kp_caller)
        
        # Verify call succeeded and context is preserved in target
        target_value = target_contract.functions.value().call()
        target_sender = target_contract.functions.sender().call()
        
        # In regular call, target should see caller contract as sender
        expected_sender = Web3.to_checksum_address(self._addresses["caller"])
        
        return {
            "call_success": receipt["status"] == 1,
            "target_value": target_value,
            "target_sender": target_sender,
            "expected_sender": expected_sender,
            "context_preserved": target_sender.lower() == expected_sender.lower(),
        }

    @log_func
    def delegatecall_tests(self, kp_caller):
        """Test delegatecall functionality and context preservation"""
        caller_contract = self._contracts["caller"]
        
        # Get initial caller contract state
        initial_caller_value = caller_contract.functions.value().call()
        
        # Test delegatecall - should modify caller's state, not target's
        tx = caller_contract.functions.testDelegatecallContext(
            self._test_values["delegatecall_value"]
        ).build_transaction(self.compose_build_transaction_args(kp_caller))
        
        receipt = self.send_and_check_tx(tx, kp_caller)
        
        # After delegatecall, caller contract's state should be modified
        final_caller_value = caller_contract.functions.value().call()
        caller_sender = caller_contract.functions.sender().call()
        
        # Get context from both contracts
        caller_context = caller_contract.functions.getDelegatecallContext().call()
        target_context = caller_contract.functions.getCallContext().call()
        
        return {
            "delegatecall_success": receipt["status"] == 1,
            "initial_caller_value": initial_caller_value,
            "final_caller_value": final_caller_value,
            "caller_sender": caller_sender,
            "state_modified_in_caller": final_caller_value != initial_caller_value,
            "delegatecall_context": caller_context,
            "target_context": target_context,
        }

    @log_func
    def staticcall_tests(self):
        """Test staticcall functionality - read-only operations"""
        caller_contract = self._contracts["caller"]
        
        # Test successful staticcall (read-only)
        result = caller_contract.functions.testStaticcall().call()
        staticcall_success = result[0]
        staticcall_value = result[1]
        
        # Test staticcall with state modification (should fail)
        modify_result = caller_contract.functions.testStaticcallModify().call()
        modify_success = modify_result[0]
        
        return {
            "staticcall_success": staticcall_success,
            "staticcall_value": staticcall_value,
            "modify_attempt_success": modify_success,
            "readonly_enforced": not modify_success,  # Should be False (failed)
        }

    @log_func
    def context_tests(self, kp_caller):
        """Test context preservation across different call types"""
        caller_contract = self._contracts["caller"]
        target_contract = self._contracts["target"]
        
        # Test call with ether value
        tx = caller_contract.functions.testCall(
            self._test_values["call_value"]
        ).build_transaction({
            **self.compose_build_transaction_args(kp_caller),
            "value": Web3.to_wei(0.1, "ether")
        })
        
        receipt = self.send_and_check_tx(tx, kp_caller)
        
        # Check context preservation
        target_msg_value = target_contract.functions.msgValue().call()
        target_origin = target_contract.functions.origin().call()
        
        return {
            "context_call_success": receipt["status"] == 1,
            "msg_value_preserved": target_msg_value == Web3.to_wei(0.1, "ether"),
            "tx_origin_preserved": target_origin.lower() == kp_caller["kp"].ss58_address.lower(),
        }

    @log_func
    def fallback_tests(self, kp_caller):
        """Test fallback function behavior"""
        caller_contract = self._contracts["caller"]
        
        # Test call to non-existent function (triggers fallback)
        tx = caller_contract.functions.testFallbackCall().build_transaction({
            **self.compose_build_transaction_args(kp_caller),
            "value": Web3.to_wei(0.05, "ether")
        })
        
        receipt = self.send_and_check_tx(tx, kp_caller)
        
        # Test revert behavior
        tx_revert = caller_contract.functions.testRevertCall().build_transaction(
            self.compose_build_transaction_args(kp_caller)
        )
        
        receipt_revert = self.send_and_check_tx(tx_revert, kp_caller)
        
        # Check contract state after fallback calls
        last_call_success = caller_contract.functions.lastCallSuccess().call()
        
        return {
            "fallback_call_success": receipt["status"] == 1,
            "revert_call_success": receipt_revert["status"] == 1,
            "fallback_handled": last_call_success,  # Should be True from fallback
            "revert_handled": not last_call_success,  # Should be False from revert
        }

    @log_func 
    def comprehensive_call_test(self, kp_caller):
        """Comprehensive test covering all call types and edge cases"""
        caller_contract = self._contracts["caller"]
        
        # Test batch calls
        test_values = [10, 20, 30]
        tx = caller_contract.functions.testBatchCalls(test_values).build_transaction(
            self.compose_build_transaction_args(kp_caller)
        )
        
        receipt = self.send_and_check_tx(tx, kp_caller)
        
        # Test call with custom gas
        tx_gas = caller_contract.functions.testCallWithGas(
            self._test_values["call_value"], 100000
        ).build_transaction({
            **self.compose_build_transaction_args(kp_caller),
            "value": Web3.to_wei(0.01, "ether")
        })
        
        receipt_gas = self.send_and_check_tx(tx_gas, kp_caller)
        
        return {
            "batch_calls_success": receipt["status"] == 1,
            "gas_limited_call_success": receipt_gas["status"] == 1,
            "all_comprehensive_tests_passed": (
                receipt["status"] == 1 and receipt_gas["status"] == 1
            ),
        }

    def migration_same_behavior(self, args):
        """Execute all test scenarios"""
        results = {}
        
        # Execute call tests
        if args["call_tests"]:
            results["call_tests"] = self.call_tests(*args["call_tests"])
        
        # Execute delegatecall tests  
        if args["delegatecall_tests"]:
            results["delegatecall_tests"] = self.delegatecall_tests(*args["delegatecall_tests"])
        
        # Execute staticcall tests (no args needed)
        results["staticcall_tests"] = self.staticcall_tests()
        
        # Execute context tests
        if args["context_tests"]:
            results["context_tests"] = self.context_tests(*args["context_tests"])
        
        # Execute fallback tests
        if args["fallback_tests"]:
            results["fallback_tests"] = self.fallback_tests(*args["fallback_tests"])
            
            # Also run comprehensive tests with same keypair
            results["comprehensive_tests"] = self.comprehensive_call_test(*args["fallback_tests"])
        
        return results