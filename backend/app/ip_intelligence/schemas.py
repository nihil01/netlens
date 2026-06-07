from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


class IntegrationStatus(BaseModel):
    status: Literal["ok", "not_configured", "error"]
    message: str | None = None


class NetBoxMacAddress(BaseModel):
    mac_address: str
    mac_vendor: str | None = None
    mac_oui: str | None = None
    mac_vendor_source: str | None = None
    description: str | None = None
    vlan: str | None = None
    type: str | None = None


class NetBoxInterface(BaseModel):
    id: int
    name: str
    device_id: int | None = None
    device: str | None = None
    type: str | None = None
    enabled: bool | None = None
    mac_address: str | None = None
    mac_vendor: str | None = None
    mac_oui: str | None = None
    mac_vendor_source: str | None = None
    description: str | None = None
    mode: str | None = None
    mtu: int | None = None
    speed: int | None = None
    duplex: str | None = None
    untagged_vlan: str | None = None
    learned_mac_addresses: list[NetBoxMacAddress] = Field(default_factory=list)


class NetBoxDevice(BaseModel):
    id: int
    name: str | None = None
    display: str | None = None
    site: str | None = None
    region: str | None = None
    status: str | None = None
    role: str | None = None
    device_type: str | None = None
    manufacturer: str | None = None
    primary_ip: str | None = None
    interfaces: list[NetBoxInterface] = Field(default_factory=list)


class NetBoxSite(BaseModel):
    id: int
    name: str
    slug: str | None = None
    region: str | None = None
    status: str | None = None
    facility: str | None = None
    physical_address: str | None = None
    devices: list[NetBoxDevice] = Field(default_factory=list)


class NetBoxRegion(BaseModel):
    id: int
    name: str
    slug: str | None = None
    description: str | None = None
    sites: list[NetBoxSite] = Field(default_factory=list)


class NetBoxRegionsResponse(BaseModel):
    regions: list[NetBoxRegion] = Field(default_factory=list)


class NetBoxInventory(BaseModel):
    regions: list[NetBoxRegion] = Field(default_factory=list)
    sites: list[NetBoxSite] = Field(default_factory=list)
    devices: list[NetBoxDevice] = Field(default_factory=list)
    interfaces: list[NetBoxInterface] = Field(default_factory=list)
    oui_dataset: dict[str, Any] = Field(default_factory=dict)
    status: IntegrationStatus = Field(default_factory=lambda: IntegrationStatus(status="ok"))


class NetBoxDeviceDetail(BaseModel):
    id: int
    name: str
    site: str | None = None
    region: str | None = None
    location: str | None = None
    role: str | None = None
    device_type: str | None = None
    manufacturer: str | None = None
    platform: str | None = None
    status: str | None = None
    serial: str | None = None
    asset_tag: str | None = None
    primary_ip: str | None = None
    comments: str | None = None
    interfaces: list[NetBoxInterface] = Field(default_factory=list)
    cache: dict[str, Any] = Field(default_factory=dict)
    status_meta: IntegrationStatus = Field(default_factory=lambda: IntegrationStatus(status="ok"))


class NetBoxContext(BaseModel):
    known: bool
    arp_mac_address: str | None = None
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


class IpSummary(BaseModel):
    ip: str
    netbox: NetBoxContext
    scan: ScanContext
    activity: ActivitySummary


class UnifiedActivityEvent(BaseModel):
    source_name: str
    index: str
    timestamp: str | None = None

    source_ip: str | None = None
    source_port: int | None = None

    destination_ip: str | None = None
    destination_port: int | None = None

    protocol: str | None = None
    action: str | None = None
    application: str | None = None
    rule: str | None = None
    policy: str | None = None
    user: str | None = None
    domain: str | None = None
    url: str | None = None

    bytes: int | None = None
    packets: int | None = None

    direction: str | None = None
    is_source_ip: bool = False
    is_destination_ip: bool = False

    raw: dict[str, Any] = Field(default_factory=dict)


class ActivitySummary(BaseModel):
    window: str
    internal_connections: int = 0
    external_connections: int = 0
    security_events: int = 0
    top_internal_destinations: list[ActivityCounterparty] = Field(default_factory=list)
    top_external_destinations: list[ActivityCounterparty] = Field(default_factory=list)
    events: list[UnifiedActivityEvent] = Field(default_factory=list)
    status: IntegrationStatus = Field(default_factory=lambda: IntegrationStatus(status="ok"))