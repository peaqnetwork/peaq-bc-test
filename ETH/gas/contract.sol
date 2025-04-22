// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

contract GasSensitive {
    event Success(uint256 remainingGas);
    event Fail(uint256 remainingGas);

    function checkGas() external {
        uint256 gas = gasleft();

        if (gas > 100000) {
            emit Success(gas);
        } else {
            emit Fail(gas);
        }
    }
}
