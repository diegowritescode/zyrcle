"""ZyrcleChain access: deploys and talks to the Treasury contract with backend-held keys.

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

WEI_PER_COP = 10**18
NATIVE_MINTER = "0x0200000000000000000000000000000000000001"
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
        "name": "readAllowList",
        "stateMutability": "view",
        "inputs": [{"name": "addr", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]


def treasury_artifact() -> dict[str, Any]:
    text = resources.files("zyrcle_api.contracts").joinpath("Treasury.json").read_text()
    return json.loads(text)


def deposit_id(session_id: uuid.UUID) -> bytes:
    """The Treasury's bytes32 id for a deposit session (the UUID, left-padded)."""
    return session_id.bytes.rjust(32, b"\0")


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
class TreasuryState:
    backing_cop: int
    minted_cop: int
    available_cop: int
    seed_capital_cop: int
    operations_revenue_cop: int


class Chain:
    def __init__(self, rpc_url: str, treasury_address: str | None = None):
        self.w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
        artifact = treasury_artifact()
        self._abi = artifact["abi"]
        self._bytecode = artifact["bytecode"]
        self._errors = {
            "0x"
            + keccak(text=f"{e['name']}({','.join(i['type'] for i in e['inputs'])})")[:4].hex(): e[
                "name"
            ]
            for e in self._abi
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

    # ------------------------------------------------------------------ deployment

    async def deploy_treasury(
        self,
        admin: LocalAccount,
        operator: str,
        oracle: str,
        shares_bps: tuple[int, int, int] = (7_000, 1_500, 1_500),
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
