import { Fragment, FormEvent, ReactNode, useMemo, useState, type PointerEvent, type WheelEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  AlertTriangle,
  Boxes,
  Building2,
  Cable,
  Copy,
  Cpu,
  Database,
  Download,
  Eye,
  Filter,
  GitBranch,
  Layers3,
  MapPinned,
  Network,
  Radar,
  RefreshCw,
  Search,
  Server,
  Router,
  Sparkles,
  Waypoints,
  X,
} from 'lucide-react';
import {
  fetchIpSummary,
  fetchNetBoxDeviceDetail,
  fetchNetBoxInventory,
  type NetBoxDevice,
  type NetBoxInterface,
  type NetBoxRegion,
  type NetBoxSite,
} from './api';

type MainTab = 'inventory' | 'graph' | 'ip' | 'mac';
type GraphNodeType = 'region' | 'site' | 'device' | 'interface';
type QuickFilter = 'all' | 'active' | 'offline' | 'unknownVendor' | 'interfaceProblems' | 'missingPrimaryIp';
type GraphLevels = Record<GraphNodeType, boolean>;
type GraphNode = {
  id: string;
  label: string;
  type: GraphNodeType;
  x: number;
  y: number;
  meta?: NetBoxRegion | NetBoxSite | NetBoxDevice | NetBoxInterface;
};
type GraphLink = { from: string; to: string };

function isLikelyIp(value: string): boolean {
  return /^(?:\d{1,3}\.){3}\d{1,3}$/.test(value.trim());
}

