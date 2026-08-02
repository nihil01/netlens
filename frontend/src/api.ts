import { getToken, refreshAccessToken } from './auth';

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

export type ScannerProfile = {
  ip: string;
  status: string;
  ports: number[];
  category: string;
  site_id: number | null;
  is_new: boolean;
  hostname: string;
  fingerprinting?: {
    ip?: string;
    os_guess?: string;
    accuracy?: number;
    success?: boolean;
  };
};

export type ScannerProfilesResponse = {
  status: 'ready' | 'unavailable';
  trigger: string | null;
  started_at: string | null;
  updated_at: string | null;
  hosts_total: number;
  profiles: ScannerProfile[];
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

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

async function getAuthHeaders(): Promise<Record<string, string>> {
  let token = getToken();
  if (!token && await refreshAccessToken()) token = getToken();
  if (token) {
    return { 'Authorization': `Bearer ${token}` };
  }
  return {};
}

async function apiGet<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: await getAuthHeaders(),
    });
  } catch {
    throw new Error('API qoşulma xətası');
  }
  if (!response.ok) {
    throw new Error(`API cavabı: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function apiPost<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: await getAuthHeaders(),
    });
  } catch {
    throw new Error('API qoşulma xətası');
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail || `API cavabı: ${response.status}`);
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

export function fetchScannerProfiles(): Promise<ScannerProfilesResponse> {
  return apiGet<ScannerProfilesResponse>('/scanner/profiles');
}

export function fetchNetBoxDeviceDetail(deviceId: number): Promise<NetBoxDeviceDetail> {
  return apiGet<NetBoxDeviceDetail>(`/netbox/devices/${deviceId}/detail`);
}

export type InventoryStatus = {
  enabled: boolean;
  cron: string;
  next_run: string | null;
  last_refresh_at: string | null;
};

export function fetchInventoryStatus(): Promise<InventoryStatus> {
  return apiGet<InventoryStatus>('/scheduler/inventory/status');
}

export async function triggerInventoryRefresh(): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE_URL}/scheduler/inventory/refresh`, {
    method: 'POST',
    headers: await getAuthHeaders(),
  });
  if (!response.ok) throw new Error(`Refresh failed: ${response.status}`);
  return response.json();
}

export type DataResetResponse = {
  status: 'accepted' | 'already_running' | 'completed' | 'ok';
  cache_keys_deleted?: number;
  devices_total?: number;
  started_at?: string;
  finished_at?: string;
};

export function resetNetBoxData(): Promise<DataResetResponse> {
  return apiPost<DataResetResponse>('/netbox/reset');
}

