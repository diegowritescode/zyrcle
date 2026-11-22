"""zyrcle-api command line.

  zyrcle-api serve [--host 0.0.0.0] [--port 8000]
  zyrcle-api chain deploy --admin-key-file F --operator 0x.. --oracle 0x..   deploy + enable minting
  zyrcle-api chain seed --operator-key-file F --amount-cop N --ref TEXT      record seed capital
  zyrcle-api chain state                                                     backing, minted, ...
  zyrcle-api chain accounts-deploy --admin-key-file F --guardian 0x..         account factory
  zyrcle-api chain accounts-guardian --admin-key-file F --guardian 0x..       replace guardian
  zyrcle-api demo seed --keys-dir DIR --devices ctr-0001,ctr-0002            register demo bins

Chain commands use ZYRCLE_CHAIN_RPC_URL and, except deploy, ZYRCLE_TREASURY_ADDRESS;
accounts-guardian also ZYRCLE_ACCOUNT_FACTORY_ADDRESS. The admin key is the precompile admin's: it
also puts the guardian on the deployer allow list. Keys are read from files so they never appear in
process arguments.
"""

import argparse
import asyncio
import os

import uvicorn

from .chain import Chain, load_account_file
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
    if not treasury:
        raise SystemExit("set ZYRCLE_TREASURY_ADDRESS")
    chain = Chain(rpc, treasury)
    if args.action == "seed":
        tx = await chain.record_seed_capital(
            load_account_file(args.operator_key_file), args.ref, args.amount_cop
        )
        print(f"seed capital of {args.amount_cop} COP recorded: {tx}")
    elif args.action == "state":
        for k, v in (await chain.state()).__dict__.items():
            print(f"{k:24} {v:>16,}")


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
    for name in ("accounts-deploy", "accounts-guardian"):
        accounts = chain.add_parser(name)
        accounts.add_argument("--admin-key-file", required=True)
        accounts.add_argument("--guardian", required=True, help="address of the guardian key")

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
    elif args.cmd == "demo":
        import pathlib

        from .demo_seed import seed

        devices = [d.strip() for d in args.devices.split(",") if d.strip()]
        for line in asyncio.run(seed(pathlib.Path(args.keys_dir), devices)) or ["nothing to do"]:
            print(line)
    else:
        asyncio.run(_chain(args))


if __name__ == "__main__":
    main()
