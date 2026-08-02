"""FMC Audit Service — risk scoring, diff, stats, DB operations."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db import session_scope
from app.integrations.fmc_audit.collector import CRITICAL_FIELDS, HIGH_RISK_TYPES, FmcAuditCollector
from app.integrations.fmc_audit.models import AuditRecord, DeploymentRecord, UserStats
from app.integrations.fmc_audit.schemas import (
    AuditDashboard,
    AuditDiffDto,
    AuditRecordDto,
    AuditTimeline,
    DeploymentDto,
    FieldDiff,
    RelationshipEdge,
    RelationshipGraph,
    RelationshipNode,
    UserStatsDto,
)

logger = logging.getLogger(__name__)


class FmcAuditService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.collector = FmcAuditCollector(self.settings)

    @classmethod
    def from_settings(cls) -> FmcAuditService:
        return cls(get_settings())

    # ======================================================================
    # Refresh — called by scheduler
    # ======================================================================

    async def refresh(self) -> dict[str, Any]:
        """Collect new audit records & deployments from FMC, store in DB."""
        # Find last known timestamp
        last_ts = await self._get_last_timestamp()
        since = last_ts.isoformat() if last_ts else None

        # Collect from FMC
        records = await self.collector.collect_audit_records(since=since)
        deployments = await self.collector.collect_deployments(since=since)

        stored_records = 0
        stored_deployments = 0

        async with session_scope() as session:
            # Store audit records
            for rec in records:
                risk_score, risk_factors = self._compute_risk(rec)
                rec.risk_score = risk_score
                rec.risk_factors = risk_factors
                stored = await self._upsert_audit_record(session, rec)
                if stored:
                    stored_records += 1

            # Store deployments
            for dep in deployments:
                stored = await self._upsert_deployment(session, dep)
                if stored:
                    stored_deployments += 1

            # Update user stats
            await self._recompute_user_stats(session)

        result = {
            "status": "ok",
            "new_records": stored_records,
            "new_deployments": stored_deployments,
            "collected_at": datetime.now(UTC).isoformat(),
        }
        logger.info("FMC audit refresh: %s", result)
        return result

    # ======================================================================
    # Dashboard
    # ======================================================================

    async def get_dashboard(self) -> AuditDashboard:
        async with session_scope() as session:
            now = datetime.now(UTC)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = today_start - timedelta(days=7)

            # Total counts
            total = (await session.execute(select(func.count(AuditRecord.id)))).scalar() or 0
            today = (
                await session.execute(
                    select(func.count(AuditRecord.id)).where(AuditRecord.timestamp >= today_start)
                )
            ).scalar() or 0
            this_week = (
                await session.execute(
                    select(func.count(AuditRecord.id)).where(AuditRecord.timestamp >= week_start)
                )
            ).scalar() or 0

            # Risk distribution
            risk_rows = (
                (
                    await session.execute(
                        select(AuditRecord.risk_score).where(AuditRecord.risk_score > 0)
                    )
                )
                .scalars()
                .all()
            )
            risk_dist = {"low": 0, "medium": 0, "high": 0, "critical": 0}
            for score in risk_rows:
                if score >= 70:
                    risk_dist["critical"] += 1
                elif score >= 40:
                    risk_dist["high"] += 1
                elif score >= 20:
                    risk_dist["medium"] += 1
                else:
                    risk_dist["low"] += 1

            # Top users
            user_stats = (
                (
                    await session.execute(
                        select(UserStats)
                        .where(UserStats.period_end >= week_start)
                        .order_by(UserStats.total_changes.desc())
                        .limit(10)
                    )
                )
                .scalars()
                .all()
            )
            top_users = [self._user_stats_to_dto(u) for u in user_stats]

            # Recent high risk
            high_risk = (
                (
                    await session.execute(
                        select(AuditRecord)
                        .where(AuditRecord.risk_score >= 40)
                        .order_by(AuditRecord.timestamp.desc())
                        .limit(10)
                    )
                )
                .scalars()
                .all()
            )
            recent_hr = [self._record_to_dto(r) for r in high_risk]

            # Timeline (last 30 days)
            timeline_start = now - timedelta(days=30)
            timeline_rows = (
                (
                    await session.execute(
                        select(AuditRecord)
                        .where(AuditRecord.timestamp >= timeline_start)
                        .order_by(AuditRecord.timestamp.asc())
                    )
                )
                .scalars()
                .all()
            )
            timeline = self._build_timeline(timeline_rows)

            # Deployment stats
            dep_count = (
                await session.execute(select(func.count(DeploymentRecord.id)))
            ).scalar() or 0
            dep_success = (
                await session.execute(
                    select(func.count(DeploymentRecord.id)).where(
                        DeploymentRecord.status == "SUCCESS"
                    )
                )
            ).scalar() or 0
            dep_failed = (
                await session.execute(
                    select(func.count(DeploymentRecord.id)).where(
                        DeploymentRecord.status.in_(["FAILED", "ERROR"])
                    )
                )
            ).scalar() or 0

            return AuditDashboard(
                total_records=total,
                records_today=today,
                records_this_week=this_week,
                risk_distribution=risk_dist,
                top_users=top_users,
                recent_high_risk=recent_hr,
                timeline=timeline,
                deployment_stats={
                    "total": dep_count,
                    "success": dep_success,
                    "failed": dep_failed,
                },
            )

    # ======================================================================
    # Records list with filters
    # ======================================================================

    async def list_records(
        self,
        page: int = 1,
        page_size: int = 50,
        action: str | None = None,
        user: str | None = None,
        object_type: str | None = None,
        min_risk: int | None = None,
        since: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> AuditTimeline:
        async with session_scope() as session:
            query = select(AuditRecord)
            count_query = select(func.count(AuditRecord.id))

            if action:
                query = query.where(AuditRecord.action == action.upper())
                count_query = count_query.where(AuditRecord.action == action.upper())
            if user:
                query = query.where(AuditRecord.user_name.ilike(f"%{user}%"))
                count_query = count_query.where(AuditRecord.user_name.ilike(f"%{user}%"))
            if object_type:
                query = query.where(AuditRecord.object_type.ilike(f"%{object_type}%"))
                count_query = count_query.where(AuditRecord.object_type.ilike(f"%{object_type}%"))
            if min_risk is not None:
                query = query.where(AuditRecord.risk_score >= min_risk)
                count_query = count_query.where(AuditRecord.risk_score >= min_risk)
            if since:
                try:
                    since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                    query = query.where(AuditRecord.timestamp >= since_dt)
                    count_query = count_query.where(AuditRecord.timestamp >= since_dt)
                except Exception:
                    pass
            if date_from:
                query = query.where(AuditRecord.timestamp >= date_from)
                count_query = count_query.where(AuditRecord.timestamp >= date_from)
            if date_to:
                query = query.where(AuditRecord.timestamp <= date_to)
                count_query = count_query.where(AuditRecord.timestamp <= date_to)

            total = (await session.execute(count_query)).scalar() or 0

            offset = (page - 1) * page_size
            query = query.order_by(AuditRecord.timestamp.desc()).offset(offset).limit(page_size)
            rows = (await session.execute(query)).scalars().all()

            return AuditTimeline(
                records=[self._record_to_dto(r) for r in rows],
                total=total,
                page=page,
                page_size=page_size,
            )

    async def get_record(self, fmc_id: str) -> AuditDiffDto | None:
        async with session_scope() as session:
            row = (
                (await session.execute(select(AuditRecord).where(AuditRecord.fmc_id == fmc_id)))
                .scalars()
                .first()
            )
            if not row:
                return None
            dto = self._record_to_dto(row)
            diffs = self._compute_diffs(row.before_json, row.after_json)
            return AuditDiffDto(
                record=dto, before=row.before_json, after=row.after_json, field_diffs=diffs
            )

    # ======================================================================
    # User stats
    # ======================================================================

    async def get_user_stats(self, user_name: str | None = None) -> list[UserStatsDto]:
        async with session_scope() as session:
            query = select(UserStats).order_by(UserStats.total_changes.desc())
            if user_name:
                query = query.where(UserStats.user_name.ilike(f"%{user_name}%"))
            query = query.limit(50)
            rows = (await session.execute(query)).scalars().all()
            return [self._user_stats_to_dto(u) for u in rows]

    # ======================================================================
    # Relationships graph
    # ======================================================================

    async def get_relationships(self, since_days: int = 30) -> RelationshipGraph:
        async with session_scope() as session:
            since = datetime.now(UTC) - timedelta(days=since_days)
            rows = (
                (
                    await session.execute(
                        select(AuditRecord)
                        .where(AuditRecord.timestamp >= since)
                        .where(AuditRecord.object_type.isnot(None))
                    )
                )
                .scalars()
                .all()
            )

            nodes_map: dict[str, RelationshipNode] = {}
            edges: list[RelationshipEdge] = []

            for r in rows:
                obj_key = f"{r.object_type}:{r.object_name}"
                if obj_key not in nodes_map:
                    nodes_map[obj_key] = RelationshipNode(
                        id=obj_key,
                        type=r.object_type or "Unknown",
                        name=r.object_name or "Unknown",
                        risk=r.risk_score or 0,
                    )
                if r.parent_name:
                    parent_key = f"{r.parent_type}:{r.parent_name}"
                    if parent_key not in nodes_map:
                        nodes_map[parent_key] = RelationshipNode(
                            id=parent_key,
                            type=r.parent_type or "Unknown",
                            name=r.parent_name or "Unknown",
                        )
                    edges.append(
                        RelationshipEdge(
                            source=parent_key,
                            target=obj_key,
                            type=r.action or "MODIFIED",
                        )
                    )

                if r.user_name:
                    user_key = f"user:{r.user_name}"
                    if user_key not in nodes_map:
                        nodes_map[user_key] = RelationshipNode(
                            id=user_key,
                            type="User",
                            name=r.user_name,
                        )
                    edges.append(
                        RelationshipEdge(
                            source=user_key,
                            target=obj_key,
                            type=r.action or "MODIFIED",
                        )
                    )

            # Deduplicate edges
            seen_edges = set()
            unique_edges = []
            for e in edges:
                key = (e.source, e.target, e.type)
                if key not in seen_edges:
                    seen_edges.add(key)
                    unique_edges.append(e)

            return RelationshipGraph(
                nodes=list(nodes_map.values()),
                edges=unique_edges,
            )

    # ======================================================================
    # Deployment history
    # ======================================================================

    async def list_deployments(self, limit: int = 50) -> list[DeploymentDto]:
        async with session_scope() as session:
            rows = (
                (
                    await session.execute(
                        select(DeploymentRecord)
                        .order_by(DeploymentRecord.started_at.desc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            return [self._deployment_to_dto(d) for d in rows]

    # ======================================================================
    # Export
    # ======================================================================

    async def export_records(
        self,
        format: str = "csv",
        since: str | None = None,
        action: str | None = None,
        user: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> str | list[dict]:
        async with session_scope() as session:
            query = select(AuditRecord)
            if since:
                try:
                    since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                    query = query.where(AuditRecord.timestamp >= since_dt)
                except Exception:
                    pass
            if action:
                query = query.where(AuditRecord.action == action.upper())
            if user:
                query = query.where(AuditRecord.user_name.ilike(f"%{user}%"))
            if date_from:
                query = query.where(AuditRecord.timestamp >= date_from)
            if date_to:
                query = query.where(AuditRecord.timestamp <= date_to)
            query = query.order_by(AuditRecord.timestamp.desc()).limit(5000)
            rows = (await session.execute(query)).scalars().all()
            records = [self._record_to_dto(r).model_dump() for r in rows]

            if format == "csv":
                return self._to_csv(records)
            return records

    def _to_csv(self, records: list[dict]) -> str:
        if not records:
            return ""
        headers = [
            "fmc_id",
            "timestamp",
            "user_name",
            "source_ip",
            "action",
            "object_type",
            "object_name",
            "risk_score",
            "changed_fields",
        ]
        lines = [",".join(headers)]
        for r in records:
            row = [str(r.get(h, "")) for h in headers]
            lines.append(",".join(f'"{c}"' for c in row))
        return "\n".join(lines)

    # ======================================================================
    # Risk scoring
    # ======================================================================

    def _compute_risk(self, record: AuditRecordDto) -> tuple[int, list[str]]:
        score = 0
        factors: list[str] = []

        # Action weight
        if record.action == "DELETE":
            score += 40
            factors.append("delete_action")
        elif record.action == "UPDATE":
            score += 15
            factors.append("update_action")
        elif record.action == "ADD":
            score += 5
            factors.append("add_action")

        # Object type weight
        if record.object_type in HIGH_RISK_TYPES:
            score += 25
            factors.append(f"high_risk_object:{record.object_type}")

        # Critical fields changed
        if record.changed_fields:
            overlap = set(record.changed_fields) & CRITICAL_FIELDS
            if overlap:
                score += 20
                factors.append(f"critical_fields:{list(overlap)}")

        # Off-hours
        if record.timestamp:
            hour = record.timestamp.hour
            if hour < 7 or hour > 20:
                score += 10
                factors.append("off_hours")

        # References changed
        if record.refs_added or record.refs_removed:
            score += 10
            factors.append("refs_changed")

        return min(score, 100), factors

    # ======================================================================
    # Diff computation
    # ======================================================================

    def _compute_diffs(self, before: dict | None, after: dict | None) -> list[FieldDiff]:
        if not before and not after:
            return []
        before = before or {}
        after = after or {}
        diffs = []
        all_keys = set(before.keys()) | set(after.keys())
        for key in sorted(all_keys):
            b_val = before.get(key)
            a_val = after.get(key)
            if b_val == a_val:
                continue
            if key not in before:
                change_type = "added"
            elif key not in after:
                change_type = "removed"
            else:
                change_type = "modified"
            diffs.append(FieldDiff(field=key, before=b_val, after=a_val, change_type=change_type))
        return diffs

    # ======================================================================
    # Timeline builder
    # ======================================================================

    def _build_timeline(self, records: list[AuditRecord]) -> list[dict]:
        by_date: dict[str, dict] = {}
        for r in records:
            if not r.timestamp:
                continue
            day = r.timestamp.strftime("%Y-%m-%d")
            if day not in by_date:
                by_date[day] = {
                    "date": day,
                    "total": 0,
                    "adds": 0,
                    "updates": 0,
                    "deletes": 0,
                    "high_risk": 0,
                }
            by_date[day]["total"] += 1
            action = (r.action or "").upper()
            if action == "ADD":
                by_date[day]["adds"] += 1
            elif action == "UPDATE":
                by_date[day]["updates"] += 1
            elif action == "DELETE":
                by_date[day]["deletes"] += 1
            if (r.risk_score or 0) >= 40:
                by_date[day]["high_risk"] += 1
        return [by_date[k] for k in sorted(by_date.keys())]

    # ======================================================================
    # DB operations
    # ======================================================================

    async def _get_last_timestamp(self) -> datetime | None:
        async with session_scope() as session:
            result = await session.execute(select(func.max(AuditRecord.timestamp)))
            return result.scalar()

    async def _upsert_audit_record(self, session: AsyncSession, rec: AuditRecordDto) -> bool:
        stmt = (
            pg_insert(AuditRecord)
            .values(
                fmc_id=rec.fmc_id,
                audit_id=rec.audit_id,
                record_id=rec.record_id,
                snapshot_id=rec.snapshot_id,
                timestamp=rec.timestamp,
                user_name=rec.user_name,
                user_id=rec.user_id,
                source_ip=rec.source_ip,
                source=rec.source,
                subsystem=rec.subsystem,
                message=rec.message,
                description=rec.description,
                action=rec.action,
                object_type=rec.object_type,
                object_name=rec.object_name,
                object_id=rec.object_id,
                parent_type=rec.parent_type,
                parent_name=rec.parent_name,
                parent_id=rec.parent_id,
                before_json=rec.before_json,
                after_json=rec.after_json,
                changed_fields=rec.changed_fields,
                refs_added=rec.refs_added,
                refs_removed=rec.refs_removed,
                values_added=rec.values_added,
                values_deleted=rec.values_deleted,
                values_updated=rec.values_updated,
                config_changes=rec.config_changes,
                raw_json=rec.raw_json,
                normalization_notes=rec.normalization_notes,
                risk_score=rec.risk_score,
                risk_factors=rec.risk_factors,
                deployed=rec.deployed,
                deploy_success=rec.deploy_success,
                deployment_id=rec.deployment_id,
            )
            .on_conflict_do_update(
                index_elements=["fmc_id"],
                set_={
                    "risk_score": rec.risk_score,
                    "risk_factors": rec.risk_factors,
                    "config_changes": rec.config_changes,
                    "raw_json": rec.raw_json,
                    "normalization_notes": rec.normalization_notes,
                },
            )
        )
        result = await session.execute(stmt.returning(literal_column("xmax = 0").label("inserted")))
        return bool(result.scalar_one())

    async def _upsert_deployment(self, session: AsyncSession, dep: DeploymentDto) -> bool:
        stmt = (
            pg_insert(DeploymentRecord)
            .values(
                fmc_id=dep.fmc_id,
                name=dep.name,
                status=dep.status,
                started_at=dep.started_at,
                completed_at=dep.completed_at,
                triggered_by=dep.triggered_by,
                device_count=dep.device_count,
                success_count=dep.success_count,
                failed_count=dep.failed_count,
                devices=dep.devices,
                raw_json=dep.raw_json,
            )
            .on_conflict_do_nothing(index_elements=["fmc_id"])
        )
        result = await session.execute(stmt)
        return result.rowcount > 0

    async def _recompute_user_stats(self, session: AsyncSession) -> None:
        """Recompute user stats for the last 30 days."""
        since = datetime.now(UTC) - timedelta(days=30)
        rows = (
            (await session.execute(select(AuditRecord).where(AuditRecord.timestamp >= since)))
            .scalars()
            .all()
        )

        by_user: dict[str, dict] = {}
        for r in rows:
            name = r.user_name or "unknown"
            if name not in by_user:
                by_user[name] = {
                    "total": 0,
                    "adds": 0,
                    "updates": 0,
                    "deletes": 0,
                    "risk_sum": 0,
                    "max_risk": 0,
                    "objects": set(),
                }
            u = by_user[name]
            u["total"] += 1
            action = (r.action or "").upper()
            if action == "ADD":
                u["adds"] += 1
            elif action == "UPDATE":
                u["updates"] += 1
            elif action == "DELETE":
                u["deletes"] += 1
            u["risk_sum"] += r.risk_score or 0
            u["max_risk"] = max(u["max_risk"], r.risk_score or 0)
            if r.object_name:
                u["objects"].add(r.object_name)

        # UserStats is a derived rolling snapshot, not an append-only fact table.
        period_start = since
        period_end = datetime.now(UTC)
        await session.execute(delete(UserStats))

        for name, u in by_user.items():
            avg_risk = u["risk_sum"] / u["total"] if u["total"] else 0
            stat = UserStats(
                user_name=name,
                period_start=period_start,
                period_end=period_end,
                total_changes=u["total"],
                adds=u["adds"],
                updates=u["updates"],
                deletes=u["deletes"],
                avg_risk_score=round(avg_risk, 1),
                max_risk_score=u["max_risk"],
                objects_touched=sorted(u["objects"])[:100],
            )
            session.add(stat)

    # ======================================================================
    # DTO converters
    # ======================================================================

    @staticmethod
    def _record_to_dto(r: AuditRecord) -> AuditRecordDto:
        return AuditRecordDto(
            id=r.id,
            fmc_id=r.fmc_id,
            audit_id=r.audit_id,
            record_id=r.record_id,
            snapshot_id=r.snapshot_id,
            timestamp=r.timestamp,
            local_timestamp=r.timestamp.astimezone(ZoneInfo("Asia/Baku")) if r.timestamp else None,
            user_name=r.user_name,
            user_id=r.user_id,
            source_ip=r.source_ip,
            source=r.source,
            subsystem=r.subsystem,
            message=r.message,
            description=r.description,
            action=r.action or "UNKNOWN",
            object_type=r.object_type,
            object_name=r.object_name,
            object_id=r.object_id,
            parent_type=r.parent_type,
            parent_name=r.parent_name,
            parent_id=r.parent_id,
            before_json=r.before_json,
            after_json=r.after_json,
            changed_fields=r.changed_fields or [],
            refs_added=r.refs_added or [],
            refs_removed=r.refs_removed or [],
            values_added=r.values_added or [],
            values_deleted=r.values_deleted or [],
            values_updated=r.values_updated or [],
            config_changes=r.config_changes or [],
            raw_json=r.raw_json or {},
            normalization_notes=r.normalization_notes or [],
            risk_score=r.risk_score or 0,
            risk_factors=r.risk_factors or [],
            deployed=r.deployed or False,
            deploy_success=r.deploy_success,
            deployment_id=r.deployment_id,
        )

    @staticmethod
    def _deployment_to_dto(d: DeploymentRecord) -> DeploymentDto:
        return DeploymentDto(
            id=d.id,
            fmc_id=d.fmc_id,
            name=d.name,
            status=d.status or "UNKNOWN",
            started_at=d.started_at,
            completed_at=d.completed_at,
            triggered_by=d.triggered_by,
            device_count=d.device_count or 0,
            success_count=d.success_count or 0,
            failed_count=d.failed_count or 0,
            devices=d.devices or [],
            raw_json=d.raw_json or {},
        )

    @staticmethod
    def _user_stats_to_dto(u: UserStats) -> UserStatsDto:
        return UserStatsDto(
            user_name=u.user_name,
            total_changes=u.total_changes or 0,
            adds=u.adds or 0,
            updates=u.updates or 0,
            deletes=u.deletes or 0,
            avg_risk_score=u.avg_risk_score or 0,
            max_risk_score=u.max_risk_score or 0,
            objects_touched=u.objects_touched or [],
        )
