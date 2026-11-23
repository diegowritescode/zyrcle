// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {Treasury} from "../src/Treasury.sol";
import {TreasuryBase} from "./Base.t.sol";

/// @dev Drives the Treasury with random sequences of seed capital, sales, advances, settlements and
///      collector and host payments. Calls that revert are fine; the invariants must hold after every
///      call.
contract Handler is Test {
    uint256 internal constant COP = 1e18;
    Treasury internal t;
    address internal operator;
    address internal oracle;
    address[] internal residents;
    bytes32[] public saleIds;
    uint256 internal nonce;
    uint256 public ghostMintedToActors;

    constructor(Treasury treasury, address operator_, address oracle_) {
        t = treasury;
        operator = operator_;
        oracle = oracle_;
        for (uint256 i; i < 5; ++i) {
            residents.push(makeAddr(string(abi.encode("resident", i))));
        }
    }

    function seed(uint256 pesos) external {
        pesos = bound(pesos, 1, 50_000);
        vm.prank(operator);
        t.recordSeedCapital(bytes32(++nonce), pesos * COP);
    }

    function sale(uint256 pesos) external {
        pesos = bound(pesos, 1, 200_000);
        bytes32 id = bytes32(++nonce);
        vm.prank(operator);
        t.recordSale(id, pesos * COP, bytes32(0));
        saleIds.push(id);
    }

    function advance(uint256 depositSeed, uint256 who, uint256 pesos) external {
        address r = residents[who % residents.length];
        uint256 before = r.balance;
        vm.prank(oracle);
        try t.payAdvance(bytes32(depositSeed % 50), r, bound(pesos, 1, 6_000) * COP) {
            ghostMintedToActors += r.balance - before;
        } catch {}
    }

    function settle(uint256 saleSeed, uint256 depositSeed, uint256 who, uint256 pesos) external {
        if (saleIds.length == 0) return;
        bytes32[] memory ids = new bytes32[](1);
        address[] memory rs = new address[](1);
        uint256[] memory shares = new uint256[](1);
        ids[0] = bytes32(depositSeed % 50);
        rs[0] = residents[who % residents.length];
        shares[0] = bound(pesos, 0, 100_000) * COP;
        uint256 before = rs[0].balance;
        vm.prank(oracle);
        try t.settleResidents(saleIds[saleSeed % saleIds.length], ids, rs, shares, bytes32(0)) {
            ghostMintedToActors += rs[0].balance - before;
        } catch {}
    }

    function payCollector(uint256 saleSeed, uint256 pesos) external {
        if (saleIds.length == 0) return;
        address c = residents[0];
        uint256 before = c.balance;
        vm.prank(oracle);
        try t.payCollector(saleIds[saleSeed % saleIds.length], c, bound(pesos, 1, 50_000) * COP) {
            ghostMintedToActors += c.balance - before;
        } catch {}
    }

    function payHost(uint256 saleSeed, uint256 who, uint256 pesos) external {
        if (saleIds.length == 0) return;
        address h = residents[who % residents.length];
        uint256 before = h.balance;
        vm.prank(oracle);
        try t.payHost(saleIds[saleSeed % saleIds.length], h, bound(pesos, 1, 30_000) * COP) {
            ghostMintedToActors += h.balance - before;
        } catch {}
    }

    function warp(uint256 secondsAhead) external {
        vm.warp(block.timestamp + bound(secondsAhead, 0, 2 days));
    }

    function saleCount() external view returns (uint256) {
        return saleIds.length;
    }
}

contract TreasuryInvariantTest is TreasuryBase {
    Handler internal handler;

    function setUp() public override {
        super.setUp();
        handler = new Handler(treasury, operator, oracle);
        targetContract(address(handler));
    }

    /// The core rule: no ZYR exists without pesos behind it.
    function invariant_minted_never_exceeds_backing() public view {
        assertLe(treasury.minted(), treasury.backing());
    }

    /// Every ZYR the precompile created went through the Treasury's books, and reached residents.
    function invariant_books_match_the_chain() public view {
        assertEq(minter.totalMinted(), treasury.minted());
        assertEq(handler.ghostMintedToActors(), treasury.minted());
    }

    function invariant_sales_never_overpay_their_parts() public view {
        for (uint256 i; i < handler.saleCount(); ++i) {
            (
                ,
                uint128 residentsPart,
                uint128 collectorPart,
                uint128 hostPart,
                uint128 settled,
                uint128 collectorPaid,
                uint128 hostPaid,
            ) = treasury.sales(handler.saleIds(i));
            assertLe(settled, residentsPart);
            assertLe(collectorPaid, collectorPart);
            assertLe(hostPaid, hostPart);
        }
    }

    function invariant_backing_is_seed_plus_distributable_sales() public view {
        uint256 distributable;
        for (uint256 i; i < handler.saleCount(); ++i) {
            (, uint128 residentsPart, uint128 collectorPart, uint128 hostPart,,,,) = treasury.sales(handler.saleIds(i));
            distributable += uint256(residentsPart) + collectorPart + hostPart;
        }
        assertEq(treasury.backing(), treasury.seedCapital() + distributable);
    }
}
