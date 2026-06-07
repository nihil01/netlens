import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  Boxes,
  Copy,
  Cpu,
  Database,
  Download,
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
  type NetBoxSite,
} from './api';
import { DeviceDetailPanel } from './components/DeviceDetailPanel';
import { GraphInspector, GraphLevelToggles, InventoryGraph } from './components/InventoryGraph';
import { InventoryCommandBar } from './components/InventoryCommandBar';
import { InterfaceList } from './components/InterfaceList';
import { MetricCard, OuiStatus, TabButton } from './components/common';
import { downloadJson, emptyLabel, isLikelyIp, statusClass } from './lib/format';
import { buildGraph } from './lib/graphModel';
import {
  buildRiskSummary,
  devicePassesFilters,
  interfacePassesFilters,
  regionPassesFilters,
  sitePassesFilters,
} from './lib/inventoryFilters';
import type { GraphLevels, GraphNode, MainTab, QuickFilter } from './types';

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
  const [expandedSiteId, setExpandedSiteId] = useState<number | null>(null);
  const [collapsingSiteId, setCollapsingSiteId] = useState<number | null>(null);
  const collapseTimerRef = useRef<number | null>(null);

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

  const allInterfacesByDevice = useMemo(() => groupInterfacesByDevice(data?.interfaces ?? []), [data?.interfaces]);

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

  const sitesByRegion = useMemo(() => groupSitesByRegion(filteredSites), [filteredSites]);
  const devicesBySite = useMemo(() => groupDevicesBySite(filteredDevices), [filteredDevices]);
  const interfacesByDevice = useMemo(() => groupInterfacesByDevice(filteredInterfaces), [filteredInterfaces]);

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

  useEffect(() => {
    return () => {
      if (collapseTimerRef.current !== null) {
        window.clearTimeout(collapseTimerRef.current);
      }
    };
  }, []);

  function clearCollapseTimer() {
    if (collapseTimerRef.current !== null) {
      window.clearTimeout(collapseTimerRef.current);
      collapseTimerRef.current = null;
    }
  }

  function animateCollapse(siteId: number | null) {
    clearCollapseTimer();

    if (siteId === null) {
      setCollapsingSiteId(null);
      return;
    }

    setCollapsingSiteId(siteId);
    collapseTimerRef.current = window.setTimeout(() => {
      setCollapsingSiteId(null);
      collapseTimerRef.current = null;
    }, 240);
  }

  function toggleSiteInterfaces(siteId: number) {
    if (expandedSiteId === siteId) {
      animateCollapse(expandedSiteId);
      setExpandedSiteId(null);
      return;
    }

    animateCollapse(expandedSiteId);
    setExpandedSiteId(siteId);
  }

  const graph = useMemo(
    () =>
      buildGraph(
        selectedRegion,
        selectedRegionSites,
        selectedRegionDevices,
        interfacesByDevice,
        graphLevels,
        expandedSiteId,
        collapsingSiteId,
      ),
    [
      selectedRegion,
      selectedRegionSites,
      selectedRegionDevices,
      interfacesByDevice,
      graphLevels,
      expandedSiteId,
      collapsingSiteId,
    ],
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
                  <select
                    value={selectedRegion ?? ''}
                    onChange={(event) => {
                      setSelectedRegionName(event.target.value);
                      animateCollapse(expandedSiteId);
                      setExpandedSiteId(null);
                      setSelectedGraphNode(null);
                    }}
                  >
                {(filteredRegions ?? []).map((region) => <option key={region.id} value={region.name}>{region.name}</option>)}
              </select>
            </div>
            <GraphLevelToggles levels={graphLevels} onChange={setGraphLevels} />

            <InventoryGraph
              graph={graph}
              selectedNode={selectedGraphNode}
              onSelect={setSelectedGraphNode}
              expandedSiteId={expandedSiteId}
              onToggleSite={toggleSiteInterfaces}
            />

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
                  <dt>ARP MAC</dt><dd className="mono">{summary.data.netbox.arp_mac_address ?? '—'}</dd>
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

function groupInterfacesByDevice(interfaces: NetBoxInterface[]) {
  const grouped = new Map<number, NetBoxInterface[]>();
  for (const item of interfaces) {
    if (!item.device_id) continue;
    grouped.set(item.device_id, [...(grouped.get(item.device_id) ?? []), item]);
  }
  return grouped;
}

function groupSitesByRegion(sites: NetBoxSite[]) {
  const grouped = new Map<string, NetBoxSite[]>();
  for (const site of sites) {
    if (!site.region) continue;
    grouped.set(site.region, [...(grouped.get(site.region) ?? []), site]);
  }
  return grouped;
}

function groupDevicesBySite(devices: NetBoxDevice[]) {
  const grouped = new Map<string, NetBoxDevice[]>();
  for (const device of devices) {
    if (!device.site) continue;
    grouped.set(device.site, [...(grouped.get(device.site) ?? []), device]);
  }
  return grouped;
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