function emptyLabel(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

function statusClass(status: string | null | undefined): string {
  if (!status) return 'muted';
  const normalized = status.toLowerCase();
  if (['active', 'online', 'ok'].includes(normalized)) return 'good';
  if (['planned', 'staged', 'offline'].includes(normalized)) return 'warn';
  return 'muted';
}

function nodeColor(type: GraphNodeType): string {
  return {
    region: '#38bdf8',
    site: '#a78bfa',
    device: '#22c55e',
    interface: '#f59e0b',
  }[type];
}

export function App() {
  const [input, setInput] = useState('10.255.127.60');
  const [ip, setIp] = useState('10.255.127.60');
  const [selectedDeviceId, setSelectedDeviceId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<MainTab>('inventory');
  const [selectedRegionName, setSelectedRegionName] = useState<string | null>(null);
  const [selectedGraphNode, setSelectedGraphNode] = useState<GraphNode | null>(null);
  const [inventorySearch, setInventorySearch] = useState('');
  const [quickFilter, setQuickFilter] = useState<QuickFilter>('all');
  const [graphLevels, setGraphLevels] = useState<GraphLevels>({ region: true, site: true, device: true, interface: true });

  const summary = useQuery({
    queryKey: ['ip-summary', ip],
    queryFn: () => fetchIpSummary(ip),
    enabled: isLikelyIp(ip),
  });

  const inventory = useQuery({
    queryKey: ['netbox-inventory'],
    queryFn: fetchNetBoxInventory,
  });

  const selectedDeviceDetail = useQuery({
    queryKey: ['netbox-device-detail', selectedDeviceId],
    queryFn: () => fetchNetBoxDeviceDetail(selectedDeviceId as number),
    enabled: selectedDeviceId !== null,
  });

  const data = inventory.data;
  const normalizedSearch = inventorySearch.trim().toLowerCase();

  const allInterfacesByDevice = useMemo(() => {
    const grouped = new Map<number, NetBoxInterface[]>();
    for (const item of data?.interfaces ?? []) {
      if (!item.device_id) continue;
      grouped.set(item.device_id, [...(grouped.get(item.device_id) ?? []), item]);
    }
    return grouped;
  }, [data?.interfaces]);

  const filteredDevices = useMemo(
    () => (data?.devices ?? []).filter((device) => devicePassesFilters(device, allInterfacesByDevice.get(device.id) ?? [], normalizedSearch, quickFilter)),
    [allInterfacesByDevice, data?.devices, normalizedSearch, quickFilter],
  );

  const filteredInterfaces = useMemo(
    () => (data?.interfaces ?? []).filter((item) => interfacePassesFilters(item, filteredDevices, normalizedSearch, quickFilter)),
    [data?.interfaces, filteredDevices, normalizedSearch, quickFilter],
  );

  const filteredSites = useMemo(
    () => (data?.sites ?? []).filter((site) => sitePassesFilters(site, filteredDevices, filteredInterfaces, normalizedSearch, quickFilter)),
    [data?.sites, filteredDevices, filteredInterfaces, normalizedSearch, quickFilter],
  );

  const filteredRegions = useMemo(
    () => (data?.regions ?? []).filter((region) => regionPassesFilters(region, filteredSites, filteredDevices, normalizedSearch, quickFilter)),
    [data?.regions, filteredDevices, filteredSites, normalizedSearch, quickFilter],
  );

  const selectedRegion = selectedRegionName && filteredRegions.some((region) => region.name === selectedRegionName)
    ? selectedRegionName
    : filteredRegions[0]?.name ?? data?.regions[0]?.name ?? null;

  const sitesByRegion = useMemo(() => {
    const grouped = new Map<string, NetBoxSite[]>();
    for (const site of filteredSites) {
      if (!site.region) continue;
      grouped.set(site.region, [...(grouped.get(site.region) ?? []), site]);
    }
    return grouped;
  }, [filteredSites]);

  const devicesBySite = useMemo(() => {
    const grouped = new Map<string, NetBoxDevice[]>();
    for (const device of filteredDevices) {
      if (!device.site) continue;
      grouped.set(device.site, [...(grouped.get(device.site) ?? []), device]);
    }
    return grouped;
  }, [filteredDevices]);

  const interfacesByDevice = useMemo(() => {
    const grouped = new Map<number, NetBoxInterface[]>();
    for (const item of filteredInterfaces) {
      if (!item.device_id) continue;
      grouped.set(item.device_id, [...(grouped.get(item.device_id) ?? []), item]);
    }
    return grouped;
  }, [filteredInterfaces]);

  const selectedDevice = useMemo(() => {
    if (!selectedDeviceId) return null;
    return data?.devices.find((device) => device.id === selectedDeviceId) ?? null;
  }, [data?.devices, selectedDeviceId]);

  const selectedRegionSites = useMemo(
    () => (selectedRegion ? sitesByRegion.get(selectedRegion) ?? [] : []),
    [selectedRegion, sitesByRegion],
  );
  const selectedRegionDevices = useMemo(
    () => selectedRegionSites.flatMap((site) => devicesBySite.get(site.name) ?? []),
    [devicesBySite, selectedRegionSites],
  );
  const selectedRegionInterfaceCount = selectedRegionDevices.reduce(
    (total, device) => total + (interfacesByDevice.get(device.id)?.length ?? 0),
    0,
  );

  const macInterfaces = useMemo(
    () => filteredInterfaces.filter((item) => item.mac_address),
    [filteredInterfaces],
  );

  const graph = useMemo(
    () => buildGraph(selectedRegion, selectedRegionSites, selectedRegionDevices, interfacesByDevice, graphLevels),
    [graphLevels, interfacesByDevice, selectedRegion, selectedRegionDevices, selectedRegionSites],
  );

  const riskSummary = useMemo(() => buildRiskSummary(data?.devices ?? [], data?.interfaces ?? []), [data?.devices, data?.interfaces]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIp(input.trim());
    setActiveTab('ip');
  }

  function selectDevice(deviceId: number) {
    setSelectedDeviceId(deviceId);
    setActiveTab('inventory');
  }

  return (
    <main className="shell">
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow"><Sparkles size={14} /> Şəbəkə analitikası</p>
          <h1>NetLens</h1>
          <p className="subtitle">NetBox inventarı, qurğu detalları, MAC/OUI və IP analizi.</p>
        </div>
        <div className="hero-orb" aria-hidden="true">
          <span />
          <Network size={64} />
        </div>
      </section>

      <section className="overview-grid">
        <MetricCard icon={<MapPinned size={20} />} label="Regionlar" value={data?.regions.length ?? 0} />
        <MetricCard icon={<Layers3 size={20} />} label="Sahələr" value={data?.sites.length ?? 0} />
        <MetricCard icon={<Server size={20} />} label="Qurğular" value={data?.devices.length ?? 0} />
        <MetricCard icon={<Network size={20} />} label="İnterfeyslər" value={data?.interfaces.length ?? 0} />
      </section>

      {inventory.isLoading && <div className="panel shimmer">NetBox inventarı yüklənir...</div>}
      {inventory.isError && <div className="panel error">NetBox inventar xətası: {(inventory.error as Error).message}</div>}
      {data && data.status.status !== 'ok' && (
        <div className="panel warning">NetBox statusu: {data.status.message ?? data.status.status}</div>
      )}

      <InventoryCommandBar
        filter={quickFilter}
        onClear={() => {
          setInventorySearch('');
          setQuickFilter('all');
        }}
        onFilterChange={setQuickFilter}
        onSearchChange={setInventorySearch}
        query={inventorySearch}
        resultCount={filteredRegions.length + filteredSites.length + filteredDevices.length + filteredInterfaces.length}
        riskSummary={riskSummary}
      />

      <nav className="tabs" aria-label="NetLens bölmələri">
        <TabButton active={activeTab === 'inventory'} icon={<Boxes size={18} />} onClick={() => setActiveTab('inventory')}>İnventar</TabButton>
        <TabButton active={activeTab === 'graph'} icon={<Waypoints size={18} />} onClick={() => setActiveTab('graph')}>Qraf</TabButton>
        <TabButton active={activeTab === 'mac'} icon={<Cpu size={18} />} onClick={() => setActiveTab('mac')}>MAC/OUI</TabButton>
        <TabButton active={activeTab === 'ip'} icon={<Radar size={18} />} onClick={() => setActiveTab('ip')}>IP analizi</TabButton>
      </nav>

      {activeTab === 'inventory' && (
        <section className="tab-panel inventory-tab">
          <aside className="panel region-rail">
            <div className="panel-title"><MapPinned size={20} /> Regionlar</div>
            <div className="region-buttons">
              {(filteredRegions ?? []).map((region) => (
                <button
                  className={`region-button ${region.name === selectedRegion ? 'selected' : ''}`}
                  key={region.id}
                  onClick={() => setSelectedRegionName(region.name)}
                  type="button"
                >
                  <b>{region.name}</b>
                  <span>{sitesByRegion.get(region.name)?.length ?? 0} sahə</span>
                </button>
              ))}
              {!data?.regions.length && <p className="muted-text">Region yoxdur və ya NetBox qoşulmayıb.</p>}
            </div>
          </aside>

          <section className="panel region-workspace">
            <div className="workspace-header">
              <div>
                <div className="panel-title"><Layers3 size={20} /> {selectedRegion ?? 'Region seçilməyib'}</div>
                <p className="muted-text">Sahələr: {selectedRegionSites.length} · Qurğular: {selectedRegionDevices.length} · İnterfeyslər: {selectedRegionInterfaceCount}</p>
              </div>
              <button className="ghost-button" type="button" onClick={() => setActiveTab('graph')}>
                <GitBranch size={16} /> Qrafı aç
              </button>
            </div>

            <div className="site-grid">
              {selectedRegionSites.map((site) => (
                <article className="site-card" key={site.id}>
                  <header>
                    <b>{site.name}</b>
                    <span className={statusClass(site.status)}>{emptyLabel(site.status)}</span>
                  </header>
                  <p>{emptyLabel(site.physical_address ?? site.facility)}</p>
                  <div className="device-list compact">
                    {(devicesBySite.get(site.name) ?? []).map((device) => (
                      <DeviceRow
                        key={device.id}
                        device={device}
                        interfaceCount={interfacesByDevice.get(device.id)?.length ?? 0}
                        selected={device.id === selectedDeviceId}
                        onSelect={() => selectDevice(device.id)}
                      />
                    ))}
                  </div>
                </article>
              ))}
            </div>
          </section>

          <DeviceDetailPanel
            detail={selectedDeviceDetail.data}
            isError={selectedDeviceDetail.isError}
            isLoading={selectedDeviceDetail.isLoading}
            error={selectedDeviceDetail.error as Error | null}
            selectedDevice={selectedDevice}
          />
        </section>
      )}

      {activeTab === 'graph' && (
        <section className="tab-panel graph-tab">
          <article className="panel graph-panel">
            <div className="workspace-header">
              <div>
                <div className="panel-title"><Waypoints size={20} /> Region qrafı</div>
                <p className="muted-text">Region seçin və qrafdan obyekt açın.</p>
              </div>
              <select value={selectedRegion ?? ''} onChange={(event) => setSelectedRegionName(event.target.value)}>
                {(filteredRegions ?? []).map((region) => <option key={region.id} value={region.name}>{region.name}</option>)}
              </select>
            </div>
            <GraphLevelToggles levels={graphLevels} onChange={setGraphLevels} />
            <InventoryGraph graph={graph} selectedId={selectedGraphNode?.id} onSelect={setSelectedGraphNode} />
          </article>
          <GraphInspector node={selectedGraphNode} onSelectDevice={selectDevice} />
        </section>
      )}

      {activeTab === 'mac' && (
        <section className="tab-panel mac-tab">
          <article className="panel wide-panel">
            <div className="workspace-header">
              <div>
                <div className="panel-title"><Cpu size={20} /> MAC/OUI</div>
                <OuiStatus dataset={data?.oui_dataset} />
              </div>
              <div className="action-row">
                <button className="ghost-button" type="button" onClick={() => navigator.clipboard?.writeText(JSON.stringify(macInterfaces, null, 2))}>
                  <Copy size={16} /> Kopyala
                </button>
                <button className="ghost-button" type="button" onClick={() => downloadJson('netlens-mac-oui.json', macInterfaces)}>
                  <Download size={16} /> JSON
                </button>
              </div>
            </div>
            <InterfaceList interfaces={macInterfaces} showDevice showVendor />
          </article>
        </section>
      )}

      {activeTab === 'ip' && (
        <section className="tab-panel ip-tab">
          <form className="search-card" onSubmit={submit}>
            <Search size={22} />
            <input value={input} onChange={(event) => setInput(event.target.value)} placeholder="10.255.127.60" />
            <button type="submit">IP-ni yoxla</button>
          </form>

          {summary.isLoading && <div className="panel shimmer">Məlumat yüklənir...</div>}
          {summary.isError && <div className="panel error">Xəta: {(summary.error as Error).message}</div>}

          {summary.data && (
            <section className="grid">
              <article className="panel wide">
                <div className="panel-title"><Database size={20} /> NetBox konteksti</div>
                <dl>
                  <dt>IP</dt><dd>{summary.data.ip}</dd>
                  <dt>Məlumdur</dt><dd>{summary.data.netbox.known ? 'bəli' : 'xeyr'}</dd>
                  <dt>Qurğu</dt><dd>{summary.data.netbox.device ?? '—'}</dd>
                  <dt>Sahə</dt><dd>{summary.data.netbox.site ?? '—'}</dd>
                  <dt>Region / Şəhər</dt><dd>{summary.data.netbox.region ?? '—'} / {summary.data.netbox.city ?? '—'}</dd>
                  <dt>Rol</dt><dd>{summary.data.netbox.role ?? '—'}</dd>
                </dl>
                <InterfaceList interfaces={summary.data.netbox.interfaces as NetBoxInterface[]} showVendor />
              </article>

              <article className="panel">
                <div className="panel-title"><Radar size={20} /> Skan</div>
                <div className="metric">{summary.data.scan.status}</div>
                <p>Portlar: {summary.data.scan.open_ports.length ? summary.data.scan.open_ports.join(', ') : 'hələ skan edilməyib'}</p>
                <p>OS: {summary.data.scan.os_guess ?? 'bilinmir'}</p>
              </article>

              <article className="panel">
                <div className="panel-title"><Activity size={20} /> Aktivlik / {summary.data.activity.window}</div>
                <div className="cards">
                  <span><b>{summary.data.activity.internal_connections}</b> daxili</span>
                  <span><b>{summary.data.activity.external_connections}</b> xarici</span>
                  <span><b>{summary.data.activity.security_events}</b> təhlükəsizlik</span>
                </div>
                <h3>Əsas daxili istiqamətlər</h3>
                <ul>
                  {summary.data.activity.top_internal_destinations.map((item) => (
                    <li key={`${item.ip}-${item.port}`}>{item.ip}:{item.port ?? '*'} — {item.count}</li>
                  ))}
                </ul>
              </article>
            </section>
          )}
        </section>
      )}
    </main>
  );
}

function containsValue(value: string | number | boolean | null | undefined, needle: string): boolean {
  return needle.length === 0 || emptyLabel(value).toLowerCase().includes(needle);
}

function interfaceHasProblem(item: NetBoxInterface): boolean {
  return item.enabled === false || (!!item.mac_address && (!item.mac_vendor || item.mac_vendor_source === 'unknown'));
}

function devicePassesFilters(device: NetBoxDevice, interfaces: NetBoxInterface[], needle: string, filter: QuickFilter): boolean {
  const matchesSearch = [device.name, device.site, device.region, device.role, device.device_type, device.manufacturer, device.status, device.primary_ip]
    .some((value) => containsValue(value, needle))
    || interfaces.some((item) => interfaceMatchesSearch(item, needle));
  if (!matchesSearch) return false;
  if (filter === 'active') return (device.status ?? '').toLowerCase() === 'active';
  if (filter === 'offline') return (device.status ?? '').toLowerCase() === 'offline';
  if (filter === 'unknownVendor') return interfaces.some((item) => !!item.mac_address && (!item.mac_vendor || item.mac_vendor_source === 'unknown'));
  if (filter === 'interfaceProblems') return interfaces.some(interfaceHasProblem);
  if (filter === 'missingPrimaryIp') return !device.primary_ip;
  return true;
}

function interfaceMatchesSearch(item: NetBoxInterface, needle: string): boolean {
  return [item.name, item.device, item.type, item.mac_address, item.mac_vendor, item.mac_oui, item.description, item.mode, item.untagged_vlan]
    .some((value) => containsValue(value, needle));
}

function interfacePassesFilters(item: NetBoxInterface, devices: NetBoxDevice[], needle: string, filter: QuickFilter): boolean {
  const relatedDevice = devices.find((device) => device.id === item.device_id);
  const matchesSearch = interfaceMatchesSearch(item, needle) || (relatedDevice ? containsValue(relatedDevice.name, needle) : false);
  if (!matchesSearch) return false;
  if (filter === 'unknownVendor') return !!item.mac_address && (!item.mac_vendor || item.mac_vendor_source === 'unknown');
  if (filter === 'interfaceProblems') return interfaceHasProblem(item);
  if (filter === 'active') return item.enabled !== false;
  if (filter === 'offline') return item.enabled === false || (relatedDevice?.status ?? '').toLowerCase() === 'offline';
  if (filter === 'missingPrimaryIp') return relatedDevice ? !relatedDevice.primary_ip : false;
  return true;
}

function sitePassesFilters(site: NetBoxSite, devices: NetBoxDevice[], interfaces: NetBoxInterface[], needle: string, filter: QuickFilter): boolean {
  const siteDevices = devices.filter((device) => device.site === site.name);
  const siteInterfaces = interfaces.filter((item) => item.device && siteDevices.some((device) => device.name === item.device));
  const matchesSearch = [site.name, site.region, site.status, site.facility, site.physical_address].some((value) => containsValue(value, needle))
    || siteDevices.length > 0
    || siteInterfaces.length > 0;
  if (!matchesSearch) return false;
  return filter === 'all' || siteDevices.length > 0 || siteInterfaces.length > 0;
}

function regionPassesFilters(region: NetBoxRegion, sites: NetBoxSite[], devices: NetBoxDevice[], needle: string, filter: QuickFilter): boolean {
  const regionSites = sites.filter((site) => site.region === region.name);
  const regionDevices = devices.filter((device) => device.region === region.name);
  const matchesSearch = [region.name, region.slug, region.description].some((value) => containsValue(value, needle))
    || regionSites.length > 0
    || regionDevices.length > 0;
  if (!matchesSearch) return false;
  return filter === 'all' || regionSites.length > 0 || regionDevices.length > 0;
}

function buildRiskSummary(devices: NetBoxDevice[], interfaces: NetBoxInterface[]) {
  return {
    unknownVendor: interfaces.filter((item) => !!item.mac_address && (!item.mac_vendor || item.mac_vendor_source === 'unknown')).length,
    interfaceProblems: interfaces.filter(interfaceHasProblem).length,
    missingPrimaryIp: devices.filter((device) => !device.primary_ip).length,
    offlineDevices: devices.filter((device) => (device.status ?? '').toLowerCase() === 'offline').length,
  };
}

function downloadJson(filename: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function buildGraph(
  region: string | null,
  sites: NetBoxSite[],
  devices: NetBoxDevice[],
  interfacesByDevice: Map<number, NetBoxInterface[]>,
  levels: GraphLevels,
): { nodes: GraphNode[]; links: GraphLink[] } {
  if (!region || !levels.region) return { nodes: [], links: [] };

  const nodes: GraphNode[] = [{ id: `region:${region}`, label: region, type: 'region', x: 720, y: 90 }];
  const links: GraphLink[] = [];
  const siteSpacing = 1260 / Math.max(sites.length, 1);

  sites.forEach((site, siteIndex) => {
    const siteX = 90 + siteSpacing * siteIndex + siteSpacing / 2;
    const siteNode: GraphNode = { id: `site:${site.id}`, label: site.name, type: 'site', x: siteX, y: 280, meta: site };
    if (levels.site) {
      nodes.push(siteNode);
      links.push({ from: `region:${region}`, to: siteNode.id });
    }

    if (!levels.device) return;
    const siteDevices = devices.filter((device) => device.site === site.name).slice(0, 8);
    const deviceSpacing = Math.min(170, 1120 / Math.max(siteDevices.length, 1));
    const startX = siteX - ((siteDevices.length - 1) * deviceSpacing) / 2;
    siteDevices.forEach((device, deviceIndex) => {
      const deviceNode: GraphNode = {
        id: `device:${device.id}`,
        label: device.name,
        type: 'device',
        x: Math.max(65, Math.min(1375, startX + deviceIndex * deviceSpacing)),
        y: 500,
        meta: device,
      };
      nodes.push(deviceNode);
      links.push({ from: levels.site ? siteNode.id : `region:${region}`, to: deviceNode.id });

      if (!levels.interface) return;
      const ifaces = (interfacesByDevice.get(device.id) ?? []).filter((iface) => iface.mac_address).slice(0, 3);
      ifaces.forEach((iface, ifaceIndex) => {
        const ifaceNode: GraphNode = {
          id: `interface:${iface.id}`,
          label: iface.name,
          type: 'interface',
          x: deviceNode.x + (ifaceIndex - (ifaces.length - 1) / 2) * 74,
          y: 710,
          meta: iface,
        };
        nodes.push(ifaceNode);
        links.push({ from: deviceNode.id, to: ifaceNode.id });
      });
    });
  });

  return { nodes, links };
}

const QUICK_FILTERS: Array<{ value: QuickFilter; label: string }> = [
  { value: 'all', label: 'Hamısı' },
  { value: 'active', label: 'Aktiv' },
  { value: 'offline', label: 'Offline' },
  { value: 'unknownVendor', label: 'Vendor boşdur' },
  { value: 'interfaceProblems', label: 'İnterfeys problemi' },
  { value: 'missingPrimaryIp', label: 'IP boşdur' },
];

const GRAPH_LEVEL_LABELS: Record<GraphNodeType, string> = {
  region: 'Region',
  site: 'Sahə',
  device: 'Qurğu',
  interface: 'İnterfeys',
};

function InventoryCommandBar({
  filter,
  onClear,
  onFilterChange,
  onSearchChange,
  query,
  resultCount,
  riskSummary,
}: {
  filter: QuickFilter;
  onClear: () => void;
  onFilterChange: (filter: QuickFilter) => void;
  onSearchChange: (query: string) => void;
  query: string;
  resultCount: number;
  riskSummary: { unknownVendor: number; interfaceProblems: number; missingPrimaryIp: number; offlineDevices: number };
}) {
  return (
    <section className="command-bar">
      <div className="global-search">
        <Search size={18} />
        <input
          value={query}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Hostname, IP, MAC, vendor, sahə, region..."
        />
        {(query || filter !== 'all') && <button type="button" onClick={onClear}><X size={16} /> Təmizlə</button>}
      </div>
      <div className="filter-row" aria-label="Sürətli filtrlər">
        <Filter size={16} />
        {QUICK_FILTERS.map((item) => (
          <button className={filter === item.value ? 'selected' : ''} key={item.value} type="button" onClick={() => onFilterChange(item.value)}>
            {item.label}
          </button>
        ))}
        <span className="result-pill">Nəticə: {resultCount}</span>
      </div>
      <div className="risk-strip">
        <RiskPill label="Unknown vendor" value={riskSummary.unknownVendor} />
        <RiskPill label="İnterfeys" value={riskSummary.interfaceProblems} />
        <RiskPill label="Primary IP yoxdur" value={riskSummary.missingPrimaryIp} />
        <RiskPill label="Offline" value={riskSummary.offlineDevices} />
      </div>
    </section>
  );
}

function RiskPill({ label, value }: { label: string; value: number }) {
  return <span className={`risk-pill ${value ? 'warn' : 'good'}`}><AlertTriangle size={14} /> {label}: {value}</span>;
}

function GraphLevelToggles({ levels, onChange }: { levels: GraphLevels; onChange: (levels: GraphLevels) => void }) {
  return (
    <div className="level-toggles">
      <Eye size={16} />
      {(Object.keys(levels) as GraphNodeType[]).map((level) => (
        <button
          className={levels[level] ? 'selected' : ''}
          key={level}
          type="button"
          onClick={() => onChange({ ...levels, [level]: !levels[level] })}
        >
          {GRAPH_LEVEL_LABELS[level]}
        </button>
      ))}
    </div>
  );
}

function OuiStatus({ dataset }: { dataset?: { source?: string; source_url?: string; created_at?: string | null; records?: number; cache?: string } }) {
  return (
    <div className="oui-status">
      <span><RefreshCw size={14} /> Mənbə: {dataset?.source ?? 'Wireshark'}</span>
      <span>Yazılar: {dataset?.records ?? 0}</span>
      <span>Keş: {dataset?.cache ?? 'memory'}</span>
      <span>Yaradılıb: {dataset?.created_at ?? '—'}</span>
    </div>
  );
}

function TabButton({ active, children, icon, onClick }: { active: boolean; children: ReactNode; icon: ReactNode; onClick: () => void }) {
  return <button className={`tab-button ${active ? 'active' : ''}`} onClick={onClick} type="button">{icon}{children}</button>;
}

function MetricCard({ icon, label, value }: { icon: ReactNode; label: string; value: number }) {
  return (
    <article className="metric-card">
      {icon}
      <span>{label}</span>
      <b>{value}</b>
    </article>
  );
}

function DeviceRow({ device, interfaceCount, selected, onSelect }: { device: NetBoxDevice; interfaceCount: number; selected: boolean; onSelect: () => void }) {
  return (
    <button className={`device-row ${selected ? 'selected' : ''}`} type="button" onClick={onSelect}>
      <span>
        <b>{device.name}</b>
        <small>{emptyLabel(device.role)} · {interfaceCount} interfeys · {emptyLabel(device.primary_ip)}</small>
      </span>
      <em className={statusClass(device.status)}>{emptyLabel(device.status)}</em>
    </button>
  );
}

function DeviceDetailPanel({
  detail,
  error,
  isError,
  isLoading,
  selectedDevice,
}: {
  detail: ReturnType<typeof useQuery<unknown>>['data'] extends never ? never : import('./api').NetBoxDeviceDetail | undefined;
  error: Error | null;
  isError: boolean;
  isLoading: boolean;
  selectedDevice: NetBoxDevice | null;
}) {
  return (
    <article className="panel detail-panel">
      <div className="panel-title"><Database size={20} /> Qurğu detalları</div>
      {!selectedDevice && <p className="muted-text">Qurğu seçin.</p>}
      {isLoading && <p className="muted-text">Detallar yüklənir...</p>}
      {isError && <p className="error-text">{error?.message}</p>}
      {detail && (
        <>
          <div className="cache-line">
            <span className={detail.cache.hit ? 'badge good' : 'badge warn'}>Keş: {detail.cache.hit ? 'hit' : 'miss'}</span>
            <code>{String(detail.cache.key ?? '')}</code>
          </div>
          <dl>
            <dt>Ad</dt><dd>{detail.name}</dd>
            <dt>Sahə / Region</dt><dd>{emptyLabel(detail.site)} / {emptyLabel(detail.region)}</dd>
            <dt>Rol</dt><dd>{emptyLabel(detail.role)}</dd>
            <dt>Tip</dt><dd>{emptyLabel(detail.manufacturer)} {emptyLabel(detail.device_type)}</dd>
            <dt>Platforma</dt><dd>{emptyLabel(detail.platform)}</dd>
            <dt>Seriya nömrəsi</dt><dd>{emptyLabel(detail.serial)}</dd>
            <dt>Əsas IP</dt><dd>{emptyLabel(detail.primary_ip)}</dd>
          </dl>
          <InterfaceList interfaces={detail.interfaces} showVendor />
        </>
      )}
    </article>
  );
}

function InventoryGraph({ graph, selectedId, onSelect }: { graph: { nodes: GraphNode[]; links: GraphLink[] }; selectedId?: string; onSelect: (node: GraphNode) => void }) {
  const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
  const [graphMode, setGraphMode] = useState<'inline' | 'expanded'>('inline');
  const [viewport, setViewport] = useState({ x: 0, y: 0, scale: 1 });
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);

  function resetViewport() {
    setViewport({ x: 0, y: 0, scale: 1 });
  }

  function moveViewport(deltaX: number, deltaY: number) {
    setViewport((current) => ({ ...current, x: current.x + deltaX, y: current.y + deltaY }));
  }

  function zoom(delta: number) {
    setViewport((current) => ({ ...current, scale: Math.min(2.4, Math.max(0.55, current.scale + delta)) }));
  }

  function onPointerDown(event: PointerEvent<SVGSVGElement>) {
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragStart({ x: event.clientX, y: event.clientY });
  }

  function onPointerMove(event: PointerEvent<SVGSVGElement>) {
    if (!dragStart) return;
    moveViewport(event.clientX - dragStart.x, event.clientY - dragStart.y);
    setDragStart({ x: event.clientX, y: event.clientY });
  }

  function onWheel(event: WheelEvent<SVGSVGElement>) {
    event.preventDefault();
    zoom(event.deltaY > 0 ? -0.08 : 0.08);
  }

  function toggleGraphMode() {
    setGraphMode((current) => (current === 'expanded' ? 'inline' : 'expanded'));
  }

  return (
    <div className={`graph-canvas ${graphMode}`}>
      <div className="graph-toolbar">
        <button type="button" onClick={() => zoom(0.12)}>+</button>
        <button type="button" onClick={() => zoom(-0.12)}>−</button>
        <button type="button" onClick={resetViewport}>sıfırla</button>
        <button type="button" onClick={toggleGraphMode}>{graphMode === 'expanded' ? 'div-ə qayıt' : 'tam pəncərə'}</button>
      </div>
      <svg
        onPointerDown={onPointerDown}
        onPointerLeave={() => setDragStart(null)}
        onPointerMove={onPointerMove}
        onPointerUp={() => setDragStart(null)}
        onWheel={onWheel}
        role="img"
        aria-label="NetBox region qrafı"
        viewBox="0 0 1440 820"
      >
        <defs>
          <filter id="glow"><feGaussianBlur stdDeviation="4" result="coloredBlur"/><feMerge><feMergeNode in="coloredBlur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        </defs>
        <g transform={`translate(${viewport.x} ${viewport.y}) scale(${viewport.scale})`}>
          {graph.links.map((link) => {
            const from = nodeById.get(link.from);
            const to = nodeById.get(link.to);
            if (!from || !to) return null;
            return <line className="graph-link" key={`${link.from}-${link.to}`} x1={from.x} y1={from.y} x2={to.x} y2={to.y} />;
          })}
          {graph.nodes.map((node) => (
            <g
              className={`graph-node ${selectedId === node.id ? 'selected' : ''}`}
              key={node.id}
              onClick={() => onSelect(node)}
              tabIndex={0}
              transform={`translate(${node.x} ${node.y})`}
            >
              <circle fill={nodeColor(node.type)} filter="url(#glow)" r={node.type === 'region' ? 34 : node.type === 'interface' ? 18 : 26} />
              <foreignObject x="-16" y="-16" width="32" height="32">
                <div className="graph-node-icon" style={{ color: nodeColor(node.type) }}><GraphNodeIcon type={node.type} /></div>
              </foreignObject>
              <text y={node.type === 'interface' ? 42 : 50}>{node.label}</text>
            </g>
          ))}
        </g>
      </svg>
      {!graph.nodes.length && <p className="muted-text">Qraf üçün məlumat yoxdur.</p>}
    </div>
  );
}

function GraphNodeIcon({ type }: { type: GraphNodeType }) {
  const size = 22;
  if (type === 'region') return <MapPinned size={size} />;
  if (type === 'site') return <Building2 size={size} />;
  if (type === 'device') return <Router size={size} />;
  return <Cable size={size} />;
}

function GraphInspector({ node, onSelectDevice }: { node: GraphNode | null; onSelectDevice: (deviceId: number) => void }) {
  if (!node) {
    return <aside className="panel inspector"><div className="panel-title"><Search size={20} /> Obyekt məlumatı</div><p className="muted-text">Qrafdan obyekt seçin.</p></aside>;
  }
  const meta = node.meta as Record<string, unknown> | undefined;
  const risks = nodeRisks(node);
  return (
    <aside className="panel inspector">
      <div className="panel-title"><Search size={20} /> {nodeTypeLabel(node.type)}: {node.label}</div>
      {!!risks.length && <div className="risk-list">{risks.map((risk) => <span key={risk} className="risk-pill warn"><AlertTriangle size={14} /> {risk}</span>)}</div>}
      <dl>
        {inspectorFields(node).map(([key, value]) => (
          <Fragment key={key}><dt>{key}</dt><dd>{value}</dd></Fragment>
        ))}
      </dl>
      {node.type === 'device' && meta?.id !== undefined && <button className="primary-button" onClick={() => onSelectDevice(Number(meta.id))} type="button">Detalları aç</button>}
    </aside>
  );
}

function nodeTypeLabel(type: GraphNodeType): string {
  return GRAPH_LEVEL_LABELS[type];
}

function inspectorFields(node: GraphNode): Array<[string, string]> {
  const meta = node.meta as NetBoxRegion | NetBoxSite | NetBoxDevice | NetBoxInterface | undefined;
  if (!meta) return [['Ad', node.label]];
  if (node.type === 'region') {
    const item = meta as NetBoxRegion;
    return [['Ad', item.name], ['Slug', emptyLabel(item.slug)], ['Təsvir', emptyLabel(item.description)]];
  }
  if (node.type === 'site') {
    const item = meta as NetBoxSite;
    return [['Ad', item.name], ['Region', emptyLabel(item.region)], ['Status', emptyLabel(item.status)], ['Ünvan', emptyLabel(item.physical_address ?? item.facility)]];
  }
  if (node.type === 'device') {
    const item = meta as NetBoxDevice;
    return [['Ad', item.name], ['Sahə / Region', `${emptyLabel(item.site)} / ${emptyLabel(item.region)}`], ['Rol', emptyLabel(item.role)], ['Tip', `${emptyLabel(item.manufacturer)} ${emptyLabel(item.device_type)}`], ['Status', emptyLabel(item.status)], ['Əsas IP', emptyLabel(item.primary_ip)]];
  }
  const item = meta as NetBoxInterface;
  return [['Ad', item.name], ['Qurğu', emptyLabel(item.device)], ['Tip', emptyLabel(item.type)], ['Status', item.enabled ? 'aktiv' : 'deaktiv'], ['MAC', emptyLabel(item.mac_address)], ['Vendor', `${emptyLabel(item.mac_vendor)} / ${emptyLabel(item.mac_oui)}`]];
}

function nodeRisks(node: GraphNode): string[] {
  const meta = node.meta as NetBoxDevice | NetBoxInterface | undefined;
  if (node.type === 'device') {
    const item = meta as NetBoxDevice | undefined;
    return [!item?.site ? 'Sahə yoxdur' : null, !item?.primary_ip ? 'Primary IP yoxdur' : null, (item?.status ?? '').toLowerCase() === 'offline' ? 'Offline' : null].filter(Boolean) as string[];
  }
  if (node.type === 'interface') {
    const item = meta as NetBoxInterface | undefined;
    return [item?.enabled === false ? 'Deaktiv' : null, item?.mac_address && (!item.mac_vendor || item.mac_vendor_source === 'unknown') ? 'Vendor tapılmadı' : null].filter(Boolean) as string[];
  }
  return [];
}

function InterfaceList({ interfaces, showDevice = false, showVendor = false }: { interfaces: NetBoxInterface[]; showDevice?: boolean; showVendor?: boolean }) {
  if (!interfaces.length) return <p className="muted-text">İnterfeys yoxdur</p>;
  return (
    <div className="interface-table">
      <h3>İnterfeyslər</h3>
      {interfaces.map((item) => (
        <div className="interface-row" key={item.id ?? item.name}>
          <b>{item.name}</b>
          {showDevice && <span>{emptyLabel(item.device)}</span>}
          <span>{emptyLabel(item.type)}</span>
          <span className={item.enabled ? 'good' : 'muted'}>{item.enabled ? 'aktiv' : 'deaktiv'}</span>
          <span className="mono">{emptyLabel(item.mac_address)}</span>
          {showVendor && <span>{emptyLabel(item.mac_vendor)} <small>{emptyLabel(item.mac_oui)} · {emptyLabel(item.mac_vendor_source)}</small></span>}
          <small>{emptyLabel(item.description)}</small>
        </div>
      ))}
    </div>
  );
}
