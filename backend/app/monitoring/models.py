"""PostgreSQL models for local NOC current state and history."""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db_base import Base


class CollectorRun(Base):
    __tablename__ = "collector_runs"

    id = Column(UUID(as_uuid=False), primary_key=True)
    collector = Column(String(128), nullable=False, index=True)
    source = Column(String(128), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    finished_at = Column(DateTime(timezone=True))
    status = Column(String(32), nullable=False, index=True)
    partial_result = Column(Boolean, nullable=False, default=False)
    records_received = Column(Integer)
    duration_seconds = Column(Float)
    error_category = Column(String(64))
    error = Column(Text)
    metadata_json = Column(JSONB, nullable=False, default=dict)


class SourceFreshnessState(Base):
    __tablename__ = "source_freshness"

    source = Column(String(128), primary_key=True)
    state = Column(String(32), nullable=False, index=True)
    last_attempt = Column(DateTime(timezone=True))
    last_success = Column(DateTime(timezone=True))
    collection_duration_seconds = Column(Float)
    records_received = Column(Integer)
    partial_result = Column(Boolean, nullable=False, default=False)
    error = Column(Text)
    stale_threshold_seconds = Column(Integer, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class FmcDeviceCurrent(Base):
    __tablename__ = "fmc_devices_current"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    domain_id = Column(UUID(as_uuid=False), nullable=False)
    device_id = Column(UUID(as_uuid=False), nullable=False)
    name = Column(String(512))
    host_name = Column(String(512))
    management_ip = Column(String(64))
    model = Column(String(255))
    model_number = Column(String(255))
    software_version = Column(String(128))
    serial_number = Column(String(255), index=True)
    is_connected = Column(Boolean)
    health_status = Column(String(64), index=True)
    health_message = Column(Text)
    deployment_status = Column(String(64))
    role = Column(String(64))
    status = Column(String(64))
    health_policy = Column(String(512))
    access_policy = Column(String(512))
    is_dummy_device = Column(Boolean, nullable=False, default=False)
    is_part_of_container = Column(Boolean, nullable=False, default=False)
    container_details = Column(JSONB, nullable=False, default=dict)
    capabilities = Column(JSONB, nullable=False, default=dict)
    aggregate_status = Column(String(32), nullable=False)
    raw_json = Column(JSONB, nullable=False, default=dict)
    last_collection_run_id = Column(
        UUID(as_uuid=False), ForeignKey("collector_runs.id", ondelete="SET NULL")
    )
    first_seen_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("domain_id", "device_id", name="uq_fmc_device_domain_device"),
        Index("idx_fmc_device_name", "domain_id", "name"),
    )


class MetricSample(Base):
    __tablename__ = "metric_samples"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    domain_id = Column(UUID(as_uuid=False), nullable=False)
    device_id = Column(UUID(as_uuid=False), index=True)
    interface_id = Column(String(128), index=True)
    ha_pair_id = Column(UUID(as_uuid=False), index=True)
    vpn_tunnel_id = Column(String(256), index=True)
    metric_name = Column(String(128), nullable=False, index=True)
    metric_value = Column(Float)
    metric_status = Column(String(32), nullable=False, index=True)
    source = Column(String(128), nullable=False)
    metric_window = Column(String(32))
    collection_run_id = Column(
        UUID(as_uuid=False),
        ForeignKey("collector_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    __table_args__ = (
        Index(
            "idx_metric_device_name_time",
            "device_id",
            "metric_name",
            "timestamp",
        ),
        Index(
            "idx_metric_interface_name_time",
            "interface_id",
            "metric_name",
            "timestamp",
        ),
    )


class RawFmcResponse(Base):
    __tablename__ = "raw_fmc_responses"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    collection_run_id = Column(
        UUID(as_uuid=False),
        ForeignKey("collector_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    collected_at = Column(DateTime(timezone=True), nullable=False, index=True)
    device_id = Column(UUID(as_uuid=False), index=True)
    endpoint = Column(Text, nullable=False)
    http_status = Column(Integer)
    duration_ms = Column(Float)
    response_bytes = Column(Integer, nullable=False, default=0)
    items_count = Column(Integer)
    error_category = Column(String(64), index=True)
    payload = Column(JSONB)
    payload_omitted = Column(Boolean, nullable=False, default=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)


class NetboxFmcCorrelation(Base):
    __tablename__ = "netbox_fmc_correlations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    netbox_device_id = Column(BigInteger, nullable=False, index=True)
    fmc_domain_id = Column(UUID(as_uuid=False), nullable=False)
    fmc_device_id = Column(UUID(as_uuid=False), nullable=False, index=True)
    method = Column(String(64), nullable=False)
    confidence = Column(Float, nullable=False)
    matched_fields = Column(JSONB, nullable=False, default=list)
    manual_override = Column(Boolean, nullable=False, default=False)
    last_verified_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "netbox_device_id",
            "fmc_domain_id",
            "fmc_device_id",
            name="uq_netbox_fmc_correlation",
        ),
    )


class HaPairCurrent(Base):
    __tablename__ = "ha_pairs_current"

    pair_id = Column(UUID(as_uuid=False), primary_key=True)
    domain_id = Column(UUID(as_uuid=False), nullable=False, index=True)
    name = Column(String(512))
    pair_state = Column(String(32), nullable=False, index=True)
    health_status = Column(String(64))
    health_message = Column(Text)
    primary_device_id = Column(UUID(as_uuid=False), nullable=False, index=True)
    secondary_device_id = Column(UUID(as_uuid=False), nullable=False, index=True)
    active_member_id = Column(UUID(as_uuid=False), index=True)
    standby_member_id = Column(UUID(as_uuid=False), index=True)
    failover_link = Column(JSONB, nullable=False, default=dict)
    stateful_link = Column(JSONB, nullable=False, default=dict)
    monitored_interfaces = Column(JSONB, nullable=False, default=list)
    last_role_transition_at = Column(DateTime(timezone=True))
    last_health_transition_at = Column(DateTime(timezone=True))
    first_seen_at = Column(DateTime(timezone=True), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=False, index=True)
    raw_json = Column(JSONB, nullable=False, default=dict)


class HaRoleTransition(Base):
    __tablename__ = "ha_role_transitions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    domain_id = Column(UUID(as_uuid=False), nullable=False)
    pair_id = Column(UUID(as_uuid=False), nullable=False, index=True)
    device_id = Column(UUID(as_uuid=False), nullable=False, index=True)
    previous_role = Column(String(64))
    new_role = Column(String(64), nullable=False)
    changed_at = Column(DateTime(timezone=True), nullable=False, index=True)
    collection_run_id = Column(
        UUID(as_uuid=False), ForeignKey("collector_runs.id", ondelete="SET NULL")
    )
    raw_json = Column(JSONB, nullable=False, default=dict)


class VpnTunnelCurrent(Base):
    __tablename__ = "vpn_tunnels_current"

    tunnel_id = Column(String(256), primary_key=True)
    domain_id = Column(UUID(as_uuid=False), nullable=False, index=True)
    name = Column(String(512))
    peer = Column(String(512))
    device_id = Column(UUID(as_uuid=False), index=True)
    policy = Column(String(512))
    current_status = Column(String(32), nullable=False, index=True)
    is_flapping = Column(Boolean, nullable=False, default=False, index=True)
    first_seen_at = Column(DateTime(timezone=True), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=False, index=True)
    state_changed_at = Column(DateTime(timezone=True), nullable=False)
    last_up_at = Column(DateTime(timezone=True))
    last_down_at = Column(DateTime(timezone=True))
    transition_count = Column(Integer, nullable=False, default=0)
    flap_count = Column(Integer, nullable=False, default=0)
    raw_json = Column(JSONB, nullable=False, default=dict)


class VpnTunnelTransition(Base):
    __tablename__ = "vpn_tunnel_transitions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tunnel_id = Column(
        String(256), ForeignKey("vpn_tunnels_current.tunnel_id", ondelete="CASCADE"), index=True
    )
    previous_status = Column(String(32))
    new_status = Column(String(32), nullable=False)
    changed_at = Column(DateTime(timezone=True), nullable=False, index=True)
    duration_in_previous_state_seconds = Column(Integer)
    collection_run_id = Column(
        UUID(as_uuid=False), ForeignKey("collector_runs.id", ondelete="SET NULL")
    )

    __table_args__ = (Index("idx_vpn_transition_tunnel_time", "tunnel_id", "changed_at"),)


class HealthAlertCurrent(Base):
    __tablename__ = "health_alerts_current"

    alert_id = Column(String(256), primary_key=True)
    domain_id = Column(UUID(as_uuid=False), nullable=False, index=True)
    device_id = Column(UUID(as_uuid=False), index=True)
    module_id = Column(String(256), index=True)
    severity = Column(String(32), index=True)
    source_status = Column(String(64))
    lifecycle_state = Column(String(32), nullable=False, index=True)
    description = Column(Text)
    details = Column(Text)
    first_seen_at = Column(DateTime(timezone=True), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=False, index=True)
    resolved_at = Column(DateTime(timezone=True))
    reopen_count = Column(Integer, nullable=False, default=0)
    repeat_count = Column(Integer, nullable=False, default=0)
    raw_json = Column(JSONB, nullable=False, default=dict)


class HealthAlertObservation(Base):
    __tablename__ = "health_alert_observations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    alert_id = Column(
        String(256), ForeignKey("health_alerts_current.alert_id", ondelete="CASCADE"), index=True
    )
    observed_at = Column(DateTime(timezone=True), nullable=False, index=True)
    lifecycle_state = Column(String(32), nullable=False)
    severity = Column(String(32))
    source_status = Column(String(64))
    collection_run_id = Column(
        UUID(as_uuid=False), ForeignKey("collector_runs.id", ondelete="SET NULL")
    )
    raw_json = Column(JSONB, nullable=False, default=dict)
