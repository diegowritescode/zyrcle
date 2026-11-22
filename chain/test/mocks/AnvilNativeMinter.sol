// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

/// @dev NativeMinter stand-in for anvil, used by the backend's end-to-end tests. Anvil has no
///      Subnet-EVM precompiles, so this contract is placed at the precompile address with
///      anvil_setCode and pre-funded with anvil_setBalance; "minting" transfers from that float.
///      Same allow-list ABI as the real precompile.
contract AnvilNativeMinter {
    mapping(address => uint256) private roles; // 0 none, 1 enabled, 2 admin

    function setEnabled(address addr) external {
        roles[addr] = 1;
    }

    function readAllowList(address addr) external view returns (uint256) {
        return roles[addr];
    }

    function mintNativeCoin(address addr, uint256 amount) external {
        require(roles[msg.sender] >= 1, "non-enabled cannot mint");
        (bool ok,) = addr.call{value: amount}("");
        require(ok, "transfer failed");
    }

    receive() external payable {}
}
