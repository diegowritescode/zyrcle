// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {Treasury} from "../src/Treasury.sol";
import {MockNativeMinter} from "./mocks/MockNativeMinter.sol";

abstract contract TreasuryBase is Test {
    uint256 internal constant COP = 1e18; // 1 ZYR = 1 peso
    address internal admin = makeAddr("admin");
    address internal operator = makeAddr("operator");
    address internal oracle = makeAddr("oracle");
    Treasury internal treasury;
    MockNativeMinter internal minter;

    function setUp() public virtual {
        address precompile = 0x0200000000000000000000000000000000000001;
        vm.etch(precompile, type(MockNativeMinter).runtimeCode);
        minter = MockNativeMinter(precompile);
        // 65% residents, 15% collector, 10% host, 10% operations; advances up to 5,000 COP, 20,000 a day.
        treasury = new Treasury(admin, Treasury.Shares(6_500, 1_500, 1_000, 1_000), 5_000 * COP, 20_000 * COP);
        minter.setEnabled(address(treasury));
        vm.startPrank(admin);
        treasury.grantRole(treasury.OPERATOR_ROLE(), operator);
        treasury.grantRole(treasury.ORACLE_ROLE(), oracle);
        vm.stopPrank();
        vm.warp(1_795_315_300);
    }

    function _seed(uint256 pesos) internal {
        vm.prank(operator);
        treasury.recordSeedCapital(keccak256(abi.encode("seed", pesos, block.timestamp)), pesos * COP);
    }
}
