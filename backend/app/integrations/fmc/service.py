"""FMC monitoring business service backed only by local cached state."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

from app.cache.redis_cache import JsonRedisCache
from app.core.config import Settings, get_settings
from app.integrations.fmc.collector import FmcCollector
from app.integrations.fmc.schemas import FreshnessState, MonitoringDashboard, SourceFreshness
from app.observability.metrics import increment

logger = logging.getLogger(__name__)

CACHE_KEY_FULL = "fmc:dashboard:full"
CACHE_KEY_DISCOVERY = "fmc:discovery:devices"
CACHE_KEY_VPN = "fmc:dashboard:vpn"
CACHE_KEY_FRESHNESS = "fmc:source:freshness"
CACHE_KEY_RESET_STATUS = "fmc:reset:status"
FMC_CACHE_KEYS = (
    CACHE_KEY_FULL,
    CACHE_KEY_DISCOVERY,
    CACHE_KEY_VPN,
    CACHE_KEY_FRESHNESS,
)


class FmcMonitoringService:
    def __init__(
        self,
        settings: Settings | None = None,
        cache: JsonRedisCache | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.cache = cache or JsonRedisCache()
        self.collector = FmcCollector(self.settings)
        self._state_lock = asyncio.Lock()

    @classmethod
    def from_settings(cls) -> FmcMonitoringService:
        return cls(get_settings())

    async def get_dashboard(self) -> MonitoringDashboard:
        """Read local state only; frontend requests never trigger FMC collection."""
        reset_status = await self.get_reset_status()
        if reset_status.get("state") in {"queued", "clearing"}:
            dashboard = self._merge({}, {}, {})
            dashboard.reset_status = reset_status
            return dashboard
        full = await self._cache_get(CACHE_KEY_FULL)
        vpn = await self._cache_get(CACHE_KEY_VPN)
        if not vpn:
            vpn = await self._load_persisted_vpn_snapshot()
            if vpn:
                await self._cache_set(CACHE_KEY_VPN, vpn, ttl_seconds=86400)
        freshness = await self._cache_get(CACHE_KEY_FRESHNESS)
        dashboard = self._merge(full or {}, vpn or {}, freshness or {})
        dashboard.reset_status = reset_status
        return dashboard

    async def _load_persisted_vpn_snapshot(self) -> dict[str, Any]:
        """Restore last-known VPN state when the short-lived cache is unavailable."""
        if not self.settings.database_url:
            return {}
        try:
            from sqlalchemy import select

            from app.db import session_scope
            from app.monitoring.models import VpnTunnelCurrent

            async with session_scope() as session:
                result = await session.execute(
                    select(VpnTunnelCurrent.raw_json, VpnTunnelCurrent.last_seen_at)
                )
                rows = result.all()
            tunnels = [raw for raw, _ in rows if isinstance(raw, dict)]
            if not tunnels:
                return {}
            summaries = self._summarize_vpn_tunnels(tunnels)
            observed_at = max(
                (last_seen_at for _, last_seen_at in rows if last_seen_at),
                default=datetime.now(UTC),
            )
            logger.info("Restored %d VPN tunnels from PostgreSQL", len(tunnels))
            return {
                "tunnel_statuses": tunnels,
                "tunnel_summaries": summaries,
                "tunnel_up": sum(item.get("tunnelUpCount", 0) for item in summaries),
                "tunnel_down": sum(item.get("tunnelDownCount", 0) for item in summaries),
                "tunnel_unknown": sum(
                    item.get("tunnelUnknownCount", 0) for item in summaries
                ),
                "collected_at": observed_at.isoformat(),
            }
        except Exception as exc:
            logger.warning("Persisted VPN snapshot restore failed: %s", exc)
            return {}

    async def get_reset_status(self) -> dict[str, Any]:
        return await self._cache_get(CACHE_KEY_RESET_STATUS) or {"state": "idle"}

    async def set_reset_status(
        self,
        state: str,
        *,
        started_at: str | None = None,
        completed_scopes: list[str] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        previous = await self.get_reset_status()
        status = {
            "state": state,
            "started_at": started_at or previous.get("started_at"),
            "updated_at": datetime.now(UTC).isoformat(),
            "completed_scopes": completed_scopes or [],
            "error": error,
        }
        if state in {"completed", "failed"}:
            status["finished_at"] = datetime.now(UTC).isoformat()
        await self._cache_set(CACHE_KEY_RESET_STATUS, status, ttl_seconds=86400)
        return status

    async def refresh_full_scan(self) -> MonitoringDashboard:
        """Backward-compatible full collector, intended only for manual diagnostics."""
        return await self._refresh_scope("full")

    async def refresh_discovery(self) -> MonitoringDashboard:
        return await self._refresh_scope("discovery")

    async def refresh_device_health(self) -> MonitoringDashboard:
        return await self._refresh_scope("health")

    async def refresh_interfaces(self) -> MonitoringDashboard:
        return await self._refresh_scope("interfaces")

    async def refresh_alerts(self) -> MonitoringDashboard:
        return await self._refresh_scope("alerts")

    async def refresh_ha(self) -> MonitoringDashboard:
        return await self._refresh_scope("ha")

    async def refresh_policy_analysis(self) -> MonitoringDashboard:
        return await self._refresh_scope("policy")

    async def clear_monitoring_data(self) -> dict[str, Any]:
        """Clear FMC monitoring cache and persistence, leaving FMC audit data intact."""
        cache_keys_deleted = 0
        for key in FMC_CACHE_KEYS:
            try:
                cache_keys_deleted += await self.cache.delete(key)
            except Exception as exc:
                logger.warning("FMC cache delete failed for %s: %s", key, exc)
        self.collector.client.clear_diagnostics()
        self.collector.client.clear_capability_cache()

        database_rows_deleted: dict[str, int] = {}
        if self.settings.database_url:
            from app.db import session_scope
            from app.monitoring.repository import MonitoringRepository

            async with session_scope() as session:
                database_rows_deleted = await MonitoringRepository(
                    session
                ).clear_fmc_monitoring_data()

        result = {
            "cache_keys_deleted": cache_keys_deleted,
            "database_rows_deleted": database_rows_deleted,
            "audit_preserved": True,
        }
        logger.warning("FMC monitoring data reset: %s", result)
        return result

    async def _refresh_scope(self, scope: str) -> MonitoringDashboard:
        """Refresh one independent component and merge it into local current state."""
        started = time.monotonic()
        attempted_at = datetime.now(UTC).isoformat()
        source, stale_threshold = self._scope_freshness(scope)
        try:
            summaries = None
            if scope not in {"full", "discovery", "policy"}:
                discovery = await self._cache_get(CACHE_KEY_DISCOVERY)
                summaries = discovery.get("devices") if discovery else None
                if not summaries:
                    raise RuntimeError("FMC discovery cache is empty")
            dashboard = await self.collector.collect(scope=scope, device_summaries=summaries)
            if dashboard.domain_id is None:
                raise RuntimeError("FMC collection did not produce an authenticated domain")
            data = await self._store_scope_state(dashboard, scope)

            persistence_error: Exception | None = None
            if self.settings.database_url:
                try:
                    await self._persist_dashboard(dashboard, scope=scope)
                except Exception as exc:
                    persistence_error = exc
                    increment("database_write_errors_total")
                    logger.exception("FMC %s persistence failed: %s", scope, exc)
            partial = (
                persistence_error is not None
                or bool(dashboard.collection_errors)
                or any(device.collection_errors for device in dashboard.devices)
                or any(pair.collection_errors for pair in dashboard.ha_pairs)
            )
            records_received = len(dashboard.ha_pairs) if scope == "ha" else dashboard.total_devices
            if scope == "policy":
                records_received = int(dashboard.policy_analysis.get("total_policies", 0))
            freshness_record = SourceFreshness(
                source=source,
                state=FreshnessState.DEGRADED if partial else FreshnessState.FRESH,
                last_attempt=attempted_at,
                last_success=datetime.now(UTC).isoformat(),
                collection_duration_seconds=round(time.monotonic() - started, 3),
                records_received=records_received,
                partial_result=partial,
                error=(
                    f"database persistence: {type(persistence_error).__name__}: {persistence_error}"
                    if persistence_error
                    else None
                ),
                stale_threshold_seconds=stale_threshold,
            ).model_dump(mode="json")
            freshness = await self._store_freshness_record(source, freshness_record)
            await self._persist_freshness(freshness_record)
            logger.info("FMC %s scope cached: %d records", scope, records_received)
            increment("collector_success_total")
            increment("records_collected_total", records_received)
            increment("collector_duration_seconds_sum", time.monotonic() - started)
            increment("collector_duration_seconds_count")
            vpn = await self._cache_get(CACHE_KEY_VPN)
            return self._merge(data, vpn or {}, freshness)
        except Exception as exc:
            increment("collector_failure_total")
            logger.exception("FMC %s scope failed: %s", scope, exc)
            freshness = await self._record_failure(
                source=source,
                attempted_at=attempted_at,
                started=started,
                stale_threshold_seconds=stale_threshold,
                error=exc,
            )
            cached = await self._cache_get(CACHE_KEY_FULL)
            vpn = await self._cache_get(CACHE_KEY_VPN)
            return self._merge(cached or {}, vpn or {}, freshness)

    def _scope_freshness(self, scope: str) -> tuple[str, int]:
        return {
            "full": ("fmc_full", 3600),
            "discovery": (
                "fmc_discovery",
                max(1800, self.settings.fmc_discovery_refresh_minutes * 120),
            ),
            "health": ("fmc_device_health", self.settings.fmc_device_health_stale_seconds),
            "interfaces": (
                "fmc_interfaces",
                max(3600, self.settings.fmc_interface_refresh_minutes * 120),
            ),
            "alerts": (
                "fmc_alerts",
                max(180, self.settings.fmc_alert_refresh_seconds * 2),
            ),
            "ha": ("fmc_ha", max(180, self.settings.fmc_ha_refresh_seconds * 2)),
            "policy": (
                "fmc_policy_analysis",
                max(3600, self.settings.fmc_policy_analysis_refresh_hours * 7200),
            ),
        }[scope]

    async def _store_scope_state(
        self, dashboard: MonitoringDashboard, scope: str
    ) -> dict[str, Any]:
        component_data = dashboard.model_dump(mode="json")
        async with self._state_lock:
            cached = await self._cache_get(CACHE_KEY_FULL) or {}
            data = self._merge_scope(cached, component_data, scope)
            if scope in {"full", "discovery"}:
                discovered = [
                    device.device.raw
                    for device in dashboard.devices
                    if device.device.id and device.device.raw
                ]
                await self._cache_set(
                    CACHE_KEY_DISCOVERY,
                    {"devices": discovered, "collected_at": dashboard.collected_at},
                    ttl_seconds=86400,
                )
            await self._cache_set(CACHE_KEY_FULL, data, ttl_seconds=86400)
        return data

    async def _store_freshness_record(self, source: str, record: dict[str, Any]) -> dict[str, Any]:
        async with self._state_lock:
            freshness = await self._cache_get(CACHE_KEY_FRESHNESS) or {}
            freshness[source] = record
            await self._cache_set(CACHE_KEY_FRESHNESS, freshness, ttl_seconds=86400 * 30)
        return freshness

    async def refresh_vpn_status(self) -> MonitoringDashboard:
        """Run the independent VPN snapshot collector."""
        from app.integrations.fmc.client import FmcClient

        started = time.monotonic()
        attempted_at = datetime.now(UTC).isoformat()
        client = FmcClient(self.settings)
        try:
            if not client.configured:
                raise RuntimeError("FMC is not configured")
            await client.authenticate()
            errors: list[str] = []
            tunnels: list[dict[str, Any]] = []
            summaries: list[dict[str, Any]] = []
            try:
                tunnels = (await client.get_tunnel_statuses()).get("items", [])
            except Exception as exc:
                errors.append(f"tunnelstatuses: {type(exc).__name__}: {exc}")
                try:
                    tunnels = await client.get_vpn_tunnel_statuses()
                except Exception as fallback_exc:
                    errors.append(
                        "policy/vpntunnelstatuses: "
                        f"{type(fallback_exc).__name__}: {fallback_exc}"
                    )
            try:
                summaries = (await client.get_tunnel_summaries()).get("items", [])
            except Exception as exc:
                errors.append(f"tunnelsummaries: {type(exc).__name__}: {exc}")
            if tunnels and not summaries:
                summaries = self._summarize_vpn_tunnels(tunnels)
            if not tunnels and not summaries and any(
                error.startswith("policy/vpntunnelstatuses:") for error in errors
            ):
                raise RuntimeError("; ".join(errors))

            vpn_data = {
                "tunnel_statuses": tunnels,
                "tunnel_summaries": summaries,
                "tunnel_up": sum(item.get("tunnelUpCount", 0) for item in summaries),
                "tunnel_down": sum(item.get("tunnelDownCount", 0) for item in summaries),
                "tunnel_unknown": sum(
                    item.get("tunnelUnknownCount", 0) for item in summaries
                ),
                "collected_at": datetime.now(UTC).isoformat(),
            }
            if self.settings.database_url:
                await self._persist_vpn_snapshot(
                    domain_id=client.domain_uuid,
                    tunnels=tunnels,
                    observed_at=datetime.now(UTC),
                    raw_responses=client.raw_responses,
                    partial_error="; ".join(errors) or None,
                )
            # Keep the last known-good snapshot available when a later scheduled
            # run is delayed by another rate-limited FMC collector. Freshness is
            # tracked separately and still tells the UI when this data is stale.
            await self._cache_set(CACHE_KEY_VPN, vpn_data, ttl_seconds=86400)
            freshness_record = SourceFreshness(
                source="fmc_vpn",
                state=FreshnessState.DEGRADED if errors else FreshnessState.FRESH,
                last_attempt=attempted_at,
                last_success=datetime.now(UTC).isoformat(),
                collection_duration_seconds=round(time.monotonic() - started, 3),
                records_received=len(tunnels),
                partial_result=bool(errors),
                error="; ".join(errors) or None,
                stale_threshold_seconds=self._vpn_stale_seconds,
            ).model_dump(mode="json")
            freshness = await self._store_freshness_record("fmc_vpn", freshness_record)
            await self._persist_freshness(freshness_record)
            full = await self._cache_get(CACHE_KEY_FULL)
            return self._merge(full or {}, vpn_data, freshness)
        except Exception as exc:
            logger.exception("FMC VPN refresh failed: %s", exc)
            await self._record_failure(
                source="fmc_vpn",
                attempted_at=attempted_at,
                started=started,
                stale_threshold_seconds=self._vpn_stale_seconds,
                error=exc,
            )
            return await self.get_dashboard()
        finally:
            await client.close()

    @staticmethod
    def _summarize_vpn_tunnels(tunnels: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[str, dict[str, Any]] = {}
        for tunnel in tunnels:
            topology = tunnel.get("vpnTopology") or {}
            group_id = str(topology.get("id") or topology.get("name") or "all")
            summary = groups.setdefault(
                group_id,
                {
                    "group": {
                        "id": topology.get("id"),
                        "name": topology.get("name") or "All Tunnels",
                        "type": topology.get("type") or "FTDS2SVPNTopology",
                    },
                    "tunnelCount": 0,
                    "tunnelUpCount": 0,
                    "tunnelDownCount": 0,
                    "tunnelUnknownCount": 0,
                    "type": "TunnelSummary",
                },
            )
            summary["tunnelCount"] += 1
            state = str(tunnel.get("state") or "UNKNOWN").upper()
            if state == "TUNNEL_UP":
                summary["tunnelUpCount"] += 1
            elif state == "TUNNEL_DOWN":
                summary["tunnelDownCount"] += 1
            else:
                summary["tunnelUnknownCount"] += 1
        return list(groups.values())

    @property
    def _vpn_stale_seconds(self) -> int:
        return max(60, self.settings.fmc_vpn_refresh_minutes * 120)

    def _merge_scope(self, current: dict, component: dict, scope: str) -> dict:
        """Merge only fields owned by a collector so partial scopes cannot erase state."""
        if scope == "full" or not current:
            return component
        merged = {**current}
        merged["collection_run_id"] = component.get("collection_run_id")
        merged["collected_at"] = component.get("collected_at")
        merged["domain_id"] = component.get("domain_id") or current.get("domain_id")
        existing = {
            str(item.get("device", {}).get("id")): item
            for item in current.get("devices", [])
            if item.get("device", {}).get("id")
        }
        for incoming in component.get("devices", []):
            device_id = str(incoming.get("device", {}).get("id") or "")
            if not device_id:
                continue
            previous = existing.get(device_id, {})
            result = {**previous, "device": incoming.get("device", previous.get("device", {}))}
            if scope == "discovery":
                result["raw_references"] = incoming.get("raw_references", [])
            elif scope in {"health", "interfaces"}:
                result.update(
                    {
                        "load": incoming.get("load", {}),
                        "aggregate_status": incoming.get("aggregate_status", "NO_DATA"),
                        "diagnostics": incoming.get("diagnostics", []),
                        "collection_errors": incoming.get("collection_errors", []),
                    }
                )
                result["capabilities"] = {
                    **previous.get("capabilities", {}),
                    **incoming.get("capabilities", {}),
                }
                if scope == "interfaces":
                    result["interfaces"] = incoming.get("interfaces", [])
            elif scope == "alerts":
                result["alerts"] = incoming.get("alerts", [])
                result["capabilities"] = {
                    **previous.get("capabilities", {}),
                    **incoming.get("capabilities", {}),
                }
                result["collection_errors"] = incoming.get("collection_errors", [])
            existing[device_id] = result

        merged["devices"] = list(existing.values())
        if scope == "ha":
            merged["ha_pairs"] = component.get("ha_pairs", [])
            member_pairs = {
                member.get("device_id"): pair
                for pair in merged["ha_pairs"]
                for member in (pair.get("primary", {}), pair.get("secondary", {}))
                if member.get("device_id")
            }
            for device in merged["devices"]:
                pair = member_pairs.get(device.get("device", {}).get("id"))
                if pair:
                    device["ha"] = pair
        elif scope == "policy":
            merged["policy_analysis"] = component.get("policy_analysis", {})

        devices = merged["devices"]
        alerts = [alert for device in devices for alert in device.get("alerts", [])]
        merged["total_devices"] = len(devices)
        merged["devices_connected"] = sum(
            1 for device in devices if device.get("device", {}).get("is_connected") is True
        )
        merged["alerts_total"] = len(alerts)
        merged["alerts_red"] = sum(
            1 for alert in alerts if str(alert.get("status") or "").upper() == "RED"
        )
        merged["alerts_yellow"] = sum(
            1 for alert in alerts if str(alert.get("status") or "").upper() == "YELLOW"
        )
        return merged

    def _merge(self, full: dict, vpn: dict, freshness: dict) -> MonitoringDashboard:
        result = {**full}
        if vpn:
            result["collected_at"] = vpn.get("collected_at") or result.get("collected_at")
            result["tunnel_statuses"] = vpn.get(
                "tunnel_statuses", result.get("tunnel_statuses", [])
            )
            result["tunnel_summaries"] = vpn.get(
                "tunnel_summaries", result.get("tunnel_summaries", [])
            )
            result["tunnel_up"] = vpn.get("tunnel_up", result.get("tunnel_up", 0))
            result["tunnel_down"] = vpn.get("tunnel_down", result.get("tunnel_down", 0))
            result["tunnel_unknown"] = vpn.get(
                "tunnel_unknown", result.get("tunnel_unknown", 0)
            )
        result["source_freshness"] = self._freshness_records(freshness)
        return MonitoringDashboard.model_validate(result)

    def _freshness_records(self, raw: dict) -> list[dict[str, Any]]:
        defaults = {
            "fmc_discovery": max(
                1800, self.settings.fmc_discovery_refresh_minutes * 120
            ),
            "fmc_device_health": self.settings.fmc_device_health_stale_seconds,
            "fmc_interfaces": max(
                3600, self.settings.fmc_interface_refresh_minutes * 120
            ),
            "fmc_alerts": max(180, self.settings.fmc_alert_refresh_seconds * 2),
            "fmc_ha": max(180, self.settings.fmc_ha_refresh_seconds * 2),
            "fmc_policy_analysis": max(
                3600, self.settings.fmc_policy_analysis_refresh_hours * 7200
            ),
            "fmc_vpn": self._vpn_stale_seconds,
        }
        records: list[dict[str, Any]] = []
        now = datetime.now(UTC)
        for source, threshold in defaults.items():
            cached = raw.get(source, {}) if isinstance(raw.get(source), dict) else {}
            item = {
                "source": source,
                "state": FreshnessState.NEVER_COLLECTED.value,
                **cached,
                "stale_threshold_seconds": threshold,
            }
            last_success = item.get("last_success")
            if last_success and item.get("state") in {
                FreshnessState.FRESH.value,
                FreshnessState.DEGRADED.value,
            }:
                try:
                    age = (now - datetime.fromisoformat(last_success)).total_seconds()
                    if age > item["stale_threshold_seconds"]:
                        item["state"] = FreshnessState.STALE.value
                except (TypeError, ValueError):
                    item["state"] = FreshnessState.ERROR.value
                    item["error"] = "invalid last_success timestamp"
            records.append(item)
        return records

    async def _record_failure(
        self,
        *,
        source: str,
        attempted_at: str,
        started: float,
        stale_threshold_seconds: int,
        error: Exception,
    ) -> dict[str, Any]:
        cached = await self._cache_get(CACHE_KEY_FRESHNESS) or {}
        previous = cached.get(source, {}) if isinstance(cached.get(source), dict) else {}
        record = {
            **previous,
            "source": source,
            "state": FreshnessState.ERROR.value,
            "last_attempt": attempted_at,
            "collection_duration_seconds": round(time.monotonic() - started, 3),
            "error": f"{type(error).__name__}: {error}",
            "stale_threshold_seconds": stale_threshold_seconds,
        }
        freshness = await self._store_freshness_record(source, record)
        await self._persist_freshness(record)
        return freshness

    async def _persist_dashboard(self, dashboard: MonitoringDashboard, *, scope: str) -> None:
        from app.db import session_scope
        from app.monitoring.repository import MonitoringRepository

        async with session_scope() as session:
            await MonitoringRepository(session).persist_fmc_dashboard(
                dashboard,
                self.collector.client.raw_responses,
                raw_retention_days=self.settings.fmc_raw_response_retention_days,
                alert_flap_reopen_threshold=self.settings.fmc_alert_flap_reopen_threshold,
                collector_name=f"fmc_{scope}",
                persist_metrics=scope in {"full", "health", "interfaces"},
                persist_alerts=scope in {"full", "alerts"},
                persist_ha=scope in {"full", "ha"},
            )

    async def _persist_vpn_snapshot(
        self,
        *,
        domain_id: str,
        tunnels: list[dict[str, Any]],
        observed_at: datetime,
        raw_responses: list[dict[str, Any]],
        partial_error: str | None,
    ) -> None:
        from app.db import session_scope
        from app.monitoring.repository import MonitoringRepository

        async with session_scope() as session:
            await MonitoringRepository(session).persist_vpn_snapshot(
                domain_id=domain_id,
                tunnels=tunnels,
                observed_at=observed_at,
                raw_responses=raw_responses,
                raw_retention_days=self.settings.fmc_raw_response_retention_days,
                flap_threshold=self.settings.fmc_vpn_flap_transition_threshold,
                flap_window_seconds=self.settings.fmc_vpn_flap_window_seconds,
                partial_error=partial_error,
            )

    async def _persist_freshness(self, freshness: dict[str, Any]) -> None:
        if not self.settings.database_url:
            return
        from app.db import session_scope
        from app.monitoring.repository import MonitoringRepository

        try:
            async with session_scope() as session:
                await MonitoringRepository(session).upsert_source_freshness(freshness)
        except Exception as exc:
            logger.warning("Source freshness persistence failed: %s", exc)

    async def _cache_get(self, key: str) -> dict[str, Any] | None:
        try:
            cached = await self.cache.get_json(key)
            return cached if isinstance(cached, dict) else None
        except Exception as exc:
            logger.warning("FMC cache read failed for %s: %s", key, exc)
            return None

    async def _cache_set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        try:
            await self.cache.set_json(key, value, ttl_seconds)
        except Exception as exc:
            logger.warning("FMC cache write failed for %s: %s", key, exc)
