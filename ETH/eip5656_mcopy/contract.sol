// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

/**
 * @title EIP5656MCOPYTest
 * @dev Test EIP-5656 MCOPY instruction for gas-optimized memory copying
 */
contract EIP5656MCOPYTest {
    
    /**
     * @dev Test basic MCOPY vs manual memory copying
     */
    function testBasicMCOPY(bytes memory data) external pure returns (bytes memory, bool) {
        bytes memory copied = new bytes(data.length);
        
        // Use MCOPY instruction via inline assembly
        assembly {
            let dataPtr := add(data, 0x20)
            let copiedPtr := add(copied, 0x20)
            let length := mload(data)
            
            // MCOPY: dest, src, length
            mcopy(copiedPtr, dataPtr, length)
        }
        
        // Verify copy is identical
        bool identical = keccak256(data) == keccak256(copied);
        
        return (copied, identical);
    }
    
    /**
     * @dev Test MCOPY with different data sizes
     */
    function testMCOPYSizes() external pure returns (bool[4] memory results) {
        // Test different sizes: 32, 64, 128, 256 bytes
        uint256[4] memory sizes = [uint256(32), 64, 128, 256];
        
        for (uint256 i = 0; i < 4; i++) {
            bytes memory source = new bytes(sizes[i]);
            bytes memory dest = new bytes(sizes[i]);
            
            // Fill source with test data
            for (uint256 j = 0; j < sizes[i]; j++) {
                source[j] = bytes1(uint8(j % 256));
            }
            
            // Copy using MCOPY
            assembly {
                let srcPtr := add(source, 0x20)
                let destPtr := add(dest, 0x20)
                let length := mload(source)
                
                mcopy(destPtr, srcPtr, length)
            }
            
            // Verify copy
            results[i] = keccak256(source) == keccak256(dest);
        }
        
        return results;
    }
    
    /**
     * @dev Test MCOPY vs traditional memory operations for gas comparison
     */
    function testMCOPYGasComparison(bytes memory data) external pure returns (bytes memory mcopyResult, bytes memory manualResult) {
        // MCOPY version
        mcopyResult = new bytes(data.length);
        assembly {
            let dataPtr := add(data, 0x20)
            let resultPtr := add(mcopyResult, 0x20)
            let length := mload(data)
            
            mcopy(resultPtr, dataPtr, length)
        }
        
        // Manual copy version
        manualResult = new bytes(data.length);
        assembly {
            let dataPtr := add(data, 0x20)
            let resultPtr := add(manualResult, 0x20)
            let length := mload(data)
            
            // Manual word-by-word copy
            for { let i := 0 } lt(i, length) { i := add(i, 0x20) } {
                let word := mload(add(dataPtr, i))
                mstore(add(resultPtr, i), word)
            }
            
            // Handle remaining bytes
            let remaining := mod(length, 0x20)
            if remaining {
                let lastWordOffset := sub(length, remaining)
                let lastWord := mload(add(dataPtr, lastWordOffset))
                mstore(add(resultPtr, lastWordOffset), lastWord)
            }
        }
        
        return (mcopyResult, manualResult);
    }
    
    /**
     * @dev Test MCOPY with overlapping memory (should handle correctly)
     */
    function testMCOPYOverlap() external pure returns (bool) {
        bytes memory buffer = new bytes(128);
        
        // Fill first half with test data
        for (uint256 i = 0; i < 64; i++) {
            buffer[i] = bytes1(uint8(i));
        }
        
        // Copy first half to second half using MCOPY
        assembly {
            let bufferPtr := add(buffer, 0x20)
            let srcPtr := bufferPtr
            let destPtr := add(bufferPtr, 64)
            
            mcopy(destPtr, srcPtr, 64)
        }
        
        // Verify copy
        bool correct = true;
        for (uint256 i = 0; i < 64; i++) {
            if (buffer[i] != buffer[i + 64]) {
                correct = false;
                break;
            }
        }
        
        return correct;
    }
    
    /**
     * @dev Test MCOPY with large data blocks
     */
    function testMCOPYLarge(uint256 size) external pure returns (bool, uint256) {
        require(size <= 1024, "Size too large for test");
        
        bytes memory source = new bytes(size);
        bytes memory dest = new bytes(size);
        
        // Fill source with pattern
        for (uint256 i = 0; i < size; i++) {
            source[i] = bytes1(uint8((i * 7) % 256));
        }
        
        // Copy using MCOPY
        assembly {
            let srcPtr := add(source, 0x20)
            let destPtr := add(dest, 0x20)
            let length := mload(source)
            
            mcopy(destPtr, srcPtr, length)
        }
        
        // Verify and return hash for verification
        bool identical = keccak256(source) == keccak256(dest);
        uint256 hash = uint256(keccak256(dest));
        
        return (identical, hash);
    }
    
    /**
     * @dev Test MCOPY with zero-length copy
     */
    function testMCOPYZeroLength() external pure returns (bool) {
        bytes memory buffer = new bytes(64);
        
        // Fill with test data
        for (uint256 i = 0; i < 64; i++) {
            buffer[i] = bytes1(uint8(i));
        }
        
        // Store original hash
        bytes32 originalHash = keccak256(buffer);
        
        // Perform zero-length MCOPY (should not change anything)
        assembly {
            let bufferPtr := add(buffer, 0x20)
            mcopy(bufferPtr, bufferPtr, 0)
        }
        
        // Verify buffer unchanged
        return keccak256(buffer) == originalHash;
    }
    
    /**
     * @dev Compare gas usage between MCOPY and manual copying
     */
    function getMCOPYGasEstimate(bytes memory data) external view returns (uint256 mcopyGas, uint256 manualGas) {
        uint256 gasBefore;
        uint256 gasAfter;
        
        // Estimate MCOPY gas
        gasBefore = gasleft();
        this.testBasicMCOPY(data);
        gasAfter = gasleft();
        mcopyGas = gasBefore - gasAfter;
        
        // Estimate manual copy gas
        gasBefore = gasleft();
        this.testMCOPYGasComparison(data);
        gasAfter = gasleft();
        manualGas = gasBefore - gasAfter;
        
        return (mcopyGas, manualGas);
    }
}