// SPDX-License-Identifier: MIT
pragma solidity ^0.8.11;

contract Event {
    uint256 public number;

    // Event declaration
    // Up to 3 parameters can be indexed.
    // Indexed parameters helps you filter the logs by the indexed parameter
    event Log(address indexed sender, string message, uint256);
    event AnotherLog();

    function test() public {
        emit Log(msg.sender, "Hello World!", number);
        number += 1;
        emit Log(msg.sender, "Hello EVM!", number);
        number += 1;
        emit AnotherLog();
    }
}
