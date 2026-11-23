"""Turn a local anvil into a ZyrcleChain stand-in: NativeMinter mock, Treasury, seed capital, and
the account factory (guardian = the oracle key). The operator key records sales (docs/adr/0013).

    anvil --chain-id 20261121 &
    python dev/local_chain.py            # prints the ZYRCLE_* variables for the API

Uses anvil's well-known development keys. Never point this at a real network.
"""

import asyncio
import json
import os
import pathlib

from zyrcle_api.chain import NATIVE_MINTER, Chain, load_account

RPC = os.environ.get("ANVIL_RPC", "http://127.0.0.1:8545")
HERE = pathlib.Path(__file__).parent
KEYS = {  # anvil accounts 0, 1 and 2
    "admin": "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    "operator": "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    "oracle": "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
}


async def main() -> None:
    chain = Chain(RPC)
    if await chain.w3.eth.chain_id != 20261121:
        raise SystemExit("start anvil with --chain-id 20261121 (the SIWE messages carry it)")
    mock = json.loads((HERE.parent / "tests" / "fixtures" / "AnvilNativeMinter.json").read_text())
    await chain.w3.provider.make_request("anvil_setCode", [NATIVE_MINTER, mock["deployedBytecode"]])
    await chain.w3.provider.make_request("anvil_setBalance", [NATIVE_MINTER, hex(10**30)])
    admin, operator, oracle = (load_account(KEYS[k]) for k in ("admin", "operator", "oracle"))
    address = await chain.deploy_treasury(admin, operator.address, oracle.address)
    await chain.enable_minting(admin)
    await chain.record_seed_capital(operator, "local-seed", 1_000_000)
    factory = await chain.deploy_account_factory(admin, oracle.address)
    key_file = HERE / ".local" / "oracle.key"
    key_file.parent.mkdir(exist_ok=True)
    key_file.write_text(KEYS["oracle"])
    key_file.chmod(0o600)
    operator_file = key_file.parent / "operator.key"
    operator_file.write_text(KEYS["operator"])
    operator_file.chmod(0o600)
    print(f"ZYRCLE_CHAIN_RPC_URL={RPC}")
    print(f"ZYRCLE_TREASURY_ADDRESS={address}")
    print(f"ZYRCLE_ORACLE_KEY_FILE={key_file}")
    print(f"ZYRCLE_OPERATOR_KEY_FILE={operator_file}")
    print(f"ZYRCLE_ACCOUNT_FACTORY_ADDRESS={factory}")
    print("ZYRCLE_EMAIL_LOG_ONLY=true")


if __name__ == "__main__":
    asyncio.run(main())
