// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.30;

import {IERC1271} from "@openzeppelin/contracts/interfaces/IERC1271.sol";
import {Initializable} from "@openzeppelin/contracts/proxy/utils/Initializable.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {SafeCast} from "@openzeppelin/contracts/utils/math/SafeCast.sol";

/// @dev Where an account reads who its guardian is: the factory that created it.
interface IGuardianSource {
    function guardian() external view returns (address);
}

/// @title Zyrcle account
/// @notice A resident's wallet. It holds their ZYR at an address that never changes and obeys one
///         key, the owner, which lives in the secure storage of the resident's phone.
///
///         If the phone is lost, the guardian (Zyrcle, after checking the resident's identity) can
///         hand the account to a new key, but only after RECOVERY_DELAY. During that time the
///         current owner can cancel, so a stolen email account or a leaked guardian key is not
///         enough to take an account whose owner is paying attention. The balance never moves.
///
///         The owner rarely holds ZYR for gas, so besides calling `execute` directly it can sign an
///         EIP-712 `Execute` message that anyone (in practice the Zyrcle backend) submits.
///
///         See docs/adr/0010-smart-accounts-and-recovery.md.
contract ZyrcleAccount is Initializable, EIP712, IERC1271 {
    struct Call {
        address target;
        uint256 value;
        bytes data;
    }

    struct Recovery {
        address newOwner;
        uint64 readyAt;
    }

    uint256 public constant RECOVERY_DELAY = 48 hours;

    bytes32 private constant CALL_TYPEHASH = keccak256("Call(address target,uint256 value,bytes data)");
    bytes32 private constant EXECUTE_TYPEHASH =
        keccak256("Execute(Call[] calls,uint256 nonce,uint256 deadline)Call(address target,uint256 value,bytes data)");
    /// @dev ERC-1271 messages are wrapped in this account's EIP-712 domain, so a signature made for
    ///      one account is not valid for another account with the same owner.
    bytes32 private constant MESSAGE_TYPEHASH = keccak256("ZyrcleMessage(bytes32 hash)");

    /// @notice The factory that created this account and names its guardian.
    address public immutable FACTORY;

    address public owner;
    /// @notice Next nonce for a signed `Execute`.
    uint256 public nonce;
    Recovery public recovery;

    event OwnerChanged(address indexed previousOwner, address indexed newOwner);
    event Executed(uint256 indexed nonce, uint256 calls);
    event RecoveryStarted(address indexed newOwner, uint256 readyAt);
    event RecoveryCancelled(address indexed newOwner, address indexed by);

    error ZeroAddress();
    error SameOwner();
    error NotOwner();
    error NotGuardian();
    error NotAuthorized();
    error BadSignature();
    error Expired(uint256 deadline);
    error NoRecovery();
    error RecoveryNotReady(uint256 readyAt);
    error CallFailed(uint256 index, bytes reason);

    constructor(address factory) EIP712("Zyrcle Account", "1") {
        if (factory == address(0)) revert ZeroAddress();
        FACTORY = factory;
        _disableInitializers();
    }

    /// @notice Called once by the factory, in the transaction that creates the account.
    function initialize(address initialOwner) external initializer {
        if (initialOwner == address(0)) revert ZeroAddress();
        owner = initialOwner;
        emit OwnerChanged(address(0), initialOwner);
    }

    receive() external payable {}

    function guardian() public view returns (address) {
        return IGuardianSource(FACTORY).guardian();
    }

    // ------------------------------------------------------------------ spending

    /// @notice The owner acting directly, paying its own gas.
    function execute(Call[] calldata calls) external {
        if (msg.sender != owner) revert NotOwner();
        _run(calls);
    }

    /// @notice The owner acting through a signed message that anyone may submit.
    function executeSigned(Call[] calldata calls, uint256 deadline, bytes calldata signature) external {
        if (block.timestamp > deadline) revert Expired(deadline);
        uint256 current = nonce;
        if (!_signedByOwner(executeDigest(calls, current, deadline), signature)) revert BadSignature();
        nonce = current + 1; // before the calls run, so a call cannot replay the same message
        emit Executed(current, calls.length);
        _run(calls);
    }

    /// @notice The EIP-712 digest the owner signs for `executeSigned`.
    function executeDigest(Call[] calldata calls, uint256 nonce_, uint256 deadline) public view returns (bytes32) {
        bytes32[] memory hashes = new bytes32[](calls.length);
        for (uint256 i; i < calls.length; ++i) {
            hashes[i] = keccak256(abi.encode(CALL_TYPEHASH, calls[i].target, calls[i].value, keccak256(calls[i].data)));
        }
        return _hashTypedDataV4(
            keccak256(abi.encode(EXECUTE_TYPEHASH, keccak256(abi.encodePacked(hashes)), nonce_, deadline))
        );
    }

    // ------------------------------------------------------------------ owner changes

    /// @notice Move the account to another key right away. Only through `execute` or
    ///         `executeSigned`, that is, with the current owner's consent. Clears a pending recovery.
    function transferOwnership(address newOwner) external {
        if (msg.sender != address(this)) revert NotAuthorized();
        if (newOwner == address(0)) revert ZeroAddress();
        if (newOwner == owner) revert SameOwner();
        Recovery memory r = recovery;
        if (r.newOwner != address(0)) {
            delete recovery;
            emit RecoveryCancelled(r.newOwner, address(this));
        }
        _setOwner(newOwner);
    }

    /// @notice The guardian starts handing the account to `newOwner`. Replaces any pending recovery
    ///         and restarts the wait.
    function startRecovery(address newOwner) external {
        if (msg.sender != guardian()) revert NotGuardian();
        if (newOwner == address(0)) revert ZeroAddress();
        if (newOwner == owner) revert SameOwner();
        uint64 readyAt = SafeCast.toUint64(block.timestamp + RECOVERY_DELAY);
        recovery = Recovery({newOwner: newOwner, readyAt: readyAt});
        emit RecoveryStarted(newOwner, readyAt);
    }

    /// @notice Stop a pending recovery: the owner (directly or through a signed `Execute`) or the
    ///         guardian.
    function cancelRecovery() external {
        if (msg.sender != owner && msg.sender != address(this) && msg.sender != guardian()) {
            revert NotAuthorized();
        }
        Recovery memory r = recovery;
        if (r.newOwner == address(0)) revert NoRecovery();
        delete recovery;
        emit RecoveryCancelled(r.newOwner, msg.sender);
    }

    /// @notice Anyone may complete a recovery once its wait is over.
    function finishRecovery() external {
        Recovery memory r = recovery;
        if (r.newOwner == address(0)) revert NoRecovery();
        if (block.timestamp < r.readyAt) revert RecoveryNotReady(r.readyAt);
        delete recovery;
        _setOwner(r.newOwner);
    }

    // ------------------------------------------------------------------ ERC-1271

    /// @notice Valid if the owner signed `ZyrcleMessage(hash)` in this account's EIP-712 domain.
    function isValidSignature(bytes32 hash, bytes calldata signature) external view returns (bytes4) {
        bytes32 digest = _hashTypedDataV4(keccak256(abi.encode(MESSAGE_TYPEHASH, hash)));
        return _signedByOwner(digest, signature) ? IERC1271.isValidSignature.selector : bytes4(0xffffffff);
    }

    // ------------------------------------------------------------------ internals

    function _signedByOwner(bytes32 digest, bytes calldata signature) private view returns (bool) {
        (address signer, ECDSA.RecoverError err,) = ECDSA.tryRecoverCalldata(digest, signature);
        return err == ECDSA.RecoverError.NoError && signer == owner;
    }

    function _setOwner(address newOwner) private {
        emit OwnerChanged(owner, newOwner);
        owner = newOwner;
    }

    function _run(Call[] calldata calls) private {
        for (uint256 i; i < calls.length; ++i) {
            (bool ok, bytes memory reason) = calls[i].target.call{value: calls[i].value}(calls[i].data);
            if (!ok) revert CallFailed(i, reason);
        }
    }
}
