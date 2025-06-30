from tests.evm_sc.base import SmartContractBehavior, log_func
from tools.peaq_eth_utils import get_eth_info
from web3 import Web3
import time


class ChainInfoTestBehavior(SmartContractBehavior):
    def __init__(self, unittest, w3, kp_deployer):
        super().__init__(unittest, "ETH/chain_info", w3, kp_deployer)

    @log_func
    def deploy(self, deploy_args=None):
        super().deploy(deploy_args)

    def compose_all_args(self):
        self._args = {
            "pre": {
                "chain_metadata_tests": [get_eth_info()],
                "time_locked_tests": [get_eth_info()],
                "block_dependent_tests": [get_eth_info()],
            },
            "after": {
                "chain_metadata_tests": [get_eth_info()],
                "time_locked_tests": [get_eth_info()],
                "block_dependent_tests": [get_eth_info()],
            },
        }

    def get_fund_ss58_keys(self):
        """Get the ss58 keys for funding"""
        return [self._kp_deployer["substrate"]] + [
            kp["substrate"]
            for action_type in ["pre", "after"]
            for test_type in ["chain_metadata_tests", "time_locked_tests", "block_dependent_tests"]
            for kp in self._args[action_type][test_type]
        ]

    @log_func
    def chain_metadata_tests(self, kp_caller):
        """Test chain metadata preservation and correctness"""
        contract = self._get_contract()

        # Get current chain info from Web3
        current_block = self._w3.eth.block_number
        current_timestamp = int(time.time())
        current_chain_id = self._w3.eth.chain_id

        # Test chain info function
        tx = contract.functions.testChainInfo(
            current_timestamp,
            current_block,
            current_chain_id
        ).build_transaction(self.compose_build_transaction_args(kp_caller))
        receipt = self.send_and_check_tx(tx, kp_caller)

        # Get result from contract call
        result = contract.functions.testChainInfo(
            current_timestamp,
            current_block,
            current_chain_id
        ).call()

        (actual_timestamp, actual_block_number, actual_chain_id,
         block_hash, coinbase, prevrandao, gas_limit, base_fee,
         timestamp_match, block_number_match, chain_id_match) = result

        # Verify metadata consistency
        web3_block = self._w3.eth.get_block(actual_block_number)

        return {
            "chain_metadata_success": receipt["status"] == 1,
            "actual_timestamp": actual_timestamp,
            "actual_block_number": actual_block_number,
            "actual_chain_id": actual_chain_id,
            "block_hash": Web3.to_hex(block_hash),
            "coinbase": coinbase,
            "prevrandao": prevrandao,
            "gas_limit": gas_limit,
            "base_fee": base_fee,
            "timestamp_match": timestamp_match,
            "block_number_match": block_number_match,
            "chain_id_match": chain_id_match,
            "web3_consistency": {
                "timestamp_close": abs(web3_block['timestamp'] - actual_timestamp) <= 5,
                "block_number_match": web3_block['number'] == actual_block_number,
                "chain_id_match": self._w3.eth.chain_id == actual_chain_id,
                "prevrandao_exists": prevrandao > 0,  # Should be non-zero randomness
                "gas_limit_reasonable": gas_limit > 0,  # Should have positive gas limit
                "base_fee_exists": base_fee >= 0,  # Base fee can be 0 but should exist
                "coinbase_valid": coinbase != "0x0000000000000000000000000000000000000000",
                "block_hash_exists": block_hash != "0x0000000000000000000000000000000000000000000000000000000000000000",
            },
            "metadata_preserved": timestamp_match and block_number_match and chain_id_match,
            "gas_used": receipt.get("gasUsed", 0)
        }

    @log_func
    def time_locked_tests(self, kp_caller):
        """Test time-sensitive operations that depend on block.timestamp"""
        contract = self._get_contract()

        current_time = int(time.time())
        test_amount = Web3.to_wei(1, 'ether')

        # Test 1: Operation that should succeed (unlock time in past)
        past_unlock = current_time - 3600  # 1 hour ago
        tx1 = contract.functions.timeLockedOperation(
            past_unlock, test_amount
        ).build_transaction(self.compose_build_transaction_args(kp_caller))
        receipt1 = self.send_and_check_tx(tx1, kp_caller)

        result1 = contract.functions.timeLockedOperation(
            past_unlock, test_amount
        ).call()

        # Test 2: Operation that should fail (unlock time in future)
        future_unlock = current_time + 3600  # 1 hour from now
        try:
            tx2 = contract.functions.timeLockedOperation(
                future_unlock, test_amount
            ).build_transaction(self.compose_build_transaction_args(kp_caller))
            receipt2 = self.send_and_check_tx(tx2, kp_caller)

            result2 = contract.functions.timeLockedOperation(
                future_unlock, test_amount
            ).call()
            future_test_success = True
        except Exception:
            # Expected to fail or return false
            result2 = (0, current_time, False)
            future_test_success = False
            receipt2 = {"status": 0, "gasUsed": 0}

        # Test 3: Edge case - unlock time exactly now
        now_unlock = current_time
        tx3 = contract.functions.timeLockedOperation(
            now_unlock, test_amount
        ).build_transaction(self.compose_build_transaction_args(kp_caller))
        receipt3 = self.send_and_check_tx(tx3, kp_caller)

        result3 = contract.functions.timeLockedOperation(
            now_unlock, test_amount
        ).call()

        return {
            "time_locked_success": receipt1["status"] == 1 and receipt3["status"] == 1,
            "past_unlock_test": {
                "success": result1[2],
                "result": result1[0],
                "execution_time": result1[1],
                "has_time_bonus": result1[0] >= test_amount,
                "gas_used": receipt1.get("gasUsed", 0)
            },
            "future_unlock_test": {
                "success": result2[2],
                "result": result2[0],
                "execution_time": result2[1],
                "correctly_failed": not result2[2],
                "gas_used": receipt2.get("gasUsed", 0)
            },
            "edge_case_test": {
                "success": result3[2],
                "result": result3[0],
                "execution_time": result3[1],
                "gas_used": receipt3.get("gasUsed", 0)
            },
            "timestamp_dependency_working": result1[2] and not result2[2] and result3[2],
            "time_calculations_correct": result1[0] >= test_amount,
        }

    @log_func
    def block_dependent_tests(self, kp_caller):
        """Test block number dependent operations"""
        contract = self._get_contract()

        current_block = self._w3.eth.block_number
        test_data = Web3.to_bytes(text="block_dependent_test_data")

        # Test 1: Target block in past (should be ready)
        past_block = current_block - 5
        tx1 = contract.functions.blockNumberDependentOperation(
            past_block, test_data
        ).build_transaction(self.compose_build_transaction_args(kp_caller))
        receipt1 = self.send_and_check_tx(tx1, kp_caller)

        result1 = contract.functions.blockNumberDependentOperation(
            past_block, test_data
        ).call()

        # Test 2: Target block in future (should not be ready)
        future_block = current_block + 100
        tx2 = contract.functions.blockNumberDependentOperation(
            future_block, test_data
        ).build_transaction(self.compose_build_transaction_args(kp_caller))
        receipt2 = self.send_and_check_tx(tx2, kp_caller)

        result2 = contract.functions.blockNumberDependentOperation(
            future_block, test_data
        ).call()

        # Test 3: Current block (edge case)
        current_block_updated = self._w3.eth.block_number  # Get fresh block number
        tx3 = contract.functions.blockNumberDependentOperation(
            current_block_updated, test_data
        ).build_transaction(self.compose_build_transaction_args(kp_caller))
        receipt3 = self.send_and_check_tx(tx3, kp_caller)

        result3 = contract.functions.blockNumberDependentOperation(
            current_block_updated, test_data
        ).call()

        return {
            "block_dependent_success": receipt1["status"] == 1 and receipt2["status"] == 1 and receipt3["status"] == 1,
            "past_block_test": {
                "current_block": result1[0],
                "is_ready": result1[1],
                "data_hash": Web3.to_hex(result1[2]),
                "correctly_ready": result1[1] == True,
                "gas_used": receipt1.get("gasUsed", 0)
            },
            "future_block_test": {
                "current_block": result2[0],
                "is_ready": result2[1],
                "data_hash": Web3.to_hex(result2[2]),
                "correctly_not_ready": result2[1] == False,
                "gas_used": receipt2.get("gasUsed", 0)
            },
            "current_block_test": {
                "current_block": result3[0],
                "is_ready": result3[1],
                "data_hash": Web3.to_hex(result3[2]),
                "gas_used": receipt3.get("gasUsed", 0)
            },
            "block_number_dependency_working": result1[1] and not result2[1],
            "data_hash_consistent": result1[2] == result2[2] == result3[2],
        }

    def migration_same_behavior(self, args):
        """Execute all chain info dependency test scenarios"""
        results = {}

        # Execute chain metadata tests
        if args["chain_metadata_tests"]:
            results["chain_metadata_tests"] = self.chain_metadata_tests(*args["chain_metadata_tests"])

        # Execute time locked tests
        if args["time_locked_tests"]:
            results["time_locked_tests"] = self.time_locked_tests(*args["time_locked_tests"])

        # Execute block dependent tests
        if args["block_dependent_tests"]:
            results["block_dependent_tests"] = self.block_dependent_tests(*args["block_dependent_tests"])

        return results
