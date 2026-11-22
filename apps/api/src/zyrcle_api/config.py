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
    operator_token: str = Field(min_length=24)

    siwe_domain: str = "zyrcle.deviego.xyz"
    chain_id: int = 20261121

    code_rotation_s: int = 30
    device_offline_after_s: int = 90
    unlock_ack_timeout_s: int = 15
    idle_timeout_s: int = 60
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
    # Advance = ratio x reference price x kg, capped like the contract (docs/adr/0003).
    advance_ratio_bps: int = 5_000
    max_advance_cop: int = 5_000
    payout_interval_s: float = 2.0

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


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
