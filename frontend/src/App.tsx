import { Fragment, FormEvent, ReactNode, useMemo, useState, type PointerEvent, type WheelEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  Boxes,
  Building2,
  Cable,
  Cpu,
  Database,
  GitBranch,
  Layers3,
  MapPinned,
  Network,
  Radar,
  Search,
  Server,
  Router,
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
          <p className="eyebrow"><Sparkles size={14} /> Network Intelligence Platform</p>
          <h1>NetLens</h1>
          <p className="subtitle">
            Живой NetBox inventory, Redis-cached device detail, MAC/OUI enrichment и OSINT-style graph по регионам. Без сырого JSON — все слои видны и кликабельны.
          </p>
        </div>
        <div className="hero-orb" aria-hidden="true">
          <span />
          <Network size={64} />
        </div>
      </section>

      <section className="overview-grid">
        <MetricCard icon={<MapPinned size={20} />} label="Regions" value={data?.regions.length ?? 0} />
        <MetricCard icon={<Layers3 size={20} />} label="Sites" value={data?.sites.length ?? 0} />
        <MetricCard icon={<Server size={20} />} label="Devices" value={data?.devices.length ?? 0} />
        <MetricCard icon={<Network size={20} />} label="Interfaces" value={data?.interfaces.length ?? 0} />
      </section>

      {inventory.isLoading && <div className="panel shimmer">Загружаю NetBox inventory...</div>}
      {inventory.isError && <div className="panel error">NetBox inventory error: {(inventory.error as Error).message}</div>}
      {data?.status.status !== 'ok' && (
        <div className="panel warning">NetBox status: {data?.status.message ?? data?.status.status}</div>
      )}

      <nav className="tabs" aria-label="NetLens sections">
        <TabButton active={activeTab === 'inventory'} icon={<Boxes size={18} />} onClick={() => setActiveTab('inventory')}>Inventory</TabButton>
        <TabButton active={activeTab === 'graph'} icon={<Waypoints size={18} />} onClick={() => setActiveTab('graph')}>Graph view</TabButton>
        <TabButton active={activeTab === 'mac'} icon={<Cpu size={18} />} onClick={() => setActiveTab('mac')}>MAC/OUI</TabButton>
        <TabButton active={activeTab === 'ip'} icon={<Radar size={18} />} onClick={() => setActiveTab('ip')}>IP analysis</TabButton>
      </nav>

      {activeTab === 'inventory' && (
        <section className="tab-panel inventory-tab">
          <aside className="panel region-rail">
            <div className="panel-title"><MapPinned size={20} /> Regions</div>
            <div className="region-buttons">
              {(data?.regions ?? []).map((region) => (
                <button
                  className={`region-button ${region.name === selectedRegion ? 'selected' : ''}`}
                  key={region.id}
                  onClick={() => setSelectedRegionName(region.name)}
                  type="button"
                >
                  <b>{region.name}</b>
                  <span>{sitesByRegion.get(region.name)?.length ?? 0} sites</span>
                </button>
              ))}
              {!data?.regions.length && <p className="muted-text">Нет регионов или NetBox не настроен.</p>}
            </div>
          </aside>

          <section className="panel region-workspace">
            <div className="workspace-header">
              <div>
                <div className="panel-title"><Layers3 size={20} /> {selectedRegion ?? 'No region selected'}</div>
                <p className="muted-text">Sites: {selectedRegionSites.length} · Devices: {selectedRegionDevices.length} · Interfaces: {selectedRegionInterfaceCount}</p>
              </div>
              <button className="ghost-button" type="button" onClick={() => setActiveTab('graph')}>
                <GitBranch size={16} /> открыть граф
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
                <div className="panel-title"><Waypoints size={20} /> Region graph</div>
                <p className="muted-text">Граф теперь менее плотный: крупнее слои, drag/pan как на карте, zoom колесом/кнопками и режим на всё окно с возвратом в обычный div.</p>
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
            <div className="panel-title"><Cpu size={20} /> MAC/OUI enrichment</div>
            <p className="muted-text">Vendor берётся из cached Wireshark `manuf.json` (`created_at` сохраняется в кеше), lookup идёт напрямую по OID/OUI ключу без Python `manuf`.</p>
            <InterfaceList interfaces={macInterfaces} showDevice showVendor />
          </article>
        </section>
      )}

      {activeTab === 'ip' && (
        <section className="tab-panel ip-tab">
          <form className="search-card" onSubmit={submit}>
            <Search size={22} />
            <input value={input} onChange={(event) => setInput(event.target.value)} placeholder="10.255.127.60" />
            <button type="submit">Analyze IP</button>
          </form>

          {summary.isLoading && <div className="panel shimmer">Загружаю summary...</div>}
          {summary.isError && <div className="panel error">Ошибка: {(summary.error as Error).message}</div>}

          {summary.data && (
            <section className="grid">
              <article className="panel wide">
                <div className="panel-title"><Database size={20} /> NetBox Context</div>
                <dl>
                  <dt>IP</dt><dd>{summary.data.ip}</dd>
                  <dt>Known</dt><dd>{summary.data.netbox.known ? 'yes' : 'no'}</dd>
                  <dt>Device</dt><dd>{summary.data.netbox.device ?? '—'}</dd>
                  <dt>Site</dt><dd>{summary.data.netbox.site ?? '—'}</dd>
                  <dt>Region / City</dt><dd>{summary.data.netbox.region ?? '—'} / {summary.data.netbox.city ?? '—'}</dd>
                  <dt>Role</dt><dd>{summary.data.netbox.role ?? '—'}</dd>
                </dl>
                <InterfaceList interfaces={summary.data.netbox.interfaces as NetBoxInterface[]} showVendor />
              </article>

              <article className="panel">
                <div className="panel-title"><Radar size={20} /> Scan</div>
                <div className="metric">{summary.data.scan.status}</div>
                <p>Ports: {summary.data.scan.open_ports.length ? summary.data.scan.open_ports.join(', ') : 'not scanned yet'}</p>
                <p>OS: {summary.data.scan.os_guess ?? 'unknown'}</p>
              </article>

              <article className="panel">
                <div className="panel-title"><Activity size={20} /> Activity / {summary.data.activity.window}</div>
                <div className="cards">
                  <span><b>{summary.data.activity.internal_connections}</b> internal</span>
                  <span><b>{summary.data.activity.external_connections}</b> external</span>
                  <span><b>{summary.data.activity.security_events}</b> security</span>
                </div>
                <h3>Top internal destinations</h3>
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

  const nodes: GraphNode[] = [{ id: `region:${region}`, label: region, type: 'region', x: 720, y: 90 }];
  const links: GraphLink[] = [];
  const siteSpacing = 1260 / Math.max(sites.length, 1);

  sites.forEach((site, siteIndex) => {
    const siteX = 90 + siteSpacing * siteIndex + siteSpacing / 2;
    const siteNode: GraphNode = { id: `site:${site.id}`, label: site.name, type: 'site', x: siteX, y: 280, meta: site };
    nodes.push(siteNode);
    links.push({ from: `region:${region}`, to: siteNode.id });

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
      links.push({ from: siteNode.id, to: deviceNode.id });

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
        <small>{emptyLabel(device.role)} · {interfaceCount} ifaces · {emptyLabel(device.primary_ip)}</small>
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
      <div className="panel-title"><Database size={20} /> Device details cache</div>
      {!selectedDevice && <p className="muted-text">Выбери девайс — подробные данные придут через cached endpoint.</p>}
      {isLoading && <p className="muted-text">Загружаю detail...</p>}
      {isError && <p className="error-text">{error?.message}</p>}
      {detail && (
        <>
          <div className="cache-line">
            <span className={detail.cache.hit ? 'badge good' : 'badge warn'}>Redis cache: {detail.cache.hit ? 'hit' : 'miss'}</span>
            <code>{String(detail.cache.key ?? '')}</code>
          </div>
          <dl>
            <dt>Name</dt><dd>{detail.name}</dd>
            <dt>Site / Region</dt><dd>{emptyLabel(detail.site)} / {emptyLabel(detail.region)}</dd>
            <dt>Role</dt><dd>{emptyLabel(detail.role)}</dd>
            <dt>Type</dt><dd>{emptyLabel(detail.manufacturer)} {emptyLabel(detail.device_type)}</dd>
            <dt>Platform</dt><dd>{emptyLabel(detail.platform)}</dd>
            <dt>Serial</dt><dd>{emptyLabel(detail.serial)}</dd>
            <dt>Primary IP</dt><dd>{emptyLabel(detail.primary_ip)}</dd>
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
        <button type="button" onClick={resetViewport}>reset</button>
        <button type="button" onClick={toggleGraphMode}>{graphMode === 'expanded' ? 'minimize to div' : 'open full window'}</button>
      </div>
      <svg
        onPointerDown={onPointerDown}
        onPointerLeave={() => setDragStart(null)}
        onPointerMove={onPointerMove}
        onPointerUp={() => setDragStart(null)}
        onWheel={onWheel}
        role="img"
        aria-label="NetBox region graph"
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
            <g className={`graph-node ${selectedId === node.id ? 'selected' : ''}`} key={node.id} onClick={() => onSelect(node)} tabIndex={0}>
              <circle cx={node.x} cy={node.y} fill={nodeColor(node.type)} filter="url(#glow)" r={node.type === 'region' ? 34 : node.type === 'interface' ? 18 : 26} />
              <foreignObject x={node.x - 16} y={node.y - 16} width="32" height="32">
                <div className="graph-node-icon" style={{ color: nodeColor(node.type) }}><GraphNodeIcon type={node.type} /></div>
              </foreignObject>
              <text x={node.x} y={node.y + (node.type === 'interface' ? 42 : 50)}>{node.label}</text>
            </g>
          ))}
        </g>
      </svg>
      {!graph.nodes.length && <p className="muted-text">Нет данных для графа.</p>}
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
    return <aside className="panel inspector"><div className="panel-title"><Search size={20} /> Node inspector</div><p className="muted-text">Кликни по узлу на графе.</p></aside>;
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
      {node.type === 'device' && meta?.id !== undefined && <button className="primary-button" onClick={() => onSelectDevice(Number(meta.id))} type="button">Открыть detail</button>}
    </aside>
  );
}

function InterfaceList({ interfaces, showDevice = false, showVendor = false }: { interfaces: NetBoxInterface[]; showDevice?: boolean; showVendor?: boolean }) {
  if (!interfaces.length) return <p className="muted-text">Interfaces: none</p>;
  return (
    <div className="interface-table">
      <h3>Interfaces</h3>
      {interfaces.map((item) => (
        <div className="interface-row" key={item.id ?? item.name}>
          <b>{item.name}</b>
          {showDevice && <span>{emptyLabel(item.device)}</span>}
          <span>{emptyLabel(item.type)}</span>
          <span className={item.enabled ? 'good' : 'muted'}>{item.enabled ? 'enabled' : 'disabled'}</span>
          <span className="mono">{emptyLabel(item.mac_address)}</span>
          {showVendor && <span>{emptyLabel(item.mac_vendor)} <small>{emptyLabel(item.mac_oui)} · {emptyLabel(item.mac_vendor_source)}</small></span>}
          <small>{emptyLabel(item.description)}</small>
        </div>
      ))}
    </div>
  );
}
