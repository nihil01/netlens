export type NetBoxContext = {
  known: boolean;
  device: string | null;
  site: string | null;
  region: string | null;
  city: string | null;
  role: string | null;
  interfaces: Array<Record<string, unknown>>;
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
};

export type IpSummary = {
  ip: string;
  netbox: NetBoxContext;
  scan: ScanContext;
  activity: ActivitySummary;
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api';

export async function fetchIpSummary(ip: string): Promise<IpSummary> {
  const response = await fetch(`${API_BASE_URL}/ip/${encodeURIComponent(ip)}/summary`);
  if (!response.ok) {
    throw new Error(`API returned ${response.status}`);
  }
  return response.json();
}
