"""The Safe on ZyrcleChain: deploy it, execute signed proposals, and move the admin powers to it
(docs/adr/0040). The rules of the handover are in multisig.py."""

from dataclasses import dataclass
from typing import Any

from eth_account.signers.local import LocalAccount
from eth_utils import to_checksum_address
from web3.logs import DISCARD

from .chain import ALLOW_LIST_ABI, Chain, TxFailed, artifact
from .multisig import PRECOMPILES, ZERO, Proposal

VALIDATOR_MANAGER = "0x0Feedc0de0000000000000000000000000000000"
# EIP-1967: where a transparent proxy keeps the address of its admin.
PROXY_ADMIN_SLOT = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"
DEFAULT_ADMIN_ROLE = b"\x00" * 32
OWNABLE_ABI = [
    {
        "type": "function",
        "name": "owner",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
    },
    {
        "type": "function",
        "name": "transferOwnership",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "newOwner", "type": "address"}],
        "outputs": [],
    },
]
ROLE_ABI = [
    {
        "type": "function",
        "name": name,
        "stateMutability": "view" if name == "hasRole" else "nonpayable",
        "inputs": [{"name": "role", "type": "bytes32"}, {"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "bool"}] if name == "hasRole" else [],
    }
    for name in ("hasRole", "grantRole", "renounceRole")
]
SET_ADMIN_ABI = [
    *ALLOW_LIST_ABI,
    {
        "type": "function",
        "name": "setAdmin",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "addr", "type": "address"}],
        "outputs": [],
    },
]


@dataclass(frozen=True)
class Power:
    """One admin power: who holds it now is read from the chain."""

    name: str
    kind: str  # "precompile", "role", "owner"
    address: str


