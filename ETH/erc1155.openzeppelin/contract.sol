// contracts/GameItems.sol
// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import "@openzeppelin/contracts/token/ERC1155/extensions/ERC1155Supply.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract MoonItem is Ownable, ERC1155Supply {
    uint256 public constant GOLD = 0;
    uint256 public constant SILVER = 1;

    constructor() ERC1155("https://game.example/api/item/{id}.json") Ownable(msg.sender) {
        _mint(msg.sender, GOLD, 10**18, "");
        _mint(msg.sender, SILVER, 10**18, "");
    }

    function mintBatch(address to, uint256[] memory ids, uint256[] memory amounts, bytes memory data) public onlyOwner {
        _mintBatch(to, ids, amounts, data);
    }

    function burnBatch(address from, uint256[] memory ids, uint256[] memory amounts) public onlyOwner {
        _burnBatch(from, ids, amounts);
    }

    function updateBatch(address from, address to, uint256[] memory ids, uint256[] memory values) public onlyOwner {
        _update(from, to, ids, values);
    }
}
