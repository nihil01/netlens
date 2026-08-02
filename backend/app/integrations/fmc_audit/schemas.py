"""Pydantic DTOs for FMC Audit & Change Intelligence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditRecordDto(BaseModel):
    id: int | None = None
    fmc_id: str
    audit_id: str | None = None
    record_id: str | None = None
    snapshot_id: str | None = None
    timestamp: datetime | None = None
    local_timestamp: datetime | None = None
    user_name: str | None = None
    user_id: str | None = None
    source_ip: str | None = None
    source: str | None = None
    subsystem: str | None = None
    message: str | None = None
    description: str | None = None
    action: str = "UNKNOWN"
    object_type: str | None = None
    object_name: str | None = None
    object_id: str | None = None
    parent_type: str | None = None
    parent_name: str | None = None
    parent_id: str | None = None
    before_json: dict | None = None
    after_json: dict | None = None
    changed_fields: list[str] = Field(default_factory=list)
    refs_added: list[dict] = Field(default_factory=list)
    refs_removed: list[dict] = Field(default_factory=list)
    values_added: list[dict] = Field(default_factory=list)
    values_deleted: list[dict] = Field(default_factory=list)
    values_updated: list[dict] = Field(default_factory=list)
    config_changes: list[dict] = Field(default_factory=list)
    raw_json: dict = Field(default_factory=dict)
    normalization_notes: list[str] = Field(default_factory=list)
    risk_score: int = 0
    risk_factors: list[str] = Field(default_factory=list)
    deployed: bool = False
    deploy_success: bool | None = None
    deployment_id: str | None = None


class DeploymentDto(BaseModel):
    id: int | None = None
    fmc_id: str
    name: str | None = None
    status: str = "UNKNOWN"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    triggered_by: str | None = None
    device_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    devices: list[dict] = Field(default_factory=list)
    raw_json: dict = Field(default_factory=dict)


class UserStatsDto(BaseModel):
    user_name: str
    total_changes: int = 0
    adds: int = 0
    updates: int = 0
    deletes: int = 0
    avg_risk_score: float = 0
    max_risk_score: int = 0
    objects_touched: list[str] = Field(default_factory=list)


class FieldDiff(BaseModel):
    field: str
    before: Any = None
    after: Any = None
    change_type: str  # added | removed | modified


class AuditDiffDto(BaseModel):
    record: AuditRecordDto
    before: dict | None = None
    after: dict | None = None
    field_diffs: list[FieldDiff] = Field(default_factory=list)


class RelationshipNode(BaseModel):
    id: str
    type: str
    name: str
    risk: int = 0


class RelationshipEdge(BaseModel):
    source: str
    target: str
    type: str


class RelationshipGraph(BaseModel):
    nodes: list[RelationshipNode] = Field(default_factory=list)
    edges: list[RelationshipEdge] = Field(default_factory=list)


class AuditDashboard(BaseModel):
    total_records: int = 0
    records_today: int = 0
    records_this_week: int = 0
    risk_distribution: dict = Field(default_factory=dict)
    top_users: list[UserStatsDto] = Field(default_factory=list)
    recent_high_risk: list[AuditRecordDto] = Field(default_factory=list)
    timeline: list[dict] = Field(default_factory=list)
    deployment_stats: dict = Field(default_factory=dict)


class AuditTimeline(BaseModel):
    records: list[AuditRecordDto] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50
