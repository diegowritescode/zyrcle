"""zyrcle-sim: run simulated containers against a broker.

zyrcle-sim keygen --id ctr-0001 --out keys/       write keys/ctr-0001.pem and print the public key
zyrcle-sim run --broker localhost --password ... --key keys/ctr-0001.pem [--key ...]
"""

import argparse
import asyncio
import logging
import pathlib

from zyrcle_protocol import generate_private_key, load_private_key, public_key_pem
from zyrcle_protocol.keys import private_key_pem

from .container import SimulatedContainer
from .runner import DeviceRunner


def main() -> None:
    parser = argparse.ArgumentParser(prog="zyrcle-sim")
    sub = parser.add_subparsers(dest="cmd", required=True)
    kg = sub.add_parser("keygen")
    kg.add_argument("--id", required=True)
    kg.add_argument("--out", type=pathlib.Path, default=pathlib.Path("keys"))
    run = sub.add_parser("run")
    run.add_argument("--broker", default="localhost")
    run.add_argument("--port", type=int, default=1883)
    run.add_argument("--password", required=True)
    run.add_argument("--key", action="append", type=pathlib.Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    if args.cmd == "keygen":
        args.out.mkdir(parents=True, exist_ok=True)
        key = generate_private_key()
        path = args.out / f"{args.id}.pem"
        path.write_text(private_key_pem(key))
        path.chmod(0o600)
        print(public_key_pem(key), end="")
        return

    runners = [
        DeviceRunner(
            SimulatedContainer(p.stem),
            load_private_key(p.read_bytes()),
            args.broker,
            args.port,
            args.password,
        )
        for p in args.key
    ]

    async def _all() -> None:
        await asyncio.gather(*(r.run() for r in runners))

    asyncio.run(_all())


if __name__ == "__main__":
    main()
