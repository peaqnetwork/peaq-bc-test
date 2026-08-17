from tests.evm_sc.base import SmartContractBehavior, log_func
from tools.peaq_eth_utils import get_eth_info
from web3 import Web3


class StorageTestSCBehavior(SmartContractBehavior):
    def __init__(self, unittest, w3, kp_deployer):
        super().__init__(unittest, "ETH/storagetest", w3, kp_deployer)

        # Storage layout constants for verification
        self._expected_storage = {
            0: 0x1111111111111111111111111111111111111111111111111111111111111111,
            1: int("0x2222222222222222222222222222222222222222", 16),  # address as uint256
            2: 1,  # bool true
            3: 0x3333333333333333333333333333333333333333333333333333333333333333,
            # slot 4 has packed values
            5: 2,  # dynamic array length
        }

        # Test addresses for mapping operations
        self._test_addresses = [
            "0x8888888888888888888888888888888888888888",
            "0xAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAa",
            "0xbBbBBBBbbBBBbbbBbbBbbbbBBbBbbbbBbBbbBBbB",
            "0xCcCCccccCCCCcCCCCCCcCcCccCcCCCcCcccccccC",
        ]

    @log_func
    def deploy(self, deploy_args=None):
        super().deploy(deploy_args)

    def compose_all_args(self):
        self._args = {
            "pre": {
                "basic_storage_tests": [get_eth_info()],
                "assembly_storage_tests": [get_eth_info()],
                "complex_storage_tests": [get_eth_info()],
                "mapping_storage_tests": [get_eth_info()],
                "packed_storage_tests": [get_eth_info()],
                "integrity_tests": [],
            },
            "after": {
                "basic_storage_tests": [get_eth_info()],
                "assembly_storage_tests": [get_eth_info()],
                "complex_storage_tests": [get_eth_info()],
                "mapping_storage_tests": [get_eth_info()],
                "packed_storage_tests": [get_eth_info()],
                "integrity_tests": [],
            },
        }

    def get_fund_ss58_keys(self):
        """Get the ss58 keys for funding"""
        return [self._kp_deployer["substrate"]] + [
            kp["substrate"]
            for action_type in ["pre", "after"]
            for test_type in ["basic_storage_tests", "assembly_storage_tests", "complex_storage_tests",
                              "mapping_storage_tests", "packed_storage_tests"]
            for kp in self._args[action_type][test_type]
        ]

    @log_func
    def basic_storage_tests(self, kp_caller):
        """Test basic storage slot read/write operations"""
        contract = self._get_contract()

        # Test reading initial storage values
        initial_snapshot = contract.functions.getStorageSnapshot().call()

        # Test reading individual slots
        slot_values = {}
        for slot in range(10):
            value = contract.functions.readStorageSlot(slot).call()
            slot_values[slot] = value

        # Test writing to storage slots
        test_value = 0xFEEDBEEFCAFEBABEDEADBEEFBADC0DEFEEDFACE123456789ABCDEF0123456789
        test_value_hex = Web3.to_hex(test_value).ljust(66, '0')  # Pad to 32 bytes (66 chars with 0x)
        tx = contract.functions.writeStorageSlot(0, test_value_hex).build_transaction(
            self.compose_build_transaction_args(kp_caller)
        )
        receipt = self.send_and_check_tx(tx, kp_caller)

        # Verify the write
        new_value = contract.functions.readStorageSlot(0).call()

        # Restore original value
        original_value_hex = Web3.to_hex(self._expected_storage[0]).ljust(66, '0')
        tx_restore = contract.functions.writeStorageSlot(0, original_value_hex).build_transaction(
            self.compose_build_transaction_args(kp_caller)
        )
        self.send_and_check_tx(tx_restore, kp_caller)

        return {
            "initial_snapshot": [Web3.to_hex(val) for val in initial_snapshot],
            "slot_values": {k: Web3.to_hex(v) for k, v in slot_values.items()},
            "write_success": receipt["status"] == 1,
            "write_verification": Web3.to_hex(new_value),
            "expected_write_value": hex(test_value),
            "write_correct": Web3.to_hex(new_value) == test_value_hex,
        }

    @log_func
    def assembly_storage_tests(self, kp_caller):
        """Test assembly-based storage operations"""
        contract = self._get_contract()

        # Test range reading
        range_values = contract.functions.readStorageRange(0, 5).call()

        # Test packed value operations
        packed_values = contract.functions.readPackedValues().call()
        lower_before = packed_values[0]
        upper_before = packed_values[1]

        # Modify packed values
        new_lower = 0x11111111111111111111111111111111
        new_upper = 0x22222222222222222222222222222222

        tx_packed = contract.functions.writePackedValues(new_lower, new_upper).build_transaction(
            self.compose_build_transaction_args(kp_caller)
        )
        receipt_packed = self.send_and_check_tx(tx_packed, kp_caller)

        # Verify packed write
        packed_after = contract.functions.readPackedValues().call()

        # Restore original packed values
        tx_restore = contract.functions.writePackedValues(
            0x44444444444444444444444444444444,
            0x55555555555555555555555555555555
        ).build_transaction(self.compose_build_transaction_args(kp_caller))
        self.send_and_check_tx(tx_restore, kp_caller)

        return {
            "range_read_success": len(range_values) == 5,
            "range_values": [Web3.to_hex(val) for val in range_values],
            "packed_before": [Web3.to_hex(lower_before), Web3.to_hex(upper_before)],
            "packed_after": [Web3.to_hex(packed_after[0]), Web3.to_hex(packed_after[1])],
            "packed_write_success": receipt_packed["status"] == 1,
            "packed_values_correct": (
                packed_after[0] == new_lower and packed_after[1] == new_upper
            ),
        }

    @log_func
    def complex_storage_tests(self, kp_caller):
        """Test complex storage patterns and calculations"""
        contract = self._get_contract()

        # Test array slot calculation and access
        array_slot_0 = contract.functions.getArraySlot(5, 0).call()
        array_slot_1 = contract.functions.getArraySlot(5, 1).call()

        # Read array elements manually
        array_elem_0 = contract.functions.readArrayElement(0).call()
        array_elem_1 = contract.functions.readArrayElement(1).call()

        # Test mapping slot calculation
        test_addr = self._test_addresses[0]
        # Convert address to bytes32 (pad with zeros on the left)
        addr_bytes32 = Web3.to_bytes(hexstr=test_addr).rjust(32, b'\x00')
        mapping_slot = contract.functions.getMappingSlot(
            addr_bytes32, 6
        ).call()

        # Read mapping value manually
        mapping_value = contract.functions.readMappingValue(Web3.to_checksum_address(test_addr)).call()

        # Test nested mapping slot calculation
        key1_bytes32 = Web3.to_bytes(123).rjust(32, b'\x00')  # uint256 123 as bytes32
        key2_bytes32 = Web3.to_bytes(hexstr=self._test_addresses[3]).rjust(32, b'\x00')  # address as bytes32
        nested_slot = contract.functions.getNestedMappingSlot(
            key1_bytes32,
            key2_bytes32,
            9  # nestedMapping slot
        ).call()

        # Test complex storage operations
        tx_complex = contract.functions.complexStorageTest(3).build_transaction(
            self.compose_build_transaction_args(kp_caller)
        )
        receipt_complex = self.send_and_check_tx(tx_complex, kp_caller)

        return {
            "array_slot_calculations": [Web3.to_hex(array_slot_0), Web3.to_hex(array_slot_1)],
            "array_elements": [Web3.to_hex(array_elem_0), Web3.to_hex(array_elem_1)],
            "mapping_slot": Web3.to_hex(mapping_slot),
            "mapping_value": Web3.to_hex(mapping_value),
            "nested_mapping_slot": Web3.to_hex(nested_slot),
            "complex_operations_success": receipt_complex["status"] == 1,
            "slot_calculations_valid": array_slot_0 != array_slot_1,
        }

    @log_func
    def mapping_storage_tests(self, kp_caller):
        """Test mapping storage operations"""
        contract = self._get_contract()

        results = {}

        # Test mapping operations for multiple addresses
        for i, addr in enumerate(self._test_addresses[:3]):
            test_value = 0x1000 + i * 0x1000

            # Convert string address to Web3 address format
            addr_checksum = Web3.to_checksum_address(addr)

            # Write mapping value
            tx_write = contract.functions.writeMappingValue(addr_checksum, test_value).build_transaction(
                self.compose_build_transaction_args(kp_caller)
            )
            receipt_write = self.send_and_check_tx(tx_write, kp_caller)

            # Read mapping value back
            read_value = contract.functions.readMappingValue(addr_checksum).call()

            # Also test via standard mapping access
            standard_value = contract.functions.addressToValue(addr_checksum).call()

            results[f"mapping_{i}"] = {
                "address": addr,
                "write_success": receipt_write["status"] == 1,
                "test_value": Web3.to_hex(test_value),
                "read_value": Web3.to_hex(read_value),
                "standard_value": Web3.to_hex(standard_value),
                "values_match": read_value == test_value == standard_value,
            }

        return results

    @log_func
    def packed_storage_tests(self, kp_caller):
        """Test packed storage layout integrity"""
        contract = self._get_contract()

        # Get initial packed values
        initial_packed = contract.functions.readPackedValues().call()

        # Test various packed value combinations
        test_cases = [
            (0x12345678, 0x87654321),
            (0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF, 0x0),
            (0x0, 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF),
            (0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAA, 0x55555555555555555555555555555555),
        ]

        results = []
        for i, (lower, upper) in enumerate(test_cases):
            # Write packed values
            tx_write = contract.functions.writePackedValues(lower, upper).build_transaction(
                self.compose_build_transaction_args(kp_caller)
            )
            receipt_write = self.send_and_check_tx(tx_write, kp_caller)

            # Read back
            read_packed = contract.functions.readPackedValues().call()

            # Verify via manual slot reading
            slot4_raw = contract.functions.readStorageSlot(4).call()
            slot4_int = int.from_bytes(slot4_raw, byteorder='big')
            manual_lower = slot4_int & 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
            manual_upper = (slot4_int >> 128) & 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF

            results.append({
                "test_case": i,
                "input_lower": Web3.to_hex(lower),
                "input_upper": Web3.to_hex(upper),
                "read_lower": Web3.to_hex(read_packed[0]),
                "read_upper": Web3.to_hex(read_packed[1]),
                "manual_lower": Web3.to_hex(manual_lower),
                "manual_upper": Web3.to_hex(manual_upper),
                "write_success": receipt_write["status"] == 1,
                "values_correct": (
                    read_packed[0] == lower and read_packed[1] == upper and
                    manual_lower == lower and manual_upper == upper
                ),
            })

        # Restore original packed values
        tx_restore = contract.functions.writePackedValues(
            initial_packed[0], initial_packed[1]
        ).build_transaction(self.compose_build_transaction_args(kp_caller))
        self.send_and_check_tx(tx_restore, kp_caller)

        return {
            "initial_packed": [Web3.to_hex(val) for val in initial_packed],
            "test_results": results,
            "all_tests_passed": all(result["values_correct"] for result in results),
        }

    @log_func
    def integrity_tests(self):
        """Test storage layout integrity and comprehensive state verification"""
        contract = self._get_contract()

        # Verify storage integrity
        integrity_check = contract.functions.verifyStorageIntegrity().call()

        # Get comprehensive storage state
        storage_state = contract.functions.getStorageState().call()

        # Get array elements individually to avoid memory allocation issues
        array_length = storage_state[1]
        array_elements = []
        for i in range(min(array_length, 5)):  # Limit to first 5 elements to avoid memory issues
            try:
                element = contract.functions.dynamicArray(i).call()
                array_elements.append(element)
            except Exception:
                break  # Stop if we can't read more elements

        # Get detailed snapshot
        storage_snapshot = contract.functions.getStorageSnapshot().call()

        # Emit storage snapshot event for event log verification
        tx_snapshot = contract.functions.emitStorageSnapshot().build_transaction(
            self.compose_build_transaction_args(self._kp_deployer)
        )
        receipt_snapshot = self.send_and_check_tx(tx_snapshot, self._kp_deployer)

        return {
            "integrity_check_passed": integrity_check,
            "storage_snapshot": [Web3.to_hex(val) for val in storage_snapshot],
            "storage_state": {
                "basic_slots": [Web3.to_hex(val) for val in storage_state[0]],
                "array_length": storage_state[1],
                "array_elements": [Web3.to_hex(val) for val in array_elements],
                "mapping_test_value": Web3.to_hex(storage_state[2]),
                "string_value": storage_state[3],
            },
            "snapshot_event_success": receipt_snapshot["status"] == 1,
            "comprehensive_state_valid": (
                integrity_check and
                storage_state[1] >= 0 and  # array length valid
                len(storage_state[3]) > 0   # string not empty
            ),
        }

    def migration_same_behavior(self, args):
        """Execute all storage test scenarios"""
        results = {}

        # Execute basic storage tests
        if args["basic_storage_tests"]:
            results["basic_storage_tests"] = self.basic_storage_tests(*args["basic_storage_tests"])

        # Execute assembly storage tests
        if args["assembly_storage_tests"]:
            results["assembly_storage_tests"] = self.assembly_storage_tests(*args["assembly_storage_tests"])

        # Execute complex storage tests
        if args["complex_storage_tests"]:
            results["complex_storage_tests"] = self.complex_storage_tests(*args["complex_storage_tests"])

        # Execute mapping storage tests
        if args["mapping_storage_tests"]:
            results["mapping_storage_tests"] = self.mapping_storage_tests(*args["mapping_storage_tests"])

        # Execute packed storage tests
        if args["packed_storage_tests"]:
            results["packed_storage_tests"] = self.packed_storage_tests(*args["packed_storage_tests"])

        # Execute integrity tests (no args needed)
        results["integrity_tests"] = self.integrity_tests()

        return results
