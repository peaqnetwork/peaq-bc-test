// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

contract StructReturn {
    struct Info {
        uint256 id;
        address owner;
        string name;
    }

    Info public example;

    constructor() {
        example = Info(1, msg.sender, "test");
    }

    function getInfo() external view returns (Info memory) {
        return example;
    }

    function getTuple() external view returns (uint256, address, string memory) {
        return (example.id, example.owner, example.name);
    }
}
