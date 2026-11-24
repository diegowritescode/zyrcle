"""`zyrcle-api safe …`: the Safe that holds ZyrcleChain's admin powers (docs/adr/0040).

  safe deploy   --admin-key-file F --owners A,B,C --threshold 2   deploy the Safe
  safe status   --safe S --admin A                                who holds each power
  safe grant    --admin-key-file F --safe S                       step 1: the Safe gets them too
  safe propose  --safe S --what proof --out FILE                  step 2: prove the Safe works
  safe own      --admin-key-file F --safe S                       step 3: ownerships to the Safe
  safe propose  --safe S --what revoke --admin A --multisend M --out FILE   step 4
  safe renounce --admin-key-file F --safe S                       step 5: the admin key gives up
  safe propose  --safe S --what guardian --guardian G --multisend M --out FILE   new guardian
  safe propose  --safe S --what call --to T --function "f(type,…)" --args A …
                --description TEXT --out FILE                    any later admin change
                (or --data 0x… instead of --function and --args)
  safe sign     --proposal FILE --key-file F|-                    sign with a key (- asks for it)
  safe exec     --proposal FILE --key-file F                      send it once two owners signed

Owners with a wallet sign proposals on the web app's multisig page instead of `safe sign`. Uses
ZYRCLE_CHAIN_RPC_URL, ZYRCLE_TREASURY_ADDRESS and ZYRCLE_ACCOUNT_FACTORY_ADDRESS.
"""

import argparse
import getpass
import os
import pathlib

from .chain import Chain, load_account, load_account_file
from .multisig import Proposal, sign_with_key
from .safe_ops import SafeOps


def add_parser(sub) -> None:
    safe = sub.add_parser("safe").add_subparsers(dest="action", required=True)
    deploy = safe.add_parser("deploy")
    deploy.add_argument("--admin-key-file", required=True)
    deploy.add_argument("--owners", required=True, help="comma-separated addresses")
    deploy.add_argument("--threshold", type=int, required=True)
    status = safe.add_parser("status")
    status.add_argument("--safe")
    status.add_argument("--admin", required=True)
    for name in ("grant", "own", "renounce"):
        step = safe.add_parser(name)
        step.add_argument("--admin-key-file", required=True)
        step.add_argument("--safe", required=True)
    propose = safe.add_parser("propose")
    propose.add_argument("--safe", required=True)
    propose.add_argument("--what", choices=["proof", "revoke", "guardian", "call"], required=True)
    propose.add_argument("--guardian", help="the new guardian's address (guardian)")
    propose.add_argument("--to", help="the contract to call (call)")
    propose.add_argument("--data", help="the calldata, 0x… (call; or --function and --args)")
    propose.add_argument("--function", help='e.g. "pause()" or "grantRole(bytes32,address)" (call)')
    propose.add_argument("--args", nargs="*", default=[], help="the function's arguments, in order")
    propose.add_argument("--description", help="what it does, in plain words (call)")
    propose.add_argument("--admin", help="the admin key's address (revoke)")
    propose.add_argument("--multisend", help="the MultiSendCallOnly address (revoke)")
    propose.add_argument("--out", required=True)
    sign = safe.add_parser("sign")
    sign.add_argument("--proposal", required=True)
    sign.add_argument("--key-file", required=True, help="a key file, or - to type the key")
    execute = safe.add_parser("exec")
    execute.add_argument("--proposal", required=True)
    execute.add_argument("--key-file", required=True, help="pays the gas; any funded key")


