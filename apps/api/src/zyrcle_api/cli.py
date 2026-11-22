"""zyrcle-api command line.

  zyrcle-api serve [--host 0.0.0.0] [--port 8000]
  zyrcle-api chain deploy --admin-key-file F --operator 0x.. --oracle 0x..   deploy + enable minting
  zyrcle-api chain seed --operator-key-file F --amount-cop N --ref TEXT      record seed capital
  zyrcle-api chain state                                                     backing, minted, ...

Chain commands use ZYRCLE_CHAIN_RPC_URL and, except deploy, ZYRCLE_TREASURY_ADDRESS. Keys are read
from files so they never appear in process arguments.
"""

import argparse
import asyncio

import uvicorn

from .chain import Chain, load_account_file
from .config import get_settings
from .main import create_app


async def _chain(args: argparse.Namespace) -> None:
    settings = get_settings()
    if not settings.chain_rpc_url:
        raise SystemExit("set ZYRCLE_CHAIN_RPC_URL")
    if args.action == "deploy":
        chain = Chain(settings.chain_rpc_url)
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
    if not settings.treasury_address:
        raise SystemExit("set ZYRCLE_TREASURY_ADDRESS")
    chain = Chain(settings.chain_rpc_url, settings.treasury_address)
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

    args = parser.parse_args()
    if args.cmd == "serve":
        uvicorn.run(create_app(), host=args.host, port=args.port, proxy_headers=True)
    else:
        asyncio.run(_chain(args))


if __name__ == "__main__":
    main()