export function resetFmcMonitoringData(): Promise<DataResetResponse> {
  return apiPost<DataResetResponse>('/monitoring/reset');
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
    response = await fetch(`${API_BASE_URL}/ip/${encodeURIComponent(ip)}/report.pdf?${params.toString()}`, {
      headers: await getAuthHeaders(),
    });
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
    response = await fetch(`${API_BASE_URL}/ip/${encodeURIComponent(ip)}/export.xlsx${query ? `?${query}` : ''}`, {
      headers: await getAuthHeaders(),
    });
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

// ---------------------------------------------------------------------------
// FMC Monitoring
// ---------------------------------------------------------------------------

export type VpnInterface = {
  name: string | null;
  ip_address: string | null;
  public_ip: string | null;
  interface_type: string | null;
};

export type TunnelPeer = {
  device_id: string | null;
  device_name: string | null;
  ip_addresses: string[];
  vpn_interface: VpnInterface | null;
  role: string | null;
  peer_type: string | null;
};

export type SecurityAssociation = {
  protected_network: string | null;
  inbound_spi_id: string | null;
  outbound_spi_id: string | null;
  spi_seconds_remaining: number | null;
  spi_bytes_remaining: number | null;
  packet_encrypt: number | null;
  packet_decrypt: number | null;
  packet_encaps: number | null;
  packet_dcaps: number | null;
};

export type TunnelPeerDetail = {
  device_id: string | null;
  device_name: string | null;
  auth_mode: string | null;
  bytes_tx: number;
  bytes_rx: number;
  port: number | null;
  vpn_interface_ip: string | null;
  security_associations: SecurityAssociation[];
  crypto_output: string | null;
};

export type TunnelStatus = {
  id: string | null;
  name: string | null;
  state: string;
  topology_type: string | null;
  ike_v1_enabled: boolean;
  ike_v2_enabled: boolean;
  route_based: boolean;
  total_tunnels: number;
  active_tunnels: number;
  down_tunnels: number;
  unknown_tunnels: number;
  peer_a: TunnelPeer | null;
  peer_b: TunnelPeer | null;
  peer_a_detail: TunnelPeerDetail | null;
  peer_b_detail: TunnelPeerDetail | null;
  last_change: number | null;
  message: string | null;
};

export type TunnelSummary = {
  group_name: string | null;
  group_type: string | null;
  tunnel_count: number;
  tunnel_up_count: number;
  tunnel_down_count: number;
  tunnel_unknown_count: number;
};

export type DeviceInventory = {
  cpu_type: string | null;
  cpu_cores: string | null;
  memory_mb: string | null;
  storage_gb: string | null;
};

export type FmcDevice = {
  id: string | null;
  host_name: string | null;
  model: string | null;
  model_number: string | null;
  model_id: string | null;
  sw_version: string | null;
  snort_engine: string | null;
  is_connected: boolean;
  health_status: string | null;
  health_message: string | null;
  deployment_status: string | null;
  ftd_mode: string | null;
  name: string | null;
  serial_number: string | null;
  access_policy: string | null;
  license_caps: string[];
  performance_tier: string | null;
  inventory: DeviceInventory | null;
  snort_version: string | null;
  sru_version: string | null;
  vdb_version: string | null;
};

export type InterfaceHealth = {
  interface_name: string | null;
  interface_type: string | null;
  operational_status: string | null;
  link_status: string | null;
  duplex_mode: string | null;
};

export type InterfaceTraffic = {
  name: string | null;
  interface_id: string | null;
  input_bytes_avg: number | null;
  output_bytes_avg: number | null;
  drop_packets_avg: number | null;
  input_errors_avg: number | null;
  output_errors_avg: number | null;
  metric_status: MetricStatus;
};

export type MetricStatus =
  | 'VALUE'
  | 'VALUE_ZERO'
  | 'NO_DATA'
  | 'AVAILABLE_NO_DATA'
  | 'UNSUPPORTED'
  | 'PERMISSION_ERROR'
  | 'TEMPORARY_ERROR'
  | 'INVALID_RESPONSE'
  | 'DEVICE_DISCONNECTED'
  | 'HEALTH_POLICY_MISSING'
  | 'STALE_DEVICE'
  | 'PARTIAL';

export type AggregateMetrics = {
  device_id: string | null;
  device_name: string | null;
  metric_status: MetricStatus;
  cpu_percent: number | null;
  cpu_lina_percent: number | null;
  cpu_snort_percent: number | null;
  cpu_system_percent: number | null;
  cpu_metric_statuses: Record<string, MetricStatus>;
  snort_cpu_average: number | null;
  snort_cpu_maximum: number | null;
  snort_cpu_sample_count: number;
  memory_percent: number | null;
  memory_lina_percent: number | null;
  memory_snort_percent: number | null;
  memory_system_percent: number | null;
  memory_metric_statuses: Record<string, MetricStatus>;
  disk_percent: number | null;
  disk_metric_statuses: Record<string, MetricStatus>;
  interfaces: InterfaceHealth[];
  interface_traffic: InterfaceTraffic[];
  fan_rpm: number[];
  start_time: string | null;
  end_time: string | null;
  capabilities: Record<string, string>;
  collection_errors: string[];
};

export type HealthAlert = {
  id: string | null;
  module_id: string | null;
  name: string | null;
  details: string | null;
  params: string | null;
};

export type MonitoringDashboard = {
  collected_at: string | null;
  reset_status: {
    state: 'idle' | 'queued' | 'clearing' | 'refetching' | 'completed' | 'failed';
    started_at?: string | null;
    finished_at?: string | null;
    completed_scopes?: string[];
    error?: string | null;
  };
  source_freshness: Array<{
    source: string;
    state: 'FRESH' | 'DEGRADED' | 'STALE' | 'ERROR' | 'NEVER_COLLECTED';
    last_attempt: string | null;
    last_success: string | null;
    collection_duration_seconds: number | null;
    records_received: number | null;
    partial_result: boolean;
    error: string | null;
    stale_threshold_seconds: number;
  }>;
  tunnel_statuses: TunnelStatus[];
  tunnel_summaries: TunnelSummary[];
  devices: FmcDevice[];
  aggregate_metrics: AggregateMetrics[];
  alerts: HealthAlert[];
  tunnel_up: number;
  tunnel_down: number;
  tunnel_unknown: number;
  devices_connected: number;
  devices_total: number;
  alerts_count: number;
  status?: string;
  message?: string;
};

export function fetchMonitoringDashboard(): Promise<MonitoringDashboard> {
  return apiGet<MonitoringDashboard>('/monitoring/dashboard');
}

export async function subscribeMonitoringEvents(
  onEvent: (event: { id: string | null; data: unknown }) => void,
  signal: AbortSignal,
  lastEventId?: string | null,
): Promise<void> {
  const headers = await getAuthHeaders();
  headers.Accept = 'text/event-stream';
  if (lastEventId) headers['Last-Event-ID'] = lastEventId;
  const response = await fetch(`${API_BASE_URL}/monitoring/events`, { headers, signal });
  if (!response.ok || !response.body) throw new Error(`SSE response: ${response.status}`);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (!signal.aborted) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf('\n\n');
    while (boundary >= 0) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      if (!frame.startsWith(':')) {
        let id: string | null = null;
        const data: string[] = [];
        for (const line of frame.split('\n')) {
          if (line.startsWith('id:')) id = line.slice(3).trim();
          if (line.startsWith('data:')) data.push(line.slice(5).trim());
        }
        if (data.length) onEvent({ id, data: JSON.parse(data.join('\n')) });
      }
      boundary = buffer.indexOf('\n\n');
    }
  }
}

