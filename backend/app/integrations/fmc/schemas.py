"""Normalized FMC monitoring schemas — per the technical specification."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class MetricStatus(StrEnum):
    VALUE = "VALUE"
    VALUE_ZERO = "VALUE_ZERO"
    NO_DATA = "NO_DATA"
    AVAILABLE_NO_DATA = "AVAILABLE_NO_DATA"
    UNSUPPORTED = "UNSUPPORTED"
    PERMISSION_ERROR = "PERMISSION_ERROR"
    TEMPORARY_ERROR = "TEMPORARY_ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    DEVICE_DISCONNECTED = "DEVICE_DISCONNECTED"
    HEALTH_POLICY_MISSING = "HEALTH_POLICY_MISSING"
    STALE_DEVICE = "STALE_DEVICE"
    PARTIAL = "PARTIAL"


class FreshnessState(StrEnum):
    FRESH = "FRESH"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    ERROR = "ERROR"
    NEVER_COLLECTED = "NEVER_COLLECTED"


class SourceFreshness(BaseModel):
    source: str
    state: FreshnessState = FreshnessState.NEVER_COLLECTED
    last_attempt: str | None = None
    last_success: str | None = None
    collection_duration_seconds: float | None = None
    records_received: int | None = None
    partial_result: bool = False
    error: str | None = None
    stale_threshold_seconds: int


class CapabilityStatus(BaseModel):
    status: str = "UNKNOWN"


class DeviceIdentity(BaseModel):
    id: str | None = None
    name: str | None = None
    host_name: str | None = None
    model: str | None = None
    model_number: str | None = None
    model_type: str | None = None
    model_id: str | None = None
    sw_version: str | None = None
    ftd_mode: str | None = None
    role: str | None = None
    status: str | None = None
    is_connected: bool | None = None
    health_status: str | None = None
    health_message: str | None = None
    deployment_status: str | None = None
    snort_engine: str | None = None
    performance_tier: str | None = None
    health_policy: str | None = None
    access_policy: str | None = None
    license_caps: list[str] = Field(default_factory=list)
    serial_number: str | None = None
    snort_version: str | None = None
    sru_version: str | None = None
    vdb_version: str | None = None
    is_dummy_device: bool = False
    is_part_of_container: bool = False
    container_details: dict = Field(default_factory=dict)
    links_self: str | None = None
    raw: dict = Field(default_factory=dict)


class CpuMetrics(BaseModel):
    lina_percent: float | None = None
    snort_percent: float | None = None
    system_percent: float | None = None
    source: str = "unknown"
    metric_window: str = "5m"


class MemoryMetrics(BaseModel):
    lina_percent: float | None = None
    snort_percent: float | None = None
    system_percent: float | None = None
    source: str = "unknown"
    metric_window: str = "5m"


class DiskMetrics(BaseModel):
    total_usage_percent: float | None = None
    source: str = "unknown"


class HardwareFan(BaseModel):
    name: str | None = None
    rpm: float | None = None
    source: str = "health_aggregate"


class HardwareBlock(BaseModel):
    fans: list[HardwareFan] = Field(default_factory=list)
    power_supplies: list[dict] = Field(default_factory=list)
    processors: list[dict] = Field(default_factory=list)
    memory_modules: list[dict] = Field(default_factory=list)
    security_modules: list[dict] = Field(default_factory=list)
    storage_controllers: list[dict] = Field(default_factory=list)


class InterfaceRuntime(BaseModel):
    link_status: str | None = None
    operational_status: str | None = None
    duplex: str | None = None
    input_bytes_average: float | None = None
    output_bytes_average: float | None = None
    input_errors_average: float | None = None
    output_errors_average: float | None = None
    drops_average: float | None = None
    l2_decode_drops_average: float | None = None
    buffer_overruns_average: float | None = None
    buffer_underruns_average: float | None = None
    input_packet_size_average: float | None = None
    output_packet_size_average: float | None = None
    metric_status: MetricStatus = MetricStatus.NO_DATA
    metric_window: str = "5m"


class NormalizedInterface(BaseModel):
    id: str | None = None
    physical_name: str | None = None
    logical_name: str | None = None
    type: str | None = None
    enabled: bool = False
    mode: str | None = None
    mtu: int | None = None
    management_only: bool = False
    security_zone: dict = Field(default_factory=dict)
    addresses: dict = Field(default_factory=dict)
    mac_active: str | None = None
    mac_standby: str | None = None
    runtime: InterfaceRuntime = Field(default_factory=InterfaceRuntime)
    metric_status: MetricStatus = MetricStatus.NO_DATA
    collected_at: str | None = None
    sources: list[str] = Field(default_factory=list)
    raw: dict = Field(default_factory=dict)


class HealthAlert(BaseModel):
    id: str | None = None
    name: str | None = None
    device_uuid: str | None = None
    status: str | None = None  # RED, YELLOW, GREEN
    module_id: str | None = None
    details: str | None = None
    timestamp: int | None = None
    raw: dict = Field(default_factory=dict)


class HaMember(BaseModel):
    device_id: str | None = None
    role: str | None = None
    runtime_role: str | None = None
    device_health: dict = Field(default_factory=dict)


class HaIpv4Configuration(BaseModel):
    active_address: str | None = None
    active_mask: str | None = None
    standby_address: str | None = None


class HaIpv6AddressPair(BaseModel):
    active_address: str | None = None
    standby_address: str | None = None


class HaIpv6Configuration(BaseModel):
    active_link_local_address: str | None = None
    standby_link_local_address: str | None = None
    address_pairs: list[HaIpv6AddressPair] = Field(default_factory=list)


class HaMonitoredInterface(BaseModel):
    id: str | None = None
    name: str | None = None
    description: str | None = None
    interface_logical_name: str | None = None
    monitor_for_failures: bool | None = None
    ipv4: HaIpv4Configuration = Field(default_factory=HaIpv4Configuration)
    ipv6: HaIpv6Configuration = Field(default_factory=HaIpv6Configuration)
    raw: dict = Field(default_factory=dict)
    collection_errors: list[str] = Field(default_factory=list)


class HaPair(BaseModel):
    id: str | None = None
    name: str | None = None
    health_status: str | None = None
    health_message: str | None = None
    status: str | None = None
    pair_state: str = "UNKNOWN"
    active_member_id: str | None = None
    standby_member_id: str | None = None
    failover_link: dict = Field(default_factory=dict)
    stateful_link: dict = Field(default_factory=dict)
    primary: HaMember = Field(default_factory=HaMember)
    secondary: HaMember = Field(default_factory=HaMember)
    monitored_interfaces: list[HaMonitoredInterface] = Field(default_factory=list)
    raw: dict = Field(default_factory=dict)
    collection_errors: list[str] = Field(default_factory=list)


class ChassisFault(BaseModel):
    severity: str | None = None
    code: str | None = None
    cause: str | None = None
    description: str | None = None
    raw: dict = Field(default_factory=dict)


class ChassisData(BaseModel):
    id: str | None = None
    name: str | None = None
    host_name: str | None = None
    model: str | None = None
    model_number: str | None = None
    sw_version: str | None = None
    is_connected: bool = False
    inventory: dict = Field(default_factory=dict)
    faults: list[ChassisFault] = Field(default_factory=list)
    interface_summary: list[dict] = Field(default_factory=list)
    instances: list[dict] = Field(default_factory=list)
    logical_devices: list[dict] = Field(default_factory=list)
    raw: dict = Field(default_factory=dict)
    collection_errors: list[str] = Field(default_factory=list)


class CollectedDevice(BaseModel):
    collection_run_id: str | None = None
    collected_at: str | None = None
    domain_id: str | None = None
    device: DeviceIdentity = Field(default_factory=DeviceIdentity)
    load: dict = Field(default_factory=dict)
    hardware: HardwareBlock = Field(default_factory=HardwareBlock)
    interfaces: list[NormalizedInterface] = Field(default_factory=list)
    alerts: list[HealthAlert] = Field(default_factory=list)
    ha: HaPair | None = None
    chassis: ChassisData | None = None
    capabilities: dict[str, str] = Field(default_factory=dict)
    aggregate_status: MetricStatus = MetricStatus.NO_DATA
    diagnostics: list[dict] = Field(default_factory=list)
    collection_errors: list[str] = Field(default_factory=list)
    raw_references: list[dict] = Field(default_factory=list)


class MonitoringDashboard(BaseModel):
    collection_run_id: str | None = None
    collected_at: str | None = None
    domain_id: str | None = None
    devices: list[CollectedDevice] = Field(default_factory=list)
    ha_pairs: list[HaPair] = Field(default_factory=list)
    chassis: list[ChassisData] = Field(default_factory=list)
    tunnel_statuses: list[dict] = Field(default_factory=list)
    tunnel_summaries: list[dict] = Field(default_factory=list)
    policy_analysis: dict = Field(default_factory=dict)
    total_devices: int = 0
    devices_connected: int = 0
    tunnel_up: int = 0
    tunnel_down: int = 0
    tunnel_unknown: int = 0
    alerts_total: int = 0
    alerts_red: int = 0
    alerts_yellow: int = 0
    source_freshness: list[SourceFreshness] = Field(default_factory=list)
    collection_errors: list[str] = Field(default_factory=list)
    reset_status: dict = Field(default_factory=lambda: {"state": "idle"})
