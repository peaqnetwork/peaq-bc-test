// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

contract SimpleReentrancyGuard {
    bool private locked;

    modifier nonReentrant() {
        require(!locked, "ReentrancyGuard: reentrant call");
        locked = true;
        _;
        locked = false;
    }

    uint256 public balance;

    function deposit() external payable {
        balance += msg.value;
    }

    function withdraw() external nonReentrant {
        require(balance > 0, "Nothing to withdraw");
        uint256 amount = balance;
        balance = 0;
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "Transfer failed");
    }

    receive() external payable {}
}

