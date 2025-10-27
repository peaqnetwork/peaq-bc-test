// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

/**
 * @title ManualStorageTest
 * @dev Contract for testing manual storage access and layout integrity
 * Tests assembly-based storage manipulation and verifies storage layout
 * remains intact across runtime upgrades
 */
contract ManualStorageTest {
    // Standard storage variables (slots 0-9)
    uint256 public slot0Value;           // slot 0
    address public slot1Address;        // slot 1  
    bool public slot2Bool;              // slot 2
    bytes32 public slot3Bytes32;        // slot 3
    uint128 public slot4Lower;          // slot 4 (lower 16 bytes)
    uint128 public slot4Upper;          // slot 4 (upper 16 bytes) - packed
    
    // Array storage (slot 5)
    uint256[] public dynamicArray;      // slot 5 (length), keccak256(5) + index (elements)
    
    // Mapping storage (slot 6)
    mapping(address => uint256) public addressToValue;  // slot 6, keccak256(key . 6) (values)
    
    // String storage (slot 7)
    string public dynamicString;        // slot 7
    
    // Struct storage (slot 8)
    struct StorageStruct {
        uint256 value;
        address addr;
        bool flag;
    }
    StorageStruct public slot8Struct;   // slot 8-9 (multiple slots)
    
    // Nested mapping (slot 9)
    mapping(uint256 => mapping(address => uint256)) public nestedMapping;
    
    // Events for tracking storage operations
    event StorageRead(uint256 slot, bytes32 value);
    event StorageWrite(uint256 slot, bytes32 oldValue, bytes32 newValue);
    event StorageLayoutSnapshot(bytes32[10] slots);
    
    constructor() {
        // Initialize with known values for testing
        slot0Value = 0x1111111111111111111111111111111111111111111111111111111111111111;
        slot1Address = address(0x2222222222222222222222222222222222222222);
        slot2Bool = true;
        slot3Bytes32 = 0x3333333333333333333333333333333333333333333333333333333333333333;
        slot4Lower = 0x44444444444444444444444444444444;
        slot4Upper = 0x55555555555555555555555555555555;
        
        // Initialize dynamic data
        dynamicArray.push(0x6666666666666666666666666666666666666666666666666666666666666666);
        dynamicArray.push(0x7777777777777777777777777777777777777777777777777777777777777777);
        
        addressToValue[address(0x8888888888888888888888888888888888888888)] = 0x9999999999999999999999999999999999999999999999999999999999999999;
        
        dynamicString = "Storage Layout Test String";
        
        slot8Struct = StorageStruct({
            value: 0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA,
            addr: address(0xbBbBBBBbbBBBbbbBbbBbbbbBBbBbbbbBbBbbBBbB),
            flag: true
        });
        
        nestedMapping[123][address(0xCcCCccccCCCCcCCCCCCcCcCccCcCCCcCcccccccC)] = 0xDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD;
    }
    
    /**
     * @dev Read raw storage value from a specific slot using assembly
     */
    function readStorageSlot(uint256 slot) external view returns (bytes32 value) {
        assembly {
            value := sload(slot)
        }
        return value;
    }
    
    /**
     * @dev Write raw value to a specific storage slot using assembly
     */
    function writeStorageSlot(uint256 slot, bytes32 value) external {
        bytes32 oldValue;
        assembly {
            oldValue := sload(slot)
            sstore(slot, value)
        }
        emit StorageWrite(slot, oldValue, value);
    }
    
    /**
     * @dev Read multiple storage slots at once
     */
    function readStorageRange(uint256 startSlot, uint256 count) external view returns (bytes32[] memory values) {
        values = new bytes32[](count);
        for (uint256 i = 0; i < count; i++) {
            uint256 slot = startSlot + i;
            assembly {
                let value := sload(slot)
                mstore(add(add(values, 0x20), mul(i, 0x20)), value)
            }
        }
        return values;
    }
    
    /**
     * @dev Get storage layout snapshot for the first 10 slots
     */
    function getStorageSnapshot() public view returns (bytes32[10] memory snapshot) {
        for (uint256 i = 0; i < 10; i++) {
            assembly {
                let value := sload(i)
                mstore(add(add(snapshot, 0x20), mul(i, 0x20)), value)
            }
        }
        return snapshot;
    }
    
    /**
     * @dev Emit storage layout snapshot event
     */
    function emitStorageSnapshot() external {
        bytes32[10] memory snapshot = getStorageSnapshot();
        emit StorageLayoutSnapshot(snapshot);
    }
    
    /**
     * @dev Calculate storage slot for array element
     */
    function getArraySlot(uint256 arraySlot, uint256 index) public pure returns (uint256 slot) {
        return uint256(keccak256(abi.encode(arraySlot))) + index;
    }
    
    /**
     * @dev Calculate storage slot for mapping value
     */
    function getMappingSlot(bytes32 key, uint256 mapSlot) public pure returns (uint256 slot) {
        return uint256(keccak256(abi.encode(key, mapSlot)));
    }
    
    /**
     * @dev Calculate storage slot for nested mapping value
     */
    function getNestedMappingSlot(bytes32 key1, bytes32 key2, uint256 mapSlot) public pure returns (uint256 slot) {
        uint256 innerMapSlot = uint256(keccak256(abi.encode(key1, mapSlot)));
        return uint256(keccak256(abi.encode(key2, innerMapSlot)));
    }
    
    /**
     * @dev Read array element using manual storage access
     */
    function readArrayElement(uint256 index) external view returns (uint256 value) {
        uint256 slot = getArraySlot(5, index); // slot 5 is dynamicArray
        assembly {
            value := sload(slot)
        }
        return value;
    }
    
    /**
     * @dev Write array element using manual storage access
     */
    function writeArrayElement(uint256 index, uint256 value) external {
        uint256 slot = getArraySlot(5, index);
        assembly {
            sstore(slot, value)
        }
    }
    
    /**
     * @dev Read mapping value using manual storage access
     */
    function readMappingValue(address key) external view returns (uint256 value) {
        uint256 slot = getMappingSlot(bytes32(uint256(uint160(key))), 6); // slot 6 is addressToValue
        assembly {
            value := sload(slot)
        }
        return value;
    }
    
    /**
     * @dev Write mapping value using manual storage access
     */
    function writeMappingValue(address key, uint256 value) external {
        uint256 slot = getMappingSlot(bytes32(uint256(uint160(key))), 6);
        assembly {
            sstore(slot, value)
        }
    }
    
    /**
     * @dev Test packed storage manipulation (slot 4)
     */
    function readPackedValues() external view returns (uint128 lower, uint128 upper) {
        bytes32 slot4Data;
        assembly {
            slot4Data := sload(4)
        }
        
        lower = uint128(uint256(slot4Data));
        upper = uint128(uint256(slot4Data >> 128));
        
        return (lower, upper);
    }
    
    /**
     * @dev Write packed values to slot 4
     */
    function writePackedValues(uint128 lower, uint128 upper) external {
        bytes32 oldValue;
        bytes32 newValue = bytes32((uint256(upper) << 128) | uint256(lower));
        
        assembly {
            oldValue := sload(4)
            sstore(4, newValue)
        }
        
        emit StorageWrite(4, oldValue, newValue);
    }
    
    /**
     * @dev Complex storage pattern test - interleaved reads/writes
     */
    function complexStorageTest(uint256 iterations) external {
        for (uint256 i = 0; i < iterations; i++) {
            // Read from multiple slots
            bytes32 val0 = this.readStorageSlot(0);
            bytes32 val1 = this.readStorageSlot(1);
            
            // Manipulate values
            bytes32 newVal0 = bytes32(uint256(val0) + 1);
            bytes32 newVal1 = bytes32(uint256(val1) ^ uint256(val0));
            
            // Write back
            this.writeStorageSlot(0, newVal0);
            this.writeStorageSlot(1, newVal1);
            
            emit StorageRead(i, val0);
        }
    }
    
    /**
     * @dev Verify storage layout integrity by checking all known values
     */
    function verifyStorageIntegrity() external view returns (bool intact) {
        // Check basic slots by reading directly
        bytes32 slot0;
        bytes32 slot1;
        bytes32 slot2;
        bytes32 slot3;
        bytes32 slot5;
        
        assembly {
            slot0 := sload(0)
            slot1 := sload(1)
            slot2 := sload(2)
            slot3 := sload(3)
            slot5 := sload(5)
        }
        
        if (slot0 != bytes32(slot0Value)) return false;
        if (slot1 != bytes32(uint256(uint160(slot1Address)))) return false;
        if (slot2 != bytes32(uint256(slot2Bool ? 1 : 0))) return false;
        if (slot3 != slot3Bytes32) return false;
        
        // Check packed slot by reading directly
        bytes32 slot4Data;
        assembly {
            slot4Data := sload(4)
        }
        uint128 lower = uint128(uint256(slot4Data));
        uint128 upper = uint128(uint256(slot4Data >> 128));
        if (lower != slot4Lower || upper != slot4Upper) return false;
        
        // Check dynamic array length
        if (uint256(slot5) != dynamicArray.length) return false;
        
        return true;
    }
    
    /**
     * @dev Stress test storage operations
     */
    function stressTestStorage(uint256 operations) external {
        for (uint256 i = 0; i < operations; i++) {
            uint256 slot = i % 10; // Cycle through first 10 slots
            bytes32 value = keccak256(abi.encode(i, block.timestamp, msg.sender));
            
            this.writeStorageSlot(slot, value);
            
            // Verify immediately
            bytes32 readBack = this.readStorageSlot(slot);
            require(readBack == value, "Storage integrity check failed");
        }
    }
    
    /**
     * @dev Get basic storage state for comparison (simplified to avoid memory issues)
     */
    function getStorageState() external view returns (
        bytes32[10] memory basicSlots,
        uint256 arrayLength,
        uint256 mappingTestValue,
        string memory stringValue
    ) {
        // Get storage snapshot directly instead of external call
        basicSlots = getStorageSnapshot();
        arrayLength = dynamicArray.length;
        
        mappingTestValue = addressToValue[address(0x8888888888888888888888888888888888888888)];
        stringValue = dynamicString;
        
        return (basicSlots, arrayLength, mappingTestValue, stringValue);
    }
    
    /**
     * @dev Get array elements separately to avoid memory allocation issues
     */
    function getArrayElements() external view returns (uint256[] memory arrayElements) {
        arrayElements = new uint256[](dynamicArray.length);
        for (uint256 i = 0; i < dynamicArray.length; i++) {
            arrayElements[i] = dynamicArray[i];
        }
        return arrayElements;
    }
}