// SPDX-License-Identifier: LGPL-3.0-only
pragma solidity 0.8.30;

// The Safe contracts the backend deploys (docs/adr/0040), compiled with the rest of the project so
// their artifacts are exported like the Treasury's. Sources: lib/safe-smart-account (v1.4.1).
import {SafeL2} from "../lib/safe-smart-account/contracts/SafeL2.sol";
import {SafeProxyFactory} from "../lib/safe-smart-account/contracts/proxies/SafeProxyFactory.sol";
import {
    CompatibilityFallbackHandler
} from "../lib/safe-smart-account/contracts/handler/CompatibilityFallbackHandler.sol";
import {MultiSendCallOnly} from "../lib/safe-smart-account/contracts/libraries/MultiSendCallOnly.sol";

/// @dev Nothing to deploy: it names the Safe contracts so the compiler builds them.
abstract contract SafeImports {
    function _safeContracts() internal pure returns (bytes32, bytes32, bytes32, bytes32) {
        return (
            keccak256(type(SafeL2).creationCode),
            keccak256(type(SafeProxyFactory).creationCode),
            keccak256(type(CompatibilityFallbackHandler).creationCode),
            keccak256(type(MultiSendCallOnly).creationCode)
        );
    }
}
