// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import "./reentry.sol";

contract Attacker {
    SimpleReentrancyGuard public target;
    bool public attacked;

    constructor(address payable _target) {
        target = SimpleReentrancyGuard(_target);
    }

    function attack() external payable {
        require(msg.value > 0, "Need some ether");
        target.deposit{value: msg.value}();
        target.withdraw();
    }

    receive() external payable {
        if (!attacked) {
            attacked = true;
            target.withdraw();
        }
    }
}
