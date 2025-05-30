// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

contract ProxyContract {
    uint256 public num;

    function delegateSetNum(address logicAddress, uint256 _num) public {
        (bool success, ) = logicAddress.delegatecall(
            abi.encodeWithSignature("setNum(uint256)", _num)
        );
        require(success, "delegatecall failed");
    }
}
