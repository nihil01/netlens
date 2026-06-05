from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class IntegrationStatus(BaseModel):
    status: Literal["ok", "not_configured", "error"]
    message: str | None = None

class NetBoxInterface(BaseModel):
    id: int
    name: str
    type: str | None = None
    enabled: bool | None = None
    mac_address: str | None = None
    description: str | None = None
    mode: str | None = None
    mtu: int | None = None
    speed: int | None = None
    duplex: str | None = None
    untagged_vlan: str | None = None


class NetBoxDevice(BaseModel):
    id: int
    name: str | None = None
    display: str | None = None
    status: str | None = None
    role: str | None = None
    device_type: str | None = None
    interfaces: list[NetBoxInterface] = Field(default_factory=list)


class NetBoxSite(BaseModel):
    id: int
    name: str
    slug: str
    devices: list[NetBoxDevice] = Field(default_factory=list)


class NetBoxRegion(BaseModel):
    id: int
    name: str
    slug: str
    sites: list[NetBoxSite] = Field(default_factory=list)


class NetBoxRegionsResponse(BaseModel):
    regions: list[NetBoxRegion]

class NetBoxContext(BaseModel):
    known: bool
    device: str | None = None
    site: str | None = None
    region: str | None = None
    city: str | None = None
    role: str | None = None
    interfaces: list[dict[str, Any]] = Field(default_factory=list)
    status: IntegrationStatus = Field(default_factory=lambda: IntegrationStatus(status="ok"))


class ScanContext(BaseModel):
    last_seen: datetime | None = None
    status: str = "unknown"
    open_ports: list[int] = Field(default_factory=list)
    os_guess: str | None = None
    accuracy: int | None = None


class ActivityCounterparty(BaseModel):
    ip: str
    port: int | None = None
    service: str | None = None
    count: int


class ActivitySummary(BaseModel):
    window: str
    internal_connections: int = 0
    external_connections: int = 0
    security_events: int = 0
    top_internal_destinations: list[ActivityCounterparty] = Field(default_factory=list)
    top_external_destinations: list[ActivityCounterparty] = Field(default_factory=list)
    status: IntegrationStatus = Field(default_factory=lambda: IntegrationStatus(status="ok"))


class IpSummary(BaseModel):
    ip: str
    netbox: NetBoxContext
    scan: ScanContext
    activity: ActivitySummary