export type MetricHistoryPoint = {
  timestamp: string;
  interface_id: string | null;
  metric_name: string;
  metric_value: number | null;
  metric_status: MetricStatus;
  source: string;
  window: string | null;
};

export type MetricHistoryResponse = {
  items: MetricHistoryPoint[];
  total: number;
  limit: number;
  offset: number;
};

export function fetchDeviceMetricHistory(
  deviceId: string,
  metricNames: string[] = [
    'cpu.system',
    'memory.system',
    'disk.usage',
    'interface.input_bytes_avg',
    'interface.output_bytes_avg',
  ],
  historyHours = 2,
): Promise<MetricHistoryResponse> {
  const params = new URLSearchParams();
  metricNames.forEach((name) => params.append('metric_names', name));
  params.set('start', new Date(Date.now() - historyHours * 60 * 60 * 1000).toISOString());
  params.set('limit', '5000');
  return apiGet<MetricHistoryResponse>(
    `/monitoring/devices/${encodeURIComponent(deviceId)}/metrics?${params}`,
  );
}

export type HaMonitoredInterface = {
  id: string | null;
  name: string | null;
  interface_logical_name: string | null;
  monitor_for_failures: boolean | null;
  ipv4: {
    active_address: string | null;
    active_mask: string | null;
    standby_address: string | null;
  };
  ipv6: {
    active_link_local_address: string | null;
    standby_link_local_address: string | null;
    address_pairs: Array<{ active_address: string | null; standby_address: string | null }>;
  };
  collection_errors: string[];
};

export type HaPairCurrent = {
  pair_id: string;
  name: string | null;
  pair_state: 'HEALTHY' | 'DEGRADED' | 'FAILED' | 'UNKNOWN' | 'ROLE_TRANSITION';
  health_status: string | null;
  health_message: string | null;
  primary_device_id: string;
  primary_device_name: string | null;
  secondary_device_id: string;
  secondary_device_name: string | null;
  active_member_id: string | null;
  active_member_name: string | null;
  standby_member_id: string | null;
  standby_member_name: string | null;
  failover_link: Record<string, unknown>;
  stateful_link: Record<string, unknown>;
  monitored_interfaces: HaMonitoredInterface[];
  last_role_transition_at: string | null;
  last_health_transition_at: string | null;
  last_seen_at: string;
};

export function fetchHaPairs(): Promise<{ items: HaPairCurrent[] }> {
  return apiGet<{ items: HaPairCurrent[] }>('/monitoring/ha/pairs');
}

export type PolicySummary = {
  policy_id: string | null;
  name: string | null;
  total_rules: number;
  enabled_rules: number;
  disabled_rules: number;
  allow_rules: number;
  block_rules: number;
  rules_without_logging: number;
  allow_rules_without_ips_policy: number;
  rules_with_any_source: number;
  rules_with_any_destination: number;
  rules_with_any_destination_port: number;
};

export type PolicyAnalysis = {
  total_policies: number;
  total_rules: number;
  enabled_rules: number;
  disabled_rules: number;
  allow_rules: number;
  block_rules: number;
  rules_without_logging: number;
  allow_rules_without_ips_policy: number;
  rules_with_any_source: number;
  rules_with_any_destination: number;
  rules_with_any_destination_port: number;
  policies: PolicySummary[];
};

export function fetchPolicyAnalysis(): Promise<PolicyAnalysis> {
  return apiGet<PolicyAnalysis>('/monitoring/policy-analysis');
}

export type StoredHealthAlert = {
  alert_id: string;
  device_id: string | null;
  module_id: string | null;
  severity: string | null;
  source_status: string | null;
  lifecycle_state: 'NEW' | 'ACTIVE' | 'RESOLVED' | 'REOPENED' | 'FLAPPING' | 'UNKNOWN';
  description: string | null;
  details: string | null;
  first_seen_at: string;
  last_seen_at: string;
  resolved_at: string | null;
  reopen_count: number;
  repeat_count: number;
};

