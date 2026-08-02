"""FMC Monitoring Collector — follows the technical specification.

One auth per cycle. Capability detection. Pagination. Raw storage.
Read-only. No POST/PUT/PATCH/DELETE.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings, get_settings
from app.integrations.fmc.analytics import summarize_access_policies, summarize_health_series
from app.integrations.fmc.client import AGGREGATE_METRIC_CATEGORIES, FmcClient
from app.integrations.fmc.errors import FmcErrorCategory, FmcRequestError
from app.integrations.fmc.normalizer import (
    normalize_aggregate,
    normalize_operational,
    select_device_metric,
)
from app.integrations.fmc.schemas import (
    ChassisData,
    ChassisFault,
    CollectedDevice,
    DeviceIdentity,
    HaIpv4Configuration,
    HaIpv6AddressPair,
    HaIpv6Configuration,
    HaMember,
    HaMonitoredInterface,
    HaPair,
    HealthAlert,
    InterfaceRuntime,
    MetricStatus,
    MonitoringDashboard,
    NormalizedInterface,
)

logger = logging.getLogger(__name__)


class FmcCollector:
    """Read-only FMC data collector. One auth → discover → collect → normalize."""

    def __init__(self, settings: Settings | None = None, max_concurrent: int = 3) -> None:
        self.settings = settings or get_settings()
        self.client = FmcClient(self.settings)
        self.max_concurrent = max_concurrent

    @classmethod
    def from_settings(cls) -> FmcCollector:
        return cls(get_settings())

    async def collect(
        self,
        scope: str = "full",
        device_summaries: list[dict[str, Any]] | None = None,
    ) -> MonitoringDashboard:
        """Collect one bounded FMC scope; ``full`` remains backward compatible."""
        valid_scopes = {"full", "discovery", "health", "interfaces", "alerts", "ha", "policy"}
        if scope not in valid_scopes:
            raise ValueError(f"unsupported FMC collection scope: {scope}")
        if not self.client.configured:
            return MonitoringDashboard()
        self.client.clear_diagnostics()

        try:
            await self.client.authenticate()
        except Exception as exc:
            logger.exception("FMC auth failed: %s", exc)
            return MonitoringDashboard()

        collection_run_id = str(uuid.uuid4())
        domain_id = self.client.domain_uuid
        collected_at = datetime.now(UTC).isoformat()
        dashboard_errors: list[str] = []

        if scope == "policy":
            analysis = await self._collect_policy_analysis()
            return MonitoringDashboard(
                collection_run_id=collection_run_id,
                collected_at=collected_at,
                domain_id=domain_id,
                policy_analysis=analysis,
            )

        if device_summaries is None:
            try:
                devices_raw = self._deduplicate_devices(await self.client.get_devices())
            except Exception as exc:
                logger.exception("FMC device discovery failed: %s", exc)
                return MonitoringDashboard(collected_at=collected_at, domain_id=domain_id)
        else:
            devices_raw = self._deduplicate_devices(device_summaries)

        ha_pairs_raw: list[dict[str, Any]] = []
        if scope in {"full", "ha"}:
            try:
                ha_pairs_raw = await self.client.get_ha_pairs()
            except Exception as exc:
                if scope == "ha":
                    raise
                dashboard_errors.append(f"ha: {type(exc).__name__}: {exc}")
                logger.warning("FMC HA discovery failed: %s", exc)

        chassis_raw: list[dict[str, Any]] = []
        if scope == "full":
            try:
                chassis_raw = await self.client.get_chassis_list()
            except Exception as exc:
                logger.warning("FMC chassis discovery failed: %s", exc)

        ha_map = self._build_ha_map(ha_pairs_raw)
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def collect_one(raw_device: dict) -> CollectedDevice | None:
            device_id = raw_device.get("id")
            if not device_id:
                return None
            async with semaphore:
                try:
                    collected = await self._collect_device(
                        device_id,
                        raw_device,
                        domain_id,
                        collected_at,
                        collection_run_id,
                        collect_detail=scope in {"full", "discovery"},
                        collect_health=scope in {"full", "health", "interfaces"},
                        collect_history=scope in {"full", "health"},
                        collect_interfaces=scope in {"full", "interfaces"},
                        collect_alerts=scope in {"full", "alerts"},
                    )
                except Exception as exc:
                    logger.exception(
                        "FMC device collection failed",
                        extra={
                            "collection_run_id": collection_run_id,
                            "device_id": device_id,
                            "component": f"fmc_{scope}",
                        },
                    )
                    collected = CollectedDevice(
                        collection_run_id=collection_run_id,
                        collected_at=collected_at,
                        domain_id=domain_id,
                        device=self._parse_device(raw_device),
                        aggregate_status=MetricStatus.TEMPORARY_ERROR,
                        collection_errors=[f"deviceCollection: {type(exc).__name__}: {exc}"],
                    )
            if device_id in ha_map:
                collected.ha = ha_map[device_id]
            return collected

        device_scopes = {"full", "discovery", "health", "interfaces", "alerts"}
        tasks = [collect_one(raw) for raw in devices_raw] if scope in device_scopes else []
        results = await asyncio.gather(*tasks, return_exceptions=True)
        collected_devices = [result for result in results if isinstance(result, CollectedDevice)]
        for result in results:
            if isinstance(result, Exception):
                logger.error("Unhandled FMC %s task error: %s", scope, result)

        ha_pairs = await self._collect_ha_pairs(ha_pairs_raw) if ha_pairs_raw else []
        detailed_ha_map = {
            member_id: pair
            for pair in ha_pairs
            for member_id in (pair.primary.device_id, pair.secondary.device_id)
            if member_id
        }
        for collected_device in collected_devices:
            if collected_device.device.id in detailed_ha_map:
                collected_device.ha = detailed_ha_map[collected_device.device.id]

        chassis_list = await self._collect_chassis(chassis_raw) if chassis_raw else []
        tunnels: list[dict[str, Any]] = []
        tunnel_sums: list[dict[str, Any]] = []
        if scope == "full":
            try:
                tunnels = (await self.client.get_tunnel_statuses()).get("items", [])
                tunnel_sums = (await self.client.get_tunnel_summaries()).get("items", [])
            except Exception as exc:
                dashboard_errors.append(f"vpn: {type(exc).__name__}: {exc}")
                logger.warning("FMC VPN collection in full scan failed: %s", exc)

        all_alerts = [alert for device in collected_devices for alert in device.alerts]
        return MonitoringDashboard(
            collection_run_id=collection_run_id,
            collected_at=collected_at,
            domain_id=domain_id,
            devices=collected_devices,
            ha_pairs=ha_pairs,
            chassis=chassis_list,
            tunnel_statuses=tunnels,
            tunnel_summaries=tunnel_sums,
            total_devices=len(collected_devices) if collected_devices else len(devices_raw),
            devices_connected=sum(1 for device in collected_devices if device.device.is_connected),
            tunnel_up=sum(summary.get("tunnelUpCount", 0) for summary in tunnel_sums),
            tunnel_down=sum(summary.get("tunnelDownCount", 0) for summary in tunnel_sums),
            alerts_total=len(all_alerts),
            alerts_red=sum(1 for alert in all_alerts if (alert.status or "").upper() == "RED"),
            alerts_yellow=sum(
                1 for alert in all_alerts if (alert.status or "").upper() == "YELLOW"
            ),
            collection_errors=dashboard_errors,
        )

    # ======================================================================
    # Per-device collection
    # ======================================================================

    async def _collect_device(
        self,
        device_id: str,
        raw_summary: dict,
        domain_id: str,
        collected_at: str,
        collection_run_id: str | None = None,
        *,
        collect_detail: bool = True,
        collect_health: bool = True,
        collect_history: bool = True,
        collect_interfaces: bool = True,
        collect_alerts: bool = True,
    ) -> CollectedDevice:
        capabilities: dict[str, str] = {}
        errors: list[str] = []

        # Tier 1: Device detail
        raw_detail = {}
        if collect_detail:
            try:
                raw_detail = await self.client.get_device(device_id)
                if raw_detail.get("id") != device_id:
                    raise FmcRequestError(
                        FmcErrorCategory.STALE_DEVICE,
                        f"Device detail UUID mismatch: requested={device_id}, "
                        f"response={raw_detail.get('id')}",
                        path="deviceRecord",
                    )
                capabilities["deviceRecord"] = "SUPPORTED"
            except Exception as exc:
                capabilities["deviceRecord"] = _classify_error(exc)
                errors.append(f"deviceRecord: {exc}")

        device = self._parse_device(raw_detail or raw_summary)

        load: dict[str, Any] = {"status": MetricStatus.NO_DATA.value}
        aggregate_status = MetricStatus.NO_DATA
        if collect_health:
            load, aggregate_status = await self._collect_aggregate_metrics(
                device_id,
                device,
                capabilities,
                errors,
            )

        # Tier 1: Alerts
        alerts: list[HealthAlert] = []
        if collect_alerts:
            try:
                alert_response = await self.client.get_alerts(device_id)
                for item in alert_response.get("items", []):
                    alerts.append(
                        HealthAlert(
                            id=item.get("id"),
                            name=item.get("name"),
                            device_uuid=item.get("deviceUUID"),
                            status=item.get("status"),
                            module_id=item.get("moduleID"),
                            details=item.get("details"),
                            timestamp=item.get("timestamp"),
                            raw=item,
                        )
                    )
                capabilities["healthAlerts"] = "SUPPORTED" if alerts else "AVAILABLE_NO_DATA"
            except Exception as exc:
                capabilities["healthAlerts"] = _classify_error(exc)
                errors.append(f"healthAlerts: {exc}")

        # Tier 1: All interfaces
        interfaces: list[NormalizedInterface] = []
        if collect_interfaces:
            try:
                interface_response = await self.client.get_all_interfaces(device_id)
                for item in interface_response.get("items", []):
                    parsed = self._parse_interface_config(item)
                    parsed.collected_at = collected_at
                    interfaces.append(parsed)
                capabilities["allInterfaces"] = "SUPPORTED" if interfaces else "AVAILABLE_NO_DATA"
            except Exception as exc:
                capabilities["allInterfaces"] = _classify_error(exc)
                errors.append(f"allInterfaces: {exc}")

        # Merge interface runtime from aggregate metrics
        if load.get("interfaces"):
            self._merge_interface_runtime(interfaces, load["interfaces"])

        # Tier 5: Chassis (if device has one)
        # Not per-device — collected separately

        # Load load into normalized format
        load["metricWindow"] = load.get("metricWindow", "5m")
        load["source"] = load.get("source", "health_aggregatemetrics")

        return CollectedDevice(
            collection_run_id=collection_run_id,
            collected_at=collected_at,
            domain_id=domain_id,
            device=device,
            load=load,
            interfaces=interfaces,
            alerts=alerts,
            capabilities=capabilities,
            aggregate_status=aggregate_status,
            diagnostics=[
                item for item in self.client.raw_responses if device_id in item.get("path", "")
            ][-20:],
            collection_errors=errors,
            raw_references=[
                {"source": "devices", "data": raw_summary},
                {"source": "deviceDetail", "data": raw_detail},
            ],
        )

    async def _collect_aggregate_metrics(
        self,
        device_id: str,
        device: DeviceIdentity,
        capabilities: dict[str, str],
        errors: list[str],
    ) -> tuple[dict[str, Any], MetricStatus]:
        if device.is_connected is False:
            capabilities["aggregateAll"] = MetricStatus.DEVICE_DISCONNECTED.value
            return {
                "status": MetricStatus.DEVICE_DISCONNECTED.value
            }, MetricStatus.DEVICE_DISCONNECTED

        try:
            response = await self.client.get_aggregate_metrics(
                device_id,
                AGGREGATE_METRIC_CATEGORIES,
            )
            item = select_device_metric(response, device_id)
            if item is None:
                capabilities["aggregateAll"] = MetricStatus.AVAILABLE_NO_DATA.value
                return {
                    "status": MetricStatus.AVAILABLE_NO_DATA.value
                }, MetricStatus.AVAILABLE_NO_DATA
            load, block_capabilities = normalize_aggregate(item)
            capabilities.update(block_capabilities)
            capabilities["aggregateAll"] = "SUPPORTED"
            load["status"] = MetricStatus.VALUE.value
            return load, MetricStatus.VALUE
        except FmcRequestError as exc:
            status = _metric_status_for_error(exc)
            capabilities["aggregateAll"] = status.value
            errors.append(f"aggregateAll: {exc.category.value}: {exc}")
            return {"status": status.value}, status
        except Exception as exc:
            capabilities["aggregateAll"] = MetricStatus.TEMPORARY_ERROR.value
            errors.append(f"aggregateAll: {type(exc).__name__}: {exc}")
        return {"status": MetricStatus.TEMPORARY_ERROR.value}, MetricStatus.TEMPORARY_ERROR

    async def _apply_operational_fallback(
        self,
        device_id: str,
        metric: str,
        load_key: str,
        capability_key: str,
        load: dict[str, Any],
        capabilities: dict[str, str],
        errors: list[str],
    ) -> None:
        block = load.get(load_key)
        if isinstance(block, dict) and any(
            block.get(name) is not None for name in ("linaPercent", "snortPercent", "systemPercent")
        ):
            return
        try:
            response = await self.client.get_operational_metrics(device_id, metric)
            normalized = normalize_operational(response.get("items"), "operational_metrics")
            if normalized is None:
                capabilities[capability_key] = MetricStatus.AVAILABLE_NO_DATA.value
                return
            load[load_key] = normalized
            capabilities[capability_key] = "SUPPORTED"
            if load.get("status") != MetricStatus.VALUE.value:
                load["status"] = MetricStatus.PARTIAL.value
        except FmcRequestError as exc:
            capabilities[capability_key] = _metric_status_for_error(exc).value
            errors.append(f"{capability_key}: {exc.category.value}: {exc}")
        except Exception as exc:
            capabilities[capability_key] = MetricStatus.TEMPORARY_ERROR.value
            errors.append(f"{capability_key}: {type(exc).__name__}: {exc}")

    async def _apply_snort_history(
        self,
        device_id: str,
        load: dict[str, Any],
        capabilities: dict[str, str],
        errors: list[str],
    ) -> None:
        cache_key = "health_metrics_snort"
        cached = self.client.capability_status(device_id, cache_key)
        if cached:
            capabilities["historicalSnortCpu"] = cached
            return
        cpu = load.get("cpu") if isinstance(load.get("cpu"), dict) else {}
        if cpu.get("snortPercent") is not None:
            capabilities["historicalSnortCpu"] = "NOT_NEEDED"
            return
        end = int(datetime.now(UTC).timestamp())
        start = end - max(300, self.settings.fmc_health_history_lookback_seconds)
        try:
            response = await self.client.get_health_metrics(
                device_id,
                "cpu",
                start,
                end,
                regex_filter="snort_avg",
                step=self.settings.fmc_health_history_step_seconds,
            )
            summary = summarize_health_series(response, expected_device_id=device_id)
            if summary is None:
                capabilities["historicalSnortCpu"] = MetricStatus.AVAILABLE_NO_DATA.value
                return
            cpu = load.setdefault("cpu", {})
            cpu["snortPercent"] = summary["average"]
            cpu.setdefault("metricStatuses", {})["snortPercent"] = MetricStatus.VALUE.value
            load["snortHistory"] = summary
            capabilities["historicalSnortCpu"] = "SUPPORTED"
            if load.get("status") != MetricStatus.VALUE.value:
                load["status"] = MetricStatus.PARTIAL.value
        except FmcRequestError as exc:
            status = _metric_status_for_error(exc).value
            capabilities["historicalSnortCpu"] = status
            if exc.category in {
                FmcErrorCategory.PERMISSION_ERROR,
                FmcErrorCategory.UNSUPPORTED_ENDPOINT,
                FmcErrorCategory.INVALID_REQUEST,
            }:
                self.client.cache_capability_status(device_id, cache_key, status, 3600)
            errors.append(f"historicalSnortCpu: {exc.category.value}: {exc}")
        except Exception as exc:
            capabilities["historicalSnortCpu"] = MetricStatus.TEMPORARY_ERROR.value
            errors.append(f"historicalSnortCpu: {type(exc).__name__}: {exc}")

    async def _collect_policy_analysis(self) -> dict[str, Any]:
        policies = await self.client.get_access_policies()
        rules_by_policy: dict[str, list[dict[str, Any]]] = {}
        for policy in policies:
            policy_id = policy.get("id")
            if policy_id:
                rules_by_policy[str(policy_id)] = await self.client.get_access_rules(str(policy_id))
        return summarize_access_policies(policies, rules_by_policy)

    # ======================================================================
    # HA pairs
    # ======================================================================

    def _build_ha_map(self, ha_pairs_raw: list[dict]) -> dict[str, HaPair]:
        """Map device_id → HaPair for quick lookup."""
        result: dict[str, HaPair] = {}
        for pair in ha_pairs_raw:
            hp = self._parse_ha_pair(pair)
            primary_id = (hp.primary.device_id) if hp.primary else None
            secondary_id = (hp.secondary.device_id) if hp.secondary else None
            if primary_id:
                result[primary_id] = hp
            if secondary_id:
                result[secondary_id] = hp
        return result

    async def _collect_ha_pairs(self, pairs_raw: list[dict]) -> list[HaPair]:
        async def _collect_one(raw: dict) -> HaPair | None:
            pair_id = raw.get("id")
            if not pair_id:
                return None
            detail_error: str | None = None
            try:
                detail = await self.client.get_ha_pair(pair_id)
            except Exception as exc:
                logger.warning("FMC HA pair detail failed for %s: %s", pair_id, exc)
                detail_error = f"detail: {type(exc).__name__}: {exc}"
                detail = raw
            hp = self._parse_ha_pair(detail)
            if detail_error:
                hp.collection_errors.append(detail_error)
            try:
                summaries = await self.client.get_ha_monitored_interfaces(pair_id)
                for summary in summaries:
                    object_id = summary.get("id")
                    if not object_id:
                        continue
                    cache_key = f"monitoredinterfaces/{object_id}"
                    cached = self.client.capability_status(pair_id, cache_key)
                    if cached:
                        parsed = self._parse_ha_monitored_interface(summary)
                        parsed.collection_errors.append(f"detail: cached {cached}")
                        hp.monitored_interfaces.append(parsed)
                        hp.collection_errors.append(
                            f"monitoredInterfaceDetail[{object_id}]: cached {cached}"
                        )
                        continue
                    try:
                        detail = await self.client.get_ha_monitored_interface(pair_id, object_id)
                        hp.monitored_interfaces.append(self._parse_ha_monitored_interface(detail))
                    except Exception as exc:
                        status = (
                            exc.category.value
                            if isinstance(exc, FmcRequestError)
                            else MetricStatus.TEMPORARY_ERROR.value
                        )
                        self.client.cache_capability_status(pair_id, cache_key, status, 600)
                        parsed = self._parse_ha_monitored_interface(summary)
                        parsed.collection_errors.append(f"detail: {type(exc).__name__}: {exc}")
                        hp.monitored_interfaces.append(parsed)
                        hp.collection_errors.append(
                            f"monitoredInterfaceDetail[{object_id}]: {type(exc).__name__}: {exc}"
                        )
            except Exception as exc:
                hp.collection_errors.append(f"monitoredInterfaces: {type(exc).__name__}: {exc}")
                logger.warning("FMC HA monitored interfaces failed for %s: %s", pair_id, exc)
            return hp

        # FMC is sensitive to request bursts on the HA resource. Collect strictly
        # sequentially; the client also enforces a process-wide quiet interval.
        results: list[HaPair] = []
        for raw in pairs_raw:
            pair = await _collect_one(raw)
            if pair is not None:
                results.append(pair)
        return results

    @staticmethod
    def _parse_ha_monitored_interface(data: dict) -> HaMonitoredInterface:
        ipv4 = data.get("ipv4Configuration")
        ipv4 = ipv4 if isinstance(ipv4, dict) else {}
        ipv6 = data.get("ipv6Configuration")
        ipv6 = ipv6 if isinstance(ipv6, dict) else {}
        pairs = ipv6.get("ipv6ActiveStandbyPair")
        pairs = pairs if isinstance(pairs, list) else []
        monitor = data.get("monitorForFailures")
        if isinstance(monitor, str):
            monitor = monitor.casefold() == "true"
        elif not isinstance(monitor, bool):
            monitor = None
        return HaMonitoredInterface(
            id=data.get("id"),
            name=data.get("name"),
            description=data.get("description"),
            interface_logical_name=data.get("interfaceLogicalName"),
            monitor_for_failures=monitor,
            ipv4=HaIpv4Configuration(
                active_address=ipv4.get("activeIPv4Address"),
                active_mask=ipv4.get("activeIPv4Mask"),
                standby_address=ipv4.get("standbyIPv4Address"),
            ),
            ipv6=HaIpv6Configuration(
                active_link_local_address=ipv6.get("activeIPv6LinkLocalAddress"),
                standby_link_local_address=ipv6.get("standbyIPv6LinkLocalAddress"),
                address_pairs=[
                    HaIpv6AddressPair(
                        active_address=pair.get("activeIPv6"),
                        standby_address=pair.get("standbyIPv6"),
                    )
                    for pair in pairs
                    if isinstance(pair, dict)
                ],
            ),
            raw=data,
        )

    def _parse_ha_pair(self, data: dict) -> HaPair:
        primary_data = data.get("primary", {}) if isinstance(data.get("primary"), dict) else {}
        secondary_data = (
            data.get("secondary", {}) if isinstance(data.get("secondary"), dict) else {}
        )
        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        primary_status = (
            metadata.get("primaryStatus") if isinstance(metadata.get("primaryStatus"), dict) else {}
        )
        secondary_status = (
            metadata.get("secondaryStatus")
            if isinstance(metadata.get("secondaryStatus"), dict)
            else {}
        )
        primary_runtime = primary_status.get("currentStatus")
        secondary_runtime = secondary_status.get("currentStatus")
        active_ids = [
            member_id
            for member_id, runtime_role in (
                (primary_data.get("id"), primary_runtime),
                (secondary_data.get("id"), secondary_runtime),
            )
            if str(runtime_role or "").upper() == "ACTIVE" and member_id
        ]
        standby_ids = [
            member_id
            for member_id, runtime_role in (
                (primary_data.get("id"), primary_runtime),
                (secondary_data.get("id"), secondary_runtime),
            )
            if str(runtime_role or "").upper() == "STANDBY" and member_id
        ]
        pair_state = self._derive_ha_state(
            data.get("healthStatus"),
            active_ids,
            standby_ids,
            runtime_roles=[primary_runtime, secondary_runtime],
            config_status=metadata.get("configStatus"),
        )
        bootstrap = (
            data.get("ftdHABootstrap") if isinstance(data.get("ftdHABootstrap"), dict) else {}
        )
        return HaPair(
            id=data.get("id"),
            name=data.get("name"),
            health_status=data.get("healthStatus"),
            health_message=data.get("healthMessage"),
            status=data.get("status"),
            pair_state=pair_state,
            active_member_id=active_ids[0] if len(active_ids) == 1 else None,
            standby_member_id=standby_ids[0] if len(standby_ids) == 1 else None,
            failover_link=bootstrap.get("lanFailover")
            if isinstance(bootstrap.get("lanFailover"), dict)
            else {},
            stateful_link=bootstrap.get("statefulFailover")
            if isinstance(bootstrap.get("statefulFailover"), dict)
            else {},
            primary=HaMember(
                device_id=primary_data.get("id"),
                role="PRIMARY",
                runtime_role=primary_runtime,
            ),
            secondary=HaMember(
                device_id=secondary_data.get("id"),
                role="SECONDARY",
                runtime_role=secondary_runtime,
            ),
            raw=data,
        )

    @staticmethod
    def _derive_ha_state(
        health_status: str | None,
        active_ids: list[str],
        standby_ids: list[str],
        *,
        runtime_roles: list[str | None] | None = None,
        config_status: str | None = None,
    ) -> str:
        health = str(health_status or "").upper()
        roles = {str(role or "").upper() for role in runtime_roles or []}
        config = str(config_status or "").upper()
        if len(active_ids) > 1 or len(standby_ids) > 1:
            return "FAILED"
        if health in {"CRITICAL", "FAILED", "ERROR", "RED"} or roles.intersection(
            {"FAILED", "ERROR", "DOWN", "UNREACHABLE"}
        ):
            return "FAILED"
        if len(active_ids) != 1 or len(standby_ids) != 1:
            return "UNKNOWN"
        if health in {"WARNING", "DEGRADED", "YELLOW"} or config == "MISSING_CONFIG":
            return "DEGRADED"
        # FMC's documented and observed detail response can omit healthStatus.
        # A single Active/Standby pair is nevertheless a positive runtime signal.
        return "HEALTHY"

    # ======================================================================
    # Chassis
    # ======================================================================

    async def _collect_chassis(self, chassis_raw: list[dict]) -> list[ChassisData]:
        sem = asyncio.Semaphore(2)

        async def _collect_one(raw: dict) -> ChassisData | None:
            cid = raw.get("id")
            if not cid:
                return None
            async with sem:
                try:
                    detail = await self.client.get_chassis(cid)
                except Exception as exc:
                    logger.warning("FMC chassis detail failed for %s: %s", cid, exc)
                    detail = raw

                chassis = ChassisData(
                    id=cid,
                    name=detail.get("chassisName"),
                    host_name=detail.get("chassisHostName"),
                    model=detail.get("model"),
                    model_number=detail.get("modelNumber"),
                    sw_version=detail.get("swVersion"),
                    is_connected=detail.get("isConnected", False),
                    raw=detail,
                )

                # Inventory
                try:
                    inv = await self.client.get_chassis_inventory(cid)
                    chassis.inventory = inv
                except Exception as exc:
                    chassis.collection_errors.append(f"inventory: {type(exc).__name__}: {exc}")

                # Faults
                try:
                    faults_data = await self.client.get_chassis_faults(cid)
                    for f in faults_data.get("faultList", []):
                        chassis.faults.append(
                            ChassisFault(
                                severity=f.get("severity"),
                                code=f.get("code"),
                                cause=f.get("cause"),
                                description=f.get("description"),
                                raw=f,
                            )
                        )
                except Exception as exc:
                    chassis.collection_errors.append(f"faults: {type(exc).__name__}: {exc}")

                # Interface summary
                try:
                    isum = await self.client.get_chassis_interface_summary(cid)
                    chassis.interface_summary = isum.get("interfaceList", [])
                except Exception as exc:
                    chassis.collection_errors.append(
                        f"interfaceSummary: {type(exc).__name__}: {exc}"
                    )

                # Instances
                try:
                    inst = await self.client.get_chassis_instances(cid)
                    chassis.instances = inst.get("instanceList", [])
                except Exception as exc:
                    chassis.collection_errors.append(
                        f"instanceSummary: {type(exc).__name__}: {exc}"
                    )

                # Logical devices
                try:
                    chassis.logical_devices = await self.client.get_chassis_logical_devices(cid)
                except Exception as exc:
                    chassis.collection_errors.append(f"logicalDevices: {type(exc).__name__}: {exc}")

                return chassis

        tasks = [_collect_one(raw) for raw in chassis_raw]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.error("FMC chassis collection task failed: %s", result)
        return [r for r in results if isinstance(r, ChassisData)]

    # ======================================================================
    # Parsing helpers
    # ======================================================================

    def _deduplicate_devices(self, devices: list[dict]) -> list[dict]:
        """Remove exact duplicate IDs while preserving distinct records for review."""
        by_id: dict[str, dict] = {}
        for raw in devices:
            device_id = raw.get("id")
            if not device_id:
                logger.warning("FMC discovery record has no device ID")
                continue
            if device_id in by_id:
                logger.warning("FMC discovery duplicate device ID", extra={"device_id": device_id})
                current_updated = str(by_id[device_id].get("last_updated") or "")
                candidate_updated = str(raw.get("last_updated") or "")
                if candidate_updated > current_updated:
                    by_id[device_id] = raw
                continue
            by_id[device_id] = raw

        for raw in by_id.values():
            metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
            logger.info(
                "FMC device discovered",
                extra={
                    "device_id": raw.get("id"),
                    "device_name": raw.get("name"),
                    "model": raw.get("model"),
                    "software_version": raw.get("sw_version") or raw.get("swVersion"),
                    "is_connected": raw.get("isConnected"),
                    "health_status": raw.get("healthStatus"),
                    "role": raw.get("role"),
                    "status": raw.get("status"),
                    "is_part_of_container": metadata.get("isPartOfContainer"),
                    "is_dummy_device": metadata.get("isDummyDevice") or metadata.get("dummyDevice"),
                },
            )
        return list(by_id.values())

    def _parse_device(self, data: dict) -> DeviceIdentity:
        meta = data.get("metadata") or {}
        return DeviceIdentity(
            id=data.get("id"),
            name=data.get("name"),
            host_name=data.get("hostName"),
            model=data.get("model"),
            model_number=data.get("modelNumber"),
            model_type=data.get("modelType"),
            model_id=data.get("modelId"),
            sw_version=data.get("sw_version") or data.get("swVersion"),
            ftd_mode=data.get("ftdMode"),
            role=data.get("role"),
            status=data.get("status"),
            is_connected=data.get("isConnected"),
            health_status=data.get("healthStatus"),
            health_message=data.get("healthMessage"),
            deployment_status=data.get("deploymentStatus"),
            snort_engine=data.get("snortEngine"),
            performance_tier=data.get("performanceTier"),
            health_policy=(data.get("healthPolicy") or {}).get("name")
            if isinstance(data.get("healthPolicy"), dict)
            else data.get("healthPolicy"),
            access_policy=(data.get("accessPolicy") or {}).get("name")
            if isinstance(data.get("accessPolicy"), dict)
            else None,
            license_caps=data.get("license_caps", []),
            serial_number=meta.get("deviceSerialNumber"),
            snort_version=meta.get("snortVersion"),
            sru_version=meta.get("sruVersion"),
            vdb_version=meta.get("vdbVersion"),
            is_dummy_device=bool(meta.get("isDummyDevice") or meta.get("dummyDevice")),
            is_part_of_container=bool(meta.get("isPartOfContainer")),
            container_details=meta.get("containerDetails")
            if isinstance(meta.get("containerDetails"), dict)
            else {},
            links_self=(data.get("links") or {}).get("self")
            if isinstance(data.get("links"), dict)
            else None,
            raw=data,
        )

    def _parse_load(self, metrics: dict) -> dict:
        normalized, _capabilities = normalize_aggregate(metrics)
        return normalized

    def _parse_operational_cpu(self, items: list[dict]) -> dict:
        if not items:
            return {}
        latest = items[-1]
        metric = latest.get("healthMonitorMetric", {})
        return {"linaPercent": _safe_float(metric.get("value")), "source": "operational_metrics"}

    def _parse_interface_config(self, item: dict) -> NormalizedInterface:
        ipv4 = item.get("ipv4", {}) if isinstance(item.get("ipv4"), dict) else {}
        ipv6 = item.get("ipv6", {}) if isinstance(item.get("ipv6"), dict) else {}
        zone = item.get("securityZone", {}) if isinstance(item.get("securityZone"), dict) else {}
        mac_active = item.get("activeMACAddress")
        mac_standby = item.get("standbyMACAddress")
        return NormalizedInterface(
            id=item.get("id"),
            physical_name=item.get("name"),
            logical_name=item.get("ifname"),
            type=item.get("type"),
            enabled=item.get("enabled", False),
            mode=item.get("mode"),
            mtu=item.get("MTU"),
            management_only=item.get("managementOnly", False),
            security_zone={"id": zone.get("id"), "name": zone.get("name")} if zone else {},
            addresses={"ipv4": ipv4, "ipv6": ipv6},
            mac_active=mac_active,
            mac_standby=mac_standby,
            sources=["ftdallinterfaces"],
            raw=item,
        )

    def _merge_interface_runtime(
        self, interfaces: list[NormalizedInterface], runtime_ifaces: list[dict]
    ) -> None:
        """Merge health_aggregate runtime data into config interfaces."""
        for rt in runtime_ifaces:
            runtime_id = rt.get("interfaceId")
            name = rt.get("interfaceName") or rt.get("interface")
            candidates: list[NormalizedInterface] = []
            if runtime_id:
                candidates = [iface for iface in interfaces if iface.id == runtime_id]
            if not candidates and name:
                candidates = [iface for iface in interfaces if iface.physical_name == name]
            if not candidates and name:
                candidates = [iface for iface in interfaces if iface.logical_name == name]
            if not candidates and name:
                normalized_name = str(name).casefold()
                candidates = [
                    iface
                    for iface in interfaces
                    if normalized_name
                    in {
                        str(iface.physical_name or "").casefold(),
                        str(iface.logical_name or "").casefold(),
                    }
                ]
            if len(candidates) != 1:
                if len(candidates) > 1:
                    logger.warning(
                        "Ambiguous FMC interface runtime match", extra={"interface": name}
                    )
                continue
            iface = candidates[0]
            metric_status = rt.get("metricStatus", MetricStatus.NO_DATA.value)
            try:
                parsed_status = MetricStatus(metric_status)
            except ValueError:
                parsed_status = MetricStatus.INVALID_RESPONSE
            iface.runtime = InterfaceRuntime(
                link_status=rt.get("linkStatus"),
                operational_status=rt.get("operationalStatus"),
                duplex=rt.get("duplexMode"),
                input_bytes_average=_safe_float(rt.get("inputBytesAverage")),
                output_bytes_average=_safe_float(rt.get("outputBytesAverage")),
                input_errors_average=_safe_float(rt.get("inputErrorsAverage")),
                output_errors_average=_safe_float(rt.get("outputErrorsAverage")),
                drops_average=_safe_float(rt.get("dropsAverage")),
                l2_decode_drops_average=_safe_float(rt.get("l2DecodeDropsAverage")),
                buffer_overruns_average=_safe_float(rt.get("bufferOverrunsAverage")),
                buffer_underruns_average=_safe_float(rt.get("bufferUnderrunsAverage")),
                input_packet_size_average=_safe_float(rt.get("inputPacketSizeAverage")),
                output_packet_size_average=_safe_float(rt.get("outputPacketSizeAverage")),
                metric_status=parsed_status,
            )
            iface.metric_status = parsed_status
            iface.sources.append("health_aggregatemetrics")


# ======================================================================
# Helpers
# ======================================================================


def _pct(metrics: dict, key: str) -> float | None:
    val = metrics.get(key)
    return _safe_float(val)


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _classify_error(e: Exception) -> str:
    if isinstance(e, FmcRequestError):
        return _metric_status_for_error(e).value
    msg = str(e)
    if "429" in msg:
        return "TEMPORARY_ERROR"
    if "401" in msg or "403" in msg:
        return "PERMISSION_ERROR"
    if "404" in msg or "400" in msg:
        return "UNSUPPORTED"
    return "TEMPORARY_ERROR"


def _metric_status_for_error(error: FmcRequestError) -> MetricStatus:
    return {
        FmcErrorCategory.PERMISSION_ERROR: MetricStatus.PERMISSION_ERROR,
        FmcErrorCategory.UNSUPPORTED_ENDPOINT: MetricStatus.UNSUPPORTED,
        FmcErrorCategory.INVALID_REQUEST: MetricStatus.UNSUPPORTED,
        FmcErrorCategory.INVALID_RESPONSE: MetricStatus.INVALID_RESPONSE,
        FmcErrorCategory.STALE_DEVICE: MetricStatus.STALE_DEVICE,
        FmcErrorCategory.AUTH_ERROR: MetricStatus.PERMISSION_ERROR,
        FmcErrorCategory.RATE_LIMIT: MetricStatus.TEMPORARY_ERROR,
        FmcErrorCategory.TEMPORARY_FMC_ERROR: MetricStatus.TEMPORARY_ERROR,
        FmcErrorCategory.TIMEOUT: MetricStatus.TEMPORARY_ERROR,
        FmcErrorCategory.NETWORK_ERROR: MetricStatus.TEMPORARY_ERROR,
        FmcErrorCategory.PARTIAL_RESULT: MetricStatus.PARTIAL,
    }.get(error.category, MetricStatus.TEMPORARY_ERROR)
