from functools import lru_cache
import json
from typing import Any, Literal

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_cors(value: str | list[str]) -> list[str]:
    """Parse CORS origins from JSON string or list."""
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "local"
    log_level: str = "INFO"
    redis_url: str = "redis://localhost:6379/0"
    netbox_device_cache_ttl_seconds: int = 3600

    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:80",
            "http://localhost",
        ]
    )

    @classmethod
    def model_validate(cls, obj: Any, **kwargs: Any) -> "Settings":
        instance = super().model_validate(obj, **kwargs)
        if isinstance(instance.cors_origins, str):
            instance.cors_origins = _parse_cors(instance.cors_origins)
        return instance

    # --- Auth / Keycloak ---
    auth_enabled: bool = False
    keycloak_issuer_url: AnyHttpUrl | None = "http://net-mgmt.taxes.gov.az:8080/realms/dvx"
    keycloak_client_id: str = "netlens"
    keycloak_audience: str = "account"
    keycloak_realm_roles: list[str] = Field(default_factory=lambda: ["admin", "user"])

    # --- NetBox ---
    netbox_token: str = "4e5dd1cf728f732fa4b2d4f0b2cf11e2aef343f4"
    netbox_url: str | None = "https://net-mgmt.taxes.gov.az:5050"
    netbox_verify_ssl: bool = False
    netbox_timeout_seconds: float = 15.0

    # --- OpenSearch ---
    opensearch_url: AnyHttpUrl | None = "https://10.22.10.186:9200"
    opensearch_username: str | None = "admin"
    opensearch_password: str | None = "Orxan20052004!"
    opensearch_verify_ssl: bool = False

    opensearch_cisco_asa_index_pattern: str = "asa-*"
    opensearch_firepower_index_pattern: str = "firepower-*"
    opensearch_fmc_estreamer_index_pattern: str = "fmc-estreamer-*"
    opensearch_cisco_user_activity_index_pattern: str = "fmc-useractivity-*"
    opensearch_checkpoint_index_pattern: str = "checkpoint-*"

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

    # --- Scanner ---
    scanner_schedule_enabled: bool = True
    scanner_schedule_cron: str = "12 15 * * *"
    scanner_default_scope: str = "netbox-management"
    scanner_profile: Literal["safe", "normal", "aggressive"] = "safe"
    scanner_dataset_path: str = "./scanner/net_dataset.json"
    scanner_credentials: list[dict[str, str]] = Field(default_factory=list)


@lru_cache
def get_settings() -> Settings:
    return Settings()
