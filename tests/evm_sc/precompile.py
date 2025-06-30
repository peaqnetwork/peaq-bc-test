from tests.evm_sc.base import SmartContractBehavior, log_func
from tools.peaq_eth_utils import get_eth_info
from web3 import Web3
import hashlib


class PrecompileTestSCBehavior(SmartContractBehavior):
    def __init__(self, unittest, w3, kp_deployer):
        super().__init__(unittest, "ETH/precompile", w3, kp_deployer)
        
        # Known test vectors for verification
        self._test_vectors = {
            "ecrecover": {
                "hash": "0x456e9aea5e197a1f1af7a3e85a3212fa4049a3ba34c2289b4c860fc0b0c64ef3",
                "v": 28,
                "r": "0x9242685bf161793cc25603c231bc2f568eb630ea16aa137d2664ac8038825608",
                "s": "0x4f8ae3bd7535248d0bd448298cc2e2071e56992d0774dc340c368ae950852ada",
                "expected": "0x7156526fbd7a3c72969b54f64e42c10fbb768c8a"
            },
            "sha256": {
                "input": b"Hello, World!",
                "expected": "0xdffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
            },
            "ripemd160": {
                "input": b"Hello, World!", 
                "expected": "0x527a6a4b9a6da75607546842e0e00105350b1aaf"
            },
            "identity": {
                "input": b"Test identity precompile function",
            },
            "modexp": {
                "base": 3,
                "exp": 2,
                "mod": 5,
                "expected": 4  # (3^2) % 5 = 9 % 5 = 4
            }
        }

    @log_func
    def deploy(self, deploy_args=None):
        super().deploy(deploy_args)

    def compose_all_args(self):
        self._args = {
            "pre": {
                "ecrecover_tests": [get_eth_info()],
                "hash_precompile_tests": [get_eth_info()],
                "modexp_tests": [get_eth_info()],
                "elliptic_curve_tests": [get_eth_info()],
                "comprehensive_tests": [],
            },
            "after": {
                "ecrecover_tests": [get_eth_info()],
                "hash_precompile_tests": [get_eth_info()],
                "modexp_tests": [get_eth_info()],
                "elliptic_curve_tests": [get_eth_info()],
                "comprehensive_tests": [],
            },
        }

    def get_fund_ss58_keys(self):
        """Get the ss58 keys for funding"""
        return [self._kp_deployer["substrate"]] + [
            kp["substrate"]
            for action_type in ["pre", "after"]
            for test_type in ["ecrecover_tests", "hash_precompile_tests", "modexp_tests", "elliptic_curve_tests"]
            for kp in self._args[action_type][test_type]
        ]

    @log_func
    def ecrecover_tests(self, kp_caller):
        """Test ecrecover precompile functionality"""
        contract = self._get_contract()
        
        # Test with known vector
        vector = self._test_vectors["ecrecover"]
        tx = contract.functions.testEcrecover(
            Web3.to_bytes(hexstr=vector["hash"]),
            vector["v"],
            Web3.to_bytes(hexstr=vector["r"]),
            Web3.to_bytes(hexstr=vector["s"])
        ).build_transaction(self.compose_build_transaction_args(kp_caller))
        
        receipt = self.send_and_check_tx(tx, kp_caller)
        
        # Get function result from call
        result = contract.functions.testEcrecover(
            Web3.to_bytes(hexstr=vector["hash"]),
            vector["v"],
            Web3.to_bytes(hexstr=vector["r"]),
            Web3.to_bytes(hexstr=vector["s"])
        ).call()
        
        recovered_address = result[0]
        success = result[1]
        
        # Verify against expected result
        expected_address = Web3.to_checksum_address(vector["expected"])
        address_correct = recovered_address.lower() == expected_address.lower()
        
        # Test with invalid signature (should return zero address)
        invalid_result = contract.functions.testEcrecover(
            Web3.to_bytes(hexstr=vector["hash"]),
            29,  # Invalid v value
            Web3.to_bytes(hexstr=vector["r"]),
            Web3.to_bytes(hexstr=vector["s"])
        ).call()
        
        invalid_recovered = invalid_result[0]
        
        return {
            "transaction_success": receipt["status"] == 1,
            "precompile_success": success,
            "recovered_address": recovered_address,
            "expected_address": expected_address,
            "address_correct": address_correct,
            "invalid_signature_test": invalid_recovered == "0x0000000000000000000000000000000000000000",
            "test_success": success and address_correct,
        }

    @log_func
    def hash_precompile_tests(self, kp_caller):
        """Test hash precompiles (SHA256, RIPEMD160, Identity)"""
        contract = self._get_contract()
        results = {}
        
        # Test SHA256
        sha256_vector = self._test_vectors["sha256"]
        sha256_result = contract.functions.testSha256(sha256_vector["input"]).call()
        sha256_hash = Web3.to_hex(sha256_result[0])
        sha256_success = sha256_result[1]
        
        # Verify with Python hashlib
        expected_sha256 = "0x" + hashlib.sha256(sha256_vector["input"]).hexdigest()
        sha256_correct = sha256_hash.lower() == expected_sha256.lower()
        
        results["sha256"] = {
            "precompile_success": sha256_success,
            "hash_result": sha256_hash,
            "expected_hash": expected_sha256,
            "hash_correct": sha256_correct,
            "test_success": sha256_success and sha256_correct,
        }
        
        # Test RIPEMD160
        ripemd_vector = self._test_vectors["ripemd160"]
        ripemd_result = contract.functions.testRipemd160(ripemd_vector["input"]).call()
        ripemd_hash = Web3.to_hex(ripemd_result[0])
        ripemd_success = ripemd_result[1]
        
        results["ripemd160"] = {
            "precompile_success": ripemd_success,
            "hash_result": ripemd_hash,
            "expected_hash": ripemd_vector["expected"],
            "hash_correct": ripemd_hash.lower() == ripemd_vector["expected"].lower(),
            "test_success": ripemd_success,
        }
        
        # Test Identity precompile
        identity_vector = self._test_vectors["identity"]
        identity_result = contract.functions.testIdentity(identity_vector["input"]).call()
        identity_output = identity_result[0]
        identity_success = identity_result[1]
        
        # Verify output matches input
        identity_correct = identity_output == identity_vector["input"]
        
        results["identity"] = {
            "precompile_success": identity_success,
            "input_data": Web3.to_hex(identity_vector["input"]),
            "output_data": Web3.to_hex(identity_output),
            "data_matches": identity_correct,
            "test_success": identity_success and identity_correct,
        }
        
        return results

    @log_func
    def modexp_tests(self, kp_caller):
        """Test modular exponentiation precompile"""
        contract = self._get_contract()
        
        vector = self._test_vectors["modexp"]
        
        # Prepare input as bytes
        base_bytes = vector["base"].to_bytes(32, byteorder='big')
        exp_bytes = vector["exp"].to_bytes(32, byteorder='big')
        mod_bytes = vector["mod"].to_bytes(32, byteorder='big')
        
        # Test modexp
        tx = contract.functions.testModExp(base_bytes, exp_bytes, mod_bytes).build_transaction(
            self.compose_build_transaction_args(kp_caller)
        )
        receipt = self.send_and_check_tx(tx, kp_caller)
        
        # Get result
        result = contract.functions.testModExp(base_bytes, exp_bytes, mod_bytes).call()
        modexp_output = result[0]
        modexp_success = result[1]
        
        # Convert result to integer for verification
        result_int = int.from_bytes(modexp_output, byteorder='big')
        
        # Verify against expected result
        expected_result = vector["expected"]
        result_correct = result_int == expected_result
        
        return {
            "transaction_success": receipt["status"] == 1,
            "precompile_success": modexp_success,
            "input_base": vector["base"],
            "input_exp": vector["exp"],
            "input_mod": vector["mod"],
            "result_value": result_int,
            "expected_value": expected_result,
            "result_correct": result_correct,
            "test_success": modexp_success and result_correct,
        }

    @log_func
    def elliptic_curve_tests(self, kp_caller):
        """Test elliptic curve precompiles (ecAdd, ecMul)"""
        contract = self._get_contract()
        results = {}
        
        # Test ecAdd with generator point + generator point
        # BN254 generator point
        g_x = 1
        g_y = 2
        
        # Test G + G = 2G
        ecadd_result = contract.functions.testEcAdd(g_x, g_y, g_x, g_y).call()
        ecadd_point = ecadd_result[0]
        ecadd_success = ecadd_result[1]
        
        results["ecadd"] = {
            "precompile_success": ecadd_success,
            "input_point1": [g_x, g_y],
            "input_point2": [g_x, g_y],
            "result_point": [ecadd_point[0], ecadd_point[1]],
            "test_success": ecadd_success,
        }
        
        # Test ecMul with generator point * 2
        ecmul_result = contract.functions.testEcMul(g_x, g_y, 2).call()
        ecmul_point = ecmul_result[0]
        ecmul_success = ecmul_result[1]
        
        # Verify ecAdd result matches ecMul result (G + G should equal G * 2)
        points_match = (ecadd_point[0] == ecmul_point[0] and ecadd_point[1] == ecmul_point[1])
        
        results["ecmul"] = {
            "precompile_success": ecmul_success,
            "input_point": [g_x, g_y],
            "input_scalar": 2,
            "result_point": [ecmul_point[0], ecmul_point[1]],
            "matches_ecadd": points_match,
            "test_success": ecmul_success and points_match,
        }
        
        return results

    @log_func
    def comprehensive_tests(self):
        """Run comprehensive precompile tests with known vectors"""
        contract = self._get_contract()
        
        # Run comprehensive test function
        comprehensive_result = contract.functions.runComprehensiveTests().call()
        
        # Get all test results
        all_results = contract.functions.getAllTestResults().call()
        
        # Get individual test success status
        test_statuses = {}
        test_names = ["ecrecover", "sha256", "ripemd160", "identity", "modexp"]
        
        for test_name in test_names:
            test_statuses[test_name] = contract.functions.getTestSuccess(test_name).call()
        
        return {
            "comprehensive_test_passed": comprehensive_result,
            "all_precompiles_success": all_results[5],
            "individual_test_results": {
                "ecrecover_result": Web3.to_hex(all_results[0]) if all_results[0] else "0x",
                "sha256_result": Web3.to_hex(all_results[1]) if all_results[1] else "0x",
                "ripemd160_result": Web3.to_hex(all_results[2]) if all_results[2] else "0x", 
                "identity_result": Web3.to_hex(all_results[3]) if all_results[3] else "0x",
                "modexp_result": Web3.to_hex(all_results[4]) if all_results[4] else "0x",
            },
            "individual_test_success": test_statuses,
            "all_tests_consistent": comprehensive_result and all_results[5],
        }


    def migration_same_behavior(self, args):
        """Execute all precompile test scenarios"""
        results = {}
        
        # Execute ecrecover tests
        if args["ecrecover_tests"]:
            results["ecrecover_tests"] = self.ecrecover_tests(*args["ecrecover_tests"])
        
        # Execute hash precompile tests
        if args["hash_precompile_tests"]:
            results["hash_precompile_tests"] = self.hash_precompile_tests(*args["hash_precompile_tests"])
        
        # Execute modexp tests
        if args["modexp_tests"]:
            results["modexp_tests"] = self.modexp_tests(*args["modexp_tests"])
        
        # Execute elliptic curve tests
        if args["elliptic_curve_tests"]:
            results["elliptic_curve_tests"] = self.elliptic_curve_tests(*args["elliptic_curve_tests"])
        
        # Execute comprehensive tests (no args needed)
        results["comprehensive_tests"] = self.comprehensive_tests()
        
        return results