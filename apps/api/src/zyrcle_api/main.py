import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from datetime import timedelta

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .account_routes import router as account_router
from .api import router
from .bank_routes import router as bank_router
from .booking_routes import router as booking_router
from .center_routes import router as center_router
from .chain import Chain, load_account_file
from .collection import CollectionService
from .collection_routes import router as collection_router
from .config import Settings, get_settings
from .db import make_engine, make_sessionmaker
from .health import AlertWorker
from .health import report as health_report
from .impact import AnchorWorker, ImpactService
from .impact_routes import router as impact_router
from .ipfs import PinataPin
from .live import LiveHub
from .mail import EmailWorker, LogMail, ResendMail
from .mqtt import MqttBridge
from .notifications import ExpoPush, NotificationWorker
from .observability import start_error_reports
from .operator_auth import router as operator_router
from .payment_routes import router as payment_router
from .payments import PaymentService, RelayWorker
from .payouts import PayoutWorker
from .public import router as public_router
from .ratelimit import RateLimitMiddleware
from .recovery_worker import RecoveryWorker
from .sale_routes import router as sale_router
from .sessions import SessionService
from .settlement import SettlementWorker
from .setup_routes import router as setup_router
from .ticket_routes import router as ticket_router
from .tickets import ClaudeTicketReader

log = logging.getLogger(__name__)


