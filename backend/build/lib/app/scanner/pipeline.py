import asyncio
import datetime
import ipaddress
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from icmplib import async_multiping
from scrapli.driver.core import AsyncIOSXEDriver

from app.integrations.netbox.service import NetBoxService
from app.scanner.arp_cache import update_arp_entries

COMMON_PORTS = {
    21: "FTP",
    22: "SSH",
    23: "Telnet",
    80: "HTTP",
    161: "SNMP",
    443: "HTTPS",
    445: "SMB",
    3389: "RDP",
}


def build_netbox_client(
    netbox_url: str | None,
    netbox_token: str | None,
    verify_ssl: bool,
):
    if not netbox_url or not netbox_token:
        return None

    try:
        import pynetbox
    except ImportError:
        return None

    nb = pynetbox.api(netbox_url, token=netbox_token)
    nb.http_session.verify = verify_ssl
    return nb


class NmapProfiler:
    @staticmethod
    async def fingerprint_os(ip: str) -> dict[str, Any]:
        result = {
            "ip": ip,
            "os_guess": "Unknown",
            "accuracy": 0,
            "success": False,
        }

        try:
            cmd = [
                "nmap",
                "-O",
                "-T4",
                "-Pn",
                "--osscan-limit",
                "--max-os-tries",
                "1",
                "-oX",
                "-",
                ip,
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, _ = await process.communicate()

            if process.returncode == 0 and stdout:
                root = ET.fromstring(stdout)
                osmatch = root.find(".//osmatch")

                if osmatch is not None:
                    result["os_guess"] = osmatch.get("name", "Unknown")
                    result["accuracy"] = int(osmatch.get("accuracy", 0))
                    result["success"] = True
                else:
                    result["os_guess"] = "Unknown (No match found)"

        except Exception as exc:
            result["os_guess"] = f"Error: {exc}"

        return result



class AdvancedProfilingEngine:
    def __init__(
        self,
        dataset_path: str,
        netbox_client=None,
        credentials: list[dict[str, str]] | None = None,
        common_ports: dict[int, str] | None = None,
        ping_concurrency: int = 200,
        port_concurrency: int = 200,
        ssh_concurrency: int = 20,
        nmap_concurrency: int = 15,
        output_dir: str = "scanner_output",
    ):
        self.dataset_path = dataset_path
        self.networks = self._load_networks()
        self.netbox = netbox_client or NetBoxService.build_netbox_client()
        self.credentials = credentials or []
        self.common_ports = common_ports or COMMON_PORTS

        self.ping_concurrency = ping_concurrency
        self.port_concurrency = port_concurrency
        self.ssh_concurrency = ssh_concurrency
        self.nmap_concurrency = nmap_concurrency

        self.port_semaphore = asyncio.Semaphore(port_concurrency)
        self.netbox_ip_cache: dict[str, Any] = {}
        self.arp_table_cache: dict[str, dict[str, Any]] = {}

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _load_networks(self) -> list[dict[str, Any]]:
        try:
            with open(self.dataset_path, encoding="utf-8") as file:
                return json.load(file)
        except Exception:
            return []

    async def build_netbox_cache(self) -> None:

        if not self.netbox:
            self.netbox_ip_cache = {}
            return

        print("=" * 80)
        print("[NETBOX CACHE] START")
        print(f"[NETBOX CACHE] client={self.netbox}")
        print(
            f"[NETBOX CACHE] verify="
            f"{getattr(getattr(self.netbox, 'http_session', None), 'verify', 'UNKNOWN')}"
        )

        def _fetch() -> dict[str, Any]:
            cache = {}

            for ip_obj in self.netbox.ipam.ip_addresses.all():
                ip_str = str(ip_obj.address).split("/")[0]
                print(f"[NETBOX CACHE] {ip_obj.address}")

                if ip_obj.assigned_object and hasattr(ip_obj.assigned_object, "device"):
                    cache[ip_str] = {
                        "device_id": ip_obj.assigned_object.device.id,
                        "name": ip_obj.assigned_object.device.name,
                        "status": "device",
                    }
                elif ip_obj.assigned_object and hasattr(ip_obj.assigned_object, "virtual_machine"):
                    cache[ip_str] = {
                        "device_id": ip_obj.assigned_object.virtual_machine.id,
                        "name": ip_obj.assigned_object.virtual_machine.name,
                        "status": "virtual_machine",
                    }
                else:
                    cache[ip_str] = {
                        "device_id": None,
                        "name": "Standalone_IP",
                        "status": "unassigned",
                    }

            return cache

        self.netbox_ip_cache = await asyncio.to_thread(_fetch)

    def is_ip_in_netbox(self, ip: str) -> tuple[bool, str | None]:
        data = self.netbox_ip_cache.get(ip)

        if data and not data["name"].startswith("New_device_"):
            return False, data["name"]

        return True, None

    async def check_ports_only(self, ip: str, metadata: dict[str, Any]) -> dict[str, Any]:
        async with self.port_semaphore:
            open_ports = []

            async def _check_port(port: int) -> None:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(ip, port),
                        timeout=1.0,
                    )
                    open_ports.append(port)
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass

            await asyncio.gather(*[_check_port(port) for port in self.common_ports.keys()])

            return {
                "ip": ip,
                "status": "up",
                "ports": open_ports,
                "category": metadata.get("category", "unknown"),
                "site_id": metadata.get("site_id", 71),
            }

    async def create_in_netbox(self, device_data: dict[str, Any]) -> None:
        if not self.netbox:
            return

        def _create() -> None:
            device_name = f"New_device_{device_data['ip']}"

            existing_dev = self.netbox.dcim.devices.get(
                name=device_name,
                site_id=device_data["site_id"],
            )

            if existing_dev:
                return

            device = self.netbox.dcim.devices.create(
                name=device_name,
                device_type=34,
                role=8,
                site=device_data["site_id"],
                status="active",
                custom_fields={"environment": "Prod"},
            )

            iface = self.netbox.dcim.interfaces.create(
                device=device.id,
                name="mgmt0",
                type="1000base-t",
            )

            ip_addr = self.netbox.ipam.ip_addresses.create(
                address=f"{device_data['ip']}/32",
            )

            self.netbox.ipam.ip_addresses.update(
                [
                    {
                        "id": ip_addr.id,
                        "assigned_object_type": "dcim.interface",
                        "assigned_object_id": iface.id,
                    }
                ]
            )

        await asyncio.to_thread(_create)

    async def fetch_device_data(self, ip: str) -> dict[str, Any]:
        for cred in self.credentials:

            for transport_type in ["asyncssh", "asynctelnet"]:

                print(
                    f"[SSH] "
                    f"{ip} "
                    f"cred={cred['login']} "
                    f"transport={transport_type}"
                )


                try:
                    async with AsyncIOSXEDriver(
                        host=ip,
                        auth_username=cred["login"],
                        auth_password=cred["password"],
                        auth_strict_key=False,
                        transport=transport_type,
                        ssh_config_file=True,
                        timeout_socket=5,
                        timeout_transport=5,
                    ) as conn:

                        version_result = await conn.send_command("show version")
                        interfaces_result = await conn.send_command("show interfaces")
                        arp_result = await conn.send_command("show ip arp")
                        mac_result = await conn.send_command("show mac address-table")

                        parsed_ver = version_result.textfsm_parse_output()
                        parsed_intf = interfaces_result.textfsm_parse_output()
                        parsed_arp = arp_result.textfsm_parse_output()

                        try:
                            parsed_mac = mac_result.textfsm_parse_output()
                        except Exception:
                            parsed_mac = mac_result.result

                        v_data = (
                            parsed_ver[0]
                            if isinstance(parsed_ver, list) and parsed_ver
                            else {}
                        )

                        hostname = v_data.get("hostname", ip)
                        os_version = v_data.get("version", "Unknown")

                        model = v_data.get("hardware", ["Unknown"])
                        model = model[0] if isinstance(model, list) else model

                        serial = v_data.get("serial", ["Unknown"])
                        serial = serial[0] if isinstance(serial, list) else serial

                        interfaces_data = {}

                        if isinstance(parsed_intf, list):
                            for intf in parsed_intf:
                                intf_name = intf.get("interface")

                                if intf_name:
                                    interfaces_data[intf_name] = {
                                        "mac_address": intf.get("mac_address", ""),
                                        "link_status": intf.get("link_status", ""),
                                        "protocol_status": intf.get("protocol_status", ""),
                                        "ip_address": intf.get("ip_address", ""),
                                        "description": intf.get("description", ""),
                                    }

                        print(
                            f"[SSH] "
                            f"{ip} "
                            f"interfaces={len(interfaces_data)} "
                            f"arp={len(parsed_arp) if isinstance(parsed_arp, list) else 0} "
                            f"macs={len(parsed_mac) if isinstance(parsed_mac, list) else 0}"
                        )

                        return {
                            "success": True,
                            "device_info": {
                                "mgmt_ip": ip,
                                "hostname": hostname,
                                "version": os_version,
                                "model": model,
                                "serial": serial,
                            },
                            "interfaces": interfaces_data,
                            "arp_table": parsed_arp if isinstance(parsed_arp, list) else [],
                            "mac_table": parsed_mac if isinstance(parsed_mac, list) else [],
                        }


                except Exception as exc:

                    print(

                        f"[SSH] FAILED "

                        f"{ip} "

                        f"cred={cred['login']} "

                        f"transport={transport_type} "

                        f"error={type(exc).__name__}: {exc}"

                    )

                    await asyncio.sleep(0.5)

                    continue

        return {"success": False}


