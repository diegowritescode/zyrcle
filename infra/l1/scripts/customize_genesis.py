#!/usr/bin/env python3
"""Turn the Avalanche CLI's default Subnet-EVM genesis into the ZyrcleChain genesis.

The CLI prefunds a freshly generated key with 1,000,000 coins and funds an ICM deployer. ZYR must
be backed by confirmed sales (docs/architecture.md, section 8), so this script:

- drops every funded account without code except the admin, which gets a small gas float;
- keeps the predeployed contracts (validator manager, proxy, proxy admin);
- enables the precompiles described in docs/adr/0002-own-avalanche-l1.md.

Usage: customize_genesis.py <cli-genesis.json> <admin-address> <admin-float-zyr> <out.json>
"""

import json
import sys

PRECOMPILES = (
    "contractNativeMinterConfig",
    "contractDeployerAllowListConfig",
    "feeManagerConfig",
    "rewardManagerConfig",
)
WEI_PER_ZYR = 10**18


def customize(genesis: dict, admin: str, admin_float_zyr: int) -> dict:
    admin_key = admin.lower().removeprefix("0x")
    if len(admin_key) != 40 or any(c not in "0123456789abcdef" for c in admin_key):
        raise ValueError(f"not an EVM address: {admin}")

    alloc = {
        addr: acct
        for addr, acct in genesis["alloc"].items()
        if acct.get("code") and acct["code"] != "0x"
    }
    alloc[admin_key] = {"balance": hex(admin_float_zyr * WEI_PER_ZYR)}
    genesis["alloc"] = alloc

    admins = ["0x" + admin_key]
    for name in PRECOMPILES:
        genesis["config"][name] = {"blockTimestamp": 0, "adminAddresses": admins}
    if "warpConfig" not in genesis["config"]:
        raise ValueError("warpConfig missing: create the chain with --warp")
    return genesis


def check(genesis: dict, admin: str, admin_float_zyr: int) -> None:
    funded = {
        addr: int(acct.get("balance", "0x0"), 16)
        for addr, acct in genesis["alloc"].items()
        if int(acct.get("balance", "0x0"), 16) > 0
    }
    assert funded == {admin.lower().removeprefix("0x"): admin_float_zyr * WEI_PER_ZYR}, funded
    for name in PRECOMPILES:
        assert genesis["config"][name]["adminAddresses"] == [admin.lower()], name


def main() -> None:
    src, admin, admin_float, out = sys.argv[1:5]
    with open(src) as f:
        genesis = json.load(f)
    genesis = customize(genesis, admin, int(admin_float))
    check(genesis, admin, int(admin_float))
    with open(out, "w") as f:
        json.dump(genesis, f, indent=2)
        f.write("\n")
    total = sum(int(a.get("balance", "0x0"), 16) for a in genesis["alloc"].values())
    print(f"genesis written to {out}; total supply at genesis: {total / WEI_PER_ZYR:g} ZYR")


if __name__ == "__main__":
    main()
