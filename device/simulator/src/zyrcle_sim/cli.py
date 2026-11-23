"""zyrcle-sim: run simulated containers against a broker.

zyrcle-sim keygen --id ctr-0001 --out keys/       write keys/ctr-0001.pem and print the public key
zyrcle-sim run --broker localhost --password ... --key keys/ctr-0001.pem [--key ...]
"""

import argparse
import asyncio
import logging
import os
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
    serve = sub.add_parser("serve")
    serve.add_argument("--broker", default="localhost")
    serve.add_argument("--port", type=int, default=1883)
    serve.add_argument("--keys-dir", type=pathlib.Path, required=True)
    serve.add_argument("--devices", required=True, help="comma-separated device ids")
    serve.add_argument("--control-host", default="0.0.0.0")
    serve.add_argument("--control-port", type=int, default=8090)
    serve.add_argument("--reading-interval", type=float, default=0.5)
    serve.add_argument(
        "--state-dir",
        type=pathlib.Path,
        help="where each container saves its contents (default: the keys dir)",
    )
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

    if args.cmd == "serve":
        asyncio.run(_serve(args))
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


def _load_or_create_key(keys_dir: pathlib.Path, device_id: str):
    keys_dir.mkdir(parents=True, exist_ok=True)
    path = keys_dir / f"{device_id}.pem"
    if not path.exists():
        path.write_text(private_key_pem(generate_private_key()))
        path.chmod(0o600)
        (keys_dir / f"{device_id}.pub.pem").write_text(
            public_key_pem(load_private_key(path.read_bytes()))
        )
    return load_private_key(path.read_bytes())


async def _serve(args: argparse.Namespace) -> None:
    import uvicorn

    from .control import create_control_app

    runners = {}
    state_dir = args.state_dir or args.keys_dir
    state_dir.mkdir(parents=True, exist_ok=True)
    for device_id in [d.strip() for d in args.devices.split(",") if d.strip()]:
        env = "ZYRCLE_SIM_PASSWORD_" + device_id.upper().replace("-", "_")
        password = os.environ.get(env) or os.environ.get("ZYRCLE_SIM_PASSWORD")
        runners[device_id] = DeviceRunner(
            SimulatedContainer(device_id, state_path=state_dir / f"{device_id}.state.json"),
            _load_or_create_key(args.keys_dir, device_id),
            args.broker,
            args.port,
            password,
            reading_interval_s=args.reading_interval,
        )

    async def keep_running(runner: DeviceRunner) -> None:
        while True:  # reconnect forever: the broker may restart
            try:
                await runner.run()
            except Exception as e:
                logging.warning("%s disconnected (%s); retrying in 3 s", runner.c.device_id, e)
            await asyncio.sleep(3)

    server = uvicorn.Server(
        uvicorn.Config(
            create_control_app(runners),
            host=args.control_host,
            port=args.control_port,
            log_level="warning",
        )
    )
    await asyncio.gather(server.serve(), *(keep_running(r) for r in runners.values()))
