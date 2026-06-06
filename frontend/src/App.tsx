import { Fragment, FormEvent, ReactNode, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  Boxes,
  Cpu,
  Database,
  GitBranch,
  Layers3,
  MapPinned,
  Network,
  Radar,
  Search,
  Server,
  Sparkles,
  Waypoints,
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
  const selectedRegion = selectedRegionName ?? data?.regions[0]?.name ?? null;

  const sitesByRegion = useMemo(() => {
    const grouped = new Map<string, NetBoxSite[]>();
    for (const site of data?.sites ?? []) {
      if (!site.region) continue;
      grouped.set(site.region, [...(grouped.get(site.region) ?? []), site]);
    }
    return grouped;
  }, [data?.sites]);

  const devicesBySite = useMemo(() => {
    const grouped = new Map<string, NetBoxDevice[]>();
    for (const device of data?.devices ?? []) {
      if (!device.site) continue;
      grouped.set(device.site, [...(grouped.get(device.site) ?? []), device]);
    }
    return grouped;
  }, [data?.devices]);

  const interfacesByDevice = useMemo(() => {
    const grouped = new Map<number, NetBoxInterface[]>();
    for (const item of data?.interfaces ?? []) {
      if (!item.device_id) continue;
      grouped.set(item.device_id, [...(grouped.get(item.device_id) ?? []), item]);
    }
    return grouped;
  }, [data?.interfaces]);

  const selectedDevice = useMemo(() => {
    if (!selectedDeviceId) return null;
    return data?.devices.find((device) => device.id === selectedDeviceId) ?? null;
  }, [data?.devices, selectedDeviceId]);

  const selectedRegionSites = selectedRegion ? sitesByRegion.get(selectedRegion) ?? [] : [];
  const selectedRegionDevices = selectedRegionSites.flatMap((site) => devicesBySite.get(site.name) ?? []);
  const selectedRegionInterfaceCount = selectedRegionDevices.reduce(
    (total, device) => total + (interfacesByDevice.get(device.id)?.length ?? 0),
    0,
  );

  const macInterfaces = useMemo(
    () => (data?.interfaces ?? []).filter((item) => item.mac_address),
    [data?.interfaces],
  );

  const graph = useMemo(
    () => buildGraph(selectedRegion, selectedRegionSites, selectedRegionDevices, interfacesByDevice),
    [interfacesByDevice, selectedRegion, selectedRegionDevices, selectedRegionSites],
  );

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
      {data?.status.status !== 'ok' && (
        <div className="panel warning">NetBox statusu: {data?.status.message ?? data?.status.status}</div>
      )}

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
              {(data?.regions ?? []).map((region) => (
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
                {(data?.regions ?? []).map((region) => <option key={region.id} value={region.name}>{region.name}</option>)}
              </select>
            </div>
            <InventoryGraph graph={graph} selectedId={selectedGraphNode?.id} onSelect={setSelectedGraphNode} />
          </article>
          <GraphInspector node={selectedGraphNode} onSelectDevice={selectDevice} />
        </section>
      )}

      {activeTab === 'mac' && (
        <section className="tab-panel mac-tab">
          <article className="panel wide-panel">
            <div className="panel-title"><Cpu size={20} /> MAC/OUI</div>
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

function buildGraph(
  region: string | null,
  sites: NetBoxSite[],
  devices: NetBoxDevice[],
  interfacesByDevice: Map<number, NetBoxInterface[]>,
): { nodes: GraphNode[]; links: GraphLink[] } {
  if (!region) return { nodes: [], links: [] };

  const nodes: GraphNode[] = [{ id: `region:${region}`, label: region, type: 'region', x: 500, y: 70 }];
  const links: GraphLink[] = [];
  const siteSpacing = 860 / Math.max(sites.length, 1);

  sites.forEach((site, siteIndex) => {
    const siteX = 70 + siteSpacing * siteIndex + siteSpacing / 2;
    const siteNode: GraphNode = { id: `site:${site.id}`, label: site.name, type: 'site', x: siteX, y: 210, meta: site };
    nodes.push(siteNode);
    links.push({ from: `region:${region}`, to: siteNode.id });

    const siteDevices = devices.filter((device) => device.site === site.name).slice(0, 10);
    const deviceSpacing = Math.min(120, 760 / Math.max(siteDevices.length, 1));
    const startX = siteX - ((siteDevices.length - 1) * deviceSpacing) / 2;
    siteDevices.forEach((device, deviceIndex) => {
      const deviceNode: GraphNode = {
        id: `device:${device.id}`,
        label: device.name,
        type: 'device',
        x: Math.max(45, Math.min(955, startX + deviceIndex * deviceSpacing)),
        y: 360,
        meta: device,
      };
      nodes.push(deviceNode);
      links.push({ from: siteNode.id, to: deviceNode.id });

      const ifaces = (interfacesByDevice.get(device.id) ?? []).filter((iface) => iface.mac_address).slice(0, 4);
      ifaces.forEach((iface, ifaceIndex) => {
        const ifaceNode: GraphNode = {
          id: `interface:${iface.id}`,
          label: iface.name,
          type: 'interface',
          x: deviceNode.x + (ifaceIndex - (ifaces.length - 1) / 2) * 42,
          y: 505,
          meta: iface,
        };
        nodes.push(ifaceNode);
        links.push({ from: deviceNode.id, to: ifaceNode.id });
      });
    });
  });

  return { nodes, links };
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
  return (
    <div className="graph-canvas">
      <svg viewBox="0 0 1000 590" role="img" aria-label="NetBox region qrafı">
        <defs>
          <filter id="glow"><feGaussianBlur stdDeviation="4" result="coloredBlur"/><feMerge><feMergeNode in="coloredBlur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        </defs>
        {graph.links.map((link) => {
          const from = nodeById.get(link.from);
          const to = nodeById.get(link.to);
          if (!from || !to) return null;
          return <line className="graph-link" key={`${link.from}-${link.to}`} x1={from.x} y1={from.y} x2={to.x} y2={to.y} />;
        })}
        {graph.nodes.map((node) => (
          <g className={`graph-node ${selectedId === node.id ? 'selected' : ''}`} key={node.id} onClick={() => onSelect(node)} tabIndex={0}>
            <circle cx={node.x} cy={node.y} fill={nodeColor(node.type)} filter="url(#glow)" r={node.type === 'region' ? 24 : node.type === 'interface' ? 10 : 16} />
            <text x={node.x} y={node.y + (node.type === 'interface' ? 26 : 34)}>{node.label}</text>
          </g>
        ))}
      </svg>
      {!graph.nodes.length && <p className="muted-text">Qraf üçün məlumat yoxdur.</p>}
    </div>
  );
}

function GraphInspector({ node, onSelectDevice }: { node: GraphNode | null; onSelectDevice: (deviceId: number) => void }) {
  if (!node) {
    return <aside className="panel inspector"><div className="panel-title"><Search size={20} /> Obyekt məlumatı</div><p className="muted-text">Qrafdan obyekt seçin.</p></aside>;
  }
  const meta = node.meta as Record<string, unknown> | undefined;
  return (
    <aside className="panel inspector">
      <div className="panel-title"><Search size={20} /> {node.type}: {node.label}</div>
      <dl>
        {Object.entries(meta ?? { label: node.label }).slice(0, 12).map(([key, value]) => (
          <Fragment key={key}><dt>{key}</dt><dd>{typeof value === 'object' ? JSON.stringify(value) : emptyLabel(value as string | number | boolean | null | undefined)}</dd></Fragment>
        ))}
      </dl>
      {node.type === 'device' && meta?.id !== undefined && <button className="primary-button" onClick={() => onSelectDevice(Number(meta.id))} type="button">Detalları aç</button>}
    </aside>
  );
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
