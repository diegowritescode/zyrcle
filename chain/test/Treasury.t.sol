// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.30;

import {IAccessControl} from "@openzeppelin/contracts/access/IAccessControl.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {Treasury} from "../src/Treasury.sol";
import {TreasuryBase} from "./Base.t.sol";

contract TreasuryTest is TreasuryBase {
    address internal ana = makeAddr("ana");
    address internal beto = makeAddr("beto");
    address internal collector = makeAddr("collector");
    bytes32 internal constant DEP1 = keccak256("deposit-1");
    bytes32 internal constant DEP2 = keccak256("deposit-2");
    bytes32 internal constant SALE = keccak256("sale-1");

    // ----------------------------------------------------------- backing

    function test_nothing_can_be_minted_without_backing() public {
        vm.prank(oracle);
        vm.expectRevert(abi.encodeWithSelector(Treasury.UnbackedMint.selector, 1_000 * COP, 0));
        treasury.payAdvance(DEP1, ana, 1_000 * COP);
    }

    function test_seed_capital_backs_advances() public {
        _seed(100_000);
        vm.prank(oracle);
        treasury.payAdvance(DEP1, ana, 1_200 * COP);
        assertEq(ana.balance, 1_200 * COP);
        assertEq(treasury.minted(), 1_200 * COP);
        assertEq(treasury.available(), 98_800 * COP);
    }

    function test_seed_reference_cannot_be_reused() public {
        bytes32 ref = keccak256("bank-transfer-1");
        vm.startPrank(operator);
        treasury.recordSeedCapital(ref, 10 * COP);
        vm.expectRevert(abi.encodeWithSelector(Treasury.AlreadyRecorded.selector, ref));
        treasury.recordSeedCapital(ref, 10 * COP);
    }

    // ----------------------------------------------------------- advances

    function test_an_advance_is_paid_once_per_deposit() public {
        _seed(100_000);
        vm.startPrank(oracle);
        treasury.payAdvance(DEP1, ana, 1_000 * COP);
        vm.expectRevert(abi.encodeWithSelector(Treasury.AdvanceAlreadyPaid.selector, DEP1));
        treasury.payAdvance(DEP1, ana, 1_000 * COP);
    }

    function test_advance_per_deposit_is_capped() public {
        _seed(100_000);
        vm.prank(oracle);
        vm.expectRevert(abi.encodeWithSelector(Treasury.AdvanceTooLarge.selector, 5_001 * COP, 5_000 * COP));
        treasury.payAdvance(DEP1, ana, 5_001 * COP);
    }

    function test_daily_cap_per_resident_resets_the_next_day() public {
        _seed(100_000);
        vm.startPrank(oracle);
        for (uint256 i; i < 4; ++i) {
            treasury.payAdvance(keccak256(abi.encode(i)), ana, 5_000 * COP);
        }
        vm.expectRevert(abi.encodeWithSelector(Treasury.DailyCapExceeded.selector, ana, 21_000 * COP, 20_000 * COP));
        treasury.payAdvance(DEP1, ana, 1_000 * COP);
        treasury.payAdvance(DEP2, beto, 1_000 * COP); // other residents are unaffected
        vm.warp(block.timestamp + 1 days);
        treasury.payAdvance(DEP1, ana, 1_000 * COP);
        vm.stopPrank();
        assertEq(ana.balance, 21_000 * COP);
    }

    function test_only_the_oracle_pays_advances() public {
        _seed(100_000);
        bytes32 oracleRole = treasury.ORACLE_ROLE();
        vm.prank(operator);
        vm.expectRevert(
            abi.encodeWithSelector(IAccessControl.AccessControlUnauthorizedAccount.selector, operator, oracleRole)
        );
        treasury.payAdvance(DEP1, ana, 1_000 * COP);
    }

    function test_pause_stops_payouts() public {
        _seed(100_000);
        vm.prank(admin);
        treasury.pause();
        vm.prank(oracle);
        vm.expectRevert(Pausable.EnforcedPause.selector);
        treasury.payAdvance(DEP1, ana, 1_000 * COP);
    }

    function testFuzz_advances_within_limits_always_mint_exactly(uint256 amount) public {
        _seed(100_000);
        amount = bound(amount, 1, 5_000 * COP);
        vm.prank(oracle);
        treasury.payAdvance(DEP1, ana, amount);
        assertEq(ana.balance, amount);
        assertEq(minter.totalMinted(), treasury.minted());
    }

    // ----------------------------------------------------------- sales and settlement

    function test_a_sale_splits_by_shares_and_only_distributable_parts_back_zyr() public {
        vm.prank(operator);
        treasury.recordSale(SALE, 100_000 * COP, keccak256("ticket-photo"));
        (uint128 amount, uint128 residentsPart, uint128 collectorPart,,,) = treasury.sales(SALE);
        assertEq(amount, 100_000 * COP);
        assertEq(residentsPart, 70_000 * COP);
        assertEq(collectorPart, 15_000 * COP);
        assertEq(treasury.operationsRevenue(), 15_000 * COP);
        assertEq(treasury.backing(), 85_000 * COP); // the operations part stays in pesos
    }

    function test_settlement_pays_share_minus_advance() public {
        _seed(10_000);
        vm.startPrank(oracle);
        treasury.payAdvance(DEP1, ana, 1_000 * COP);
        treasury.payAdvance(DEP2, beto, 3_000 * COP);
        vm.stopPrank();
        vm.prank(operator);
        treasury.recordSale(SALE, 10_000 * COP, bytes32(0)); // residents part: 7,000

        // Ana's share is 4,000 (advance 1,000): she gets 3,000 more.
        // Beto's share is 2,000 but his advance was 3,000: he gets 0 and keeps the advance.
        vm.prank(oracle);
        treasury.settleResidents(SALE, _ids(DEP1, DEP2), _addrs(ana, beto), _amts(4_000, 2_000), "report");
        assertEq(ana.balance, 4_000 * COP);
        assertEq(beto.balance, 3_000 * COP);
        (,,, uint128 settled,,) = treasury.sales(SALE);
        assertEq(settled, 6_000 * COP);
        assertLe(treasury.minted(), treasury.backing());
    }

    function test_a_deposit_settles_once_and_cannot_be_advanced_afterwards() public {
        vm.prank(operator);
        treasury.recordSale(SALE, 10_000 * COP, bytes32(0));
        vm.startPrank(oracle);
        treasury.settleResidents(SALE, _ids(DEP1), _addrs(ana), _amts(1_000), "r");
        vm.expectRevert(abi.encodeWithSelector(Treasury.DepositAlreadySettled.selector, DEP1));
        treasury.settleResidents(SALE, _ids(DEP1), _addrs(ana), _amts(1_000), "r");
        vm.expectRevert(abi.encodeWithSelector(Treasury.DepositAlreadySettled.selector, DEP1));
        treasury.payAdvance(DEP1, ana, 100 * COP);
    }

    function test_shares_cannot_exceed_the_residents_part() public {
        vm.prank(operator);
        treasury.recordSale(SALE, 10_000 * COP, bytes32(0));
        vm.prank(oracle);
        vm.expectRevert(abi.encodeWithSelector(Treasury.ResidentsPartExceeded.selector, SALE, 7_001 * COP, 7_000 * COP));
        treasury.settleResidents(SALE, _ids(DEP1, DEP2), _addrs(ana, beto), _amts(7_000, 1), "r");
    }

    function test_collector_is_paid_up_to_the_collector_part() public {
        vm.prank(operator);
        treasury.recordSale(SALE, 10_000 * COP, bytes32(0));
        vm.startPrank(oracle);
        treasury.payCollector(SALE, collector, 1_000 * COP);
        vm.expectRevert(abi.encodeWithSelector(Treasury.CollectorPartExceeded.selector, SALE, 1_501 * COP, 1_500 * COP));
        treasury.payCollector(SALE, collector, 501 * COP);
    }

    function test_unknown_sale_and_length_mismatch() public {
        vm.startPrank(oracle);
        vm.expectRevert(abi.encodeWithSelector(Treasury.UnknownSale.selector, SALE));
        treasury.settleResidents(SALE, _ids(DEP1), _addrs(ana), _amts(1), "r");
        vm.expectRevert(Treasury.LengthMismatch.selector);
        treasury.settleResidents(SALE, _ids(DEP1, DEP2), _addrs(ana), _amts(1, 1), "r");
    }

    function test_shares_must_add_up_and_only_admin_changes_them() public {
        vm.prank(admin);
        vm.expectRevert(Treasury.InvalidShares.selector);
        treasury.setShares(Treasury.Shares(7_000, 1_500, 1_000));
        vm.prank(operator);
        vm.expectRevert();
        treasury.setShares(Treasury.Shares(6_000, 2_000, 2_000));
    }

    // ----------------------------------------------------------- helpers

    function _ids(bytes32 a) internal pure returns (bytes32[] memory r) {
        r = new bytes32[](1);
        r[0] = a;
    }

    function _ids(bytes32 a, bytes32 b) internal pure returns (bytes32[] memory r) {
        r = new bytes32[](2);
        (r[0], r[1]) = (a, b);
    }

    function _addrs(address a) internal pure returns (address[] memory r) {
        r = new address[](1);
        r[0] = a;
    }

    function _addrs(address a, address b) internal pure returns (address[] memory r) {
        r = new address[](2);
        (r[0], r[1]) = (a, b);
    }

    function _amts(uint256 a) internal pure returns (uint256[] memory r) {
        r = new uint256[](1);
        r[0] = a * COP;
    }

    function _amts(uint256 a, uint256 b) internal pure returns (uint256[] memory r) {
        r = new uint256[](2);
        (r[0], r[1]) = (a * COP, b * COP);
    }
}
