// contracts/GameItem.sol
// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import "@openzeppelin/contracts/token/ERC721/extensions/ERC721URIStorage.sol";
import "@openzeppelin/contracts/utils/Counters.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract MoonItem is ERC721URIStorage, Ownable {
    using Counters for Counters.Counter;
    Counters.Counter private _tokenIds;

    constructor() ERC721("MoonItem", "MOON") Ownable(msg.sender) {}

    function mint(address player, string memory tokenURI)
        public onlyOwner
        returns (uint256)
    {
        uint256 newItemId = _tokenIds.current();
        _safeMint(player, newItemId);
        _setTokenURI(newItemId, tokenURI);

        _tokenIds.increment();
        return newItemId;
    }

    function burn(uint256 itemId) public onlyOwner {
        // _burn will call ERC721Burnable.burn to update the balance and metadata of a token
        // The code in ERC721URIStorage overrides _burn will delete the token URI
        _burn(itemId);
    }
}
