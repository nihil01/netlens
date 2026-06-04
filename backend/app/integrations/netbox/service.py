from app.core.config import get_settings
from app.ip_intelligence.schemas import NetBoxContext


class NetBoxService:
    def __init__(self, mode: str, url: str | None = None, token: str | None = None) -> None:
        self.mode = mode
        self.url = url
        self.token = token

    @classmethod
    def from_settings(cls) -> "NetBoxService":
        settings = get_settings()
        return cls(
            mode=settings.netbox_mode,
            url=str(settings.netbox_url) if settings.netbox_url else None,
            token=settings.netbox_token,
        )

    async def lookup_ip(self, ip: str) -> NetBoxContext:
        if self.mode == "mock":
            last_octet = int(ip.split(".")[-1]) if "." in ip else 0
            known = last_octet % 2 == 0
            return NetBoxContext(
                known=known,
                device=f"mock-device-{ip.replace('.', '-')}" if known else None,
                site="Baku HQ" if known else None,
                region="Baku" if known else None,
                city="Baku" if known else None,
                role="switch" if known else None,
                interfaces=[{"name": "mgmt0", "mac_address": "00:11:22:33:44:55"}] if known else [],
            )

        # Real NetBox mapping will be implemented after confirming object/custom-field structure.
        # Keep this read-only by default; writes need explicit approval workflow.
        return NetBoxContext(known=False)
