// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";

contract UUPSContract is Initializable, UUPSUpgradeable, OwnableUpgradeable {
    uint256 public value;
    string public versionLabel;

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    function initialize(string memory _versionLabel) public initializer {
        __Ownable_init(msg.sender);
        __UUPSUpgradeable_init();
        versionLabel = _versionLabel;
        value = 1;
    }

    function setValue(uint256 _v) public {
        value = _v;
    }

    function version() public view returns (string memory) {
        return versionLabel;
    }

    function setVersion(string calldata _v) external onlyOwner {
        versionLabel = _v;
    }

    function _authorizeUpgrade(address newImplementation) internal override onlyOwner {}
}