class SafeOps:
    def __init__(self, chain: Chain, factory_address: str | None, treasury_address: str | None):
        self.chain = chain
        self.w3 = chain.w3
        self.factory_address = factory_address
        self.treasury_address = treasury_address

    # ------------------------------------------------------------------ deploy

    async def _deploy(self, deployer: LocalAccount, name: str, *args) -> str:
        a = artifact(name)
        contract = self.w3.eth.contract(abi=a["abi"], bytecode=a["bytecode"])
        receipt = await self.chain._send(deployer, contract.constructor(*args))
        return receipt["contractAddress"]

    async def deploy(
        self, deployer: LocalAccount, owners: list[str], threshold: int, salt: int = 0
    ) -> dict[str, str]:
        """The Safe's singleton, proxy factory, fallback handler and batch helper, then a Safe."""
        if not 1 <= threshold <= len(owners) or len(set(o.lower() for o in owners)) != len(owners):
            raise ValueError("the threshold must be between 1 and the number of distinct owners")
        stack = {
            "singleton": await self._deploy(deployer, "SafeL2"),
            "factory": await self._deploy(deployer, "SafeProxyFactory"),
            "fallback_handler": await self._deploy(deployer, "CompatibilityFallbackHandler"),
            "multisend": await self._deploy(deployer, "MultiSendCallOnly"),
        }
        singleton = self.w3.eth.contract(address=stack["singleton"], abi=artifact("SafeL2")["abi"])
        setup = singleton.encode_abi(
            "setup",
            args=[
                [to_checksum_address(o) for o in owners],
                threshold,
                ZERO,
                b"",
                stack["fallback_handler"],
                ZERO,
                0,
                ZERO,
            ],
        )
        factory = self.w3.eth.contract(
            address=stack["factory"], abi=artifact("SafeProxyFactory")["abi"]
        )
        receipt = await self.chain._send(
            deployer, factory.functions.createProxyWithNonce(stack["singleton"], setup, salt)
        )
        created = factory.events.ProxyCreation().process_receipt(receipt, errors=DISCARD)
        stack["safe"] = created[0]["args"]["proxy"]
        return stack

    def safe(self, address: str):
        return self.w3.eth.contract(
            address=to_checksum_address(address), abi=artifact("SafeL2")["abi"]
        )

    async def owners(self, safe: str) -> list[str]:
        return list(await self.safe(safe).functions.getOwners().call())

    async def threshold(self, safe: str) -> int:
        return int(await self.safe(safe).functions.getThreshold().call())

    async def nonce(self, safe: str) -> int:
        return int(await self.safe(safe).functions.nonce().call())

    # ------------------------------------------------------------------ proposals

    async def propose(self, safe: str, to: str, data: str, description: str, operation: int = 0):
        return Proposal(
            safe=to_checksum_address(safe),
            chain_id=await self.w3.eth.chain_id,
            to=to_checksum_address(to),
            data=data,
            nonce=await self.nonce(safe),
            description=description,
            operation=operation,
        )

    async def onchain_hash(self, p: Proposal) -> str:
        h = await (
            self.safe(p.safe)
            .functions.getTransactionHash(
                p.to, p.value, p.data, p.operation, 0, 0, 0, ZERO, ZERO, p.nonce
            )
            .call()
        )
        return "0x" + bytes(h).hex()

    async def execute(self, executor: LocalAccount, p: Proposal) -> str:
        """Send a proposal that has enough signatures. The Safe checks them again on chain."""
        if await self.onchain_hash(p) != p.tx_hash():
            raise ValueError("this proposal does not match the Safe's own hash for it")
        if p.nonce != await self.nonce(p.safe):
            raise ValueError("the Safe has moved on: make the proposal again")
        if len(p.signatures) < await self.threshold(p.safe):
            raise ValueError(f"{len(p.signatures)} signatures; the Safe needs more")
        call = self.safe(p.safe).functions.execTransaction(
            p.to, p.value, p.data, p.operation, 0, 0, 0, ZERO, ZERO, p.packed_signatures()
        )
        receipt = await self.chain._send(executor, call)
        safe = self.safe(p.safe)
        if safe.events.ExecutionFailure().process_receipt(receipt, errors=DISCARD):
            raise TxFailed("ExecutionFailure", "the Safe ran the transaction and it failed")
        return receipt["transactionHash"].to_0x_hex()

    def multisend(self, multisend: str, calls: list[tuple[str, str]]) -> str:
        """Calldata for MultiSendCallOnly: several calls in one Safe transaction (delegatecall)."""
        packed = b""
        for to, data in calls:
            body = bytes.fromhex(data.removeprefix("0x"))
            packed += (
                b"\x00"
                + bytes.fromhex(to_checksum_address(to)[2:])
                + (0).to_bytes(32, "big")
                + len(body).to_bytes(32, "big")
                + body
            )
        contract = self.w3.eth.contract(
            address=to_checksum_address(multisend), abi=artifact("MultiSendCallOnly")["abi"]
        )
        return contract.encode_abi("multiSend", args=[packed])

    # ------------------------------------------------------------------ the powers

    async def proxy_admin(self) -> str | None:
        if len(await self.w3.eth.get_code(VALIDATOR_MANAGER)) == 0:
            return None
        raw = await self.w3.eth.get_storage_at(VALIDATOR_MANAGER, PROXY_ADMIN_SLOT)
        address = "0x" + bytes(raw)[-20:].hex()
        return None if int(address, 16) == 0 else to_checksum_address(address)

    async def powers(self) -> list[Power]:
        # An enabled precompile reports the code 0x01; one the chain does not enable has none.
        found = [
            Power(name, "precompile", addr)
            for name, addr in PRECOMPILES.items()
            if len(await self.w3.eth.get_code(to_checksum_address(addr))) > 0
        ]
        if self.treasury_address:
            found.append(Power("Treasury", "role", to_checksum_address(self.treasury_address)))
        if self.factory_address:
            found.append(Power("AccountFactory", "role", to_checksum_address(self.factory_address)))
        if len(await self.w3.eth.get_code(VALIDATOR_MANAGER)) > 0:
            found.append(Power("ValidatorManager", "owner", VALIDATOR_MANAGER))
            admin = await self.proxy_admin()
            if admin:
                found.append(Power("ValidatorManager proxy admin", "owner", admin))
        return found

    async def holds(self, power: Power, who: str) -> bool:
        who = to_checksum_address(who)
        if power.kind == "precompile":
            c = self.w3.eth.contract(address=to_checksum_address(power.address), abi=SET_ADMIN_ABI)
            return int(await c.functions.readAllowList(who).call()) == 2
        if power.kind == "role":
            c = self.w3.eth.contract(address=power.address, abi=ROLE_ABI)
            return bool(await c.functions.hasRole(DEFAULT_ADMIN_ROLE, who).call())
        c = self.w3.eth.contract(address=power.address, abi=OWNABLE_ABI)
        return to_checksum_address(await c.functions.owner().call()) == who

    async def status(self, admin: str, safe: str | None) -> list[dict[str, Any]]:
        rows = []
        for p in await self.powers():
            rows.append(
                {
                    "power": p.name,
                    "admin_key": await self.holds(p, admin),
                    "safe": await self.holds(p, safe) if safe else False,
                }
            )
        return rows

    # ------------------------------------------------------------------ the handover

    async def grant_to_safe(self, admin: LocalAccount, safe: str) -> list[str]:
        """Step 1, from the admin key: the Safe also gets every role and precompile admin."""
        done = []
        for p in await self.powers():
            if await self.holds(p, safe):
                continue
            if p.kind == "precompile":
                c = self.w3.eth.contract(address=to_checksum_address(p.address), abi=SET_ADMIN_ABI)
                await self.chain._send(admin, c.functions.setAdmin(to_checksum_address(safe)))
            elif p.kind == "role":
                c = self.w3.eth.contract(address=p.address, abi=ROLE_ABI)
                await self.chain._send(
                    admin, c.functions.grantRole(DEFAULT_ADMIN_ROLE, to_checksum_address(safe))
                )
            else:
                continue  # ownerships move in step 3, once the Safe has proved it works
            done.append(p.name)
        return done

    async def proof_proposal(self, safe: str) -> Proposal:
        """Step 2, signed by two owners: a change that changes nothing (the Safe grants itself a
        role it already has), to prove it can act before anything is taken from the admin key."""
        target = self.factory_address or self.treasury_address
        if not target:
            raise ValueError("set ZYRCLE_ACCOUNT_FACTORY_ADDRESS or ZYRCLE_TREASURY_ADDRESS")
        c = self.w3.eth.contract(address=to_checksum_address(target), abi=ROLE_ABI)
        data = c.encode_abi("grantRole", args=[DEFAULT_ADMIN_ROLE, to_checksum_address(safe)])
        note = "Prueba: el Safe puede actuar (no cambia nada)"
        return await self.propose(safe, target, data, note)

    async def transfer_ownerships(self, admin: LocalAccount, safe: str) -> list[str]:
        """Step 3, from the admin key: the validator manager and its proxy admin go to the Safe."""
        done = []
        for p in await self.powers():
            if p.kind != "owner" or await self.holds(p, safe):
                continue
            c = self.w3.eth.contract(address=p.address, abi=OWNABLE_ABI)
            await self.chain._send(admin, c.functions.transferOwnership(to_checksum_address(safe)))
            done.append(p.name)
        return done

    async def revoke_proposal(self, safe: str, admin: str, multisend: str) -> Proposal:
        """Step 4, signed by two owners: the Safe takes the admin key off every precompile."""
        calls = []
        for p in await self.powers():
            if p.kind == "precompile" and await self.holds(p, admin):
                c = self.w3.eth.contract(address=to_checksum_address(p.address), abi=SET_ADMIN_ABI)
                remove = c.encode_abi("setNone", args=[to_checksum_address(admin)])
                calls.append((p.address, remove))
        if not calls:
            raise ValueError("the admin key is on no precompile")
        data = self.multisend(multisend, calls)
        note = "Quitar la llave de administrador de las precompilas"
        return await self.propose(safe, multisend, data, note, operation=1)

    async def renounce_roles(self, admin: LocalAccount, safe: str) -> list[str]:
        """Step 5, from the admin key: it gives up its contract roles. Refuses while the Safe does
        not hold them."""
        done = []
        for p in await self.powers():
            if p.kind != "role" or not await self.holds(p, admin.address):
                continue
            if not await self.holds(p, safe):
                raise ValueError(f"the Safe does not hold {p.name} yet; run step 1 first")
            c = self.w3.eth.contract(address=p.address, abi=ROLE_ABI)
            await self.chain._send(
                admin, c.functions.renounceRole(DEFAULT_ADMIN_ROLE, admin.address)
            )
            done.append(p.name)
        return done
