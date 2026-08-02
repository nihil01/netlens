"""Pure read-only FMC health and access-policy analytics.

The calculations are intentionally independent from third-party project code. They
implement the useful monitoring ideas against the local FMC OpenAPI contract.
"""

from __future__ import annotations

import json
from math import isfinite
from statistics import fmean
from typing import Any

from app.integrations.fmc.errors import FmcErrorCategory, FmcRequestError


def summarize_health_series(
    response: dict[str, Any],
    *,
    expected_device_id: str,
) -> dict[str, Any] | None:
    """Parse FMC's JSON-encoded Prometheus matrix and calculate safe statistics."""
    items = response.get("items")
    if not isinstance(items, list):
        raise FmcRequestError(
            FmcErrorCategory.INVALID_RESPONSE,
            "Health metrics items is not an array",
            path="health/metrics",
        )
    samples: dict[float, float] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        device_id = item.get("deviceUUID")
        if device_id and device_id != expected_device_id:
            raise FmcRequestError(
                FmcErrorCategory.INVALID_RESPONSE,
                f"Health metrics UUID mismatch for {expected_device_id}",
                path="health/metrics",
            )
        encoded = item.get("response")
        if not isinstance(encoded, str):
            continue
        try:
            payload = json.loads(encoded)
        except (TypeError, ValueError) as exc:
            raise FmcRequestError(
                FmcErrorCategory.INVALID_RESPONSE,
                "Health metrics response contains malformed JSON",
                path="health/metrics",
            ) from exc
        results = (payload.get("data") or {}).get("result") or []
        if not isinstance(results, list):
            continue
        for result in results:
            values = result.get("values", []) if isinstance(result, dict) else []
            for sample in values if isinstance(values, list) else []:
                if not isinstance(sample, list) or len(sample) < 2:
                    continue
                timestamp = _number(sample[0])
                value = _number(sample[1])
                if timestamp is not None and value is not None:
                    samples[timestamp] = value
    if not samples:
        return None
    ordered = sorted(samples.items())
    values = [value for _, value in ordered]
    return {
        "average": round(fmean(values), 2),
        "maximum": max(values),
        "latest": values[-1],
        "sample_count": len(values),
        "start_time": ordered[0][0],
        "end_time": ordered[-1][0],
    }


def summarize_access_policies(
    policies: list[dict[str, Any]],
    rules_by_policy: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Build an operational review summary without changing FMC configuration."""
    totals = {
        "total_policies": len(policies),
        "total_rules": 0,
        "enabled_rules": 0,
        "disabled_rules": 0,
        "allow_rules": 0,
        "block_rules": 0,
        "rules_without_logging": 0,
        "allow_rules_without_ips_policy": 0,
        "rules_with_any_source": 0,
        "rules_with_any_destination": 0,
        "rules_with_any_destination_port": 0,
    }
    policy_summaries: list[dict[str, Any]] = []
    for policy in policies:
        policy_id = str(policy.get("id") or "")
        rules = rules_by_policy.get(policy_id, [])
        summary = {key: 0 for key in totals if key not in {"total_policies"}}
        summary.update(
            {
                "policy_id": policy_id or None,
                "name": policy.get("name"),
                "total_rules": len(rules),
            }
        )
        for rule in rules:
            enabled = rule.get("enabled") is not False
            action = str(rule.get("action") or "UNKNOWN").upper()
            summary["enabled_rules" if enabled else "disabled_rules"] += 1
            if action in {"ALLOW", "TRUST", "MONITOR"}:
                summary["allow_rules"] += 1
            if action in {"BLOCK", "BLOCK_RESET", "BLOCK_INTERACTIVE"}:
                summary["block_rules"] += 1
            if enabled and not rule.get("logBegin") and not rule.get("logEnd"):
                summary["rules_without_logging"] += 1
            if (
                enabled
                and action == "ALLOW"
                and not (rule.get("ipsPolicy") or rule.get("intrusionPolicy"))
            ):
                summary["allow_rules_without_ips_policy"] += 1
            if enabled and _is_any(rule.get("sourceNetworks")):
                summary["rules_with_any_source"] += 1
            if enabled and _is_any(rule.get("destinationNetworks")):
                summary["rules_with_any_destination"] += 1
            if enabled and _is_any(rule.get("destinationPorts")):
                summary["rules_with_any_destination_port"] += 1
        for key in totals:
            if key != "total_policies":
                totals[key] += int(summary.get(key, 0))
        policy_summaries.append(summary)
    return {**totals, "policies": policy_summaries}


def _is_any(value: Any) -> bool:
    if not isinstance(value, dict) or not value:
        return True
    return not any(value.get(key) for key in ("objects", "literals"))


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
        return parsed if isfinite(parsed) else None
    except (TypeError, ValueError):
        return None
