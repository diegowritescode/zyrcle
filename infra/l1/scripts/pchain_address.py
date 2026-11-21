#!/usr/bin/env python3
"""Print the P-Chain address of an Avalanche CLI key file without printing the key.

Avalanche CLI 1.9.7 cannot list P-Chain addresses on Fuji anymore: `avalanche key list` calls
platform.getBalance, which AvalancheGo v1.15 removed. This derives the address offline:
bech32(hrp, ripemd160(sha256(compressed secp256k1 public key))).

Usage: pchain_address.py <key-file> [hrp]   (hrp: fuji, avax, custom; default fuji)
"""

import hashlib
import sys

# secp256k1
P = 2**256 - 2**32 - 977
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G = (
    0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
    0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8,
)


def _add(a, b):
    if a is None:
        return b
    if b is None:
        return a
    if a[0] == b[0] and (a[1] + b[1]) % P == 0:
        return None
    if a == b:
        m = 3 * a[0] * a[0] * pow(2 * a[1], -1, P)
    else:
        m = (b[1] - a[1]) * pow(b[0] - a[0], -1, P)
    x = (m * m - a[0] - b[0]) % P
    return x, (m * (a[0] - x) - a[1]) % P


def _mul(k, point):
    result = None
    while k:
        if k & 1:
            result = _add(result, point)
        point = _add(point, point)
        k >>= 1
    return result


def _bech32(hrp: str, data: bytes) -> str:
    charset = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
    acc, bits, five = 0, 0, []
    for b in data:
        acc, bits = (acc << 8) | b, bits + 8
        while bits >= 5:
            bits -= 5
            five.append((acc >> bits) & 31)
    if bits:
        five.append((acc << (5 - bits)) & 31)

    def polymod(values):
        gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
        chk = 1
        for v in values:
            top = chk >> 25
            chk = (chk & 0x1FFFFFF) << 5 ^ v
            for i in range(5):
                chk ^= gen[i] if (top >> i) & 1 else 0
        return chk

    expanded = [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]
    pm = polymod(expanded + five + [0] * 6) ^ 1
    checksum = [(pm >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(charset[d] for d in five + checksum)


def p_chain_address(private_key_hex: str, hrp: str = "fuji") -> str:
    k = int(private_key_hex.strip().removeprefix("0x"), 16)
    if not 0 < k < N:
        raise ValueError("invalid private key")
    x, y = _mul(k, G)
    compressed = bytes([2 + (y & 1)]) + x.to_bytes(32, "big")
    short_id = hashlib.new("ripemd160", hashlib.sha256(compressed).digest()).digest()
    return "P-" + _bech32(hrp, short_id)


if __name__ == "__main__":
    with open(sys.argv[1]) as f:
        print(p_chain_address(f.read(), sys.argv[2] if len(sys.argv) > 2 else "fuji"))
