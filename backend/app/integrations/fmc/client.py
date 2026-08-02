"""Read-only FMC REST client with bounded retry, pagination, and diagnostics."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections import deque
from collections.abc import Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote
from weakref import WeakKeyDictionary

import httpx

from app.core.config import Settings, get_settings
from app.integrations.fmc.errors import (
    FmcErrorCategory,
    FmcRequestError,
    category_for_status,
)
from app.observability.metrics import increment

logger = logging.getLogger(__name__)

_RETRYABLE = {
    FmcErrorCategory.RATE_LIMIT,
    FmcErrorCategory.TEMPORARY_FMC_ERROR,
    FmcErrorCategory.TIMEOUT,
    FmcErrorCategory.NETWORK_ERROR,
}
AGGREGATE_METRIC_CATEGORIES = (
    "CPU",
    "MEM",
    "INTERFACE",
    "DISK_STATS",
    "CHASSIS_STATS",
)
_SECRET_KEYS = {
    "authorization",
    "cookie",
    "password",
    "passwd",
    "secret",
    "secretkey",
    "token",
    "x-auth-access-token",
    "x-auth-refresh-token",
}


@dataclass
class _RateState:
    """Request pacing shared by every FMC client on the same event loop."""

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_request_finished: float = 0.0
    blocked_until: float = 0.0


_RATE_STATES: WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, _RateState]] = (
    WeakKeyDictionary()
)


class FmcClient:
    """Async FMC client. Only authentication POST and read-only GET are implemented."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._token: str | None = None
        self._refresh_token: str | None = None
        self._domain_uuid: str | None = None
        self._base = str(self.settings.fmc_url).rstrip("/")
        if self._base.endswith("/api"):
            self._base = self._base[:-4]
        self._raw_responses: deque[dict[str, Any]] = deque(
            maxlen=max(1, self.settings.fmc_raw_response_limit)
        )
        self._capability_cache: dict[str, tuple[str, float]] = {}
        self._auth_lock = asyncio.Lock()
        self._http: httpx.AsyncClient | None = None

    @classmethod
    def from_settings(cls) -> FmcClient:
        return cls(get_settings())

    @property
    def configured(self) -> bool:
        return bool(self._base and self.settings.fmc_username and self.settings.fmc_password)

    @property
    def domain_uuid(self) -> str:
        if not self._domain_uuid:
            raise RuntimeError("FMC client is not authenticated")
        return self._domain_uuid

    @property
    def raw_responses(self) -> list[dict[str, Any]]:
        return list(self._raw_responses)

    def clear_diagnostics(self) -> None:
        self._raw_responses.clear()

    def clear_capability_cache(self) -> None:
        self._capability_cache.clear()

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                verify=self.settings.fmc_verify_ssl,
                timeout=self.settings.fmc_timeout_seconds,
                headers={"Accept": "application/json"},
            )
        return self._http

    async def close(self) -> None:
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()

    async def __aenter__(self) -> FmcClient:
        await self._get_http()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    def mark_unsupported(self, device_id: str, endpoint: str, ttl_seconds: int = 3600) -> None:
        """Remember an explicit unsupported result temporarily, never permanently."""
        self.cache_capability_status(device_id, endpoint, "UNSUPPORTED", ttl_seconds)

    def cache_capability_status(
        self,
        device_id: str,
        endpoint: str,
        status: str,
        ttl_seconds: int = 3600,
    ) -> None:
        self._capability_cache[f"{device_id}:{endpoint}"] = (
            status,
            time.monotonic() + max(1, ttl_seconds),
        )

    def capability_status(self, device_id: str, endpoint: str) -> str | None:
        key = f"{device_id}:{endpoint}"
        cached = self._capability_cache.get(key)
        if not cached:
            return None
        status, expires_at = cached
        if time.monotonic() >= expires_at:
            self._capability_cache.pop(key, None)
            return None
        return status

    def is_unsupported(self, device_id: str, endpoint: str) -> bool:
        return self.capability_status(device_id, endpoint) == "UNSUPPORTED"

    async def authenticate(self, *, force: bool = False) -> str:
        if not self.configured:
            raise FmcRequestError(
                FmcErrorCategory.AUTH_ERROR,
                "FMC credentials are not configured",
                path="/api/fmc_platform/v1/auth/generatetoken",
            )
        async with self._auth_lock:
            if self._token and self._domain_uuid and not force:
                return self._token
            path = "/api/fmc_platform/v1/auth/generatetoken"
            client = await self._get_http()
            attempts = max(1, self.settings.fmc_max_attempts)
            response: httpx.Response | None = None
            last_error: FmcRequestError | None = None
            for attempt in range(attempts):
                started = time.monotonic()
                try:
                    async with self._request_slot() as rate_state:
                        response = await client.post(
                            f"{self._base}{path}",
                            auth=httpx.BasicAuth(
                                self.settings.fmc_username,
                                self.settings.fmc_password,
                            ),
                        )
                        if response.status_code == 429:
                            self._apply_rate_limit_cooldown(rate_state, response)
                except httpx.TimeoutException as exc:
                    last_error = FmcRequestError(
                        FmcErrorCategory.TIMEOUT,
                        "FMC authentication timed out",
                        path=path,
                    )
                    self._record_transport_error(path, started, last_error.category)
                    if attempt + 1 < attempts:
                        await self._backoff(attempt)
                        continue
                    raise last_error from exc
                except httpx.RequestError as exc:
                    last_error = FmcRequestError(
                        FmcErrorCategory.NETWORK_ERROR,
                        "FMC authentication network error",
                        path=path,
                    )
                    self._record_transport_error(path, started, last_error.category)
                    if attempt + 1 < attempts:
                        await self._backoff(attempt)
                        continue
                    raise last_error from exc

                duration_ms = round((time.monotonic() - started) * 1000, 1)
                if response.status_code >= 400:
                    category = category_for_status(response.status_code)
                    self._record_response(path, response, duration_ms, category=category)
                    last_error = FmcRequestError(
                        category,
                        _error_message(response, "FMC authentication failed"),
                        path=path,
                        status_code=response.status_code,
                        response_bytes=len(response.content),
                    )
                    if category in _RETRYABLE and attempt + 1 < attempts:
                        await self._backoff(attempt)
                        continue
                    raise last_error
                break

            if response is None:
                raise last_error or FmcRequestError(
                    FmcErrorCategory.TEMPORARY_FMC_ERROR,
                    "FMC authentication attempts exhausted",
                    path=path,
                )

            self._token = response.headers.get("X-auth-access-token")
            self._refresh_token = response.headers.get("X-auth-refresh-token")
            self._domain_uuid = response.headers.get("DOMAIN_UUID")
            if not self._domain_uuid:
                try:
                    body = response.json()
                    self._domain_uuid = body.get("DOMAIN_UUID") or body.get("domainUuid")
                except ValueError:
                    self._domain_uuid = None
            if not self._token or not self._domain_uuid:
                raise FmcRequestError(
                    FmcErrorCategory.INVALID_RESPONSE,
                    "FMC authentication omitted token or domain UUID",
                    path=path,
                    status_code=response.status_code,
                    response_bytes=len(response.content),
                )
            logger.info("FMC authentication succeeded", extra={"component": "fmc_client"})
            return self._token

    def clear_token(self) -> None:
        self._token = None
        self._refresh_token = None

    def _rate_state(self) -> _RateState:
        loop = asyncio.get_running_loop()
        states = _RATE_STATES.setdefault(loop, {})
        return states.setdefault(self._base, _RateState())

    @asynccontextmanager
    async def _request_slot(self):
        """Serialize FMC traffic and leave a quiet interval after each request."""
        state = self._rate_state()
        async with state.lock:
            now = time.monotonic()
            interval = max(0.0, self.settings.fmc_min_request_interval_seconds)
            ready_at = max(state.last_request_finished + interval, state.blocked_until)
            if ready_at > now:
                await asyncio.sleep(ready_at - now)
            try:
                yield state
            finally:
                state.last_request_finished = time.monotonic()

    def _apply_rate_limit_cooldown(
        self,
        state: _RateState,
        response: httpx.Response,
    ) -> None:
        retry_after = _retry_after_seconds(response)
        if retry_after is None:
            retry_after = max(0.0, self.settings.fmc_rate_limit_cooldown_seconds)
        state.blocked_until = max(state.blocked_until, time.monotonic() + retry_after)
        logger.warning(
            "FMC rate limit reached; pausing all FMC requests for %.1f seconds",
            retry_after,
        )

    async def get(self, path: str, retries: int | None = None) -> dict[str, Any]:
        if not self._token:
            raise FmcRequestError(
                FmcErrorCategory.AUTH_ERROR,
                "FMC client is not authenticated",
                path=path,
            )
        attempts = max(1, retries or self.settings.fmc_max_attempts)
        auth_retried = False
        last_error: FmcRequestError | None = None
        client = await self._get_http()

        for attempt in range(attempts):
            started = time.monotonic()
            try:
                async with self._request_slot() as rate_state:
                    response = await client.get(
                        f"{self._base}{path}",
                        headers={"X-auth-access-token": self._token or ""},
                    )
                    if response.status_code == 429:
                        self._apply_rate_limit_cooldown(rate_state, response)
            except httpx.TimeoutException as exc:
                last_error = FmcRequestError(
                    FmcErrorCategory.TIMEOUT,
                    "FMC request timed out",
                    path=path,
                )
                self._record_transport_error(path, started, last_error.category)
                if attempt + 1 < attempts:
                    await self._backoff(attempt)
                    continue
                raise last_error from exc
            except httpx.RequestError as exc:
                last_error = FmcRequestError(
                    FmcErrorCategory.NETWORK_ERROR,
                    "FMC network request failed",
                    path=path,
                )
                self._record_transport_error(path, started, last_error.category)
                if attempt + 1 < attempts:
                    await self._backoff(attempt)
                    continue
                raise last_error from exc

            duration_ms = round((time.monotonic() - started) * 1000, 1)
            if response.status_code == 401 and not auth_retried:
                auth_retried = True
                self.clear_token()
                await self.authenticate(force=True)
                continue

            if response.status_code >= 400:
                category = category_for_status(response.status_code)
                self._record_response(path, response, duration_ms, category=category)
                last_error = FmcRequestError(
                    category,
                    _error_message(response, f"FMC returned HTTP {response.status_code}"),
                    path=path,
                    status_code=response.status_code,
                    response_bytes=len(response.content),
                )
                if category in _RETRYABLE and attempt + 1 < attempts:
                    await self._backoff(attempt)
                    continue
                raise last_error

            try:
                data = response.json()
            except ValueError as exc:
                category = FmcErrorCategory.INVALID_RESPONSE
                self._record_response(path, response, duration_ms, category=category)
                raise FmcRequestError(
                    category,
                    "FMC returned malformed JSON",
                    path=path,
                    status_code=response.status_code,
                    response_bytes=len(response.content),
                ) from exc
            if not isinstance(data, dict):
                raise FmcRequestError(
                    FmcErrorCategory.INVALID_RESPONSE,
                    "FMC response root is not an object",
                    path=path,
                    status_code=response.status_code,
                    response_bytes=len(response.content),
                )
            self._record_response(path, response, duration_ms, data=data)
            return data

        raise last_error or FmcRequestError(
            FmcErrorCategory.TEMPORARY_FMC_ERROR,
            "FMC request attempts exhausted",
            path=path,
        )

    async def _backoff(self, attempt: int) -> None:
        delay = min(8.0, float(2**attempt))
        await asyncio.sleep(delay + random.uniform(0, delay * 0.25))

    def _record_transport_error(
        self,
        path: str,
        started: float,
        category: FmcErrorCategory,
    ) -> None:
        self._raw_responses.append(
            {
                "path": path,
                "status": None,
                "duration_ms": round((time.monotonic() - started) * 1000, 1),
                "response_bytes": 0,
                "items_count": None,
                "error_category": category.value,
            }
        )
        increment("fmc_http_requests_total")
        increment("fmc_http_errors_total")

    def _record_response(
        self,
        path: str,
        response: httpx.Response,
        duration_ms: float,
        *,
        data: dict[str, Any] | None = None,
        category: FmcErrorCategory | None = None,
    ) -> None:
        record: dict[str, Any] = {
            "path": path,
            "status": response.status_code,
            "duration_ms": duration_ms,
            "response_bytes": len(response.content),
            "items_count": len(data.get("items", [])) if data else None,
            "error_category": category.value if category else None,
        }
        if data is not None and len(response.content) <= self.settings.fmc_raw_response_max_bytes:
            record["data"] = _redact(data)
        else:
            record["raw_omitted"] = True
        self._raw_responses.append(record)
        increment("fmc_http_requests_total")
        increment("fmc_response_time_seconds_sum", duration_ms / 1000)
        increment("fmc_response_time_seconds_count")
        if response.status_code >= 400:
            increment("fmc_http_errors_total")

    async def get_all(self, path: str, limit: int = 1000) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        offset = 0
        seen_pages: set[tuple[str | None, ...]] = set()
        for _page_number in range(10_000):
            separator = "&" if "?" in path else "?"
            data = await self.get(f"{path}{separator}offset={offset}&limit={limit}&expanded=true")
            page_items = data.get("items", [])
            if not isinstance(page_items, list):
                raise FmcRequestError(
                    FmcErrorCategory.INVALID_RESPONSE,
                    "FMC pagination items is not an array",
                    path=path,
                )
            signature = tuple(
                str(item.get("id")) if isinstance(item, dict) else None for item in page_items
            )
            if signature and signature in seen_pages:
                raise FmcRequestError(
                    FmcErrorCategory.INVALID_RESPONSE,
                    "FMC pagination repeated a page",
                    path=path,
                )
            seen_pages.add(signature)
            items.extend(item for item in page_items if isinstance(item, dict))
            if not page_items:
                break
            paging = data.get("paging") if isinstance(data.get("paging"), dict) else {}
            total = paging.get("count")
            if isinstance(total, int) and total > 0 and len(items) >= total:
                break
            if len(page_items) < limit:
                break
            offset += len(page_items)
        else:
            raise FmcRequestError(
                FmcErrorCategory.INVALID_RESPONSE,
                "FMC pagination exceeded the safety limit",
                path=path,
            )
        return items

    async def get_domains(self) -> list[dict[str, Any]]:
        return (await self.get("/api/fmc_platform/v1/info/domain")).get("items", [])

    def _cfg(self, endpoint: str) -> str:
        return f"/api/fmc_config/v1/domain/{self.domain_uuid}{endpoint}"

    def _health(self, endpoint: str) -> str:
        return f"/api/fmc_config/v1/domain/{self.domain_uuid}/health{endpoint}"

    def _platform(self, endpoint: str) -> str:
        return f"/api/fmc_platform/v1/domain/{self.domain_uuid}{endpoint}"

    async def get_devices(self) -> list[dict]:
        return await self.get_all(self._cfg("/devices/devicerecords"))

    async def get_device(self, uid: str) -> dict:
        return await self.get(self._cfg(f"/devices/devicerecords/{uid}"))

    async def get_aggregate_metrics(self, uid: str, metrics: Sequence[str]) -> dict:
        metric_filter = ",".join(metrics)
        if not metric_filter:
            raise ValueError("At least one aggregate metric category is required")
        filter_value = f"metric:{metric_filter};device_uuid:{uid}"
        return await self.get(
            self._health(f"/aggregatemetrics?filter={quote(filter_value, safe='')}&expanded=false")
        )

    async def get_alerts(self, uid: str) -> dict:
        filter_value = f"deviceUUIDs:{uid};status:red,yellow"
        return await self.get(
            self._health(f"/alerts?filter={quote(filter_value, safe='')}&expanded=true&limit=1000")
        )

    async def get_all_interfaces(self, uid: str) -> dict:
        return await self.get(
            self._cfg(f"/devices/devicerecords/{uid}/ftdallinterfaces?expanded=true&limit=1000")
        )

    async def get_interface_events(self, uid: str) -> dict:
        return await self.get(
            self._cfg(f"/devices/devicerecords/{uid}/interfaceevents?expanded=true&limit=1000")
        )

    async def get_health_metrics(
        self,
        uid: str,
        metric: str,
        start: int,
        end: int,
        *,
        regex_filter: str | None = None,
        step: int = 60,
    ) -> dict:
        filter_value = (
            f"deviceUUIDs:{uid};metric:{metric};startTime:{start};endTime:{end};step:{max(1, step)}"
        )
        if regex_filter:
            filter_value += f";regexFilter:{regex_filter}"
        return await self.get(
            self._health(f"/metrics?filter={quote(filter_value, safe='')}&expanded=true&limit=1000")
        )

    async def get_operational_metrics(self, uid: str, metric: str) -> dict:
        filter_value = quote(f"metric:{metric}", safe="")
        return await self.get(
            self._cfg(
                f"/devices/devicerecords/{uid}/operational/metrics"
                f"?filter={filter_value}&expanded=true&limit=100"
            )
        )

    async def get_ha_pairs(self) -> list[dict]:
        return await self.get_all(self._cfg("/devicehapairs/ftddevicehapairs"))

    async def get_ha_pair(self, uid: str) -> dict:
        return await self.get(self._cfg(f"/devicehapairs/ftddevicehapairs/{uid}"))

    async def get_ha_monitored_interfaces(self, uid: str) -> list[dict]:
        return await self.get_all(
            self._cfg(f"/devicehapairs/ftddevicehapairs/{uid}/monitoredinterfaces")
        )

    async def get_ha_monitored_interface(self, container_uid: str, object_uid: str) -> dict:
        # The expanded list item remains a usable fallback. Avoid applying the
        # generic five-attempt loop to every object with a server-side detail error.
        return await self.get(
            self._cfg(
                f"/devicehapairs/ftddevicehapairs/{container_uid}/monitoredinterfaces/{object_uid}"
            ),
            retries=1,
        )

    async def get_access_policies(self) -> list[dict]:
        return await self.get_all(self._cfg("/policy/accesspolicies"))

    async def get_access_rules(self, policy_uid: str) -> list[dict]:
        return await self.get_all(self._cfg(f"/policy/accesspolicies/{policy_uid}/accessrules"))

    async def get_chassis_list(self) -> list[dict]:
        return await self.get_all(self._cfg("/chassis/fmcmanagedchassis"))

    async def get_chassis(self, uid: str) -> dict:
        return await self.get(self._cfg(f"/chassis/fmcmanagedchassis/{uid}"))

    async def get_chassis_inventory(self, uid: str) -> dict:
        return await self.get(
            self._cfg(f"/chassis/fmcmanagedchassis/{uid}/inventorysummary?expanded=true")
        )

    async def get_chassis_faults(self, uid: str) -> dict:
        return await self.get(
            self._cfg(f"/chassis/fmcmanagedchassis/{uid}/faultsummary?expanded=true")
        )

    async def get_chassis_interface_summary(self, uid: str) -> dict:
        return await self.get(
            self._cfg(f"/chassis/fmcmanagedchassis/{uid}/interfacesummary?expanded=true")
        )

    async def get_chassis_interfaces(self, uid: str) -> list[dict]:
        return await self.get_all(self._cfg(f"/chassis/fmcmanagedchassis/{uid}/interfaces"))

    async def get_chassis_instances(self, uid: str) -> dict:
        return await self.get(
            self._cfg(f"/chassis/fmcmanagedchassis/{uid}/instancesummary?expanded=true")
        )

    async def get_chassis_logical_devices(self, uid: str) -> list[dict]:
        return await self.get_all(self._cfg(f"/chassis/fmcmanagedchassis/{uid}/logicaldevices"))

    async def get_chassis_network_modules(self, uid: str) -> list[dict]:
        return await self.get_all(self._cfg(f"/chassis/fmcmanagedchassis/{uid}/networkmodules"))

    async def get_chassis_events(self, uid: str) -> list[dict]:
        return await self.get_all(
            self._cfg(f"/chassis/fmcmanagedchassis/{uid}/chassisinterfaceevents")
        )

    async def get_tunnel_statuses(self) -> dict:
        return await self.get(self._health("/tunnelstatuses?expanded=true&limit=1000"))

    async def get_tunnel_summaries(self) -> dict:
        return await self.get(self._health("/tunnelsummaries?expanded=true&limit=1000"))

    async def get_tunnel_details(self, uid: str) -> dict:
        return await self.get(self._health(f"/tunnelstatuses/{uid}/tunneldetails?expanded=true"))

    async def get_s2s_vpn_policies(self) -> list[dict]:
        return await self.get_all(self._cfg("/policy/ftds2svpns"))

    async def get_vpn_tunnel_statuses(self) -> list[dict]:
        return await self.get_all(self._cfg("/policy/vpntunnelstatuses"))


def _error_message(response: httpx.Response, fallback: str) -> str:
    try:
        payload = response.json()
    except ValueError:
        return fallback
    messages = (payload.get("error") or {}).get("messages", []) if isinstance(payload, dict) else []
    descriptions = [
        message.get("description")
        for message in messages
        if isinstance(message, dict) and isinstance(message.get("description"), str)
    ]
    return "; ".join(descriptions) or fallback


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***" if key.lower() in _SECRET_KEYS else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
