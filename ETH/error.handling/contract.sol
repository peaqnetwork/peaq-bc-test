// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

contract ErrorTest {
    uint32 nouse;
    function requirePositive(uint256 x) external returns (uint256) {
        nouse = 1;
        require(x > 0, "Value must be positive");
        return x;
    }

    function forceRevert() external {
        nouse = 2;
        revert("Forced revert");
    }

    function alwaysFailAssert() external {
        nouse = 3;
        uint256 x = 1;
        assert(x == 2);
    }
}
