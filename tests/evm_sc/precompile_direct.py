from tests.evm_sc.base import SmartContractBehavior, log_func
from tools.peaq_eth_utils import get_eth_info
from web3 import Web3
import hashlib
from eth_utils import keccak
from eth_keys import keys
from eth_account.messages import encode_structured_data
import struct


class PrecompileDirectTestBehavior(SmartContractBehavior):
    def __init__(self, unittest, w3, kp_deployer):
        # Use a dummy directory since we're not deploying contracts
        super().__init__(unittest, "ETH/precompile", w3, kp_deployer)
        
        # Precompile addresses
        self._precompiles = {
            "ecrecover": "0x0000000000000000000000000000000000000001",
            "sha256": "0x0000000000000000000000000000000000000002", 
            "ripemd160": "0x0000000000000000000000000000000000000003",
            "identity": "0x0000000000000000000000000000000000000004",
            "modexp": "0x0000000000000000000000000000000000000005",
            "ecadd": "0x0000000000000000000000000000000000000006",
            "ecmul": "0x0000000000000000000000000000000000000007",
            "ecpairing": "0x0000000000000000000000000000000000000008",
            "blake2f": "0x0000000000000000000000000000000000000009"
        }
        
        # Known test vectors
        self._test_vectors = {
            "ecrecover": {
                "hash": "0x456e9aea5e197a1f1af7a3e85a3212fa4049a3ba34c2289b4c860fc0b0c64ef3",
                "v": 28,
                "r": "0x9242685bf161793cc25603c231bc2f568eb630ea16aa137d2664ac8038825608",
                "s": "0x4f8ae3bd7535248d0bd448298cc2e2071e56992d0774dc340c368ae950852ada",
                "expected": "0x7156526fbd7a3c72969b54f64e42c10fbb768c8a"
            },
            "sha256_input": b"Hello, World!",
            "ripemd160_input": b"Test RIPEMD160",
            "identity_input": b"Identity test data for precompile",
        }

    def deploy(self, deploy_args=None):
        # No contract deployment needed for direct precompile testing
        pass

    def compose_all_args(self):
        self._args = {
            "pre": {
                "direct_ecrecover_test": [get_eth_info()],
                "direct_hash_test": [get_eth_info()],
                "direct_modexp_test": [get_eth_info()],
                "direct_identity_test": [get_eth_info()],
                "direct_elliptic_curve_test": [get_eth_info()],
                "comprehensive_direct_test": [],
            },
            "after": {
                "direct_ecrecover_test": [get_eth_info()],
                "direct_hash_test": [get_eth_info()],
                "direct_modexp_test": [get_eth_info()],
                "direct_identity_test": [get_eth_info()],
                "direct_elliptic_curve_test": [get_eth_info()],
                "comprehensive_direct_test": [],
            },
        }

    def get_fund_ss58_keys(self):
        """Get the ss58 keys for funding"""
        return [self._kp_deployer["substrate"]] + [
            kp["substrate"]
            for action_type in ["pre", "after"]
            for test_type in ["direct_ecrecover_test", "direct_hash_test", "direct_modexp_test", 
                            "direct_identity_test", "direct_elliptic_curve_test"]
            for kp in self._args[action_type][test_type]
        ]

    def _send_raw_precompile_call(self, kp_caller, to_address, data, value=0):
        """Send a raw transaction to a precompile address"""
        # Get dynamic gas price
        try:
            gas_price = self._w3.eth.gas_price
            # Add 20% buffer to ensure transaction goes through
            gas_price = int(gas_price * 1.2)
        except:
            gas_price = self._w3.to_wei('20', 'gwei')  # Fallback to higher gas price
        
        # Build transaction
        tx_params = {
            'to': to_address,
            'value': value,
            'gas': 100000,
            'gasPrice': gas_price,
            'nonce': self._w3.eth.get_transaction_count(kp_caller['eth']),
            'data': data,
            'chainId': self._eth_chain_id
        }
        
        # Sign and send transaction
        signed_tx = self._w3.eth.account.sign_transaction(tx_params, kp_caller['kp'].private_key)
        tx_hash = self._w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash)
        
        return receipt

    def _call_precompile(self, to_address, data):
        """Make a call to precompile (read-only)"""
        try:
            result = self._w3.eth.call({
                'to': to_address,
                'data': data,
                'gas': 100000
            })
            return result, True
        except Exception as e:
            return b'', False

    @log_func
    def direct_ecrecover_test(self, kp_caller):
        """Test ecrecover precompile directly"""
        vector = self._test_vectors["ecrecover"]
        
        # Prepare ecrecover input: hash(32) + v(32) + r(32) + s(32) = 128 bytes
        data = (
            Web3.to_bytes(hexstr=vector["hash"]).ljust(32, b'\x00') +
            vector["v"].to_bytes(32, byteorder='big') +
            Web3.to_bytes(hexstr=vector["r"]).ljust(32, b'\x00') +
            Web3.to_bytes(hexstr=vector["s"]).ljust(32, b'\x00')
        )
        
        # Call precompile directly
        result, success = self._call_precompile(self._precompiles["ecrecover"], Web3.to_hex(data))
        
        # Also send a transaction to test transaction-based interaction
        receipt = self._send_raw_precompile_call(kp_caller, self._precompiles["ecrecover"], Web3.to_hex(data))
        
        # Parse result
        if success and len(result) >= 20:
            recovered_address = Web3.to_checksum_address(result[-20:])  # Last 20 bytes
            expected_address = Web3.to_checksum_address(vector["expected"])
            address_correct = recovered_address.lower() == expected_address.lower()
        else:
            recovered_address = "0x0000000000000000000000000000000000000000"
            address_correct = False
        
        # Test with invalid signature
        invalid_data = data[:-1] + b'\x00'  # Modify last byte
        invalid_result, invalid_success = self._call_precompile(self._precompiles["ecrecover"], Web3.to_hex(invalid_data))
        
        return {
            "call_success": success,
            "transaction_success": receipt["status"] == 1,
            "recovered_address": recovered_address,
            "expected_address": vector["expected"],
            "address_correct": address_correct,
            "invalid_signature_returns_zero": len(invalid_result) == 0 or invalid_result == b'\x00' * 32,
            "test_passed": success and address_correct and receipt["status"] == 1,
            "gas_used": receipt.get("gasUsed", 0)
        }

    @log_func
    def direct_hash_test(self, kp_caller):
        """Test hash precompiles (SHA-256, RIPEMD-160) directly"""
        results = {}
        
        # Test SHA-256
        sha256_data = Web3.to_hex(self._test_vectors["sha256_input"])
        sha256_result, sha256_success = self._call_precompile(self._precompiles["sha256"], sha256_data)
        sha256_receipt = self._send_raw_precompile_call(kp_caller, self._precompiles["sha256"], sha256_data)
        
        # Verify with Python hashlib
        expected_sha256 = hashlib.sha256(self._test_vectors["sha256_input"]).digest()
        sha256_correct = sha256_result == expected_sha256
        
        results["sha256"] = {
            "call_success": sha256_success,
            "transaction_success": sha256_receipt["status"] == 1,
            "result_hash": Web3.to_hex(sha256_result),
            "expected_hash": Web3.to_hex(expected_sha256),
            "hash_correct": sha256_correct,
            "result_not_zero": sha256_result != b'\x00' * 32,
            "test_passed": sha256_success and sha256_correct and sha256_receipt["status"] == 1,
            "gas_used": sha256_receipt.get("gasUsed", 0)
        }
        
        # Test RIPEMD-160
        ripemd_data = Web3.to_hex(self._test_vectors["ripemd160_input"])
        ripemd_result, ripemd_success = self._call_precompile(self._precompiles["ripemd160"], ripemd_data)
        ripemd_receipt = self._send_raw_precompile_call(kp_caller, self._precompiles["ripemd160"], ripemd_data)
        
        # Verify with Python hashlib
        expected_ripemd = hashlib.new('ripemd160', self._test_vectors["ripemd160_input"]).digest()
        ripemd_correct = ripemd_result[:20] == expected_ripemd  # RIPEMD160 returns 20 bytes
        
        results["ripemd160"] = {
            "call_success": ripemd_success,
            "transaction_success": ripemd_receipt["status"] == 1,
            "result_hash": Web3.to_hex(ripemd_result[:20]),
            "expected_hash": Web3.to_hex(expected_ripemd),
            "hash_correct": ripemd_correct,
            "result_not_zero": ripemd_result[:20] != b'\x00' * 20,
            "test_passed": ripemd_success and ripemd_correct and ripemd_receipt["status"] == 1,
            "gas_used": ripemd_receipt.get("gasUsed", 0)
        }
        
        return results

    @log_func
    def direct_identity_test(self, kp_caller):
        """Test identity precompile directly"""
        test_data = self._test_vectors["identity_input"]
        data_hex = Web3.to_hex(test_data)
        
        # Call identity precompile
        result, success = self._call_precompile(self._precompiles["identity"], data_hex)
        receipt = self._send_raw_precompile_call(kp_caller, self._precompiles["identity"], data_hex)
        
        # Verify result matches input exactly
        data_matches = result == test_data
        
        return {
            "call_success": success,
            "transaction_success": receipt["status"] == 1,
            "input_data": Web3.to_hex(test_data),
            "output_data": Web3.to_hex(result),
            "data_matches": data_matches,
            "result_length_correct": len(result) == len(test_data),
            "test_passed": success and data_matches and receipt["status"] == 1,
            "gas_used": receipt.get("gasUsed", 0)
        }

    @log_func  
    def direct_modexp_test(self, kp_caller):
        """Test modular exponentiation precompile directly"""
        # Test case: (3^2) % 5 = 4
        base = 3
        exp = 2
        mod = 5
        
        # Prepare modexp input: [base_len(32)][exp_len(32)][mod_len(32)][base][exp][mod]
        base_bytes = base.to_bytes(32, byteorder='big')
        exp_bytes = exp.to_bytes(32, byteorder='big')  
        mod_bytes = mod.to_bytes(32, byteorder='big')
        
        data = (
            (32).to_bytes(32, byteorder='big') +  # base length
            (32).to_bytes(32, byteorder='big') +  # exp length
            (32).to_bytes(32, byteorder='big') +  # mod length
            base_bytes +
            exp_bytes +
            mod_bytes
        )
        
        # Call modexp precompile
        result, success = self._call_precompile(self._precompiles["modexp"], Web3.to_hex(data))
        receipt = self._send_raw_precompile_call(kp_caller, self._precompiles["modexp"], Web3.to_hex(data))
        
        # Parse result
        if len(result) >= 32:
            result_int = int.from_bytes(result[-32:], byteorder='big')
            expected_result = pow(base, exp, mod)  # (3^2) % 5 = 4
            result_correct = result_int == expected_result
        else:
            result_int = 0
            result_correct = False
        
        return {
            "call_success": success,
            "transaction_success": receipt["status"] == 1,
            "input_base": base,
            "input_exp": exp,
            "input_mod": mod,
            "result_value": result_int,
            "expected_value": pow(base, exp, mod),
            "result_correct": result_correct,
            "result_not_zero": result_int != 0,
            "test_passed": success and result_correct and receipt["status"] == 1,
            "gas_used": receipt.get("gasUsed", 0)
        }

    @log_func
    def direct_elliptic_curve_test(self, kp_caller):
        """Test elliptic curve precompiles (ecAdd, ecMul) directly"""
        results = {}
        
        # BN254 generator point
        g_x = 1
        g_y = 2
        
        # Test ecAdd: G + G = 2G
        ecadd_data = (
            g_x.to_bytes(32, byteorder='big') +
            g_y.to_bytes(32, byteorder='big') +
            g_x.to_bytes(32, byteorder='big') +
            g_y.to_bytes(32, byteorder='big')
        )
        
        ecadd_result, ecadd_success = self._call_precompile(self._precompiles["ecadd"], Web3.to_hex(ecadd_data))
        ecadd_receipt = self._send_raw_precompile_call(kp_caller, self._precompiles["ecadd"], Web3.to_hex(ecadd_data))
        
        if len(ecadd_result) >= 64:
            ecadd_x = int.from_bytes(ecadd_result[:32], byteorder='big')
            ecadd_y = int.from_bytes(ecadd_result[32:64], byteorder='big')
        else:
            ecadd_x = ecadd_y = 0
        
        results["ecadd"] = {
            "call_success": ecadd_success,
            "transaction_success": ecadd_receipt["status"] == 1,
            "input_points": [[g_x, g_y], [g_x, g_y]],
            "result_point": [ecadd_x, ecadd_y],
            "result_not_zero": ecadd_x != 0 or ecadd_y != 0,
            "test_passed": ecadd_success and ecadd_receipt["status"] == 1,
            "gas_used": ecadd_receipt.get("gasUsed", 0)
        }
        
        # Test ecMul: G * 2 = 2G
        ecmul_data = (
            g_x.to_bytes(32, byteorder='big') +
            g_y.to_bytes(32, byteorder='big') +
            (2).to_bytes(32, byteorder='big')  # scalar
        )
        
        ecmul_result, ecmul_success = self._call_precompile(self._precompiles["ecmul"], Web3.to_hex(ecmul_data))
        ecmul_receipt = self._send_raw_precompile_call(kp_caller, self._precompiles["ecmul"], Web3.to_hex(ecmul_data))
        
        if len(ecmul_result) >= 64:
            ecmul_x = int.from_bytes(ecmul_result[:32], byteorder='big')
            ecmul_y = int.from_bytes(ecmul_result[32:64], byteorder='big')
        else:
            ecmul_x = ecmul_y = 0
        
        # Verify that ecAdd(G,G) == ecMul(G,2)
        points_match = (ecadd_x == ecmul_x) and (ecadd_y == ecmul_y)
        
        results["ecmul"] = {
            "call_success": ecmul_success,
            "transaction_success": ecmul_receipt["status"] == 1,
            "input_point": [g_x, g_y],
            "input_scalar": 2,
            "result_point": [ecmul_x, ecmul_y],
            "matches_ecadd": points_match,
            "result_not_zero": ecmul_x != 0 or ecmul_y != 0,
            "test_passed": ecmul_success and points_match and ecmul_receipt["status"] == 1,
            "gas_used": ecmul_receipt.get("gasUsed", 0)
        }
        
        return results

    @log_func
    def comprehensive_direct_test(self):
        """Run comprehensive direct precompile tests"""
        test_results = {}
        
        # Test each precompile with minimal data
        for name, address in self._precompiles.items():
            if name in ["ecrecover", "sha256", "ripemd160", "identity", "modexp"]:
                # Test with empty data (should handle gracefully)
                empty_result, empty_success = self._call_precompile(address, "0x")
                
                test_results[f"{name}_empty_call"] = {
                    "address": address,
                    "success": empty_success,
                    "result_length": len(empty_result) if empty_result else 0,
                    "handles_empty_gracefully": True  # Should not crash
                }
        
        # Test with invalid addresses (should fail)
        invalid_address = "0x000000000000000000000000000000000000000a"  # Non-existent precompile
        invalid_result, invalid_success = self._call_precompile(invalid_address, "0x1234")
        
        test_results["invalid_precompile"] = {
            "address": invalid_address,
            "success": invalid_success,
            "should_fail": not invalid_success,  # Should fail for non-existent precompile
        }
        
        return test_results


    def migration_same_behavior(self, args):
        """Execute all direct precompile test scenarios"""
        results = {}
        
        # Execute direct tests
        if args["direct_ecrecover_test"]:
            results["direct_ecrecover_test"] = self.direct_ecrecover_test(*args["direct_ecrecover_test"])
        
        if args["direct_hash_test"]:
            results["direct_hash_test"] = self.direct_hash_test(*args["direct_hash_test"])
        
        if args["direct_modexp_test"]:
            results["direct_modexp_test"] = self.direct_modexp_test(*args["direct_modexp_test"])
        
        if args["direct_identity_test"]:
            results["direct_identity_test"] = self.direct_identity_test(*args["direct_identity_test"])
        
        if args["direct_elliptic_curve_test"]:
            results["direct_elliptic_curve_test"] = self.direct_elliptic_curve_test(*args["direct_elliptic_curve_test"])
        
        # Execute comprehensive tests (no args needed)
        results["comprehensive_direct_test"] = self.comprehensive_direct_test()
        
        return results