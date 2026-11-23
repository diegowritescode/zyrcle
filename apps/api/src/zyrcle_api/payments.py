"""Paying campus merchants and redeeming ZYR for pesos (docs/adr/0029).

The participant (or the merchant, to redeem) signs an EIP-712 `Execute` for their own smart account;
the backend checks the signature, then a relay worker submits it with the guardian key, deploying
the account first when needed. The account itself verifies the signature and its nonce on chain, so
the backend can neither change what was signed nor replay it.
"""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .chain import WEI_PER_COP, Chain, TxFailed, redemption_ref
from .config import Settings
from .errors import Conflict, Forbidden, Invalid, NotFound, Unavailable
from .models import Merchant, PaymentRequest, RedemptionRequest, Resident
from .notifications import enqueue

log = logging.getLogger(__name__)

CHARGE_TTL = timedelta(minutes=10)
SIGNATURE_TTL = timedelta(minutes=10)
RETRY = timedelta(seconds=30)
PAYMENT_QR_PREFIX = "zyrcle://p/"
EXECUTE_TYPES = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "Execute": [
        {"name": "calls", "type": "Call[]"},
        {"name": "nonce", "type": "uint256"},
        {"name": "deadline", "type": "uint256"},
    ],
    "Call": [
        {"name": "target", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "data", "type": "bytes"},
    ],
}


def utcnow() -> datetime:
    return datetime.now(UTC)


def typed_execute(
    chain_id: int, account: str, calls: list[tuple[str, int, bytes]], nonce: int, deadline: int
) -> dict[str, Any]:
    """The EIP-712 message an account's owner signs (ZyrcleAccount.executeDigest)."""
    return {
        "types": EXECUTE_TYPES,
        "primaryType": "Execute",
        "domain": {
            "name": "Zyrcle Account",
            "version": "1",
            "chainId": chain_id,
            "verifyingContract": account,
        },
        "message": {
            "calls": [{"target": t, "value": v, "data": "0x" + d.hex()} for t, v, d in calls],
            "nonce": nonce,
            "deadline": deadline,
        },
    }


def signer_of(typed: dict[str, Any], signature: str) -> str:
    message = {
        **typed,
        "message": {
            **typed["message"],
            "calls": [
                {**c, "data": bytes.fromhex(c["data"].removeprefix("0x"))}
                for c in typed["message"]["calls"]
            ],
        },
    }
    return Account.recover_message(
        encode_typed_data(full_message=message), signature=signature
    ).lower()


def json_typed(typed: dict[str, Any]) -> dict[str, Any]:
    """The same message with big numbers as strings, for JSON clients (viem accepts them)."""
    msg = typed["message"]
    return {
        **typed,
        "message": {
            "calls": [{**c, "value": str(c["value"])} for c in msg["calls"]],
            "nonce": str(msg["nonce"]),
            "deadline": str(msg["deadline"]),
        },
    }


def payment_view(p: PaymentRequest, merchant: Merchant) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "qr": f"{PAYMENT_QR_PREFIX}{p.id}",
        "merchant": merchant.name,
        "amount_cop": p.amount_cop,
        "concept": p.concept,
        "status": p.status,
        "tx_hash": p.tx_hash,
        "expires_at": p.expires_at.isoformat(),
        "created_at": p.created_at.isoformat(),
        "paid_at": p.paid_at.isoformat() if p.paid_at else None,
    }


def redemption_view(r: RedemptionRequest) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "amount_cop": r.amount_cop,
        "status": r.status,
        "request_tx": r.request_tx,
        "decision_tx": r.decision_tx,
        "bank_ref": r.bank_ref,
        "decided_by": r.decided_by,
        "last_error": r.last_error,
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
    }


