"""Emissions avoided and the Merkle root of an impact certificate (docs/adr/0027). Pure: no I/O.

The factors are EPA WARM version 16 (December 2023): net emission factors of recycling against
landfilling, converted from MTCO2E per short ton to grams of CO2e per kilogram (x 1,102.3).
"""

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass

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
# What the anchor transaction's data starts with, so a reader knows what it is.
ANCHOR_PREFIX = b"ZYRCLE-CERT-1"


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


def anchor_data(certificate_id: bytes, root: bytes) -> bytes:
    """The data of the transaction that anchors a certificate: prefix, 16-byte id, 32-byte root."""
    if len(certificate_id) != 16 or len(root) != 32:
        raise ValueError("certificate id is 16 bytes and the root 32")
    return ANCHOR_PREFIX + certificate_id + root
