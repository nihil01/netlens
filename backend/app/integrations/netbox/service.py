import asyncio
from collections import defaultdict

import pynetbox
from fastapi import HTTPException

from app.core.config import Settings


class NetBoxService:
    def __init__(self) -> None:
        self.settings = Settings()
        self.netbox = None

    def _is_configured(self) -> bool:
        return bool(self.settings.netbox_url and self.settings.netbox_token)

    def _connect(self):
        if self.netbox is None:
            self.netbox = pynetbox.api(
                str(self.settings.netbox_url).rstrip("/"),
                token=self.settings.netbox_token,
            )
            self.netbox.http_session.verify = self.settings.netbox_verify_ssl

        return self.netbox

    async def fetch_all(self):
        if not self._is_configured():
            raise HTTPException(
                status_code=503,
                detail="NETBOX_URL and NETBOX_TOKEN are required",
            )

        try:
            return await asyncio.to_thread(self._load_data)

        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"NetBox mapping error: {exc}",
            )

    def _load_data(self):
        netbox = self._connect()

        regions = list(netbox.dcim.regions.all())
        sites = list(netbox.dcim.sites.all())
        devices = list(netbox.dcim.devices.all())
        interfaces = list(netbox.dcim.interfaces.all())

        sites_by_region = defaultdict(list)
        devices_by_site = defaultdict(list)
        interfaces_by_device = defaultdict(list)

        for interface in interfaces:
            if not interface.device:
                continue

            interfaces_by_device[interface.device.id].append({
                "id": interface.id,
                "name": interface.name,
                "type": self._label(interface.type),
                "enabled": interface.enabled,
                "mac_address": interface.mac_address,
                "description": interface.description,
                "mode": self._label(interface.mode),
                "mtu": interface.mtu,
                "speed": interface.speed,
                "duplex": self._label(interface.duplex),
                "untagged_vlan": self._name(interface.untagged_vlan),
            })

        for device in devices:
            if not device.site:
                continue

            devices_by_site[device.site.id].append({
                "id": device.id,
                "name": device.name,
                "display": getattr(device, "display", None),
                "status": self._label(device.status),
                "role": self._name(device.role),
                "device_type": self._device_type(device),
                "interfaces": interfaces_by_device[device.id],
            })

        for site in sites:
            if not site.region:
                continue

            sites_by_region[site.region.id].append({
                "id": site.id,
                "name": site.name,
                "slug": site.slug,
                "devices": devices_by_site[site.id],
            })

        return {
            "regions": [
                {
                    "id": region.id,
                    "name": region.name,
                    "slug": region.slug,
                    "sites": sites_by_region[region.id],
                }
                for region in regions
            ]
        }

    @staticmethod
    def _label(value):
        if not value:
            return None
        return getattr(value, "label", None) or getattr(value, "value", None) or str(value)

    @staticmethod
    def _name(value):
        if not value:
            return None
        return getattr(value, "name", None) or str(value)

    @staticmethod
    def _device_type(device):
        if not device.device_type:
            return None
        return getattr(device.device_type, "model", None) or getattr(device.device_type, "display", None)