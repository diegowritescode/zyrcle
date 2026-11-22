// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.30;

import {IAccessControl} from "@openzeppelin/contracts/access/IAccessControl.sol";
import {Initializable} from "@openzeppelin/contracts/proxy/utils/Initializable.sol";
import {Test} from "forge-std/Test.sol";
import {AccountFactory} from "../src/AccountFactory.sol";
import {ZyrcleAccount} from "../src/ZyrcleAccount.sol";

contract Reverter {
    error Nope(uint256 code);

    function fail() external pure {
        revert Nope(7);
    }
}

contract ZyrcleAccountTest is Test {
    address internal admin = makeAddr("admin");
    address internal guardian = makeAddr("guardian");
    address internal shop = makeAddr("shop");
    address internal stranger = makeAddr("stranger");
    uint256 internal oldKey;
    uint256 internal newKey;
    address internal oldPhone;
    address internal newPhone;
    AccountFactory internal factory;
    ZyrcleAccount internal account;

    function setUp() public {
        (oldPhone, oldKey) = makeAddrAndKey("old phone");
        (newPhone, newKey) = makeAddrAndKey("new phone");
        factory = new AccountFactory(admin, guardian);
        account = ZyrcleAccount(payable(factory.createAccount(oldPhone)));
        vm.warp(1_795_315_300);
    }

    // ----------------------------------------------------------- creation

    function test_the_address_is_known_before_the_account_exists() public {
        address predicted = factory.predict(newPhone);
        assertEq(predicted.code.length, 0);
        vm.deal(predicted, 1_200 ether); // the Treasury pays before anything is deployed
        address created = factory.createAccount(newPhone);
        assertEq(created, predicted);
        assertEq(created.balance, 1_200 ether);
        assertEq(ZyrcleAccount(payable(created)).owner(), newPhone);
    }

    function test_creating_twice_returns_the_same_account() public {
        assertEq(factory.createAccount(oldPhone), address(account));
        assertEq(account.owner(), oldPhone);
    }

    function test_the_implementation_is_the_factorys_first_create() public view {
        assertEq(address(factory.IMPLEMENTATION()), vm.computeCreateAddress(address(factory), 1));
    }

    function test_an_account_cannot_be_initialized_again() public {
        vm.expectRevert(Initializable.InvalidInitialization.selector);
        account.initialize(stranger);
        ZyrcleAccount implementation = factory.IMPLEMENTATION();
        vm.expectRevert(Initializable.InvalidInitialization.selector);
        implementation.initialize(stranger);
    }

    // ----------------------------------------------------------- spending

    function test_the_owner_spends_directly() public {
        vm.deal(address(account), 10 ether);
        vm.prank(oldPhone);
        account.execute(_pay(shop, 4 ether));
        assertEq(shop.balance, 4 ether);
        assertEq(address(account).balance, 6 ether);
    }

    function test_nobody_else_spends_directly() public {
        vm.deal(address(account), 10 ether);
        ZyrcleAccount.Call[] memory calls = _pay(stranger, 10 ether);
        vm.prank(stranger);
        vm.expectRevert(ZyrcleAccount.NotOwner.selector);
        account.execute(calls);
        vm.prank(guardian);
        vm.expectRevert(ZyrcleAccount.NotOwner.selector);
        account.execute(calls);
    }

    function test_a_signed_payment_can_be_submitted_by_anyone_once() public {
        vm.deal(address(account), 10 ether);
        ZyrcleAccount.Call[] memory calls = _pay(shop, 3 ether);
        uint256 deadline = block.timestamp + 10 minutes;
        bytes memory sig = _sign(oldKey, calls, 0, deadline);

        vm.prank(stranger);
        account.executeSigned(calls, deadline, sig);
        assertEq(shop.balance, 3 ether);
        assertEq(account.nonce(), 1);

        vm.expectRevert(ZyrcleAccount.BadSignature.selector);
        account.executeSigned(calls, deadline, sig);
        assertEq(shop.balance, 3 ether);
    }

    function test_a_signature_from_another_key_is_refused() public {
        vm.deal(address(account), 10 ether);
        ZyrcleAccount.Call[] memory calls = _pay(stranger, 10 ether);
        uint256 deadline = block.timestamp + 10 minutes;
        bytes memory sig = _sign(newKey, calls, 0, deadline);
        vm.expectRevert(ZyrcleAccount.BadSignature.selector);
        account.executeSigned(calls, deadline, sig);
        vm.expectRevert(ZyrcleAccount.BadSignature.selector);
        account.executeSigned(calls, deadline, hex"1234");
    }

    function test_an_expired_signature_is_refused() public {
        ZyrcleAccount.Call[] memory calls = _pay(shop, 0);
        uint256 deadline = block.timestamp - 1;
        bytes memory sig = _sign(oldKey, calls, 0, deadline);
        vm.expectRevert(abi.encodeWithSelector(ZyrcleAccount.Expired.selector, deadline));
        account.executeSigned(calls, deadline, sig);
    }

    function test_a_signature_for_one_account_does_not_work_on_another() public {
        ZyrcleAccount other = ZyrcleAccount(payable(factory.createAccount(newPhone)));
        vm.prank(guardian);
        other.startRecovery(oldPhone);
        vm.warp(block.timestamp + 48 hours);
        other.finishRecovery(); // both accounts are now owned by the old phone's key
        vm.deal(address(account), 10 ether);
        vm.deal(address(other), 10 ether);

        ZyrcleAccount.Call[] memory calls = _pay(shop, 1 ether);
        uint256 deadline = block.timestamp + 10 minutes;
        bytes memory sig = _sign(oldKey, calls, 0, deadline);
        vm.expectRevert(ZyrcleAccount.BadSignature.selector);
        other.executeSigned(calls, deadline, sig);
        account.executeSigned(calls, deadline, sig);
        assertEq(shop.balance, 1 ether);
    }

    function test_a_failed_call_reverts_everything_with_its_reason() public {
        vm.deal(address(account), 10 ether);
        Reverter r = new Reverter();
        ZyrcleAccount.Call[] memory calls = new ZyrcleAccount.Call[](2);
        calls[0] = ZyrcleAccount.Call(shop, 1 ether, "");
        calls[1] = ZyrcleAccount.Call(address(r), 0, abi.encodeCall(Reverter.fail, ()));
        vm.prank(oldPhone);
        vm.expectRevert(
            abi.encodeWithSelector(
                ZyrcleAccount.CallFailed.selector, 1, abi.encodeWithSelector(Reverter.Nope.selector, 7)
            )
        );
        account.execute(calls);
        assertEq(shop.balance, 0);
    }

    // ----------------------------------------------------------- recovery

    function test_a_lost_phone_is_replaced_after_the_wait_and_the_balance_stays() public {
        vm.deal(address(account), 25_000 ether);
        vm.prank(guardian);
        account.startRecovery(newPhone);
        (address pending, uint64 readyAt) = account.recovery();
        assertEq(pending, newPhone);
        assertEq(readyAt, block.timestamp + 48 hours);

        vm.warp(block.timestamp + 48 hours - 1);
        vm.expectRevert(abi.encodeWithSelector(ZyrcleAccount.RecoveryNotReady.selector, readyAt));
        account.finishRecovery();

        vm.warp(block.timestamp + 1);
        vm.prank(stranger); // anyone can complete it
        account.finishRecovery();
        assertEq(account.owner(), newPhone);
        assertEq(address(account).balance, 25_000 ether);

        vm.prank(newPhone);
        account.execute(_pay(shop, 1 ether));
        assertEq(shop.balance, 1 ether);
        vm.prank(oldPhone);
        vm.expectRevert(ZyrcleAccount.NotOwner.selector);
        account.execute(_pay(oldPhone, 1 ether));
    }

    function test_only_the_guardian_starts_a_recovery() public {
        vm.prank(stranger);
        vm.expectRevert(ZyrcleAccount.NotGuardian.selector);
        account.startRecovery(stranger);
        vm.prank(oldPhone);
        vm.expectRevert(ZyrcleAccount.NotGuardian.selector);
        account.startRecovery(newPhone);
    }

    function test_a_recovery_to_the_current_owner_or_to_nobody_is_refused() public {
        vm.startPrank(guardian);
        vm.expectRevert(ZyrcleAccount.SameOwner.selector);
        account.startRecovery(oldPhone);
        vm.expectRevert(ZyrcleAccount.ZeroAddress.selector);
        account.startRecovery(address(0));
    }

    function test_the_owner_cancels_a_recovery_it_did_not_ask_for() public {
        vm.prank(guardian);
        account.startRecovery(stranger);
        vm.prank(oldPhone);
        account.cancelRecovery();
        vm.warp(block.timestamp + 48 hours);
        vm.expectRevert(ZyrcleAccount.NoRecovery.selector);
        account.finishRecovery();
        assertEq(account.owner(), oldPhone);
    }

    function test_the_owner_cancels_without_gas_through_a_signed_message() public {
        vm.prank(guardian);
        account.startRecovery(stranger);
        ZyrcleAccount.Call[] memory calls = new ZyrcleAccount.Call[](1);
        calls[0] = ZyrcleAccount.Call(address(account), 0, abi.encodeCall(ZyrcleAccount.cancelRecovery, ()));
        uint256 deadline = block.timestamp + 10 minutes;
        account.executeSigned(calls, deadline, _sign(oldKey, calls, 0, deadline));
        (address pending,) = account.recovery();
        assertEq(pending, address(0));
    }

    function test_the_guardian_can_cancel_but_strangers_cannot() public {
        vm.prank(guardian);
        account.startRecovery(newPhone);
        vm.prank(stranger);
        vm.expectRevert(ZyrcleAccount.NotAuthorized.selector);
        account.cancelRecovery();
        vm.prank(guardian);
        account.cancelRecovery();
        vm.prank(guardian);
        vm.expectRevert(ZyrcleAccount.NoRecovery.selector);
        account.cancelRecovery();
    }

    function test_a_new_recovery_replaces_the_pending_one_and_restarts_the_wait() public {
        vm.prank(guardian);
        account.startRecovery(stranger);
        vm.warp(block.timestamp + 47 hours);
        vm.prank(guardian);
        account.startRecovery(newPhone);
        vm.warp(block.timestamp + 2 hours);
        vm.expectRevert();
        account.finishRecovery();
        vm.warp(block.timestamp + 46 hours);
        account.finishRecovery();
        assertEq(account.owner(), newPhone);
    }

    function test_old_signatures_die_with_the_old_key() public {
        vm.deal(address(account), 10 ether);
        ZyrcleAccount.Call[] memory calls = _pay(stranger, 10 ether);
        uint256 deadline = block.timestamp + 72 hours;
        bytes memory signedBeforeLoss = _sign(oldKey, calls, 0, deadline);
        vm.prank(guardian);
        account.startRecovery(newPhone);
        vm.warp(block.timestamp + 48 hours);
        account.finishRecovery();
        vm.expectRevert(ZyrcleAccount.BadSignature.selector);
        account.executeSigned(calls, deadline, signedBeforeLoss);
    }

    function test_the_owner_moves_to_a_new_phone_at_once_and_clears_a_pending_recovery() public {
        vm.prank(guardian);
        account.startRecovery(stranger);
        ZyrcleAccount.Call[] memory calls = new ZyrcleAccount.Call[](1);
        calls[0] = ZyrcleAccount.Call(address(account), 0, abi.encodeCall(ZyrcleAccount.transferOwnership, (newPhone)));
        vm.prank(oldPhone);
        account.execute(calls);
        assertEq(account.owner(), newPhone);
        (address pending,) = account.recovery();
        assertEq(pending, address(0));
    }

    function test_ownership_moves_only_through_the_account_itself() public {
        vm.prank(oldPhone);
        vm.expectRevert(ZyrcleAccount.NotAuthorized.selector);
        account.transferOwnership(newPhone);
        vm.prank(guardian);
        vm.expectRevert(ZyrcleAccount.NotAuthorized.selector);
        account.transferOwnership(newPhone);
    }

    // ----------------------------------------------------------- guardian

    function test_replacing_the_guardian_applies_to_every_account() public {
        address replacement = makeAddr("replacement");
        vm.prank(admin);
        factory.setGuardian(replacement);
        assertEq(account.guardian(), replacement);
        vm.prank(guardian);
        vm.expectRevert(ZyrcleAccount.NotGuardian.selector);
        account.startRecovery(newPhone);
        vm.prank(replacement);
        account.startRecovery(newPhone);
    }

    function test_only_the_admin_replaces_the_guardian() public {
        bytes32 role = factory.DEFAULT_ADMIN_ROLE();
        vm.prank(guardian);
        vm.expectRevert(
            abi.encodeWithSelector(IAccessControl.AccessControlUnauthorizedAccount.selector, guardian, role)
        );
        factory.setGuardian(guardian);
        vm.prank(admin);
        vm.expectRevert(AccountFactory.ZeroAddress.selector);
        factory.setGuardian(address(0));
    }

    // ----------------------------------------------------------- ERC-1271

    function test_erc1271_accepts_only_the_current_owner() public {
        bytes32 hash = keccak256("sign in to some app");
        assertEq(account.isValidSignature(hash, _signMessage(oldKey, account, hash)), bytes4(0x1626ba7e));
        assertEq(account.isValidSignature(hash, _signMessage(newKey, account, hash)), bytes4(0xffffffff));
        assertEq(account.isValidSignature(hash, hex"00"), bytes4(0xffffffff));

        vm.prank(guardian);
        account.startRecovery(newPhone);
        vm.warp(block.timestamp + 48 hours);
        account.finishRecovery();
        assertEq(account.isValidSignature(hash, _signMessage(oldKey, account, hash)), bytes4(0xffffffff));
        assertEq(account.isValidSignature(hash, _signMessage(newKey, account, hash)), bytes4(0x1626ba7e));
    }

    // ----------------------------------------------------------- fuzz

    function testFuzz_only_the_owner_key_can_sign(uint256 key, uint256 amount) public {
        key = bound(key, 1, 0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364140);
        vm.assume(key != oldKey);
        amount = bound(amount, 0, 1_000_000 ether);
        vm.deal(address(account), amount);
        ZyrcleAccount.Call[] memory calls = _pay(stranger, amount);
        uint256 deadline = block.timestamp + 1;
        bytes memory sig = _sign(key, calls, 0, deadline);
        vm.expectRevert(ZyrcleAccount.BadSignature.selector);
        account.executeSigned(calls, deadline, sig);
    }

    function testFuzz_a_recovery_never_completes_early(uint256 wait) public {
        wait = bound(wait, 0, 48 hours - 1);
        vm.prank(guardian);
        account.startRecovery(newPhone);
        vm.warp(block.timestamp + wait);
        vm.expectRevert();
        account.finishRecovery();
        assertEq(account.owner(), oldPhone);
    }

    // ----------------------------------------------------------- helpers

    function _pay(address to, uint256 amount) internal pure returns (ZyrcleAccount.Call[] memory calls) {
        calls = new ZyrcleAccount.Call[](1);
        calls[0] = ZyrcleAccount.Call(to, amount, "");
    }

    function _sign(uint256 key, ZyrcleAccount.Call[] memory calls, uint256 nonce, uint256 deadline)
        internal
        view
        returns (bytes memory)
    {
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(key, account.executeDigest(calls, nonce, deadline));
        return abi.encodePacked(r, s, v);
    }

    function _signMessage(uint256 key, ZyrcleAccount target, bytes32 hash) internal view returns (bytes memory) {
        bytes32 domain = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256("Zyrcle Account"),
                keccak256("1"),
                block.chainid,
                address(target)
            )
        );
        bytes32 structHash = keccak256(abi.encode(keccak256("ZyrcleMessage(bytes32 hash)"), hash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(key, keccak256(abi.encodePacked("\x19\x01", domain, structHash)));
        return abi.encodePacked(r, s, v);
    }
}
