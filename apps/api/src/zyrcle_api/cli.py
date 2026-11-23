"""zyrcle-api command line.

  zyrcle-api serve [--host 0.0.0.0] [--port 8000]
  zyrcle-api chain deploy --admin-key-file F --operator 0x.. --oracle 0x..   deploy + enable minting
  zyrcle-api chain seed --operator-key-file F --amount-cop N --ref TEXT      record seed capital
  zyrcle-api chain state                                                     backing, minted, ...
  zyrcle-api chain accounts-deploy --admin-key-file F --guardian 0x..         account factory
  zyrcle-api chain accounts-guardian --admin-key-file F --guardian 0x..       replace guardian
  zyrcle-api chain minter-revoke --admin-key-file F --address 0x..            retire old Treasury
  zyrcle-api chain fund --from-key-file F --to 0x.. --amount-zyr N            gas for a key
  zyrcle-api chain balance --address 0x..                                     native ZYR balance
  zyrcle-api demo seed --keys-dir DIR --devices ctr-0001,ctr-0002            register demo bins
  zyrcle-api keys new --out FILE                                             new key file, 0600
  zyrcle-api safe …                                                          the admin Safe

Chain commands use ZYRCLE_CHAIN_RPC_URL and, except deploy, fund and balance,
ZYRCLE_TREASURY_ADDRESS (minter-revoke refuses to revoke that one);
accounts-guardian also ZYRCLE_ACCOUNT_FACTORY_ADDRESS. The admin key is the precompile admin's: it
also puts the guardian on the deployer allow list. Keys are read from files so they never appear in
process arguments.
"""

import argparse
import asyncio
import os
import pathlib
from decimal import Decimal

import uvicorn

from . import safe_cli
from .chain import WEI_PER_COP, Chain, load_account_file
from .main import create_app


async def _chain(args: argparse.Namespace) -> None:
    # Only the chain variables: these commands must run without the API's secrets.
    rpc = os.environ.get("ZYRCLE_CHAIN_RPC_URL")
    treasury = os.environ.get("ZYRCLE_TREASURY_ADDRESS")
    if not rpc:
        raise SystemExit("set ZYRCLE_CHAIN_RPC_URL")
    if args.action == "deploy":
        chain = Chain(rpc)
        admin = load_account_file(args.admin_key_file)
        address = await chain.deploy_treasury(
            admin,
            args.operator,
            args.oracle,
            max_advance_cop=args.max_advance_cop,
            daily_cap_cop=args.daily_cap_cop,
        )
        await chain.enable_minting(admin)
        print(f"Treasury deployed at {address} and enabled on the NativeMinter")
        return
    if args.action == "accounts-deploy":
        chain = Chain(rpc)
        admin = load_account_file(args.admin_key_file)
        address = await chain.deploy_account_factory(admin, args.guardian)
        await chain.allow_deployer(admin, args.guardian)
        print(f"AccountFactory deployed at {address}; guardian {args.guardian} may deploy accounts")
        print(f"ZYRCLE_ACCOUNT_FACTORY_ADDRESS={address}")
        return
    if args.action == "accounts-guardian":
        factory = os.environ.get("ZYRCLE_ACCOUNT_FACTORY_ADDRESS")
        if not factory:
            raise SystemExit("set ZYRCLE_ACCOUNT_FACTORY_ADDRESS")
        chain = Chain(rpc, factory_address=factory)
        admin = load_account_file(args.admin_key_file)
        await chain.allow_deployer(admin, args.guardian)
        tx = await chain.set_guardian(admin, args.guardian)
        print(f"guardian is now {args.guardian}: {tx}")
        return
    if args.action == "fund":
        chain = Chain(rpc)
        sender = load_account_file(args.from_key_file)
        wei = int(Decimal(args.amount_zyr) * WEI_PER_COP)
        if wei <= 0:
            raise SystemExit("the amount must be positive")
        tx = await chain.transfer_native(sender, args.to, wei)
        left = await chain.balance_wei(sender.address)
        print(f"sent {args.amount_zyr} ZYR to {args.to}: {tx}")
        print(f"{args.to} now holds {Decimal(await chain.balance_wei(args.to)) / WEI_PER_COP} ZYR")
        print(f"{sender.address} keeps {Decimal(left) / WEI_PER_COP} ZYR")
        return
    if args.action == "balance":
        wei = await Chain(rpc).balance_wei(args.address)
        print(f"{args.address} {Decimal(wei) / WEI_PER_COP} ZYR")
        return
    if not treasury:
        raise SystemExit("set ZYRCLE_TREASURY_ADDRESS")
    chain = Chain(rpc, treasury)
    if args.action == "minter-revoke":
        if args.address.lower() == treasury.lower():
            raise SystemExit("that is the Treasury in use (ZYRCLE_TREASURY_ADDRESS); not revoked")
        if await chain.minting_role(args.address) == 0:
            print(f"{args.address} is not on the NativeMinter allow list; nothing to do")
            return
        await chain.disable_minting(load_account_file(args.admin_key_file), args.address)
        print(f"{args.address} removed from the NativeMinter allow list")
        return
    if args.action == "seed":
        tx = await chain.record_seed_capital(
            load_account_file(args.operator_key_file), args.ref, args.amount_cop
        )
        print(f"seed capital of {args.amount_cop} COP recorded: {tx}")
    elif args.action == "state":
        for k, v in (await chain.state()).__dict__.items():
            print(f"{k:24} {v:>16,}")


