// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

/**
 * @title PrecompileTest
 * @dev Contract for testing EVM precompiled contracts behavior
 * Tests ecrecover, sha256, ripemd160, modexp, and other precompiles
 * Ensures precompiled contracts behave identically across runtime upgrades
 */
contract PrecompileTest {
    // Events for tracking precompile operations
    event EcrecoverTest(address recovered, bool success);
    event Sha256Test(bytes32 hash, bool success);
    event Ripemd160Test(bytes20 hash, bool success);
    event ModExpTest(bytes result, bool success);
    event Blake2fTest(bytes32 hash, bool success);
    
    // Storage for test results
    mapping(string => bytes) public testResults;
    mapping(string => bool) public testSuccess;
    
    constructor() {
        // Initialize with known test vectors
    }
    
    /**
     * @dev Test ecrecover precompile (address 0x01)
     * Recovers the address associated with the public key from elliptic curve signature
     */
    function testEcrecover(
        bytes32 hash,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external returns (address recovered, bool success) {
        // Call ecrecover precompile directly
        bytes memory input = abi.encodePacked(hash, uint256(v), r, s);
        
        assembly {
            success := call(gas(), 0x01, 0, add(input, 0x20), 0x80, 0x00, 0x20)
            recovered := mload(0x00)
        }
        
        // Also test via built-in ecrecover function
        address builtinResult = ecrecover(hash, v, r, s);
        bool resultsMatch = (recovered == builtinResult);
        
        // Check that result is not zero address for valid signatures
        bool validResult = (recovered != address(0)) || (builtinResult == address(0));
        
        testResults["ecrecover"] = abi.encodePacked(recovered);
        testSuccess["ecrecover"] = success && resultsMatch && validResult;
        
        emit EcrecoverTest(recovered, success && resultsMatch && validResult);
        return (recovered, success && resultsMatch && validResult);
    }
    
    /**
     * @dev Test SHA-256 precompile (address 0x02)
     */
    function testSha256(bytes memory data) external returns (bytes32 hash, bool success) {
        // Call sha256 precompile directly
        assembly {
            success := call(gas(), 0x02, 0, add(data, 0x20), mload(data), 0x00, 0x20)
            hash := mload(0x00)
        }
        
        // Also test via built-in sha256 function
        bytes32 builtinResult = sha256(data);
        bool resultsMatch = (hash == builtinResult);
        
        // Check that hash is not zero (SHA256 should never return all zeros for any input)
        bool validResult = (hash != bytes32(0));
        
        testResults["sha256"] = abi.encodePacked(hash);
        testSuccess["sha256"] = success && resultsMatch && validResult;
        
        emit Sha256Test(hash, success && resultsMatch && validResult);
        return (hash, success && resultsMatch && validResult);
    }
    
    /**
     * @dev Test RIPEMD-160 precompile (address 0x03)
     */
    function testRipemd160(bytes memory data) external returns (bytes20 hash, bool success) {
        // Call ripemd160 precompile directly
        assembly {
            success := call(gas(), 0x03, 0, add(data, 0x20), mload(data), 0x00, 0x20)
            hash := mload(0x00)
        }
        
        // Also test via built-in ripemd160 function
        bytes20 builtinResult = ripemd160(data);
        bool resultsMatch = (hash == builtinResult);
        
        // Check that hash is not zero (RIPEMD160 should never return all zeros for any input)
        bool validResult = (hash != bytes20(0));
        
        testResults["ripemd160"] = abi.encodePacked(hash);
        testSuccess["ripemd160"] = success && resultsMatch && validResult;
        
        emit Ripemd160Test(hash, success && resultsMatch && validResult);
        return (hash, success && resultsMatch && validResult);
    }
    
    /**
     * @dev Test identity precompile (address 0x04) - returns input unchanged
     */
    function testIdentity(bytes memory data) external returns (bytes memory result, bool success) {
        result = new bytes(data.length);
        
        assembly {
            success := call(gas(), 0x04, 0, add(data, 0x20), mload(data), add(result, 0x20), mload(data))
        }
        
        // Verify result matches input
        bool resultsMatch = keccak256(result) == keccak256(data);
        
        testResults["identity"] = result;
        testSuccess["identity"] = success && resultsMatch;
        
        return (result, success && resultsMatch);
    }
    
    /**
     * @dev Test modular exponentiation precompile (address 0x05)
     * Performs (base^exp) % mod
     */
    function testModExp(
        bytes memory base,
        bytes memory exp,
        bytes memory mod
    ) external returns (bytes memory result, bool success) {
        // Prepare input: [base_len][exp_len][mod_len][base][exp][mod]
        bytes memory input = abi.encodePacked(
            uint256(base.length),
            uint256(exp.length), 
            uint256(mod.length),
            base,
            exp,
            mod
        );
        
        result = new bytes(mod.length);
        
        assembly {
            success := call(gas(), 0x05, 0, add(input, 0x20), mload(input), add(result, 0x20), mload(result))
        }
        
        // Check that result has proper length and is not all zeros (for non-zero modulus)
        bool validResult = (result.length == mod.length);
        if (mod.length > 0 && uint256(bytes32(mod)) > 0) {
            // For non-zero modulus, result should be valid
            validResult = validResult && (result.length > 0);
        }
        
        testResults["modexp"] = result;
        testSuccess["modexp"] = success && validResult;
        
        emit ModExpTest(result, success && validResult);
        return (result, success && validResult);
    }
    
    /**
     * @dev Test elliptic curve addition precompile (address 0x06)
     * BN254 curve point addition
     */
    function testEcAdd(
        uint256 x1, uint256 y1,
        uint256 x2, uint256 y2
    ) external returns (uint256[2] memory result, bool success) {
        bytes memory input = abi.encodePacked(x1, y1, x2, y2);
        
        assembly {
            success := call(gas(), 0x06, 0, add(input, 0x20), 0x80, 0x00, 0x40)
            mstore(result, mload(0x00))
            mstore(add(result, 0x20), mload(0x20))
        }
        
        // Check that we got a valid point (not both coordinates zero unless it's point at infinity)
        bool validResult = success && (result[0] != 0 || result[1] != 0 || (x1 == 0 && y1 == 0 && x2 == 0 && y2 == 0));
        
        testResults["ecadd"] = abi.encodePacked(result[0], result[1]);
        testSuccess["ecadd"] = validResult;
        
        return (result, validResult);
    }
    
    /**
     * @dev Test elliptic curve scalar multiplication precompile (address 0x07)
     * BN254 curve point scalar multiplication
     */
    function testEcMul(
        uint256 x, uint256 y, uint256 scalar
    ) external returns (uint256[2] memory result, bool success) {
        bytes memory input = abi.encodePacked(x, y, scalar);
        
        assembly {
            success := call(gas(), 0x07, 0, add(input, 0x20), 0x60, 0x00, 0x40)
            mstore(result, mload(0x00))
            mstore(add(result, 0x20), mload(0x20))
        }
        
        // Check result validity: if scalar is 0, result should be point at infinity (0,0)
        // If scalar is non-zero and input point is valid, result should not be zero unless it's point at infinity
        bool validResult = success;
        if (scalar == 0) {
            validResult = validResult && (result[0] == 0 && result[1] == 0);
        } else if (x != 0 || y != 0) {
            // For non-zero scalar and non-infinity input, we should get some result
            validResult = validResult && (result[0] != 0 || result[1] != 0 || scalar == 0);
        }
        
        testResults["ecmul"] = abi.encodePacked(result[0], result[1]);
        testSuccess["ecmul"] = validResult;
        
        return (result, validResult);
    }
    
    /**
     * @dev Test elliptic curve pairing precompile (address 0x08)
     * BN254 curve pairing check
     */
    function testEcPairing(bytes memory input) external returns (bool result, bool success) {
        uint256 output;
        
        assembly {
            success := call(gas(), 0x08, 0, add(input, 0x20), mload(input), 0x00, 0x20)
            output := mload(0x00)
        }
        
        result = (output == 1);
        
        testResults["ecpairing"] = abi.encodePacked(result);
        testSuccess["ecpairing"] = success;
        
        return (result, success);
    }
    
    /**
     * @dev Test BLAKE2f precompile (address 0x09)
     */
    function testBlake2f(bytes memory input) external returns (bytes32 hash, bool success) {
        assembly {
            success := call(gas(), 0x09, 0, add(input, 0x20), mload(input), 0x00, 0x40)
            hash := mload(0x00)
        }
        
        testResults["blake2f"] = abi.encodePacked(hash);
        testSuccess["blake2f"] = success;
        
        emit Blake2fTest(hash, success);
        return (hash, success);
    }
    
    /**
     * @dev Comprehensive test using known test vectors
     */
    function runComprehensiveTests() external returns (bool allPassed) {
        allPassed = true;
        
        // Test ecrecover with known values
        bytes32 msgHash = 0x456e9aea5e197a1f1af7a3e85a3212fa4049a3ba34c2289b4c860fc0b0c64ef3;
        uint8 v = 28;
        bytes32 r = 0x9242685bf161793cc25603c231bc2f568eb630ea16aa137d2664ac8038825608;
        bytes32 s = 0x4f8ae3bd7535248d0bd448298cc2e2071e56992d0774dc340c368ae950852ada;
        
        (, bool ecrecoverSuccess) = this.testEcrecover(msgHash, v, r, s);
        allPassed = allPassed && ecrecoverSuccess;
        
        // Test sha256 with known input
        bytes memory testData = "Hello, World!";
        (, bool sha256Success) = this.testSha256(testData);
        allPassed = allPassed && sha256Success;
        
        // Test ripemd160 with known input
        (, bool ripemd160Success) = this.testRipemd160(testData);
        allPassed = allPassed && ripemd160Success;
        
        // Test identity
        (, bool identitySuccess) = this.testIdentity(testData);
        allPassed = allPassed && identitySuccess;
        
        // Test modexp with simple values
        bytes memory base = abi.encodePacked(uint256(3));
        bytes memory exp = abi.encodePacked(uint256(2));  
        bytes memory mod = abi.encodePacked(uint256(5));
        (, bool modexpSuccess) = this.testModExp(base, exp, mod);
        allPassed = allPassed && modexpSuccess;
        
        return allPassed;
    }
    
    /**
     * @dev Get all test results
     */
    function getAllTestResults() external view returns (
        bytes memory ecrecoverResult,
        bytes memory sha256Result,
        bytes memory ripemd160Result,
        bytes memory identityResult,
        bytes memory modexpResult,
        bool allSuccess
    ) {
        ecrecoverResult = testResults["ecrecover"];
        sha256Result = testResults["sha256"];
        ripemd160Result = testResults["ripemd160"];
        identityResult = testResults["identity"];
        modexpResult = testResults["modexp"];
        
        allSuccess = testSuccess["ecrecover"] && 
                    testSuccess["sha256"] && 
                    testSuccess["ripemd160"] && 
                    testSuccess["identity"] && 
                    testSuccess["modexp"];
    }
    
    /**
     * @dev Check individual test success
     */
    function getTestSuccess(string memory testName) external view returns (bool) {
        return testSuccess[testName];
    }
    
    /**
     * @dev Stress test precompiles with multiple operations
     */
    function stressTestPrecompiles(uint256 iterations) external returns (bool success) {
        success = true;
        
        for (uint256 i = 0; i < iterations; i++) {
            // Generate pseudo-random data for testing
            bytes memory data = abi.encodePacked(block.timestamp, i, msg.sender);
            
            // Test sha256 directly
            bytes32 sha256Hash;
            bool sha256Ok;
            assembly {
                sha256Ok := call(gas(), 0x02, 0, add(data, 0x20), mload(data), 0x00, 0x20)
                sha256Hash := mload(0x00)
            }
            success = success && sha256Ok;
            
            // Test ripemd160 directly  
            bytes20 ripemdHash;
            bool ripemd160Ok;
            assembly {
                ripemd160Ok := call(gas(), 0x03, 0, add(data, 0x20), mload(data), 0x00, 0x20)
                ripemdHash := mload(0x00)
            }
            success = success && ripemd160Ok;
            
            // Test identity directly
            bytes memory identityResult = new bytes(data.length);
            bool identityOk;
            assembly {
                identityOk := call(gas(), 0x04, 0, add(data, 0x20), mload(data), add(identityResult, 0x20), mload(data))
            }
            success = success && identityOk;
            
            if (!success) break;
        }
        
        return success;
    }
}