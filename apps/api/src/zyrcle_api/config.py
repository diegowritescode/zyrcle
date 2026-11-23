from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ZYRCLE_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://zyrcle:zyrcle@localhost:5432/zyrcle"

    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str = "api"
    mqtt_password: str = ""
    # Shared subscription, so several API replicas split device traffic instead of duplicating it.
    mqtt_share_group: str = "zyrcle-api"

    jwt_secret: str = Field(min_length=32)
    jwt_ttl_minutes: int = 24 * 60
    # Operators' console sessions: a working day (docs/adr/0014).
    operator_jwt_ttl_minutes: int = 8 * 60
    operator_token: str = Field(min_length=24)

    siwe_domain: str = "zyrcle.deviego.xyz"
    # Local time zone for daily aggregates (dashboard charts group deposits by local day).
    timezone: str = "America/Bogota"
    chain_id: int = 20261121

    code_rotation_s: int = 30
    device_offline_after_s: int = 90
    unlock_ack_timeout_s: int = 15
    idle_timeout_s: int = 60
    # A collector bags several materials one after another (docs/adr/0012).
    collection_idle_timeout_s: int = 600
    measurement_timeout_s: int = 20
    sweep_interval_s: float = 1.0

    # Distance sensor noise (mm) used to bound the volume estimate. VL53L1X time-of-flight: ±2 mm.
    fill_sensor_noise_mm: int = 2
    # A reading this far from the tare (g) means material is going in.
    weight_change_g: int = 10

    # ZyrcleChain. Payouts stay pending until all three are configured.
    chain_rpc_url: str | None = None
    treasury_address: str | None = None
    oracle_key_file: str | None = None  # hex private key of the Treasury's ORACLE_ROLE
    # Hex private key of the Treasury's OPERATOR_ROLE: records sales once an operator confirmed the
    # bank match (docs/adr/0013). Without it, confirmed sales wait.
    operator_key_file: str | None = None
    settlement_interval_s: float = 3.0
    relay_interval_s: float = 2.0

    # Pilot readiness (docs/adr/0028). Interactive API docs are for development; production turns
    # them off.
    docs_enabled: bool = True
    # The data-processing policy in force (its date), and whether depositing requires having
    # accepted it. Off until the pilot, so apps installed before the consent screen keep working.
    privacy_version: str = "2026-11-22"
    require_consent: bool = False
    # Health warnings, emailed to admins at most once a day per kind.
    alert_interval_s: float = 600.0
    alert_gas_min_zyr: float = 1.0
    alert_available_min_cop: int = 100_000
    alert_stuck_after_min: int = 30
    alert_chain_stale_min: int = 10
    # Advance = ratio x reference price x kg, capped like the contract (docs/adr/0003).
    advance_ratio_bps: int = 5_000
    max_advance_cop: int = 5_000
    payout_interval_s: float = 2.0

    # Push notifications through Expo's push service (docs/adr/0008-push-notifications.md). The
    # access token is needed only if "enhanced security for push notifications" is on in Expo.
    push_enabled: bool = True
    expo_push_url: str = "https://exp.host/--/api/v2/push"
    expo_access_token: str | None = None
    notification_interval_s: float = 2.0
    # Expo has the delivery receipt (accepted or not by Apple/Google) about 15 minutes later.
    push_receipt_delay_s: float = 15 * 60

    # Residents' smart accounts and lost-phone recovery (docs/adr/0010). Without a factory, a
    # resident's ZYR goes straight to their phone key, as before.
    account_factory_address: str | None = None
    # The key that starts and cancels recoveries (the factory's guardian). Defaults to the oracle
    # key; production should give it its own.
    guardian_key_file: str | None = None
    recovery_interval_s: float = 5.0

    # Email through Resend's HTTP API (https://resend.com/docs/api-reference/emails/send-email):
    # verification codes and recovery alerts. No key, no email (and no recovery).
    resend_api_key: str | None = None
    resend_api_url: str = "https://api.resend.com"
    email_from: str = "Zyrcle <no-reply@zyrcle.deviego.xyz>"
    email_interval_s: float = 1.0
    # Local development only: write emails to the log instead of sending them.
    email_log_only: bool = False

    # Browser origins allowed to call the API (comma-separated), e.g. the demo page.
    cors_origins: str = ""
    # Demo mode: URL of the simulator's control panel. Empty disables the /v1/demo routes.
    demo_simulator_url: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def chain_enabled(self) -> bool:
        return bool(self.chain_rpc_url and self.treasury_address and self.oracle_key_file)

    @property
    def sales_enabled(self) -> bool:
        return self.chain_enabled and bool(self.operator_key_file)

    @property
    def accounts_enabled(self) -> bool:
        return self.chain_enabled and bool(self.account_factory_address)

    @property
    def email_enabled(self) -> bool:
        return bool(self.resend_api_key) or self.email_log_only

    @property
    def recovery_enabled(self) -> bool:
        return self.accounts_enabled and self.email_enabled


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
