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
    ("AnvilNativeMinter.sol", "AnvilNativeMinter"): API / "tests" / "fixtures" / "AnvilNativeMinter.json",
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
