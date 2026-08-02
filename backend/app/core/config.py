import json
from functools import lru_cache
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
    database_url: str = ""
    database_auto_create_schema: bool = False
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 600
    rate_limit_sensitive_requests_per_minute: int = 20
    netbox_device_cache_ttl_seconds: int = 3600
    inventory_refresh_enabled: bool = True
    inventory_refresh_cron: str = "*/30 * * * *"

    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:9090",
            "http://localhost:9091",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:9090",
            "http://127.0.0.1:9091",
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
    keycloak_issuer_url: AnyHttpUrl | None = None
    keycloak_client_id: str = "netlens"
    keycloak_audience: str = "account"
    keycloak_realm_roles: list[str] = Field(default_factory=lambda: ["admin", "user"])

    # --- NetBox ---
    netbox_token: str = ""
    netbox_url: str | None = None
    netbox_verify_ssl: bool = False
    netbox_timeout_seconds: float = 15.0

    # --- OpenSearch ---
    opensearch_url: AnyHttpUrl | None = None
    opensearch_username: str | None = None
    opensearch_password: str | None = None
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
    scanner_dataset_path: str = "app/scanner/net_dataset.json"
    scanner_credentials: list[dict[str, str]] = Field(default_factory=list)

    # --- FMC (Firewall Management Center) ---
    fmc_url: str = ""
    fmc_username: str = ""
    fmc_password: str = ""
    fmc_verify_ssl: bool = False
    fmc_timeout_seconds: float = 30.0
    fmc_max_attempts: int = 5
    fmc_min_request_interval_seconds: float = 1.0
    fmc_rate_limit_cooldown_seconds: float = 10.0
    fmc_raw_response_limit: int = 500
    fmc_raw_response_max_bytes: int = 262_144
    fmc_device_health_stale_seconds: int = 900
    fmc_raw_response_retention_days: int = 14
    fmc_monitoring_enabled: bool = True
    fmc_full_scan_enabled: bool = False
    fmc_full_scan_cron: str = "0 3 * * *"  # daily at 3 AM
    fmc_discovery_refresh_minutes: int = 30
    fmc_device_health_refresh_seconds: int = 300
    fmc_health_history_lookback_seconds: int = 3600
    fmc_health_history_step_seconds: int = 60
    fmc_interface_refresh_minutes: int = 60
    fmc_ha_refresh_seconds: int = 300
    fmc_alert_refresh_seconds: int = 600
    fmc_policy_analysis_refresh_hours: int = 24
    fmc_vpn_refresh_enabled: bool = True
    fmc_vpn_refresh_minutes: int = 5
    fmc_vpn_flap_transition_threshold: int = 3
    fmc_vpn_flap_window_seconds: int = 900

    # --- FMC Audit ---
    fmc_audit_enabled: bool = True
    fmc_audit_interval_minutes: int = 5
    fmc_alert_flap_reopen_threshold: int = 3

    # --- Retention ---
    retention_enabled: bool = True
    retention_cron: str = "17 4 * * *"
    metric_retention_days: int = 90
    vpn_transition_retention_days: int = 1095
    health_alert_retention_days: int = 1095
    collector_run_retention_days: int = 30

    # --- Slack Notifications ---
    slack_webhook_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
