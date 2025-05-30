// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

contract MultiEventContract {
    event Event0(); // 0 param
    event Event1(uint256 a); // 1 param
    event Event2(uint256 a, address b); // 2 params
    event Event3(uint256 a, address b, string c); // 3 params
    event Event4(uint256 a, address b, string c, bool d); // 4 params

    event EventIndex1(uint256 indexed a, address b, string c, bool d);
    event EventIndex2(uint256 indexed a, address indexed b, string c, bool d);
    event EventIndex3(uint256 indexed a, address indexed b, string indexed c, bool d);

    function triggerAll() external {
        emit Event0();
        emit Event1(1);
        emit Event2(2, msg.sender);
        emit Event3(3, msg.sender, "hello");
        emit Event4(4, msg.sender, "world", true);

        emit EventIndex1(11, msg.sender, "moon", false);
        emit EventIndex2(22, msg.sender, "mars", true);
        emit EventIndex3(33, msg.sender, "earth", false);
    }
}