async def _every(seconds: float, job, name: str) -> None:
    while True:
        try:
            await job()
        except Exception:
            log.exception("periodic job %s failed", name)
        await asyncio.sleep(seconds)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    start_error_reports(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = make_engine(settings.database_url)
        maker = make_sessionmaker(engine)
        hub = LiveHub()
        holder: dict[str, SessionService] = {}

        async def on_message(topic: str, payload: bytes) -> None:
            await holder["service"].handle_device_message(topic, payload)

        bridge = MqttBridge(settings, on_message)
        service = SessionService(maker, settings, bridge, hub)
        collections = CollectionService(maker, settings, bridge)
        service.collections = collections
        holder["service"] = service
        app.state.settings, app.state.maker, app.state.hub = settings, maker, hub
        app.state.bridge, app.state.sessions = bridge, service
        app.state.collections = collections
        app.state.impact = ImpactService(maker, settings)
        app.state.ticket_reader = None
        if settings.anthropic_api_key:
            import anthropic

            app.state.ticket_reader = ClaudeTicketReader(
                anthropic.AsyncAnthropic(
                    api_key=settings.anthropic_api_key,
                    base_url=settings.anthropic_base_url,
                    timeout=120,
                ),
                settings.ticket_model,
            )

        chain = None
        if settings.chain_enabled:
            chain = Chain(
                settings.chain_rpc_url,  # type: ignore[arg-type]
                settings.treasury_address,
                settings.account_factory_address,
            )
        app.state.chain = chain
        app.state.payments = PaymentService(maker, settings, chain)
        app.state.simulator = (
            httpx.AsyncClient(base_url=settings.demo_simulator_url, timeout=5)
            if settings.demo_simulator_url
            else None
        )

        tasks = [
            asyncio.create_task(bridge.run(), name="mqtt"),
            asyncio.create_task(_every(settings.sweep_interval_s, service.sweep, "sweep")),
            asyncio.create_task(
                _every(settings.sweep_interval_s, collections.sweep, "collection-sweep")
            ),
            asyncio.create_task(
                _every(min(5.0, settings.code_rotation_s / 3), service.rotate_codes, "codes")
            ),
        ]
        push_http = None
        pin_http = None
        if settings.push_enabled:
            push_http = httpx.AsyncClient(timeout=10)
            notifier = NotificationWorker(
                maker,
                ExpoPush(push_http, settings.expo_push_url, settings.expo_access_token),
                timedelta(seconds=settings.push_receipt_delay_s),
            )
            app.state.notifications = notifier
            tasks.append(
                asyncio.create_task(
                    _every(settings.notification_interval_s, notifier.run_once, "notifications")
                )
            )
        if chain is not None:
            worker = PayoutWorker(maker, chain, load_account_file(settings.oracle_key_file))  # type: ignore[arg-type]
            app.state.payouts = worker
            tasks.append(
                asyncio.create_task(_every(settings.payout_interval_s, worker.run_once, "payouts"))
            )
        if chain is not None and settings.sales_enabled:
            settlements = SettlementWorker(
                maker,
                chain,
                load_account_file(settings.operator_key_file),  # type: ignore[arg-type]
                load_account_file(settings.oracle_key_file),  # type: ignore[arg-type]
            )
            app.state.settlements = settlements
            tasks.append(
                asyncio.create_task(
                    _every(settings.settlement_interval_s, settlements.run_once, "settlements")
                )
            )
            pinata = None
            if settings.ipfs_enabled:
                pin_http = httpx.AsyncClient(timeout=30)
                pinata = PinataPin(pin_http, settings.pinata_api_url, settings.pinata_jwt)  # type: ignore[arg-type]
            anchors = AnchorWorker(
                maker,
                chain,
                load_account_file(settings.operator_key_file),  # type: ignore[arg-type]
                pinata,
                settings.ipfs_gateway,
            )
            app.state.anchors = anchors
            tasks.append(
                asyncio.create_task(
                    _every(settings.settlement_interval_s, anchors.run_once, "anchors")
                )
            )
        gas_keys = {}
        if settings.chain_enabled:
            gas_keys["oráculo"] = load_account_file(settings.oracle_key_file).address  # type: ignore[arg-type]
        if settings.sales_enabled:
            gas_keys["operador"] = load_account_file(settings.operator_key_file).address  # type: ignore[arg-type]
        if settings.accounts_enabled and settings.guardian_key_file:
            guardian_address = load_account_file(settings.guardian_key_file).address
            if guardian_address != gas_keys.get("oráculo"):
                gas_keys["guardián"] = guardian_address

        async def snapshot():
            return await health_report(maker, settings, chain, gas_keys, bridge.connected.is_set())

        app.state.health = snapshot
        if settings.email_enabled:
            alerts = AlertWorker(maker, settings, snapshot)
            app.state.alerts = alerts
            tasks.append(
                asyncio.create_task(_every(settings.alert_interval_s, alerts.run_once, "alerts"))
            )
        if chain is not None and settings.accounts_enabled:
            guardian = load_account_file(settings.guardian_key_file or settings.oracle_key_file)  # type: ignore[arg-type]
            # The guardian relays signed payments too: it may deploy accounts (docs/adr/0029).
            relays = RelayWorker(maker, chain, guardian)
            app.state.relays = relays
            tasks.append(
                asyncio.create_task(_every(settings.relay_interval_s, relays.run_once, "relays"))
            )
            recoveries = RecoveryWorker(maker, chain, guardian, settings)
            app.state.recoveries = recoveries
            tasks.append(
                asyncio.create_task(
                    _every(settings.recovery_interval_s, recoveries.run_once, "recoveries")
                )
            )
        mail_http = None
        if settings.email_enabled:
            if settings.resend_api_key:
                mail_http = httpx.AsyncClient(timeout=15)
                mailer = ResendMail(
                    mail_http, settings.resend_api_url, settings.resend_api_key, settings.email_from
                )
            else:
                mailer = LogMail()
            emails = EmailWorker(maker, mailer)
            app.state.emails = emails
            tasks.append(
                asyncio.create_task(_every(settings.email_interval_s, emails.run_once, "emails"))
            )
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            for t in tasks:
                with suppress(asyncio.CancelledError):
                    await t
            if app.state.simulator is not None:
                await app.state.simulator.aclose()
            if push_http is not None:
                await push_http.aclose()
            if mail_http is not None:
                await mail_http.aclose()
            if pin_http is not None:
                await pin_http.aclose()
            await engine.dispose()

    docs = (
        {} if settings.docs_enabled else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    )
    app = FastAPI(title="Zyrcle API", version="0.1.0", lifespan=lifespan, **docs)
    app.include_router(router)
    app.include_router(public_router)
    app.include_router(booking_router)
    app.include_router(setup_router)
    app.include_router(center_router)
    app.include_router(ticket_router)
    app.include_router(bank_router)
    app.include_router(account_router)
    app.include_router(collection_router)
    app.include_router(sale_router)
    app.include_router(operator_router)
    app.include_router(impact_router)
    app.include_router(payment_router)
    if settings.demo_simulator_url:
        from .demo import router as demo_router

        app.include_router(demo_router)
    if settings.rate_limits_enabled:
        # Added before CORS, so CORS wraps it and a 429 still carries the CORS headers.
        app.add_middleware(RateLimitMiddleware, settings=settings)
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
            # The file name of an export (docs/adr/0045), which a browser hides from scripts
            # on another origin unless it is listed.
            expose_headers=["Content-Disposition"],
        )
    return app