class PipelineOrchestrator:
    def __init__(self, engine: AdvancedProfilingEngine):
        self.engine = engine
        self.local_snapshot: dict[str, Any] = {}

    def _get_or_create_mac_on_interface(
            self,
            nb,
            mac_address: str,
            interface_id: int,
            description: str,
    ):
        existing_macs = list(nb.dcim.mac_addresses.filter(mac_address=mac_address))

        for mac_obj in existing_macs:
            assigned_object = getattr(mac_obj, "assigned_object", None)

            if assigned_object and getattr(assigned_object, "id", None) == interface_id:
                updates = {}

                if getattr(mac_obj, "description", "") != description:
                    updates["description"] = description

                if updates:
                    try:
                        mac_obj.update(updates)
                    except Exception:
                        pass

                return mac_obj

        try:
            return nb.dcim.mac_addresses.create(
                {
                    "mac_address": mac_address,
                    "assigned_object_type": "dcim.interface",
                    "assigned_object_id": interface_id,
                    "description": description,
                }
            )
        except Exception:
            return None

    def _normalize_mac(self, raw_mac: str | None) -> str | None:
        if not raw_mac:
            return None

        clean = re.sub(r"[^0-9a-fA-F]", "", str(raw_mac)).upper()

        if len(clean) != 12:
            return None

        return ":".join(clean[i: i + 2] for i in range(0, 12, 2))

    def _normalize_interface_name(self, name: str | None) -> str | None:
        if not name:
            return None

        value = str(name).strip()

        replacements = {
            "Gi": "GigabitEthernet",
            "Gig": "GigabitEthernet",
            "Fa": "FastEthernet",
            "Te": "TenGigabitEthernet",
            "Ten": "TenGigabitEthernet",
            "Tw": "TwentyFiveGigE",
            "Fo": "FortyGigabitEthernet",
            "Po": "Port-channel",
            "Vl": "Vlan",
        }

        for short, full in replacements.items():
            if value.startswith(short) and not value.startswith(full):
                return value.replace(short, full, 1)

        return value

    def _extract_learned_macs_by_interface(
            self,
            mac_table: Any,
    ) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}

        if not isinstance(mac_table, list):
            return result

        ignored_ports = {
            "CPU",
            "Router",
            "Switch",
            "Drop",
            "Null",
        }

        for row in mac_table:
            if not isinstance(row, dict):
                continue

            raw_mac = (
                    row.get("destination_address")
                    or row.get("mac_address")
                    or row.get("mac")
                    or row.get("address")
            )

            raw_interface = (
                    row.get("destination_port")
                    or row.get("port")
                    or row.get("ports")
                    or row.get("interface")
            )

            if isinstance(raw_interface, list):
                raw_interface = raw_interface[0] if raw_interface else None

            mac_address = self._normalize_mac(raw_mac)
            interface_name = self._normalize_interface_name(raw_interface)

            if not mac_address or not interface_name:
                continue

            if interface_name in ignored_ports:
                continue

            result.setdefault(interface_name, []).append(
                {
                    "mac_address": mac_address,
                    "vlan": row.get("vlan"),
                    "type": row.get("type"),
                    "raw": row,
                }
            )

        return result


    def _extract_arp_ip_mac(
        self,
        arp_table: Any,
        *,
        source: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        entries: dict[str, dict[str, Any]] = {}
        if not isinstance(arp_table, list):
            return entries

        for row in arp_table:
            if not isinstance(row, dict):
                continue
            ip = str(row.get("address") or row.get("ip") or row.get("ip_address") or "").strip()
            mac = self._normalize_mac(
                row.get("mac")
                or row.get("mac_address")
                or row.get("hardware_addr")
                or row.get("hw_address")
            )
            if not ip or not mac:
                continue
            entries[ip] = {
                "ip": ip,
                "mac_address": mac,
                "interface": row.get("interface") or row.get("port"),
                "age": row.get("age"),
                "source": source,
                "raw": row,
            }

        return entries

    def _refresh_arp_cache(self, enriched_data: dict[str, Any]) -> None:
        merged: dict[str, dict[str, Any]] = {}
        for switch_ip, data in enriched_data.items():
            if not isinstance(data, dict) or not data.get("success"):
                continue
            entries = self._extract_arp_ip_mac(data.get("arp_table", []), source=switch_ip)
            merged.update(entries)
            update_arp_entries(list(entries.values()), source=switch_ip)
        self.engine.arp_table_cache = merged

    async def run_pipeline(self) -> list[dict[str, Any]]:
        print("=" * 80)
        print("[PIPELINE] START")

        await self.engine.build_netbox_cache()

        print(
            f"[PIPELINE] netbox cache size="
            f"{len(self.engine.netbox_ip_cache)}"
        )

        discovery_results = await self.phase1_discovery()

        print(
            f"[PIPELINE] discovery results="
            f"{len(discovery_results)}"
        )

        enriched_data = await self.phase2_enrichment()
        self._refresh_arp_cache(enriched_data)

        print(
            f"[PIPELINE] enriched devices="
            f"{len(enriched_data)} arp_entries={len(self.engine.arp_table_cache)}"
        )

        self.local_snapshot = await self.phase3_save_in_netbox(enriched_data)

        snapshot_filename = self.engine.output_dir / (
            f"snapshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.json"
        )

        with open(snapshot_filename, "w", encoding="utf-8") as file:
            json.dump(self.local_snapshot, file, ensure_ascii=False, indent=4)

        final_profiles = await self.phase4_fingerprinting(discovery_results)

        profiles_filename = self.engine.output_dir / "profiles.json"

        with open(profiles_filename, "w", encoding="utf-8") as file:
            json.dump(final_profiles, file, ensure_ascii=False, indent=4)

        return final_profiles

    async def phase1_discovery(self) -> list[dict[str, Any]]:

        print("=" * 80)
        print("[DISCOVERY] START")

        print(f"[DISCOVERY] loaded networks={len(self.engine.networks)}")

        all_ips_to_ping = []
        ip_metadata = {}

        for net_entry in self.engine.networks:
            print(f"[DISCOVERY] network entry={net_entry}")
            site_id = net_entry.get("id", 71)

            for category in ["voice", "management", "data", "server"]:
                subnet_str = net_entry.get(category)

                if not subnet_str:
                    continue

                try:
                    network = ipaddress.ip_network(subnet_str, strict=False)
                    hosts = [str(host) for host in network.hosts()]
                    all_ips_to_ping.extend(hosts)

                    for host in hosts:
                        ip_metadata[host] = {
                            "category": category,
                            "site_id": site_id,
                        }

                except ValueError:
                    continue

        if not all_ips_to_ping:
            return []

        print(
            f"[DISCOVERY] total ips to ping="
            f"{len(all_ips_to_ping)}"
        )

        try:
            hosts = await async_multiping(
                all_ips_to_ping,
                count=2,
                timeout=1.5,
                concurrent_tasks=self.engine.ping_concurrency,
                privileged=False,
            )

            alive_ips = [host.address for host in hosts if host.is_alive]

            print(
                f"[DISCOVERY] alive hosts="
                f"{len(alive_ips)}"
            )

            print(alive_ips[:20])

        except Exception:
            return []

        port_tasks = [
            self.engine.check_ports_only(ip, ip_metadata[ip])
            for ip in alive_ips
        ]

        discovery_results = await asyncio.gather(*port_tasks)

        for host in discovery_results:
            is_new, existing_name = self.engine.is_ip_in_netbox(host["ip"])

            host["is_new"] = is_new
            host["hostname"] = existing_name or f"New_device_{host['ip']}"

            if is_new:
                await self.engine.create_in_netbox(host)

        return discovery_results

    async def phase2_enrichment(self) -> dict[str, Any]:
        enrichment_results = {}

        if not self.engine.netbox:
            return enrichment_results

        devices = await asyncio.to_thread(
            lambda: list(self.engine.netbox.dcim.devices.filter(cf_environment="Prod"))
        )

        ssh_semaphore = asyncio.Semaphore(self.engine.ssh_concurrency)

        async def _process_device(dev) -> None:
            if not getattr(dev, "primary_ip4", None):
                return

            print(
                f"[ENRICHMENT] trying device "
                f"{dev.name} "
            )

            ip_str = str(dev.primary_ip4.address).split("/")[0]

            async with ssh_semaphore:
                try:
                    real_data = await asyncio.wait_for(
                        self.engine.fetch_device_data(ip_str),
                        timeout=30.0,
                    )

                    enrichment_results[ip_str] = real_data
                    print(
                        f"[ENRICHMENT] SUCCESS "
                        f"{ip_str}"
                    )

                    print(real_data["device_info"])

                except Exception:
                    enrichment_results[ip_str] = {"success": False}

        await asyncio.gather(*[_process_device(device) for device in devices])

        print("=" * 80)
        print("[ENRICHMENT] START")

        print(
            f"[ENRICHMENT] netbox devices="
            f"{len(devices)}"
        )

        return enrichment_results


    def _delete_mac_address(self, mac_obj: Any) -> None:
        try:
            mac_obj.delete()
        except Exception:
            try:
                self.engine.netbox.dcim.mac_addresses.delete([mac_obj.id])
            except Exception:
                pass

    def _clear_device_mac_addresses(self, nb: Any, device_id: int) -> None:
        interface_ids = {
            getattr(interface, "id", None)
            for interface in nb.dcim.interfaces.filter(device_id=device_id)
        }
        interface_ids.discard(None)
        if not interface_ids:
            return

        try:
            mac_addresses = list(nb.dcim.mac_addresses.all())
        except Exception:
            return

        deleted = 0
        for mac_obj in mac_addresses:
            assigned_object = getattr(mac_obj, "assigned_object", None)
            if getattr(assigned_object, "id", None) in interface_ids:
                self._delete_mac_address(mac_obj)
                deleted += 1

        print(f"[NETBOX SYNC] cleared_mac_addresses={deleted}")

    async def phase3_save_in_netbox(self, enriched_data: dict[str, Any]) -> dict[str, Any]:

        print("=" * 80)
        print(f"Enriched data: {enriched_data}")

        def _sync_single_device(ip: str, data: dict[str, Any]) -> None:
            if not data.get("success"):
                return

            nb = self.engine.netbox

            dev_info = data.get("device_info", {})
            hostname = dev_info.get("hostname", ip)
            serial = dev_info.get("serial", "")
            model = dev_info.get("model", "")
            version = dev_info.get("version", "")
            interfaces_data = data.get("interfaces", {})
            mac_table = data.get("mac_table", [])

            print("=" * 80)
            print(f"[NETBOX SYNC] device={hostname}")
            print(f"[NETBOX SYNC] ip={ip}")

            print(
                f"[NETBOX SYNC] interfaces="
                f"{len(interfaces_data)}"
            )

            print(
                f"[NETBOX SYNC] mac_table="
                f"{len(mac_table)}"
            )

            learned_macs_by_interface = self._extract_learned_macs_by_interface(mac_table)

            print(
                "[NETBOX SYNC] learned_macs_by_interface="
            )

            for k, v in learned_macs_by_interface.items():
                print(f"    {k}: {len(v)} MACs")

            device = None

            try:
                ip_obj = nb.ipam.ip_addresses.get(address=f"{ip}/32")

                if ip_obj and ip_obj.assigned_object and hasattr(ip_obj.assigned_object, "device"):
                    device = ip_obj.assigned_object.device
            except Exception:
                pass

            if not device:
                device = nb.dcim.devices.get(name=hostname) or nb.dcim.devices.get(
                    name=f"New_device_{ip}"
                )

            if not device:
                return

            platform_id = None

            if version and version != "Unknown":
                platform_name = f"IOS-{version}"
                platform_slug = (
                    platform_name.lower()
                    .replace(".", "-")
                    .replace("(", "-")
                    .replace(")", "-")
                )

                try:
                    platform = nb.dcim.platforms.get(name=platform_name)

                    if platform:
                        platform_id = platform.id
                    else:
                        platform = nb.dcim.platforms.create(
                            name=platform_name,
                            slug=platform_slug,
                        )
                        platform_id = platform.id

                except Exception:
                    pass

            dev_updates = {}

            if device.name == f"New_device_{ip}" or device.name == ip:
                dev_updates["name"] = hostname

            if serial and serial != "Unknown" and device.serial != serial:
                dev_updates["serial"] = serial

            if platform_id:
                if not device.platform or device.platform.id != platform_id:
                    dev_updates["platform"] = platform_id

            try:
                if model and model != "Unknown":
                    device_type = nb.dcim.device_types.get(model=model)

                    if device_type and (
                        not device.device_type or device.device_type.id != device_type.id
                    ):
                        dev_updates["device_type"] = device_type.id
            except Exception:
                pass

            if dev_updates:
                try:
                    device.update(dev_updates)
                except Exception:
                    pass

            self._clear_device_mac_addresses(nb, device.id)

            existing_interfaces = {
                intf.name: intf
                for intf in nb.dcim.interfaces.filter(device_id=device.id)
            }

            for intf_name, intf_details in interfaces_data.items():
                mac_raw = intf_details.get("mac_address")
                desc = intf_details.get("description", "")
                is_active = intf_details.get("link_status", "down").lower() == "up"

                formatted_mac = None

                if mac_raw and len(mac_raw) == 14 and "." in mac_raw:
                    clean_mac = mac_raw.replace(".", "").upper()
                    formatted_mac = ":".join(
                        clean_mac[i : i + 2]
                        for i in range(0, 12, 2)
                    )

                intf_type = "other"

                if "FastEthernet" in intf_name:
                    intf_type = "100base-tx"
                elif "GigabitEthernet" in intf_name:
                    intf_type = "1000base-t"
                elif "TenGigabit" in intf_name:
                    intf_type = "10gbase-x-sfpp"
                elif "Vlan" in intf_name:
                    intf_type = "virtual"

                if intf_name in existing_interfaces:
                    nb_intf = existing_interfaces[intf_name]
                    intf_updates = {}

                    if formatted_mac and nb_intf.mac_address != formatted_mac:
                        intf_updates["mac_address"] = formatted_mac

                    if desc and nb_intf.description != desc:
                        intf_updates["description"] = desc

                    if nb_intf.enabled != is_active:
                        intf_updates["enabled"] = is_active

                    if intf_updates:
                        try:
                            nb_intf.update(intf_updates)
                        except Exception:
                            pass
                else:
                    nb_intf = None
                    try:
                        nb_intf = nb.dcim.interfaces.create(
                            device=device.id,
                            name=intf_name,
                            type=intf_type,
                            mac_address=formatted_mac,
                            description=desc,
                            enabled=is_active,
                        )
                    except Exception:
                        pass

                if not nb_intf:
                    continue

                # 1. MAC самого интерфейса
                if formatted_mac:
                    own_mac = self._get_or_create_mac_on_interface(
                        nb=nb,
                        mac_address=formatted_mac,
                        interface_id=nb_intf.id,
                        description=f"Interface own MAC | {device.name} | {intf_name}",
                    )

                    if own_mac:
                        try:
                            nb_intf.update(
                                {
                                    "primary_mac_address": own_mac.id,
                                }
                            )
                        except Exception:
                            pass

                # 2. MAC-адреса устройств, изученные на этом интерфейсе
                learned_macs = learned_macs_by_interface.get(intf_name, [])

                for learned in learned_macs:
                    learned_mac = learned["mac_address"]

                    # Если MAC из таблицы совпал с MAC самого интерфейса — не дублируем.
                    if formatted_mac and learned_mac == formatted_mac:
                        continue

                    vlan = learned.get("vlan")
                    learned_type = learned.get("type")

                    description_parts = [
                        "Learned MAC",
                        f"switch={device.name}",
                        f"interface={intf_name}",
                    ]

                    if vlan:
                        description_parts.append(f"vlan={vlan}")

                    if learned_type:
                        description_parts.append(f"type={learned_type}")

                    description = " | ".join(description_parts)

                    self._get_or_create_mac_on_interface(
                        nb=nb,
                        mac_address=learned_mac,
                        interface_id=nb_intf.id,
                        description=description,
                    )

        tasks = [
            asyncio.to_thread(_sync_single_device, ip, data)
            for ip, data in enriched_data.items()
        ]

        if tasks:
            await asyncio.gather(*tasks)

        return enriched_data

    async def phase4_fingerprinting(
        self,
        data: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not data:
            return []

        nmap_semaphore = asyncio.Semaphore(self.engine.nmap_concurrency)

        async def _profile(host_dict: dict[str, Any]) -> dict[str, Any]:
            ip = host_dict.get("ip")

            async with nmap_semaphore:
                host_dict["fingerprinting"] = await NmapProfiler.fingerprint_os(ip)
                return host_dict

        return await asyncio.gather(*[_profile(host) for host in data])