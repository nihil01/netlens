from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "local"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://netlens:netlens@localhost:5432/netlens"
    redis_url: str = "redis://localhost:6379/0"
    netbox_device_cache_ttl_seconds: int = 3600
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
        ]
    )

    auth_enabled: bool = False
    keycloak_issuer_url: AnyHttpUrl | None = None
    keycloak_audience: str = "netlens-api"

    netbox_url: AnyHttpUrl | None = None
    netbox_token: str | None = None
    netbox_verify_ssl: bool = True
    netbox_timeout_seconds: float = 15.0

    opensearch_url: AnyHttpUrl | None = None
    opensearch_username: str | None = None
    opensearch_password: str | None = None
    opensearch_verify_ssl: bool = True
    opensearch_index_pattern: str = "logs-*"
    opensearch_timeout_seconds: float = 20.0
    opensearch_timestamp_field: str = "@timestamp"
    opensearch_source_ip_fields: list[str] = Field(
        default_factory=lambda: ["source.ip", "src_ip", "src", "client.ip"]
    )
    opensearch_destination_ip_fields: list[str] = Field(
        default_factory=lambda: ["destination.ip", "dst_ip", "dst", "server.ip"]
    )
    opensearch_destination_port_field: str = "destination.port"
    opensearch_action_field: str = "event.action"
    opensearch_block_actions: list[str] = Field(
        default_factory=lambda: ["blocked", "block", "deny", "denied", "drop", "dropped"]
    )
    internal_cidrs: list[str] = Field(
        default_factory=lambda: ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
    )

    scanner_schedule_enabled: bool = False
    scanner_schedule_cron: str = "0 2 * * *"
    scanner_default_scope: str = "netbox-management"
    scanner_profile: Literal["safe", "normal", "aggressive"] = "safe"


@lru_cache
def get_settings() -> Settings:
    return Settings()
