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

export type UnifiedActivityEvent = {
  source_name: string;
  index: string;
  timestamp: string | null;
  source_ip: string | null;
  source_port: number | null;
  destination_ip: string | null;
  destination_port: number | null;
  protocol: string | null;
  action: string | null;
  application: string | null;
  rule: string | null;
  policy: string | null;
  user: string | null;
  domain: string | null;
  url: string | null;
  bytes: number | null;
  packets: number | null;
  direction: string | null;
  is_source_ip: boolean;
  is_destination_ip: boolean;
  raw: Record<string, unknown>;
};

export type ActivitySummary = {
  window: string;
  internal_connections: number;
  external_connections: number;
  security_events: number;
  top_internal_destinations: ActivityCounterparty[];
  top_external_destinations: ActivityCounterparty[];
  top_internal_ports: ActivityCounterparty[];
  top_external_ports: ActivityCounterparty[];
  top_domains: ActivityCounterparty[];
  source_stats: Record<string, number>;
  index_stats: Record<string, number>;
  events: UnifiedActivityEvent[];
  user: string | null;
  users: string[];
  status: IntegrationStatus;
};

export type IpSummary = {
  ip: string;
  netbox: NetBoxContext;
  scan: ScanContext;
  activity: ActivitySummary;
};

export type IpSummaryFilters = {
  srcIp?: string;
  dstIp?: string;
  dstPort?: string;
  start?: string;
  end?: string;
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
  mtu: number | null;
  speed: number | null;
  duplex: string | null;
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

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api';

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

export function fetchIpSummary(ip: string, filters: IpSummaryFilters = {}): Promise<IpSummary> {
  const params = new URLSearchParams();
  if (filters.srcIp?.trim()) params.set('src_ip', filters.srcIp.trim());
  if (filters.dstIp?.trim()) params.set('dst_ip', filters.dstIp.trim());
  if (filters.dstPort?.trim() && /^\d+$/.test(filters.dstPort.trim())) params.set('dst_port', filters.dstPort.trim());
  const query = params.toString();
  return apiGet<IpSummary>(`/ip/${encodeURIComponent(ip)}/summary${query ? `?${query}` : ''}`);
}

export function fetchNetBoxInventory(): Promise<NetBoxInventory> {
  return apiGet<NetBoxInventory>('/netbox/inventory');
}

export function fetchNetBoxDeviceDetail(deviceId: number): Promise<NetBoxDeviceDetail> {
  return apiGet<NetBoxDeviceDetail>(`/netbox/devices/${deviceId}/detail`);
}

export type DomainActivityBucket = {
  key: { domain: string; application: string };
  doc_count: number;
  first_seen: { value: number; value_as_string: string | null };
  last_seen: { value: number; value_as_string: string | null };
};

export type DomainActivityResponse = {
  ip: string;
  total_buckets: number;
  buckets: DomainActivityBucket[];
};

export function fetchDomainActivity(ip: string, start?: string, end?: string): Promise<DomainActivityResponse> {
  const params = new URLSearchParams();
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  const query = params.toString();
  return apiGet<DomainActivityResponse>(`/ip/${encodeURIComponent(ip)}/domains${query ? `?${query}` : ''}`);
}

export type AsnInfo = {
  ip: string;
  scope: string;
  asn: number | null;
  asn_org: string | null;
  vendor: string;
  category: string;
  country: string | null;
  country_name: string | null;
};

export type IpAggItem = { key: string; doc_count: number } & Partial<AsnInfo>;

export type FullAggregationResponse = {
  ip: string;
  start: string | null;
  end: string | null;
  total_hits: number;
  asn_info: AsnInfo;
  domains: { total: number; buckets: DomainActivityBucket[] };
  ips: {
    as_source: IpAggItem[];
    as_destination: IpAggItem[];
    as_initiator: IpAggItem[];
    as_responder: IpAggItem[];
  };
  ports: { key: string; doc_count: number }[];
  protocols: { key: string; doc_count: number }[];
  actions: { key: string; doc_count: number }[];
  users: { key: string; doc_count: number }[];
};

export function fetchFullAggregation(
  ip: string,
  start: string,
  end: string,
  filters?: { srcIp?: string; dstIp?: string; dstPort?: string },
): Promise<FullAggregationResponse> {
  const params = new URLSearchParams({ start, end });
  if (filters?.srcIp) params.set('src_ip', filters.srcIp);
  if (filters?.dstIp) params.set('dst_ip', filters.dstIp);
  if (filters?.dstPort) params.set('dst_port', filters.dstPort);
  return apiGet<FullAggregationResponse>(`/ip/${encodeURIComponent(ip)}/full-aggregation?${params.toString()}`);
}

export async function exportPdfReport(ip: string, start: string, end: string): Promise<void> {
  const params = new URLSearchParams({ start, end, size: '500' });
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/ip/${encodeURIComponent(ip)}/report.pdf?${params.toString()}`);
  } catch {
    throw new Error('API qoşulma xətası');
  }
  if (!response.ok) throw new Error(`PDF xətası: ${response.status}`);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `netlens-${ip}-report.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export async function exportIpExcel(ip: string, filters: IpSummaryFilters = {}): Promise<void> {
  const params = new URLSearchParams();
  if (filters.srcIp?.trim()) params.set('src_ip', filters.srcIp.trim());
  if (filters.dstIp?.trim()) params.set('dst_ip', filters.dstIp.trim());
  if (filters.dstPort?.trim() && /^\d+$/.test(filters.dstPort.trim())) params.set('dst_port', filters.dstPort.trim());
  if (filters.start) params.set('start', filters.start);
  if (filters.end) params.set('end', filters.end);
  params.set('size_per_source', '500');
  const query = params.toString();

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/ip/${encodeURIComponent(ip)}/export.xlsx${query ? `?${query}` : ''}`);
  } catch {
    throw new Error('API qoşulma xətası');
  }
  if (!response.ok) {
    throw new Error(`Export xətası: ${response.status}`);
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `netlens-${ip}-logs.xlsx`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
