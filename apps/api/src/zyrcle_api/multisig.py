"""The Safe that holds ZyrcleChain's admin powers (docs/adr/0040).

A Safe transaction is EIP-712 typed data. Each owner signs it with whatever holds their key: a
browser or phone wallet (the multisig page asks it for `eth_signTypedData_v4`) or a key file kept
offline (`zyrcle-api safe sign`). The signatures travel in a proposal file, one JSON document,
from signer to signer; when two of three are in, anyone executes it. Nothing here needs the
backend's database or its keys.

The handover moves eight powers from the L1 admin key to the Safe:

- the admin role of four precompiles: NativeMinter, ContractDeployerAllowList, FeeManager and
  RewardManager;
- the ownership of the validator manager and of the proxy admin that can upgrade it;
- `DEFAULT_ADMIN_ROLE` of the Treasury and of the AccountFactory.

First the admin key grants each one to the Safe; then the Safe, with two signatures, takes the admin
key off the precompiles, which also proves the Safe works; last the admin key renounces its contract
roles. Ownerships move whole.
"""

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak, to_checksum_address

NATIVE_MINTER = "0x0200000000000000000000000000000000000001"
DEPLOYER_ALLOW_LIST = "0x0200000000000000000000000000000000000000"
FEE_MANAGER = "0x0200000000000000000000000000000000000003"
REWARD_MANAGER = "0x0200000000000000000000000000000000000004"
PRECOMPILES = {
    "NativeMinter": NATIVE_MINTER,
    "ContractDeployerAllowList": DEPLOYER_ALLOW_LIST,
    "FeeManager": FEE_MANAGER,
    "RewardManager": REWARD_MANAGER,
}
ZERO = "0x0000000000000000000000000000000000000000"

SAFE_TX_TYPES = {
    "EIP712Domain": [
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "SafeTx": [
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "data", "type": "bytes"},
        {"name": "operation", "type": "uint8"},
        {"name": "safeTxGas", "type": "uint256"},
        {"name": "baseGas", "type": "uint256"},
        {"name": "gasPrice", "type": "uint256"},
        {"name": "gasToken", "type": "address"},
        {"name": "refundReceiver", "type": "address"},
        {"name": "nonce", "type": "uint256"},
    ],
}


@dataclass
class Proposal:
    """One Safe transaction on its way to two signatures. `signatures` maps owner to signature."""

    safe: str
    chain_id: int
    to: str
    data: str
    nonce: int
    description: str
    value: int = 0
    operation: int = 0  # 0 call, 1 delegatecall (only to MultiSendCallOnly)
    signatures: dict[str, str] = field(default_factory=dict)

    def typed_data(self) -> dict[str, Any]:
        return {
            "types": SAFE_TX_TYPES,
            "primaryType": "SafeTx",
            "domain": {
                "chainId": self.chain_id,
                "verifyingContract": to_checksum_address(self.safe),
            },
            "message": {
                "to": to_checksum_address(self.to),
                "value": self.value,
                "data": self.data,
                "operation": self.operation,
                "safeTxGas": 0,
                "baseGas": 0,
                "gasPrice": 0,
                "gasToken": ZERO,
                "refundReceiver": ZERO,
                "nonce": self.nonce,
            },
        }

    def tx_hash(self) -> str:
        """The Safe's transaction hash: keccak(0x19 0x01 domainSeparator structHash)."""
        m = encode_typed_data(full_message=self.typed_data())
        return "0x" + keccak(b"\x19" + m.version + m.header + m.body).hex()

    def signer_of(self, signature: str) -> str:
        """The address that made `signature` over this transaction."""
        return Account.recover_message(
            encode_typed_data(full_message=self.typed_data()), signature=signature
        )

    def add_signature(self, signature: str, owners: list[str]) -> str:
        """Check the signature is an owner's over this exact transaction, keep it, return who."""
        signer = self.signer_of(signature)
        if signer.lower() not in {o.lower() for o in owners}:
            raise ValueError(f"{signer} is not an owner of this Safe")
        self.signatures[to_checksum_address(signer)] = signature
        return signer

    def packed_signatures(self) -> bytes:
        """What execTransaction takes: r, s, v of each signature, owners in ascending order."""
        packed = b""
        for owner in sorted(self.signatures, key=lambda a: int(a, 16)):
            sig = bytes.fromhex(self.signatures[owner].removeprefix("0x"))
            if len(sig) != 65:
                raise ValueError(f"a signature is 65 bytes, not {len(sig)}")
            packed += sig
        return packed

    def to_json(self) -> str:
        return json.dumps(
            {**asdict(self), "safe_tx_hash": self.tx_hash(), "typed_data": self.typed_data()},
            indent=2,
        )

    @classmethod
    def from_json(cls, text: str) -> "Proposal":
        d = json.loads(text)
        fields = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        p = cls(**fields)
        if "safe_tx_hash" in d and d["safe_tx_hash"] != p.tx_hash():
            raise ValueError("the proposal was changed after it was made: its hash does not match")
        return p


def sign_with_key(p: Proposal, key_hex: str) -> str:
    """An owner's signature from a key file, as a wallet's eth_signTypedData_v4 would make it."""
    signed = Account.sign_message(encode_typed_data(full_message=p.typed_data()), key_hex)
    return "0x" + signed.signature.hex().removeprefix("0x")
