// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

contract CalldataHeavyRouter {
    event BatchSet(uint256 count, uint256 sum);
    event Decoded(uint256 a, address b);
    event Routed(string method, bytes data);

    // 1️⃣ Multi-parameter batch call
    function batchSet(uint256[] memory ids) public {
        uint256 sum = 0;
        for (uint256 i = 0; i < ids.length; i++) {
            sum += ids[i];
        }
        emit BatchSet(ids.length, sum);
    }

    // 2️⃣ Dynamic bytes input (manual decoding)
    function handle(bytes calldata data) external {
        (uint256 a, address b) = abi.decode(data, (uint256, address));
        emit Decoded(a, b);
    }

    // 3️⃣ Multi-layer ABI encoding (router-style)
    function routerCall(bytes calldata data) external {
        (string memory method, bytes memory innerPayload) = abi.decode(data, (string, bytes));

        // Simulate router dispatch (only emits event, does not actually call)
        emit Routed(method, innerPayload);

        // You could extend this with dispatch logic, e.g. if (method == "handle") this.handle(...)
    }
}
