// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.30;

import {Vm} from "forge-std/Vm.sol";

/// @dev Stand-in for the Subnet-EVM NativeMinter precompile in tests: it really increases the
///      recipient's native balance (through the cheatcode) and only obeys enabled callers.
contract MockNativeMinter {
    Vm private constant VM = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    mapping(address => bool) public enabled;
    uint256 public totalMinted;

    function setEnabled(address addr) external {
        enabled[addr] = true;
    }

    function mintNativeCoin(address addr, uint256 amount) external {
        require(enabled[msg.sender], "non-enabled cannot mint");
        totalMinted += amount;
        VM.deal(addr, addr.balance + amount);
    }
}
