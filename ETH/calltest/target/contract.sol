// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

// Target contract for testing different call types
contract TargetContract {
    uint256 public value;
    address public sender;
    address public origin;
    uint256 public msgValue;
    bool public readOnlyFlag;
    
    event ValueChanged(uint256 newValue, address sender, address origin);
    event FallbackCalled(bytes data, uint256 value);
    
    constructor() {
        value = 42;
    }
    
    // Function to set value and record context
    function setValue(uint256 _value) external payable {
        value = _value;
        sender = msg.sender;
        origin = tx.origin;
        msgValue = msg.value;
        emit ValueChanged(_value, msg.sender, tx.origin);
    }
    
    // Read-only function for staticcall testing
    function getValue() external view returns (uint256) {
        return value;
    }
    
    // Function that tries to modify state (should fail in staticcall)
    function getValueAndModify() external returns (uint256) {
        readOnlyFlag = true; // This will fail in staticcall
        return value;
    }
    
    // Function that reverts for error testing
    function revertFunction() external pure {
        revert("Intentional revert");
    }
    
    // Fallback function to test fallback logic
    fallback() external payable {
        emit FallbackCalled(msg.data, msg.value);
    }
    
    // Receive function for plain ether transfers
    receive() external payable {
        emit FallbackCalled("", msg.value);
    }
}