def new_key_file(path: pathlib.Path) -> str:
    """A fresh key in a file only its owner can read. The key itself is never printed."""
    from eth_account import Account

    if path.exists():
        raise SystemExit(f"{path} exists; not overwritten")
    account = Account.create()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(account.key.hex() + "\n")
    return account.address


def main() -> None:
    parser = argparse.ArgumentParser(prog="zyrcle-api")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    chain = sub.add_parser("chain").add_subparsers(dest="action", required=True)
    deploy = chain.add_parser("deploy")
    deploy.add_argument("--admin-key-file", required=True)
    deploy.add_argument("--operator", required=True)
    deploy.add_argument("--oracle", required=True)
    deploy.add_argument("--max-advance-cop", type=int, default=5_000)
    deploy.add_argument("--daily-cap-cop", type=int, default=20_000)
    seed = chain.add_parser("seed")
    seed.add_argument("--operator-key-file", required=True)
    seed.add_argument("--amount-cop", type=int, required=True)
    seed.add_argument("--ref", required=True, help="e.g. the bank transfer reference")
    chain.add_parser("state")
    revoke = chain.add_parser("minter-revoke")
    revoke.add_argument("--admin-key-file", required=True)
    revoke.add_argument("--address", required=True, help="the retired Treasury")
    fund = chain.add_parser("fund")
    fund.add_argument("--from-key-file", required=True)
    fund.add_argument("--to", required=True)
    fund.add_argument("--amount-zyr", required=True, help="e.g. 20 or 0.5")
    balance = chain.add_parser("balance")
    balance.add_argument("--address", required=True)
    for name in ("accounts-deploy", "accounts-guardian"):
        accounts = chain.add_parser(name)
        accounts.add_argument("--admin-key-file", required=True)
        accounts.add_argument("--guardian", required=True, help="address of the guardian key")

    safe_cli.add_parser(sub)
    keys = sub.add_parser("keys").add_subparsers(dest="action", required=True)
    new_key = keys.add_parser("new", help="write a new key to a 0600 file, print its address")
    new_key.add_argument("--out", required=True)
    demo = sub.add_parser("demo").add_subparsers(dest="action", required=True)
    demo_seed = demo.add_parser("seed")
    demo_seed.add_argument("--keys-dir", required=True)
    demo_seed.add_argument("--devices", required=True)

    args = parser.parse_args()
    if args.cmd == "serve":
        uvicorn.run(
            create_app(),
            host=args.host,
            port=args.port,
            proxy_headers=True,
            forwarded_allow_ips="*",
        )
    elif args.cmd == "safe":
        asyncio.run(safe_cli.run(args))
    elif args.cmd == "keys":
        print(new_key_file(pathlib.Path(args.out)))
    elif args.cmd == "demo":
        from .demo_seed import seed

        devices = [d.strip() for d in args.devices.split(",") if d.strip()]
        for line in asyncio.run(seed(pathlib.Path(args.keys_dir), devices)) or ["nothing to do"]:
            print(line)
    else:
        asyncio.run(_chain(args))


if __name__ == "__main__":
    main()