class PaymentService:
    def __init__(
        self,
        maker: async_sessionmaker[AsyncSession],
        settings: Settings,
        chain: Chain | None,
        clock: Callable[[], datetime] = utcnow,
    ):
        self._maker = maker
        self._s = settings
        self._chain = chain
        self._now = clock

    def _need_chain(self) -> Chain:
        if self._chain is None or self._chain.treasury is None:
            raise Unavailable("payments need the chain")
        return self._chain

    async def merchant(self, db: AsyncSession, resident_id: uuid.UUID) -> Merchant:
        m = await db.get(Merchant, resident_id)
        if m is None or not m.active:
            raise Forbidden("only merchants can do this")
        return m

    # ------------------------------------------------------------------ charges

    async def charge(self, merchant_id: uuid.UUID, amount_cop: int, concept: str) -> dict[str, Any]:
        now = self._now()
        async with self._maker() as db:
            m = await self.merchant(db, merchant_id)
            p = PaymentRequest(
                id=uuid.uuid4(),
                merchant_id=merchant_id,
                amount_cop=amount_cop,
                concept=concept.strip() or "Compra",
                status="open",
                expires_at=now + CHARGE_TTL,
                created_at=now,
            )
            db.add(p)
            await db.commit()
            return payment_view(p, m)

    async def get(self, payment_id: uuid.UUID) -> dict[str, Any]:
        async with self._maker() as db:
            p = await db.get(PaymentRequest, payment_id)
            if p is None:
                raise NotFound("unknown payment")
            m = await db.get(Merchant, p.merchant_id)
            assert m is not None
            if p.status == "open" and p.expires_at < self._now():
                p.status = "expired"
                await db.commit()
            return payment_view(p, m)

    async def _accounts(self, db: AsyncSession, payer_id: uuid.UUID, merchant_id: uuid.UUID):
        payer = await db.get(Resident, payer_id)
        target = await db.get(Resident, merchant_id)
        assert payer is not None and target is not None
        return payer, target

    async def payment_intent(self, payment_id: uuid.UUID, payer_id: uuid.UUID) -> dict[str, Any]:
        """What the payer's phone must sign to pay this charge."""
        chain = self._need_chain()
        async with self._maker() as db:
            p = await db.get(PaymentRequest, payment_id)
            if p is None:
                raise NotFound("unknown payment")
            if p.status != "open" or p.expires_at < self._now():
                raise Conflict("this charge is no longer open")
            if p.merchant_id == payer_id:
                raise Invalid("a merchant cannot pay their own charge")
            payer, target = await self._accounts(db, payer_id, p.merchant_id)
        balance = await chain.balance_wei(payer.address)
        if balance < p.amount_cop * WEI_PER_COP:
            raise Conflict("not enough ZYR for this payment")
        nonce = await chain.account_nonce(payer.address)
        deadline = int((self._now() + SIGNATURE_TTL).timestamp())
        calls = [(target.address, p.amount_cop * WEI_PER_COP, b"")]
        return json_typed(typed_execute(self._s.chain_id, payer.address, calls, nonce, deadline))

    async def pay(
        self, payment_id: uuid.UUID, payer_id: uuid.UUID, signature: str, deadline: int, nonce: int
    ) -> dict[str, Any]:
        now = self._now()
        async with self._maker() as db:
            p = await db.get(PaymentRequest, payment_id, with_for_update=True)
            if p is None:
                raise NotFound("unknown payment")
            if p.status != "open" or p.expires_at < now:
                raise Conflict("this charge is no longer open")
            payer, target = await self._accounts(db, payer_id, p.merchant_id)
            calls = [(target.address, p.amount_cop * WEI_PER_COP, b"")]
            typed = typed_execute(self._s.chain_id, payer.address, calls, nonce, deadline)
            if signer_of(typed, signature) != payer.owner_address:
                raise Forbidden("the signature is not from this phone's key")
            if deadline < now.timestamp():
                raise Conflict("the signature expired; try again")
            p.status, p.payer_id, p.signature = "paying", payer_id, signature
            p.deadline, p.nonce, p.next_attempt_at = deadline, nonce, now
            m = await db.get(Merchant, p.merchant_id)
            assert m is not None
            try:
                await db.commit()
            except IntegrityError:
                raise Conflict("you have another payment in progress") from None
            return payment_view(p, m)

    # ------------------------------------------------------------------ redemptions

    async def redemption_intent(self, merchant_id: uuid.UUID, amount_cop: int) -> dict[str, Any]:
        chain = self._need_chain()
        async with self._maker() as db:
            await self.merchant(db, merchant_id)
            me = await db.get(Resident, merchant_id)
            assert me is not None
            balance = await chain.balance_wei(me.address)
            if balance < amount_cop * WEI_PER_COP:
                raise Conflict("not enough ZYR to redeem that amount")
            now = self._now()
            r = RedemptionRequest(
                id=uuid.uuid4(),
                merchant_id=merchant_id,
                amount_cop=amount_cop,
                status="signing",
                created_at=now,
                updated_at=now,
            )
            db.add(r)
            await db.commit()
        nonce = await chain.account_nonce(me.address)
        deadline = int((self._now() + SIGNATURE_TTL).timestamp())
        calls = [
            (
                chain.treasury.address,  # type: ignore[union-attr]
                amount_cop * WEI_PER_COP,
                chain.redeem_calldata(redemption_ref(r.id)),
            )
        ]
        typed = typed_execute(self._s.chain_id, me.address, calls, nonce, deadline)
        return {"id": str(r.id), "typed_data": json_typed(typed)}

    async def sign_redemption(
        self,
        redemption_id: uuid.UUID,
        merchant_id: uuid.UUID,
        signature: str,
        deadline: int,
        nonce: int,
    ) -> dict[str, Any]:
        chain = self._need_chain()
        async with self._maker() as db:
            r = await db.get(RedemptionRequest, redemption_id, with_for_update=True)
            if r is None or r.merchant_id != merchant_id:
                raise NotFound("unknown redemption")
            if r.status != "signing":
                return redemption_view(r)
            me = await db.get(Resident, merchant_id)
            assert me is not None
            calls = [
                (
                    chain.treasury.address,  # type: ignore[union-attr]
                    r.amount_cop * WEI_PER_COP,
                    chain.redeem_calldata(redemption_ref(r.id)),
                )
            ]
            typed = typed_execute(self._s.chain_id, me.address, calls, nonce, deadline)
            if signer_of(typed, signature) != me.owner_address:
                raise Forbidden("the signature is not from this phone's key")
            r.status, r.signature, r.deadline, r.nonce = "requested", signature, deadline, nonce
            r.next_attempt_at = r.updated_at = self._now()
            await db.commit()
            return redemption_view(r)

    async def merchant_home(self, merchant_id: uuid.UUID) -> dict[str, Any]:
        async with self._maker() as db:
            m = await self.merchant(db, merchant_id)
            charges = list(
                await db.scalars(
                    select(PaymentRequest)
                    .where(PaymentRequest.merchant_id == merchant_id)
                    .order_by(PaymentRequest.created_at.desc())
                    .limit(20)
                )
            )
            redemptions = list(
                await db.scalars(
                    select(RedemptionRequest)
                    .where(
                        RedemptionRequest.merchant_id == merchant_id,
                        RedemptionRequest.status != "signing",
                    )
                    .order_by(RedemptionRequest.created_at.desc())
                    .limit(20)
                )
            )
            return {
                "name": m.name,
                "charges": [payment_view(p, m) for p in charges],
                "redemptions": [redemption_view(r) for r in redemptions],
            }

    # ------------------------------------------------------------------ operator

    async def decide_redemption(
        self, redemption_id: uuid.UUID, settle: bool, bank_ref: str | None, who: str, operator
    ) -> dict[str, Any]:
        chain = self._need_chain()
        async with self._maker() as db:
            r = await db.get(RedemptionRequest, redemption_id, with_for_update=True)
            if r is None:
                raise NotFound("unknown redemption")
            if r.status != "pending":
                raise Conflict(f"this redemption is {r.status}, not waiting for a decision")
            ref = redemption_ref(r.id)
            try:
                if settle:
                    bank = keccak(text=bank_ref) if bank_ref else bytes(32)
                    tx = await chain.settle_redemption(operator, ref, bank)
                else:
                    tx = await chain.refund_redemption(operator, ref)
            except TxFailed as e:
                raise Conflict(f"the Treasury refused: {e}") from None
            r.status = "settled" if settle else "refunded"
            r.decision_tx, r.bank_ref, r.decided_by = tx, bank_ref, who
            r.updated_at = self._now()
            await enqueue(
                db,
                resident_id=r.merchant_id,
                kind="redemption_settled" if settle else "redemption_refunded",
                dedupe_key=f"redemption:{r.id}:{r.status}",
                title=(
                    f"Te pagamos {r.amount_cop:,} pesos".replace(",", ".")
                    if settle
                    else "Devolvimos tu ZYR"
                ),
                body=(f"Transferencia {bank_ref}." if settle else "El canje no se pudo pagar."),
                data={"url": "/shop"},
                now=self._now(),
            )
            await db.commit()
            return redemption_view(r)


