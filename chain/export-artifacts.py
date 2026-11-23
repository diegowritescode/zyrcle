#!/usr/bin/env python3
"""Copy the compiled contracts the backend uses into the API package.

Run after `forge build`. CI runs it too and fails if the checked-in files differ, so the ABI and
bytecode the backend deploys always match the Solidity source.
"""

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
API = HERE.parent / "apps" / "api"
TARGETS = {
    ("Treasury.sol", "Treasury"): API / "src" / "zyrcle_api" / "contracts" / "Treasury.json",
    ("AccountFactory.sol", "AccountFactory"): API / "src" / "zyrcle_api" / "contracts" / "AccountFactory.json",
    ("ZyrcleAccount.sol", "ZyrcleAccount"): API / "src" / "zyrcle_api" / "contracts" / "ZyrcleAccount.json",
    ("AnvilNativeMinter.sol", "AnvilNativeMinter"): API / "tests" / "fixtures" / "AnvilNativeMinter.json",
    ("OwnableMock.sol", "OwnableMock"): API / "tests" / "fixtures" / "OwnableMock.json",
    # The Safe the admin powers move to (docs/adr/0040), from lib/safe-smart-account v1.4.1.
    ("SafeL2.sol", "SafeL2"): API / "src" / "zyrcle_api" / "contracts" / "SafeL2.json",
    ("SafeProxyFactory.sol", "SafeProxyFactory"): API / "src" / "zyrcle_api" / "contracts" / "SafeProxyFactory.json",
    ("CompatibilityFallbackHandler.sol", "CompatibilityFallbackHandler"): API / "src" / "zyrcle_api" / "contracts" / "CompatibilityFallbackHandler.json",
    ("MultiSendCallOnly.sol", "MultiSendCallOnly"): API / "src" / "zyrcle_api" / "contracts" / "MultiSendCallOnly.json",
}

for (source, name), target in TARGETS.items():
    artifact = json.loads((HERE / "out" / source / f"{name}.json").read_text())
    target.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "contractName": name,
        "abi": artifact["abi"],
        "bytecode": artifact["bytecode"]["object"],
        "deployedBytecode": artifact["deployedBytecode"]["object"],
    }
    target.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(f"wrote {target.relative_to(HERE.parent)}")