def calldata(function: str, values: list[str]) -> str:
    """ABI calldata from a signature and text arguments, so no other tool is needed on the server.
    A bytes32 argument that is not 0x-hex is hashed as text: OPERATOR_ROLE gives the role id."""
    from eth_abi import encode
    from eth_utils import function_signature_to_4byte_selector, keccak, to_checksum_address

    inner = function[function.index("(") + 1 : function.rindex(")")]
    types = [t.strip() for t in inner.split(",") if t.strip()]
    if len(types) != len(values):
        raise SystemExit(f"{function} takes {len(types)} arguments, got {len(values)}")

    def value(kind: str, text: str):
        if kind == "address":
            return to_checksum_address(text)
        if kind.startswith(("uint", "int")):
            return int(text, 0)
        if kind == "bool":
            return text.lower() in ("true", "1", "yes")
        if kind == "bytes32":
            raw = text.removeprefix("0x")
            is_hex = text.startswith("0x") and len(raw) == 64
            return bytes.fromhex(raw) if is_hex else keccak(text=text)
        if kind == "bytes":
            return bytes.fromhex(text.removeprefix("0x"))
        if kind == "string":
            return text
        raise SystemExit(f"type {kind} is not supported here; pass --data instead")

    selector = function_signature_to_4byte_selector(function.replace(" ", ""))
    encoded = encode(types, [value(t, v) for t, v in zip(types, values, strict=True)])
    return "0x" + (selector + encoded).hex()


def _key(path: str):
    if path == "-":
        return load_account(getpass.getpass("Clave privada del firmante (no se muestra): ").strip())
    return load_account_file(path)


async def run(args: argparse.Namespace) -> None:
    rpc = os.environ.get("ZYRCLE_CHAIN_RPC_URL")
    if not rpc:
        raise SystemExit("set ZYRCLE_CHAIN_RPC_URL")
    ops = SafeOps(
        Chain(rpc),
        os.environ.get("ZYRCLE_ACCOUNT_FACTORY_ADDRESS") or None,
        os.environ.get("ZYRCLE_TREASURY_ADDRESS") or None,
    )
    a = args.action
    if a == "deploy":
        owners = [o.strip() for o in args.owners.split(",") if o.strip()]
        stack = await ops.deploy(load_account_file(args.admin_key_file), owners, args.threshold)
        for name, address in stack.items():
            print(f"SAFE_{name.upper()}={address}" if name != "safe" else f"SAFE={address}")
    elif a == "status":
        for row in await ops.status(args.admin, args.safe):
            admin = "sí" if row["admin_key"] else "no"
            safe = "sí" if row["safe"] else "no"
            print(f"{row['power']:32} llave admin: {admin:3}  Safe: {safe}")
    elif a == "grant":
        done = await ops.grant_to_safe(load_account_file(args.admin_key_file), args.safe)
        print("granted to the Safe:", ", ".join(done) or "nothing left")
    elif a == "own":
        done = await ops.transfer_ownerships(load_account_file(args.admin_key_file), args.safe)
        print("ownership moved to the Safe:", ", ".join(done) or "nothing left")
    elif a == "renounce":
        done = await ops.renounce_roles(load_account_file(args.admin_key_file), args.safe)
        print("the admin key renounced:", ", ".join(done) or "nothing left")
    elif a == "propose":
        if args.what == "proof":
            p = await ops.proof_proposal(args.safe)
        elif args.what == "guardian":
            if not args.guardian or not args.multisend:
                raise SystemExit("guardian needs --guardian and --multisend")
            p = await ops.guardian_proposal(args.safe, args.guardian, args.multisend)
        elif args.what == "call":
            data = args.data or (calldata(args.function, args.args) if args.function else None)
            if not (args.to and data and args.description):
                raise SystemExit("call needs --to, --description and --data or --function")
            p = await ops.propose(args.safe, args.to, data, args.description)
        else:
            if not args.admin or not args.multisend:
                raise SystemExit("revoke needs --admin and --multisend")
            p = await ops.revoke_proposal(args.safe, args.admin, args.multisend)
        pathlib.Path(args.out).write_text(p.to_json() + "\n")
        print(f"{args.out}: {p.description}; hash {p.tx_hash()}")
    elif a == "sign":
        path = pathlib.Path(args.proposal)
        p = Proposal.from_json(path.read_text())
        key = _key(args.key_file)
        signer = p.add_signature(sign_with_key(p, key.key.hex()), await ops.owners(p.safe))
        path.write_text(p.to_json() + "\n")
        need = await ops.threshold(p.safe)
        print(f"signed by {signer}: {len(p.signatures)} of {need}")
    elif a == "exec":
        p = Proposal.from_json(pathlib.Path(args.proposal).read_text())
        tx = await ops.execute(load_account_file(args.key_file), p)
        print(f"executed: {tx}")