class RelayWorker:
    """Submits signed Executes: payments, then redemptions. Deploys an account first if needed."""

    def __init__(
        self,
        maker: async_sessionmaker[AsyncSession],
        chain: Chain,
        relayer,
        clock: Callable[[], datetime] = utcnow,
    ):
        self._maker = maker
        self._chain = chain
        self._relayer = relayer
        self._now = clock

    async def run_once(self) -> int:
        done = 0
        for model, status in ((PaymentRequest, "paying"), (RedemptionRequest, "requested")):
            now = self._now()
            async with self._maker() as db:
                rows = list(
                    await db.scalars(
                        select(model)
                        .where(
                            model.status == status,
                            or_(model.next_attempt_at.is_(None), model.next_attempt_at <= now),
                        )
                        .limit(5)
                        .with_for_update(skip_locked=True)
                    )
                )
                for row in rows:
                    row.attempts, row.next_attempt_at = row.attempts + 1, now + timedelta(minutes=2)
                await db.commit()
                work = [row.id for row in rows]
            for rid in work:
                await self._relay(model, rid)
                done += 1
        return done

    async def _relay(self, model, rid: uuid.UUID) -> None:
        async with self._maker() as db:
            row = await db.get(model, rid)
            assert row is not None
            owner_id = row.payer_id if model is PaymentRequest else row.merchant_id
            signer = await db.get(Resident, owner_id)
            assert signer is not None
            if model is PaymentRequest:
                target = await db.get(Resident, row.merchant_id)
                assert target is not None
                calls = [(target.address, row.amount_cop * WEI_PER_COP, b"")]
            else:
                calls = [
                    (
                        self._chain.treasury.address,  # type: ignore[union-attr]
                        row.amount_cop * WEI_PER_COP,
                        self._chain.redeem_calldata(redemption_ref(row.id)),
                    )
                ]
        tx, error, final = None, None, False
        try:
            if not await self._chain.is_deployed(signer.address):
                # Never recovered, so its first owner is its current key (docs/adr/0010).
                await self._chain.create_account(self._relayer, signer.owner_address)
            if await self._chain.account_nonce(signer.address) > row.nonce:
                # Already executed by an earlier attempt whose bookkeeping was lost.
                tx = row.tx_hash if model is PaymentRequest else row.request_tx
                tx = tx or "relayed earlier"
            else:
                tx = await self._chain.execute_signed(
                    self._relayer,
                    signer.address,
                    calls,
                    row.deadline,
                    bytes.fromhex(row.signature.removeprefix("0x")),
                )
        except TxFailed as e:
            error, final = str(e), True  # bad signature, expired, not enough ZYR: will not change
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
        async with self._maker() as db:
            row = await db.get(model, rid, with_for_update=True)
            assert row is not None
            now = self._now()
            if tx:
                if model is PaymentRequest:
                    row.status, row.tx_hash, row.paid_at = "paid", tx, now
                    await enqueue(
                        db,
                        resident_id=row.merchant_id,
                        kind="payment_received",
                        dedupe_key=f"payment_received:{row.id}",
                        title=f"Recibiste {row.amount_cop:,} pesos".replace(",", "."),
                        body=row.concept,
                        data={"url": "/shop"},
                        now=now,
                    )
                else:
                    row.status, row.request_tx, row.updated_at = "pending", tx, now
            elif final:
                row.status, row.last_error = "failed", error
            else:
                row.last_error, row.next_attempt_at = error, now + RETRY
            await db.commit()
        log.info("relay %s %s: %s", model.__tablename__, rid, tx or error)
