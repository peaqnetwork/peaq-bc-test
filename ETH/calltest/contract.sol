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

// Main caller contract that tests all call types
contract CallTestContract {
    TargetContract public target;
    
    // State variables to track context preservation
    uint256 public lastCallResult;
    bool public lastCallSuccess;
    bytes public lastCallData;
    
    // Events for logging call results
    event CallExecuted(string callType, bool success, bytes data);
    event ContextPreserved(address sender, address origin, uint256 value);
    
    constructor(address _target) {
        target = TargetContract(payable(_target));
    }
    
    // Regular call - executes in target's context
    function testCall(uint256 _value) external payable returns (bool success, bytes memory data) {
        (success, data) = address(target).call{value: msg.value}(
            abi.encodeWithSignature("setValue(uint256)", _value)
        );
        
        lastCallSuccess = success;
        lastCallData = data;
        
        emit CallExecuted("call", success, data);
        emit ContextPreserved(msg.sender, tx.origin, msg.value);
        
        return (success, data);
    }
    
    // Delegatecall - executes in this contract's context
    function testDelegatecall(uint256 _value) external returns (bool success, bytes memory data) {
        (success, data) = address(target).delegatecall(
            abi.encodeWithSignature("setValue(uint256)", _value)
        );
        
        lastCallSuccess = success;
        lastCallData = data;
        
        emit CallExecuted("delegatecall", success, data);
        
        return (success, data);
    }
    
    // Staticcall - read-only call, should preserve state
    function testStaticcall() external view returns (bool success, uint256 returnValue) {
        (bool _success, bytes memory data) = address(target).staticcall(
            abi.encodeWithSignature("getValue()")
        );
        
        if (_success) {
            returnValue = abi.decode(data, (uint256));
        }
        
        return (_success, returnValue);
    }
    
    // Staticcall with state modification (should fail)
    function testStaticcallModify() external view returns (bool success, bytes memory data) {
        (success, data) = address(target).staticcall(
            abi.encodeWithSignature("getValueAndModify()")
        );
        
        return (success, data);
    }
    
    // Test call to non-existent function (triggers fallback)
    function testFallbackCall() external payable returns (bool success, bytes memory data) {
        (success, data) = address(target).call{value: msg.value}(
            abi.encodeWithSignature("nonExistentFunction(uint256)", 123)
        );
        
        emit CallExecuted("fallback", success, data);
        
        return (success, data);
    }
    
    // Test call with revert
    function testRevertCall() external returns (bool success, bytes memory data) {
        (success, data) = address(target).call(
            abi.encodeWithSignature("revertFunction()")
        );
        
        emit CallExecuted("revert", success, data);
        
        return (success, data);
    }
    
    // Test low-level call with custom gas
    function testCallWithGas(uint256 _value, uint256 _gas) external payable returns (bool success, bytes memory data) {
        (success, data) = address(target).call{value: msg.value, gas: _gas}(
            abi.encodeWithSignature("setValue(uint256)", _value)
        );
        
        emit CallExecuted("call_with_gas", success, data);
        
        return (success, data);
    }
    
    // Test delegatecall context preservation
    // These should modify THIS contract's state, not target's
    uint256 public value;
    address public sender;
    address public origin;
    uint256 public msgValue;
    bool public readOnlyFlag;
    
    function testDelegatecallContext(uint256 _value) external payable returns (bool success) {
        (success, ) = address(target).delegatecall(
            abi.encodeWithSignature("setValue(uint256)", _value)
        );
        
        // After delegatecall, this contract's state should be modified
        return success;
    }
    
    // Getter functions to verify context preservation
    function getCallContext() external view returns (
        uint256 targetValue,
        address targetSender,
        address targetOrigin,
        uint256 targetMsgValue
    ) {
        return (target.value(), target.sender(), target.origin(), target.msgValue());
    }
    
    function getDelegatecallContext() external view returns (
        uint256 localValue,
        address localSender,
        address localOrigin,
        uint256 localMsgValue
    ) {
        return (value, sender, origin, msgValue);
    }
    
    // Test batch calls
    function testBatchCalls(uint256[] memory values) external returns (bool[] memory results) {
        results = new bool[](values.length);
        
        for (uint i = 0; i < values.length; i++) {
            (bool success, ) = address(target).call(
                abi.encodeWithSignature("setValue(uint256)", values[i])
            );
            results[i] = success;
        }
        
        return results;
    }
}

