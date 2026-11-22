"""Resident sign-in with an Ethereum wallet (EIP-4361, "Sign-In with Ethereum") and JWT sessions.

The resident app's embedded wallet signs a SIWE message containing a single-use nonce. The backend
recovers the signer, checks domain, chain, nonce and time, and issues a short JWT.

The signer is the phone key, the account's owner. A resident is found by that key; a key seen for
the first time gets a new resident whose ZYR goes to the smart account it will control
(docs/adr/0010-smart-accounts-and-recovery.md). The token names the key, so a phone whose key no
longer owns the account loses its session at once.
"""

import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from eth_account import Account
from eth_account.messages import encode_defunct
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .chain import account_address
from .config import Settings
from .models import AuthNonce, Resident

NONCE_TTL = timedelta(minutes=5)
MAX_CLOCK_SKEW = timedelta(minutes=2)

_HEADER = re.compile(r"^(?P<domain>\S+) wants you to sign in with your Ethereum account:$")
_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


class AuthError(Exception):
    pass


class KeyRetired(AuthError):
    """This key's account was handed to another phone (a recovery). It cannot sign in again."""


@dataclass(frozen=True)
class SiweMessage:
    domain: str
    address: str
    uri: str
    version: str
    chain_id: int
    nonce: str
    issued_at: datetime
    expiration_time: datetime | None


def _parse_time(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise AuthError("timestamps must carry a timezone")
    return dt


def parse_siwe(message: str) -> SiweMessage:
    lines = message.split("\n")
    if len(lines) < 7:
        raise AuthError("not a SIWE message")
    header = _HEADER.match(lines[0])
    if not header or not _ADDRESS.match(lines[1]):
        raise AuthError("not a SIWE message")
    fields: dict[str, str] = {}
    for line in lines[2:]:
        if ": " in line:
            key, value = line.split(": ", 1)
            fields.setdefault(key, value)
    try:
        return SiweMessage(
            domain=header["domain"],
            address=lines[1],
            uri=fields["URI"],
            version=fields["Version"],
            chain_id=int(fields["Chain ID"]),
            nonce=fields["Nonce"],
            issued_at=_parse_time(fields["Issued At"]),
            expiration_time=(
                _parse_time(fields["Expiration Time"]) if "Expiration Time" in fields else None
            ),
        )
    except (KeyError, ValueError) as e:
        raise AuthError(f"malformed SIWE message: {e}") from None


def build_siwe(domain: str, address: str, chain_id: int, nonce: str, issued_at: datetime) -> str:
    """The message the app asks the wallet to sign (also used by tests and the simulator)."""
    return "\n".join(
        [
            f"{domain} wants you to sign in with your Ethereum account:",
            address,
            "",
            "Sign in to Zyrcle.",
            "",
            f"URI: https://{domain}",
            "Version: 1",
            f"Chain ID: {chain_id}",
            f"Nonce: {nonce}",
            f"Issued At: {issued_at.isoformat()}",
        ]
    )


async def new_nonce(db: AsyncSession, now: datetime) -> AuthNonce:
    nonce = AuthNonce(nonce=secrets.token_hex(16), expires_at=now + NONCE_TTL)
    db.add(nonce)
    await db.commit()
    return nonce


async def verify_siwe(
    db: AsyncSession, settings: Settings, message: str, signature: str, now: datetime
) -> Resident:
    msg = parse_siwe(message)
    if msg.domain != settings.siwe_domain:
        raise AuthError("wrong domain")
    if msg.chain_id != settings.chain_id:
        raise AuthError("wrong chain")
    if msg.version != "1":
        raise AuthError("unsupported SIWE version")
    if msg.issued_at > now + MAX_CLOCK_SKEW or msg.issued_at < now - NONCE_TTL:
        raise AuthError("message is too old or from the future")
    if msg.expiration_time and msg.expiration_time < now:
        raise AuthError("message expired")
    try:
        signer = Account.recover_message(encode_defunct(text=message), signature=signature)
    except Exception:
        raise AuthError("bad signature") from None
    if signer.lower() != msg.address.lower():
        raise AuthError("signature does not match the address")

    # Burn the nonce atomically: a second use of the same message fails here.
    used = await db.execute(
        update(AuthNonce)
        .where(
            AuthNonce.nonce == msg.nonce, AuthNonce.used_at.is_(None), AuthNonce.expires_at > now
        )
        .values(used_at=now)
    )
    if used.rowcount != 1:
        raise AuthError("unknown, expired or already used nonce")

    key = msg.address.lower()
    factory = settings.account_factory_address if settings.accounts_enabled else None
    resident = await db.scalar(select(Resident).where(Resident.owner_address == key))
    if resident is None:
        address = account_address(factory, key) if factory else key
        taken = await db.scalar(select(Resident.id).where(Resident.address == address))
        if taken is not None:
            # The account this key was first given now obeys another key.
            await db.commit()
            raise KeyRetired("this phone's account was moved to another phone")
        resident = Resident(id=uuid.uuid4(), address=address, owner_address=key)
        db.add(resident)
    elif factory and resident.address == resident.owner_address:
        # First sign-in since smart accounts: from now on their ZYR goes to their account. What the
        # key itself holds, the app moves there (apps/mobile/src/lib/chain.ts).
        resident.address = account_address(factory, key)
    await db.commit()
    return resident


def issue_token(settings: Settings, resident: Resident, now: datetime) -> str:
    claims = {
        "sub": str(resident.id),
        "addr": resident.address,
        "key": resident.owner_address,
        "role": "resident",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_ttl_minutes)).timestamp()),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def read_claims(settings: Settings, token: str) -> tuple[uuid.UUID, str | None]:
    """The resident id and the key that signed in (None in tokens from before smart accounts)."""
    try:
        claims = jwt.decode(
            token, settings.jwt_secret, algorithms=["HS256"], options={"require": ["exp", "sub"]}
        )
    except jwt.PyJWTError as e:
        raise AuthError("invalid token") from e
    if claims.get("role") != "resident":
        raise AuthError("invalid token")
    return uuid.UUID(claims["sub"]), claims.get("key")


def read_token(settings: Settings, token: str) -> uuid.UUID:
    return read_claims(settings, token)[0]


def utcnow() -> datetime:
    return datetime.now(UTC)
