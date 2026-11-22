"""Device keys: ECDSA P-256, the curve the ATECC608 secure element signs with."""

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def generate_private_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def public_key_pem(key: ec.EllipticCurvePrivateKey | ec.EllipticCurvePublicKey) -> str:
    public = key.public_key() if isinstance(key, ec.EllipticCurvePrivateKey) else key
    return public.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()


def private_key_pem(key: ec.EllipticCurvePrivateKey) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def load_private_key(pem: str | bytes) -> ec.EllipticCurvePrivateKey:
    key = serialization.load_pem_private_key(pem.encode() if isinstance(pem, str) else pem, None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or key.curve.name != "secp256r1":
        raise ValueError("device keys must be ECDSA P-256")
    return key


def load_public_key(pem: str | bytes) -> ec.EllipticCurvePublicKey:
    key = serialization.load_pem_public_key(pem.encode() if isinstance(pem, str) else pem)
    if not isinstance(key, ec.EllipticCurvePublicKey) or key.curve.name != "secp256r1":
        raise ValueError("device keys must be ECDSA P-256")
    return key
