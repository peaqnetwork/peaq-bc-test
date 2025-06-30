// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

/**
 * @title EIP1153TransientTest
 * @dev Test EIP-1153 transient storage (TLOAD/TSTORE opcodes)
 */
contract EIP1153TransientTest {
    // Regular storage for comparison
    uint256 public regularStorage;
    
    /**
     * @dev Test basic TSTORE/TLOAD operations
     */
    function testBasicTransient(uint256 value) external returns (uint256) {
        // Store value in transient storage
        assembly {
            tstore(0x01, value)
        }
        
        // Load value from transient storage
        uint256 result;
        assembly {
            result := tload(0x01)
        }
        
        // Clear transient storage for safety
        assembly {
            tstore(0x01, 0)
        }
        
        return result;
    }
    
    /**
     * @dev Test transient storage isolation between calls
     */
    function testTransientIsolation() external returns (bool) {
        // Set transient value
        assembly {
            tstore(0x02, 42)
        }
        
        // Call another function that should not see this value
        bool isolated = this.checkTransientEmpty();
        
        // Verify our value is still there
        uint256 ourValue;
        assembly {
            ourValue := tload(0x02)
        }
        
        bool result = isolated && (ourValue == 42);
        
        // Clear transient storage for safety
        assembly {
            tstore(0x02, 0)
        }
        
        return result;
    }
    
    /**
     * @dev Check if transient storage is empty (separate call)
     */
    function checkTransientEmpty() external view returns (bool) {
        uint256 value;
        assembly {
            value := tload(0x02)
        }
        return value == 0; // Should be empty in new call
    }
    
    /**
     * @dev Test transient vs regular storage
     */
    function testTransientVsRegular(uint256 value) external returns (bool) {
        // Store in both regular and transient
        regularStorage = value;
        assembly {
            tstore(0x03, value)
        }
        
        // Read from both
        uint256 transientValue;
        assembly {
            transientValue := tload(0x03)
        }
        
        bool result = (regularStorage == transientValue);
        
        // Clear transient storage
        assembly {
            tstore(0x03, 0)
        }
        
        return result;
    }
    
    /**
     * @dev Test transient storage in loops
     */
    function testTransientLoop(uint256 iterations) external returns (uint256) {
        uint256 sum = 0;
        
        for (uint256 i = 0; i < iterations; i++) {
            // Store current sum in transient storage
            assembly {
                tstore(0x04, sum)
            }
            
            // Load and add current iteration
            uint256 temp;
            assembly {
                temp := tload(0x04)
            }
            sum = temp + i;
        }
        
        // Clear transient storage for safety
        assembly {
            tstore(0x04, 0)
        }
        
        return sum;
    }
    
    /**
     * @dev Test multiple transient slots
     */
    function testMultipleSlots() external returns (bool) {
        // Store different values in different slots
        assembly {
            tstore(0x10, 100)
            tstore(0x20, 200)
            tstore(0x30, 300)
        }
        
        // Read all values
        uint256 val1;
        uint256 val2;
        uint256 val3;
        assembly {
            val1 := tload(0x10)
            val2 := tload(0x20)
            val3 := tload(0x30)
        }
        
        bool result = (val1 == 100 && val2 == 200 && val3 == 300);
        
        // Clear all transient storage for safety
        assembly {
            tstore(0x10, 0)
            tstore(0x20, 0)
            tstore(0x30, 0)
        }
        
        return result;
    }
    
    /**
     * @dev Get regular storage for comparison
     */
    function getRegularStorage() external view returns (uint256) {
        return regularStorage;
    }
}