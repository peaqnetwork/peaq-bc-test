// contracts/GLDToken.sol
// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract MoonToken is ERC20, Ownable {
    constructor() ERC20("MOON", "MOON") Ownable(msg.sender) {}

    function mint(address to, uint256 amount) public onlyOwner {
        _mint(to, amount);
    }

    function burn(address addr, uint256 amount) public onlyOwner {
        _burn(addr, amount);
    }
}
