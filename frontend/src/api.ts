export type IntegrationStatus = {
  status: 'ok' | 'not_configured' | 'error';
  message: string | null;
};

export type NetBoxContext = {
  known: boolean;
  arp_mac_address: string | null;
  device: string | null;
  site: string | null;
  region: string | null;
  city: string | null;
  role: string | null;
  interfaces: Array<Record<string, unknown>>;
  status: IntegrationStatus;
};

export type ScanContext = {
  last_seen: string | null;
  status: string;
  open_ports: number[];
  os_guess: string | null;
  accuracy: number | null;
};

export type ActivityCounterparty = {
  ip: string;
  port: number | null;
  service: string | null;
  count: number;
};

export type ActivitySummary = {
  window: string;
  internal_connections: number;
  external_connections: number;
  security_events: number;
  top_internal_destinations: ActivityCounterparty[];
  top_external_destinations: ActivityCounterparty[];
  status: IntegrationStatus;
};

export type IpSummary = {
  ip: string;
  netbox: NetBoxContext;
  scan: ScanContext;
  activity: ActivitySummary;
};

export type NetBoxRegion = {
  id: number;
  name: string;
  slug: string | null;
  description: string | null;
};

export type NetBoxSite = {
  id: number;
  name: string;
  slug: string | null;
  region: string | null;
  status: string | null;
  facility: string | null;
  physical_address: string | null;
};

export type NetBoxDevice = {
  id: number;
  name: string;
  site: string | null;
  region: string | null;
  role: string | null;
  device_type: string | null;
  manufacturer: string | null;
  status: string | null;
  primary_ip: string | null;
};

export type NetBoxInterface = {
  id: number;
  name: string;
  device_id: number | null;
  device: string | null;
  type: string | null;
  enabled: boolean | null;
  mac_address: string | null;
  mac_vendor: string | null;
  mac_oui: string | null;
  mac_vendor_source: string | null;
  description: string | null;
  mode: string | null;
  untagged_vlan: string | null;
  learned_mac_addresses: NetBoxMacAddress[];
};

export type NetBoxMacAddress = {
  mac_address: string;
  mac_vendor: string | null;
  mac_oui: string | null;
  mac_vendor_source: string | null;
  description: string | null;
  vlan: string | null;
  type: string | null;
};

export type NetBoxInventory = {
  regions: NetBoxRegion[];
  sites: NetBoxSite[];
  devices: NetBoxDevice[];
  interfaces: NetBoxInterface[];
  oui_dataset: {
    source?: string;
    source_url?: string;
    created_at?: string | null;
    records?: number;
    cache?: string;
  };
  status: IntegrationStatus;
};

export type NetBoxDeviceDetail = NetBoxDevice & {
  location: string | null;
  platform: string | null;
  serial: string | null;
  asset_tag: string | null;
  comments: string | null;
  interfaces: NetBoxInterface[];
  cache: Record<string, unknown>;
  status_meta: IntegrationStatus;
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:5000/api';

async function apiGet<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`);
  } catch {
    throw new Error('API qoşulma xətası');
  }
  if (!response.ok) {
    throw new Error(`API cavabı: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function fetchIpSummary(ip: string): Promise<IpSummary> {
  return apiGet<IpSummary>(`/ip/${encodeURIComponent(ip)}/summary`);
}

export function fetchNetBoxInventory(): Promise<NetBoxInventory> {
  return apiGet<NetBoxInventory>('/netbox/inventory');
}

export function fetchNetBoxDeviceDetail(deviceId: number): Promise<NetBoxDeviceDetail> {
  return apiGet<NetBoxDeviceDetail>(`/netbox/devices/${deviceId}/detail`);
}
