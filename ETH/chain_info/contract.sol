// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

/**
 * @title ChainInfoTest
 * @dev Simple contract for testing chain metadata preservation
 */
contract ChainInfoTest {
    // Simple storage
    uint256 public counter;
    mapping(bytes32 => uint256) public results;
    
    /**
     * @dev Test basic chain metadata
     */
    function testChainInfo(
        uint256 expectedTimestamp,
        uint256 expectedBlockNumber,
        uint256 expectedChainId
    ) external returns (
        uint256 actualTimestamp,
        uint256 actualBlockNumber, 
        uint256 actualChainId,
        bytes32 blockHash,
        address coinbase,
        uint256 prevrandao,
        uint256 gasLimit,
        uint256 baseFee,
        bool timestampMatch,
        bool blockNumberMatch,
        bool chainIdMatch
    ) {
        // Get ALL chain metadata
        actualTimestamp = block.timestamp;
        actualBlockNumber = block.number;
        actualChainId = block.chainid;
        blockHash = blockhash(block.number - 1);
        coinbase = block.coinbase;
        prevrandao = block.prevrandao;
        gasLimit = block.gaslimit;
        baseFee = block.basefee;
        
        // Simple checks
        timestampMatch = actualTimestamp >= expectedTimestamp;
        blockNumberMatch = actualBlockNumber >= expectedBlockNumber;
        chainIdMatch = actualChainId == expectedChainId;
        
        counter++;
        
        return (
            actualTimestamp,
            actualBlockNumber,
            actualChainId,
            blockHash,
            coinbase,
            prevrandao,
            gasLimit,
            baseFee,
            timestampMatch,
            blockNumberMatch,
            chainIdMatch
        );
    }
    
    /**
     * @dev Test time-based operation
     */
    function timeLockedOperation(
        uint256 unlockTime,
        uint256 amount
    ) external returns (uint256 result, uint256 executionTime, bool success) {
        executionTime = block.timestamp;
        
        if (executionTime >= unlockTime) {
            success = true;
            result = amount; // Simple: just return amount
        } else {
            success = false;
            result = 0;
        }
        
        counter++;
        return (result, executionTime, success);
    }
    
    /**
     * @dev Test block number dependent operation
     */
    function blockNumberDependentOperation(
        uint256 targetBlock,
        bytes calldata data
    ) external returns (uint256 currentBlock, bool isReady, bytes32 dataHash) {
        currentBlock = block.number;
        isReady = currentBlock >= targetBlock;
        dataHash = keccak256(data);
        
        if (isReady) {
            counter++;
        }
        
        return (currentBlock, isReady, dataHash);
    }
    
    /**
     * @dev Get basic chain info
     */
    function getChainInfo() external view returns (
        uint256 timestamp,
        uint256 blockNumber,
        uint256 chainId,
        bytes32 blockHash,
        address coinbase,
        uint256 prevrandao,
        uint256 gasLimit,
        uint256 baseFee
    ) {
        return (
            block.timestamp,
            block.number,
            block.chainid,
            blockhash(block.number - 1),
            block.coinbase,
            block.prevrandao,
            block.gaslimit,
            block.basefee
        );
    }
    
    /**
     * @dev Get simple stats
     */
    function getStats() external view returns (uint256 operationCount) {
        return counter;
    }
}