"""SQLAlchemy ORM models for FMC Audit & Change Intelligence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.db_base import Base


class AuditRecord(Base):
    __tablename__ = "fmc_audit_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fmc_id = Column(String(128), nullable=False, unique=True)
    audit_id = Column(String(128), index=True)
    record_id = Column(String(128), index=True)
    snapshot_id = Column(String(128), index=True)
    timestamp = Column(DateTime(timezone=True), nullable=True, index=True)
    user_name = Column(String(255), index=True)
    user_id = Column(String(128))
    source_ip = Column(String(45))
    source = Column(String(255))
    subsystem = Column(String(255), index=True)
    message = Column(Text)
    description = Column(Text)
    action = Column(String(32), index=True)  # ADD, UPDATE, DELETE, NOCHANGE
    object_type = Column(String(128), index=True)
    object_name = Column(String(512))
    object_id = Column(String(128))
    parent_type = Column(String(128))
    parent_name = Column(String(512))
    parent_id = Column(String(128))
    before_json = Column(JSONB)
    after_json = Column(JSONB)
    changed_fields = Column(JSONB)
    refs_added = Column(JSONB)
    refs_removed = Column(JSONB)
    values_added = Column(JSONB)
    values_deleted = Column(JSONB)
    values_updated = Column(JSONB)
    config_changes = Column(JSONB)
    normalization_notes = Column(JSONB)
    raw_json = Column(JSONB)
    collected_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Risk scoring
    risk_score = Column(SmallInteger, default=0, index=True)
    risk_factors = Column(JSONB)
    deployment_id = Column(String(128))
    deployed = Column(Boolean, default=False)
    deploy_success = Column(Boolean)

    __table_args__ = (Index("idx_audit_obj", "object_type", "object_name"),)


class DeploymentRecord(Base):
    __tablename__ = "fmc_deployments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fmc_id = Column(String(128), nullable=False, unique=True)
    name = Column(String(512))
    status = Column(String(64))
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    triggered_by = Column(String(255))
    device_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    devices = Column(JSONB)
    raw_json = Column(JSONB)
    collected_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class UserStats(Base):
    __tablename__ = "fmc_user_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(String(255), nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    total_changes = Column(Integer, default=0)
    adds = Column(Integer, default=0)
    updates = Column(Integer, default=0)
    deletes = Column(Integer, default=0)
    avg_risk_score = Column(Float, default=0)
    max_risk_score = Column(SmallInteger, default=0)
    objects_touched = Column(JSONB)
    computed_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_name", "period_start", "period_end", name="uq_user_stats_period"),
    )
