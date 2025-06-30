// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

/**
 * @title CalldataHeavyTest
 * @dev Simple contract for testing calldata-heavy operations
 */
contract CalldataHeavyTest {
    // Events for tracking calldata processing
    event CalldataProcessed(uint256 calldataSize, uint256 gasUsed);
    
    // Simple storage
    uint256 public counter;
    mapping(bytes32 => uint256) public results;
    
    /**
     * @dev Simple swap with calldata
     */
    function exactInputSingle(
        uint256 deadline,
        uint256 amountIn,
        uint256 amountOutMinimum
    ) external returns (uint256 amountOut) {
        uint256 startGas = gasleft();
        
        require(deadline >= block.timestamp, "Transaction too old");
        require(amountIn > 0, "Invalid amount");
        
        // Simple calculation: 3% fee
        amountOut = (amountIn * 97) / 100;
        require(amountOut >= amountOutMinimum, "Insufficient output amount");
        
        uint256 gasUsed = startGas - gasleft();
        emit CalldataProcessed(msg.data.length, gasUsed);
        
        return amountOut;
    }
    
    /**
     * @dev Simple multi-hop swap
     */
    function exactInput(
        bytes calldata path,
        uint256 deadline,
        uint256 amountIn,
        uint256 amountOutMinimum
    ) external returns (uint256 amountOut) {
        uint256 startGas = gasleft();
        
        require(deadline >= block.timestamp, "Transaction too old");
        require(path.length > 0, "Invalid path");
        
        // Simple calculation: 5% fee
        amountOut = (amountIn * 95) / 100;
        require(amountOut >= amountOutMinimum, "Insufficient output amount");
        
        uint256 gasUsed = startGas - gasleft();
        emit CalldataProcessed(msg.data.length, gasUsed);
        
        return amountOut;
    }
    
    /**
     * @dev Simple batch operations
     */
    function batchOperations(bytes[] calldata operations) external returns (uint256[] memory results_) {
        uint256 startGas = gasleft();
        results_ = new uint256[](operations.length);
        
        for (uint256 i = 0; i < operations.length; i++) {
            results_[i] = uint256(keccak256(operations[i])) % 1000000;
        }
        
        uint256 gasUsed = startGas - gasleft();
        emit CalldataProcessed(msg.data.length, gasUsed);
        
        return results_;
    }
    
    /**
     * @dev Process calldata and store hash
     */
    function processLongCalldata(
        bytes calldata data1,
        bytes calldata data2,
        bytes calldata data3
    ) external returns (bytes32 dataHash, uint256 totalLength) {
        uint256 startGas = gasleft();
        
        totalLength = data1.length + data2.length + data3.length;
        dataHash = keccak256(abi.encodePacked(data1, data2, data3));
        
        results[dataHash] = totalLength;
        counter++;
        
        uint256 gasUsed = startGas - gasleft();
        emit CalldataProcessed(msg.data.length, gasUsed);
        
        return (dataHash, totalLength);
    }
    
    /**
     * @dev Simple nested calldata decoding
     */
    function decodeNestedCalldata(bytes calldata data) external returns (uint256 count) {
        uint256 startGas = gasleft();
        
        // Simple processing - just return data length as count
        count = data.length / 32; // Assume 32-byte chunks
        
        bytes32 hash = keccak256(data);
        results[hash] = count;
        
        uint256 gasUsed = startGas - gasleft();
        emit CalldataProcessed(msg.data.length, gasUsed);
        
        return count;
    }
    
    /**
     * @dev Simple aggregator test
     */
    function aggregateSwaps(
        uint256[] calldata amounts
    ) external returns (uint256 totalOutput) {
        uint256 startGas = gasleft();
        
        for (uint256 i = 0; i < amounts.length; i++) {
            // Simple calculation: 2% fee per swap
            totalOutput += (amounts[i] * 98) / 100;
        }
        
        uint256 gasUsed = startGas - gasleft();
        emit CalldataProcessed(msg.data.length, gasUsed);
        
        return totalOutput;
    }
    
    /**
     * @dev Test calldata size limits
     */
    function testCalldataLimits(
        bytes calldata smallData,
        bytes calldata mediumData,
        bytes calldata largeData
    ) external pure returns (bool smallOk, bool mediumOk, bool largeOk) {
        smallOk = smallData.length <= 1000;
        mediumOk = mediumData.length <= 100000;
        largeOk = largeData.length <= 1000000;
        
        return (smallOk, mediumOk, largeOk);
    }
    
    /**
     * @dev Get simple stats
     */
    function getCalldataStats() external view returns (
        uint256 currentCounter,
        uint256 totalStored,
        uint256 averageSize
    ) {
        return (counter, counter, counter > 0 ? 1000 : 0); // Mock average size
    }
}
