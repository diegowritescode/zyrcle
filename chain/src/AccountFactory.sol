// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.30;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {Clones} from "@openzeppelin/contracts/proxy/Clones.sol";
import {ZyrcleAccount} from "./ZyrcleAccount.sol";

/// @title Zyrcle account factory
/// @notice Creates residents' accounts as minimal clones of one ZyrcleAccount, at addresses that
///         depend only on the first owner key. The backend knows a resident's address the moment
///         they sign in, and the Treasury can pay it before any contract exists there; the account
///         is deployed only when it first needs to act (a recovery, a payment out).
///
///         It also names the guardian every account obeys for recoveries. Changing it here
///         changes it for all accounts at once, which is how a leaked guardian key is replaced.
contract AccountFactory is AccessControl {
    /// @notice The code every account runs. Deployed by this factory's constructor, so its address
    ///         is the factory's first CREATE (nonce 1).
    ZyrcleAccount public immutable IMPLEMENTATION;

    address public guardian;

    event AccountCreated(address indexed account, address indexed owner);
    event GuardianChanged(address indexed previousGuardian, address indexed newGuardian);

    error ZeroAddress();

    constructor(address admin, address initialGuardian) {
        if (admin == address(0)) revert ZeroAddress();
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        IMPLEMENTATION = new ZyrcleAccount(address(this));
        _setGuardian(initialGuardian);
    }

    /// @notice Deploy the account first owned by `owner`, or return it if it already exists.
    function createAccount(address owner) external returns (address account) {
        account = predict(owner);
        if (account.code.length > 0) return account;
        Clones.cloneDeterministic(address(IMPLEMENTATION), _salt(owner));
        ZyrcleAccount(payable(account)).initialize(owner);
        emit AccountCreated(account, owner);
    }

    /// @notice The address of the account first owned by `owner`, deployed or not.
    function predict(address owner) public view returns (address) {
        return Clones.predictDeterministicAddress(address(IMPLEMENTATION), _salt(owner));
    }

    function setGuardian(address newGuardian) external onlyRole(DEFAULT_ADMIN_ROLE) {
        _setGuardian(newGuardian);
    }

    function _setGuardian(address newGuardian) private {
        if (newGuardian == address(0)) revert ZeroAddress();
        emit GuardianChanged(guardian, newGuardian);
        guardian = newGuardian;
    }

    function _salt(address owner) private pure returns (bytes32) {
        return bytes32(uint256(uint160(owner)));
    }
}
