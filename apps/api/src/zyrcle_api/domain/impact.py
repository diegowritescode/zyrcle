"""Emissions avoided and the Merkle root of an impact certificate (docs/adr/0027). Pure: no I/O.

The factors are EPA WARM version 16 (December 2023): net emission factors of recycling against
landfilling, converted from MTCO2E per short ton to grams of CO2e per kilogram (x 1,102.3).
"""

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

FACTORS_VERSION = "warm-v16"
# grams of CO2e avoided per kilogram recycled instead of landfilled (ADR 0027, table)
G_CO2E_PER_KG: dict[str, int] = {
    "pet": 1_168,
    "hdpe": 860,
    "metal": 10_086,
    "glass": 331,
    "cardboard": 3_660,
    "paper": 3_990,
}
# Every version's table, so a document always states the factors its certificate used.
FACTORS: dict[str, dict[str, int]] = {FACTORS_VERSION: G_CO2E_PER_KG}
# What the anchor transaction's data starts with, so a reader knows what it is: version 1 carries
# the id and the root; version 2 adds the CID of the certificate's public copy on IPFS.
ANCHOR_PREFIX = b"ZYRCLE-CERT-1"
ANCHOR_PREFIX_IPFS = b"ZYRCLE-CERT-2"
DOCUMENT_SCHEMA = "zyrcle-certificate/1"


def co2e_g(material: str, grams: int) -> int:
    """Grams of CO2e avoided by recycling `grams` of `material`, rounded down."""
    return grams * G_CO2E_PER_KG.get(material, 0) // 1_000


@dataclass(frozen=True)
class Leaf:
    deposit_id: str
    material: str
    grams: int

    def digest(self) -> bytes:
        return hashlib.sha256(f"{self.deposit_id}|{self.material}|{self.grams}".encode()).digest()


def merkle_root(leaves: Iterable[Leaf]) -> bytes:
    """Root of the sorted leaf digests; each parent hashes its two children in sorted order, and an
    odd node out is carried up unchanged. The empty tree's root is 32 zero bytes."""
    level = sorted(leaf.digest() for leaf in leaves)
    if not level:
        return bytes(32)
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            if i + 1 == len(level):
                nxt.append(level[i])
            else:
                a, b = sorted((level[i], level[i + 1]))
                nxt.append(hashlib.sha256(a + b).digest())
        level = nxt
    return level[0]


def anchor_data(certificate_id: bytes, root: bytes, cid: str | None = None) -> bytes:
    """The data of the transaction that anchors a certificate: prefix, 16-byte id, 32-byte root,
    and, when the certificate has a copy on IPFS, its CID as ASCII text (amendment 2026-11-22)."""
    if len(certificate_id) != 16 or len(root) != 32:
        raise ValueError("certificate id is 16 bytes and the root 32")
    if cid is None:
        return ANCHOR_PREFIX + certificate_id + root
    if not cid.isascii() or not cid.isalnum() or not 10 <= len(cid) <= 100:
        raise ValueError("a CID is 10 to 100 ASCII letters and digits")
    return ANCHOR_PREFIX_IPFS + certificate_id + root + cid.encode("ascii")


def certificate_document(
    certificate: dict[str, Any], leaves: list[dict[str, Any]]
) -> dict[str, Any]:
    """The public copy pinned on IPFS: everything needed to check the certificate without
    Zyrcle's servers. `certificate` is the API's view of it. Personal data stays out: the copy
    is permanent, so it names no operator and no participant, only random deposit ids."""
    c = certificate
    return {
        "schema": DOCUMENT_SCHEMA,
        "issuer": "Zyrcle",
        "id": c["id"],
        "host": {"id": c["host"]["id"], "name": c["host"]["name"], "kind": c["host"]["kind"]},
        "site": c["site"],
        "period": c["period"],
        "issued_at": c["created_at"],
        "deposits": c["deposits"],
        "participants": c["participants"],
        "grams": c["grams"],
        "co2e_g": c["co2e_g"],
        "by_material": c["by_material"],
        "factors": {
            "version": c["factors_version"],
            "source": "EPA WARM v16 (December 2023), recycling versus landfilling",
            "g_co2e_per_kg": FACTORS.get(c["factors_version"]),
        },
        "merkle": {
            "leaf": "sha256(utf8(deposit_id + '|' + material + '|' + grams))",
            "tree": "leaf digests sorted; each parent is sha256 of its two children in sorted "
            "order; an odd node out is carried up",
            "root": c["merkle_root"],
        },
        "leaves": leaves,
    }