export function fetchHealthAlertHistory(filters: {
  search?: string;
  severity?: string;
  lifecycle?: string;
} = {}): Promise<{ items: StoredHealthAlert[]; total: number }> {
  const params = new URLSearchParams({ limit: '500' });
  if (filters.search) params.set('search', filters.search);
  if (filters.severity) params.set('severity', filters.severity);
  if (filters.lifecycle) params.set('lifecycle', filters.lifecycle);
  return apiGet<{ items: StoredHealthAlert[]; total: number }>(
    `/monitoring/health-alerts?${params}`,
  );
}

export type VpnTimelineResponse = {
  tunnel: {
    id: string;
    name: string | null;
    current_status: string;
    is_flapping: boolean;
    transition_count: number;
    flap_count: number;
  } | null;
  transitions: Array<{
    previous_status: string;
    new_status: string;
    changed_at: string;
    duration_in_previous_state_seconds: number | null;
  }>;
  analytics: {
    availability_percent: number | null;
    up_seconds: number;
    down_seconds: number;
    unknown_seconds: number;
    transition_count: number;
    longest_outage_seconds: number;
    mtbf_seconds: number | null;
    mttr_seconds: number | null;
    flapping: boolean;
  } | null;
  analytics_truncated: boolean;
  total: number;
};

export function fetchVpnTimeline(tunnelId: string): Promise<VpnTimelineResponse> {
  return apiGet<VpnTimelineResponse>(
    `/monitoring/vpn/${encodeURIComponent(tunnelId)}/timeline?limit=5000`,
  );
}

export type AuditRecord = {
  fmc_id: string;
  audit_id: string | null;
  record_id: string | null;
  snapshot_id: string | null;
  timestamp: string | null;
  local_timestamp: string | null;
  user_name: string | null;
  source: string | null;
  subsystem: string | null;
  message: string | null;
  action: string;
  object_type: string | null;
  object_name: string | null;
  changed_fields: string[];
  risk_score: number;
  risk_factors: string[];
  deployed: boolean;
  deploy_success: boolean | null;
};

export type AuditDashboard = {
  total_records: number;
  records_today: number;
  records_this_week: number;
  risk_distribution: Record<string, number>;
  recent_high_risk: AuditRecord[];
  timeline: Array<Record<string, number | string>>;
  deployment_stats: Record<string, number>;
};

export function fetchAuditDashboard(): Promise<AuditDashboard> {
  return apiGet<AuditDashboard>('/fmc-audit/dashboard');
}

export function fetchAuditRecords(filters: {
  user?: string;
  action?: string;
  minRisk?: number;
  dateFrom?: string;
  dateTo?: string;
  page?: number;
} = {}): Promise<{ records: AuditRecord[]; total: number; page: number; page_size: number }> {
  const params = new URLSearchParams({ page: String(filters.page ?? 1), page_size: '200' });
  if (filters.user) params.set('user', filters.user);
  if (filters.action) params.set('action', filters.action);
  if (filters.minRisk) params.set('min_risk', String(filters.minRisk));
  if (filters.dateFrom) params.set('date_from', filters.dateFrom);
  if (filters.dateTo) params.set('date_to', filters.dateTo);
  return apiGet<{ records: AuditRecord[]; total: number; page: number; page_size: number }>(`/fmc-audit/records?${params}`);
}

export function fetchAuditRecord(fmcId: string): Promise<{
  record: AuditRecord;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  field_diffs: Array<{ field: string; before: unknown; after: unknown; change_type: string }>;
} | null> {
  return apiGet(`/fmc-audit/records/${encodeURIComponent(fmcId)}`);
}

export async function downloadAuditCsv(filters: {
  user?: string;
  action?: string;
  dateFrom?: string;
  dateTo?: string;
} = {}): Promise<void> {
  const params = new URLSearchParams({ format: 'csv' });
  if (filters.user) params.set('user', filters.user);
  if (filters.action) params.set('action', filters.action);
  if (filters.dateFrom) params.set('date_from', filters.dateFrom);
  if (filters.dateTo) params.set('date_to', filters.dateTo);
  const response = await fetch(`${API_BASE_URL}/fmc-audit/export?${params}`, {
    headers: await getAuthHeaders(),
  });
  if (!response.ok) throw new Error(`Export response: ${response.status}`);
  const link = document.createElement('a');
  link.href = URL.createObjectURL(await response.blob());
  link.download = `fmc-audit-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}
