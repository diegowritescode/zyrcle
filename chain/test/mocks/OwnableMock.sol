// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.30;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/// @dev Stands in for the validator manager and its proxy admin in the backend's multisig tests:
///      what matters there is that ownership moves to the Safe.
contract OwnableMock is Ownable {
    constructor(address initialOwner) Ownable(initialOwner) {}
}
