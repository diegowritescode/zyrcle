"""ZyrcleChain access: deploys and talks to the Treasury and the residents' accounts with
backend-held keys.

ZYR is the chain's native coin: 1 ZYR = 1 COP, and 1e18 wei = 1 peso. Amounts cross this module's
boundary as integer pesos and are converted to wei here.
"""

import json
import uuid
from dataclasses import dataclass
from importlib import resources
from typing import Any

from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_utils import keccak, to_checksum_address
from web3 import AsyncHTTPProvider, AsyncWeb3
from web3.exceptions import ContractCustomError, ContractLogicError
from web3.middleware import ExtraDataToPOAMiddleware

WEI_PER_COP = 10**18
NATIVE_MINTER = "0x0200000000000000000000000000000000000001"
DEPLOYER_ALLOW_LIST = "0x0200000000000000000000000000000000000000"
ALLOW_LIST_ABI = [
    {
        "type": "function",
        "name": "setEnabled",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "addr", "type": "address"}],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "setNone",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "addr", "type": "address"}],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "readAllowList",
        "stateMutability": "view",
        "inputs": [{"name": "addr", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]


def artifact(name: str) -> dict[str, Any]:
    text = resources.files("zyrcle_api.contracts").joinpath(f"{name}.json").read_text()
    return json.loads(text)


def treasury_artifact() -> dict[str, Any]:
    return artifact("Treasury")


# EIP-1167 minimal proxy creation code, around the implementation address (OpenZeppelin Clones).
_CLONE_PREFIX = bytes.fromhex("3d602d80600a3d3981f3363d3d373d3d3d363d73")
_CLONE_SUFFIX = bytes.fromhex("5af43d82803e903d91602b57fd5bf3")


def _bytes20(address: str) -> bytes:
    raw = bytes.fromhex(address.removeprefix("0x"))
    if len(raw) != 20:
        raise ValueError(f"not an address: {address}")
    return raw


def implementation_address(factory: str) -> str:
    """The ZyrcleAccount the factory deployed in its constructor: its first CREATE (nonce 1)."""
    rlp = b"\xd6\x94" + _bytes20(factory) + b"\x01"
    return "0x" + keccak(rlp)[12:].hex()


def account_address(factory: str, owner: str) -> str:
    """The account first owned by `owner` (AccountFactory.predict), lowercase. Pure: works before
    the account is deployed and while the chain is unreachable."""
    init_code = _CLONE_PREFIX + _bytes20(implementation_address(factory)) + _CLONE_SUFFIX
    salt = _bytes20(owner).rjust(32, b"\0")
    digest = keccak(b"\xff" + _bytes20(factory) + salt + keccak(init_code))
    return "0x" + digest[12:].hex()


def deposit_id(session_id: uuid.UUID) -> bytes:
    """The Treasury's bytes32 id for a deposit session (the UUID, left-padded)."""
    return session_id.bytes.rjust(32, b"\0")


def sale_id(line_id: uuid.UUID) -> bytes:
    """The Treasury's bytes32 id for one bag of a sale (docs/adr/0013)."""
    return keccak(b"zyrcle-sale-line:" + line_id.bytes)


def redemption_ref(request_id: uuid.UUID) -> bytes:
    """The Treasury's bytes32 reference for a redemption request (docs/adr/0029)."""
    return keccak(b"zyrcle-redemption:" + request_id.bytes)


def load_account(key_hex: str) -> LocalAccount:
    key = key_hex.strip()
    return Account.from_key(key if key.startswith("0x") else "0x" + key)


def load_account_file(path: str) -> LocalAccount:
    with open(path) as f:
        return load_account(f.read())


class TxFailed(Exception):
    """A transaction would revert or did revert. `error` is the contract error name if known."""

    def __init__(self, error: str, detail: str = ""):
        super().__init__(f"{error}: {detail}" if detail else error)
        self.error = error


@dataclass(frozen=True)
class PendingRecovery:
    new_owner: str | None  # lowercase, None if no recovery is pending
    ready_at: int  # unix seconds (chain time)


@dataclass(frozen=True)
class OnChainSale:
    """A sale as the Treasury holds it, in wei."""

    amount: int
    residents_part: int
    collector_part: int
    host_part: int
    residents_settled: int
    collector_paid: int
    host_paid: int

    @property
    def recorded(self) -> bool:
        return self.amount > 0


@dataclass(frozen=True)
class Shares:
    """Basis points of each sale (they add up to 10,000)."""

    residents: int
    collector: int
    host: int
    operations: int


@dataclass(frozen=True)
class TreasuryState:
    backing_cop: int
    minted_cop: int
    available_cop: int
    seed_capital_cop: int
    operations_revenue_cop: int


class Chain:
    def __init__(
        self,
        rpc_url: str,
        treasury_address: str | None = None,
        factory_address: str | None = None,
    ):
        self.w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
        # Subnet-EVM block headers carry 80+ bytes of extraData (fee window); web3.py rejects
        # anything over 32 unless this middleware strips it.
        self.w3.middleware_onion.inject(
            ExtraDataToPOAMiddleware, name="subnet_evm_extradata", layer=0
        )
        treasury = treasury_artifact()
        self._abi = treasury["abi"]
        self._bytecode = treasury["bytecode"]
        factory, account = artifact("AccountFactory"), artifact("ZyrcleAccount")
        self._factory_artifact, self._account_abi = factory, account["abi"]
        self._errors = {
            "0x"
            + keccak(text=f"{e['name']}({','.join(i['type'] for i in e['inputs'])})")[:4].hex(): e[
                "name"
            ]
            for abi in (self._abi, factory["abi"], account["abi"])
            for e in abi
            if e["type"] == "error"
        }
        self.treasury = (
            self.w3.eth.contract(address=to_checksum_address(treasury_address), abi=self._abi)
            if treasury_address
            else None
        )
        self.minter = self.w3.eth.contract(
            address=to_checksum_address(NATIVE_MINTER), abi=ALLOW_LIST_ABI
        )
        self.deployers = self.w3.eth.contract(
            address=to_checksum_address(DEPLOYER_ALLOW_LIST), abi=ALLOW_LIST_ABI
        )
        self.factory = (
            self.w3.eth.contract(address=to_checksum_address(factory_address), abi=factory["abi"])
            if factory_address
            else None
        )

    # ------------------------------------------------------------------ deployment

    async def deploy_treasury(
        self,
        admin: LocalAccount,
        operator: str,
        oracle: str,
        # residents, collector, host, operations (docs/adr/0013)
        shares_bps: tuple[int, int, int, int] = (6_500, 1_500, 1_000, 1_000),
        max_advance_cop: int = 5_000,
        daily_cap_cop: int = 20_000,
    ) -> str:
        factory = self.w3.eth.contract(abi=self._abi, bytecode=self._bytecode)
        receipt = await self._send(
            admin,
            factory.constructor(
                admin.address,
                shares_bps,
                max_advance_cop * WEI_PER_COP,
                daily_cap_cop * WEI_PER_COP,
            ),
        )
        address = receipt["contractAddress"]
        self.treasury = self.w3.eth.contract(address=address, abi=self._abi)
        operator_role = await self.treasury.functions.OPERATOR_ROLE().call()
        oracle_role = await self.treasury.functions.ORACLE_ROLE().call()
        await self._send(
            admin, self.treasury.functions.grantRole(operator_role, to_checksum_address(operator))
        )
        await self._send(
            admin, self.treasury.functions.grantRole(oracle_role, to_checksum_address(oracle))
        )
        return address

    async def enable_minting(self, admin: LocalAccount) -> None:
        """Put the Treasury on the NativeMinter allow list (admin = precompile admin)."""
        assert self.treasury is not None
        await self._send(admin, self.minter.functions.setEnabled(self.treasury.address))
        if await self.minter.functions.readAllowList(self.treasury.address).call() < 1:
            raise TxFailed("NotEnabled", "the Treasury is not on the NativeMinter allow list")

    async def disable_minting(self, admin: LocalAccount, address: str) -> None:
        """Take `address` off the NativeMinter allow list: a retired Treasury can no longer mint,
        whatever backing it has left (docs/infrastructure.md, runbook 9.6)."""
        addr = to_checksum_address(address)
        await self._send(admin, self.minter.functions.setNone(addr))
        if await self.minter.functions.readAllowList(addr).call() != 0:
            raise TxFailed("StillEnabled", f"{addr} is still on the NativeMinter allow list")

    async def minting_role(self, address: str) -> int:
        """0 none, 1 enabled, 2 admin, 3 manager on the NativeMinter allow list."""
        return await self.minter.functions.readAllowList(to_checksum_address(address)).call()

    # ------------------------------------------------------------------ treasury operations

    async def record_seed_capital(self, operator: LocalAccount, ref: str, amount_cop: int) -> str:
        assert self.treasury is not None
        receipt = await self._send(
            operator,
            self.treasury.functions.recordSeedCapital(keccak(text=ref), amount_cop * WEI_PER_COP),
        )
        return receipt["transactionHash"].to_0x_hex()

    async def pay_advance(
        self, oracle: LocalAccount, session_id: uuid.UUID, resident: str, amount_cop: int
    ) -> str:
        assert self.treasury is not None
        receipt = await self._send(
            oracle,
            self.treasury.functions.payAdvance(
                deposit_id(session_id), to_checksum_address(resident), amount_cop * WEI_PER_COP
            ),
        )
        return receipt["transactionHash"].to_0x_hex()

    async def advance_of(self, session_id: uuid.UUID) -> int:
        """Advance already paid for this deposit, in pesos (0 if none)."""
        assert self.treasury is not None
        wei = await self.treasury.functions.advanceOf(deposit_id(session_id)).call()
        return wei // WEI_PER_COP

    # ------------------------------------------------------------------ sales (ADR 0013)

    async def shares(self) -> Shares:
        assert self.treasury is not None
        return Shares(*(await self.treasury.functions.shares().call()))

    async def sale(self, line_id: uuid.UUID) -> OnChainSale:
        assert self.treasury is not None
        (
            amount,
            residents,
            collector,
            host,
            settled,
            collector_paid,
            host_paid,
            _,
        ) = await self.treasury.functions.sales(sale_id(line_id)).call()
        return OnChainSale(amount, residents, collector, host, settled, collector_paid, host_paid)

    async def deposit_settled(self, session_id: uuid.UUID) -> bool:
        assert self.treasury is not None
        return await self.treasury.functions.depositSettled(deposit_id(session_id)).call()

    async def record_sale(
        self, operator: LocalAccount, line_id: uuid.UUID, amount_cop: int, evidence: bytes
    ) -> str:
        assert self.treasury is not None
        receipt = await self._send(
            operator,
            self.treasury.functions.recordSale(
                sale_id(line_id), amount_cop * WEI_PER_COP, evidence
            ),
        )
        return receipt["transactionHash"].to_0x_hex()

    async def settle_residents(
        self,
        oracle: LocalAccount,
        line_id: uuid.UUID,
        shares: list[tuple[uuid.UUID, str, int]],
        report_hash: bytes,
    ) -> str:
        """Pay each (deposit, account, share in pesos) its share minus its advance."""
        assert self.treasury is not None
        receipt = await self._send(
            oracle,
            self.treasury.functions.settleResidents(
                sale_id(line_id),
                [deposit_id(d) for d, _, _ in shares],
                [to_checksum_address(a) for _, a, _ in shares],
                [cop * WEI_PER_COP for _, _, cop in shares],
                report_hash,
            ),
        )
        return receipt["transactionHash"].to_0x_hex()

    async def pay_collector(
        self, oracle: LocalAccount, line_id: uuid.UUID, collector: str, amount_cop: int
    ) -> str:
        assert self.treasury is not None
        receipt = await self._send(
            oracle,
            self.treasury.functions.payCollector(
                sale_id(line_id), to_checksum_address(collector), amount_cop * WEI_PER_COP
            ),
        )
        return receipt["transactionHash"].to_0x_hex()

    async def pay_host(
        self, oracle: LocalAccount, line_id: uuid.UUID, host: str, amount_cop: int
    ) -> str:
        assert self.treasury is not None
        receipt = await self._send(
            oracle,
            self.treasury.functions.payHost(
                sale_id(line_id), to_checksum_address(host), amount_cop * WEI_PER_COP
            ),
        )
        return receipt["transactionHash"].to_0x_hex()

    # ------------------------------------------------------------------ certificates (ADR 0027)

    async def anchor(self, sender: LocalAccount, data: bytes) -> str:
        """A plain transaction from `sender` to itself carrying `data` (a certificate root)."""
        tx = {
            "from": sender.address,
            "to": sender.address,
            "value": 0,
            "data": data,
            "nonce": await self.w3.eth.get_transaction_count(sender.address, "pending"),
            "chainId": await self.w3.eth.chain_id,
        }
        tx["gas"] = await self.w3.eth.estimate_gas(tx)
        fees = await self.w3.eth.fee_history(1, "latest")
        base = fees["baseFeePerGas"][-1]
        tx["maxPriorityFeePerGas"] = 0
        tx["maxFeePerGas"] = base * 2 + 1
        signed = sender.sign_transaction(tx)
        tx_hash = await self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        if receipt["status"] != 1:
            raise TxFailed("Reverted", f"transaction {tx_hash.to_0x_hex()} reverted")
        return tx_hash.to_0x_hex()

    async def transfer_native(self, sender: LocalAccount, to: str, wei: int) -> str:
        """Send native ZYR from `sender` to `to`: gas for the backend's keys."""
        tx = {
            "from": sender.address,
            "to": to_checksum_address(to),
            "value": wei,
            "nonce": await self.w3.eth.get_transaction_count(sender.address, "pending"),
            "chainId": await self.w3.eth.chain_id,
            "gas": 21_000,
        }
        fees = await self.w3.eth.fee_history(1, "latest")
        tx["maxPriorityFeePerGas"] = 0
        tx["maxFeePerGas"] = fees["baseFeePerGas"][-1] * 2 + 1
        signed = sender.sign_transaction(tx)
        tx_hash = await self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        if receipt["status"] != 1:
            raise TxFailed("Reverted", f"transaction {tx_hash.to_0x_hex()} reverted")
        return tx_hash.to_0x_hex()

    async def transaction_input(self, tx_hash: str) -> bytes:
        tx = await self.w3.eth.get_transaction(tx_hash)
        return bytes(tx["input"])

    async def state(self) -> TreasuryState:
        assert self.treasury is not None
        f = self.treasury.functions
        backing, minted = await f.backing().call(), await f.minted().call()
        return TreasuryState(
            backing_cop=backing // WEI_PER_COP,
            minted_cop=minted // WEI_PER_COP,
            available_cop=(backing - minted) // WEI_PER_COP,
            seed_capital_cop=await f.seedCapital().call() // WEI_PER_COP,
            operations_revenue_cop=await f.operationsRevenue().call() // WEI_PER_COP,
        )

    async def balance_wei(self, address: str) -> int:
        return await self.w3.eth.get_balance(to_checksum_address(address))

    # ------------------------------------------------------------------ accounts (ADR 0010)

    async def deploy_account_factory(self, admin: LocalAccount, guardian: str) -> str:
        contract = self.w3.eth.contract(
            abi=self._factory_artifact["abi"], bytecode=self._factory_artifact["bytecode"]
        )
        receipt = await self._send(
            admin, contract.constructor(admin.address, to_checksum_address(guardian))
        )
        address = receipt["contractAddress"]
        self.factory = self.w3.eth.contract(address=address, abi=self._factory_artifact["abi"])
        return address

    async def allow_deployer(self, admin: LocalAccount, address: str) -> None:
        """Let `address` deploy contracts (ContractDeployerAllowList, admin = precompile admin).
        The guardian needs it: an account is deployed in the transaction of its first recovery,
        and the allow list checks tx.origin."""
        await self._send(admin, self.deployers.functions.setEnabled(to_checksum_address(address)))
        if await self.deployers.functions.readAllowList(to_checksum_address(address)).call() < 1:
            raise TxFailed("NotEnabled", f"{address} is not on the deployer allow list")

    async def set_guardian(self, admin: LocalAccount, guardian: str) -> str:
        assert self.factory is not None
        receipt = await self._send(
            admin, self.factory.functions.setGuardian(to_checksum_address(guardian))
        )
        return receipt["transactionHash"].to_0x_hex()

    async def predict_account(self, owner: str) -> str:
        assert self.factory is not None
        return (await self.factory.functions.predict(to_checksum_address(owner)).call()).lower()

    async def is_deployed(self, address: str) -> bool:
        return len(await self.w3.eth.get_code(to_checksum_address(address))) > 0

    async def create_account(self, sender: LocalAccount, first_owner: str) -> str:
        assert self.factory is not None
        receipt = await self._send(
            sender, self.factory.functions.createAccount(to_checksum_address(first_owner))
        )
        return receipt["transactionHash"].to_0x_hex()

    def _account(self, address: str):
        return self.w3.eth.contract(address=to_checksum_address(address), abi=self._account_abi)

    # ------------------------------------------------------------------ payments (ADR 0029)

    async def account_nonce(self, address: str) -> int:
        """The nonce the next signed Execute must carry: 0 while the account is not deployed."""
        if not await self.is_deployed(address):
            return 0
        return await self._account(address).functions.nonce().call()

    async def execute_signed(
        self,
        relayer: LocalAccount,
        account: str,
        calls: list[tuple[str, int, bytes]],
        deadline: int,
        signature: bytes,
    ) -> str:
        """Relay the owner's signed Execute; the relayer pays the gas."""
        receipt = await self._send(
            relayer,
            self._account(account).functions.executeSigned(
                [(to_checksum_address(t), v, d) for t, v, d in calls], deadline, signature
            ),
        )
        return receipt["transactionHash"].to_0x_hex()

    def redeem_calldata(self, ref: bytes) -> bytes:
        assert self.treasury is not None
        return bytes.fromhex(self.treasury.encode_abi("redeem", args=[ref]).removeprefix("0x"))

    async def redemption(self, ref: bytes) -> tuple[str, int, int]:
        """(merchant, amount in wei, status: 0 none, 1 pending, 2 settled, 3 refunded)."""
        assert self.treasury is not None
        merchant, amount, status = await self.treasury.functions.redemptions(ref).call()
        return merchant.lower(), amount, status

    async def settle_redemption(self, operator: LocalAccount, ref: bytes, bank_ref: bytes) -> str:
        assert self.treasury is not None
        receipt = await self._send(
            operator, self.treasury.functions.settleRedemption(ref, bank_ref)
        )
        return receipt["transactionHash"].to_0x_hex()

    async def refund_redemption(self, operator: LocalAccount, ref: bytes) -> str:
        assert self.treasury is not None
        receipt = await self._send(operator, self.treasury.functions.refundRedemption(ref))
        return receipt["transactionHash"].to_0x_hex()

    async def account_owner(self, address: str) -> str:
        return (await self._account(address).functions.owner().call()).lower()

    async def pending_recovery(self, address: str) -> PendingRecovery:
        new_owner, ready_at = await self._account(address).functions.recovery().call()
        zero = int(new_owner, 16) == 0
        return PendingRecovery(None if zero else new_owner.lower(), int(ready_at))

    async def start_recovery(self, guardian: LocalAccount, address: str, new_owner: str) -> str:
        receipt = await self._send(
            guardian,
            self._account(address).functions.startRecovery(to_checksum_address(new_owner)),
        )
        return receipt["transactionHash"].to_0x_hex()

    async def cancel_recovery(self, guardian: LocalAccount, address: str) -> str:
        receipt = await self._send(guardian, self._account(address).functions.cancelRecovery())
        return receipt["transactionHash"].to_0x_hex()

    async def finish_recovery(self, sender: LocalAccount, address: str) -> str:
        receipt = await self._send(sender, self._account(address).functions.finishRecovery())
        return receipt["transactionHash"].to_0x_hex()

    # ------------------------------------------------------------------ plumbing

    async def _send(self, account: LocalAccount, call) -> Any:
        """Estimate (surfacing contract errors by name), sign, send and wait for the receipt."""
        try:
            tx = await call.build_transaction(
                {
                    "from": account.address,
                    "nonce": await self.w3.eth.get_transaction_count(account.address, "pending"),
                    "chainId": await self.w3.eth.chain_id,
                }
            )
        except ContractCustomError as e:
            raise TxFailed(self._error_name(e), str(e.data)) from None
        except ContractLogicError as e:
            raise TxFailed("Reverted", str(e)) from None
        signed = account.sign_transaction(tx)
        tx_hash = await self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        if receipt["status"] != 1:
            raise TxFailed("Reverted", f"transaction {tx_hash.to_0x_hex()} reverted")
        return receipt

    def _error_name(self, e: ContractCustomError) -> str:
        data = e.data if isinstance(e.data, str) else str(e.message or "")
        return self._errors.get(data[:10], "UnknownError")
