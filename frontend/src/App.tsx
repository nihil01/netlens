import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'framer-motion';
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
  Loader2,
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
  type ActivityCounterparty,
  type UnifiedActivityEvent,
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
import { cn, motionPreset, ui } from './lib/ui';
import type { GraphLevels, GraphNode, MainTab, QuickFilter } from './types';

export function App() {
  const [input, setInput] = useState('10.255.127.60');
  const [ip, setIp] = useState('10.255.127.60');
  const [logSrcIp, setLogSrcIp] = useState('');
  const [logDstIp, setLogDstIp] = useState('');
  const [logDstPort, setLogDstPort] = useState('');
  const [submittedLogFilters, setSubmittedLogFilters] = useState({ srcIp: '', dstIp: '', dstPort: '' });
  const [selectedDeviceId, setSelectedDeviceId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<MainTab>('inventory');
  const [selectedRegionName, setSelectedRegionName] = useState<string | null>(null);
  const [selectedGraphNode, setSelectedGraphNode] = useState<GraphNode | null>(null);
  const [inventorySearch, setInventorySearch] = useState('');
  const [quickFilter, setQuickFilter] = useState<QuickFilter>('all');
  const [graphLevels, setGraphLevels] = useState<GraphLevels>({ region: true, site: true, device: true, interface: true });
  const [expandedSiteId, setExpandedSiteId] = useState<number | null>(null);
  const [collapsingSiteId, setCollapsingSiteId] = useState<number | null>(null);
  const [expandedGraphDeviceId, setExpandedGraphDeviceId] = useState<number | null>(null);
  const [collapsingGraphDeviceId, setCollapsingGraphDeviceId] = useState<number | null>(null);
  const siteCollapseTimerRef = useRef<number | null>(null);
  const deviceCollapseTimerRef = useRef<number | null>(null);

  const summary = useQuery({
    queryKey: ['ip-summary', ip, submittedLogFilters],
    queryFn: () => fetchIpSummary(ip, submittedLogFilters),
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
      if (siteCollapseTimerRef.current !== null) window.clearTimeout(siteCollapseTimerRef.current);
      if (deviceCollapseTimerRef.current !== null) window.clearTimeout(deviceCollapseTimerRef.current);
    };
  }, []);

  function clearSiteCollapseTimer() {
    if (siteCollapseTimerRef.current !== null) {
      window.clearTimeout(siteCollapseTimerRef.current);
      siteCollapseTimerRef.current = null;
    }
  }

  function clearDeviceCollapseTimer() {
    if (deviceCollapseTimerRef.current !== null) {
      window.clearTimeout(deviceCollapseTimerRef.current);
      deviceCollapseTimerRef.current = null;
    }
  }

  function animateSiteCollapse(siteId: number | null) {
    clearSiteCollapseTimer();

    if (siteId === null) {
      setCollapsingSiteId(null);
      return;
    }

    setCollapsingSiteId(siteId);
    siteCollapseTimerRef.current = window.setTimeout(() => {
      setCollapsingSiteId(null);
      siteCollapseTimerRef.current = null;
    }, 240);
  }

  function animateDeviceCollapse(deviceId: number | null) {
    clearDeviceCollapseTimer();

    if (deviceId === null) {
      setCollapsingGraphDeviceId(null);
      return;
    }

    setCollapsingGraphDeviceId(deviceId);
    deviceCollapseTimerRef.current = window.setTimeout(() => {
      setCollapsingGraphDeviceId(null);
      deviceCollapseTimerRef.current = null;
    }, 240);
  }

  function toggleSiteDevices(siteId: number) {
    if (expandedSiteId === siteId) {
      animateDeviceCollapse(expandedGraphDeviceId);
      animateSiteCollapse(expandedSiteId);
      setExpandedGraphDeviceId(null);
      setExpandedSiteId(null);
      return;
    }

    animateDeviceCollapse(expandedGraphDeviceId);
    animateSiteCollapse(expandedSiteId);
    setExpandedGraphDeviceId(null);
    setExpandedSiteId(siteId);
  }

  function toggleDeviceInterfaces(deviceId: number) {
    if (expandedGraphDeviceId === deviceId) {
      animateDeviceCollapse(expandedGraphDeviceId);
      setExpandedGraphDeviceId(null);
      return;
    }

    animateDeviceCollapse(expandedGraphDeviceId);
    setExpandedGraphDeviceId(deviceId);
  }

  function resetGraphView() {
    clearSiteCollapseTimer();
    clearDeviceCollapseTimer();
    setExpandedSiteId(null);
    setCollapsingSiteId(null);
    setExpandedGraphDeviceId(null);
    setCollapsingGraphDeviceId(null);
    setSelectedGraphNode(null);
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
        expandedGraphDeviceId,
        collapsingGraphDeviceId,
      ),
    [
      selectedRegion,
      selectedRegionSites,
      selectedRegionDevices,
      interfacesByDevice,
      graphLevels,
      expandedSiteId,
      collapsingSiteId,
      expandedGraphDeviceId,
      collapsingGraphDeviceId,
    ],
  );

  const riskSummary = useMemo(() => buildRiskSummary(data?.devices ?? [], data?.interfaces ?? []), [data?.devices, data?.interfaces]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fallbackIp = input.trim() || logSrcIp.trim() || logDstIp.trim();
    setIp(fallbackIp);
    setSubmittedLogFilters({ srcIp: logSrcIp.trim(), dstIp: logDstIp.trim(), dstPort: logDstPort.trim() });
    setActiveTab('ip');
  }

  function selectDevice(deviceId: number) {
    setSelectedDeviceId(deviceId);
    setActiveTab('inventory');
  }

  return (
    <main className={ui.appShell}>
      <motion.section
        className="relative grid min-h-[220px] overflow-hidden rounded-[36px] border border-blue-100 bg-white p-6 shadow-[0_24px_80px_rgba(37,99,235,0.12)] ring-1 ring-white/80 sm:p-8 lg:grid-cols-[1fr_280px]"
        {...motionPreset.page}
      >
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_15%_0%,rgba(59,130,246,0.14),transparent_34%),radial-gradient(circle_at_90%_20%,rgba(16,185,129,0.12),transparent_30%)]" />
        <div className="relative z-10 flex flex-col justify-center">
          <p className={ui.eyebrow}><Sparkles size={14} /> Şəbəkə analitikası</p>
          <h1 className="mt-4 text-5xl font-black tracking-tight text-slate-950 sm:text-6xl md:text-7xl">NetLens</h1>
          <p className="mt-4 max-w-2xl text-base font-semibold leading-7 text-slate-500 sm:text-lg">NetBox inventarı, qurğu detalları, MAC/OUI və IP analizi.</p>
        </div>
        <div className="relative hidden items-center justify-center lg:flex" aria-hidden="true">
          <motion.span className="absolute h-44 w-44 rounded-full bg-blue-500/15 blur-2xl" animate={{ scale: [1, 1.15, 1], opacity: [0.7, 1, 0.7] }} transition={{ repeat: Infinity, duration: 4 }} />
          <div className="relative grid h-40 w-40 place-items-center rounded-[36px] bg-gradient-to-br from-blue-600 to-emerald-500 text-white shadow-[0_24px_70px_rgba(37,99,235,0.26)]">
            <Network size={64} />
          </div>
        </div>
      </motion.section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon={<MapPinned size={20} />} label="Regionlar" value={data?.regions.length ?? 0} />
        <MetricCard icon={<Layers3 size={20} />} label="Sahələr" value={data?.sites.length ?? 0} />
        <MetricCard icon={<Server size={20} />} label="Qurğular" value={data?.devices.length ?? 0} />
        <MetricCard icon={<Network size={20} />} label="İnterfeyslər" value={data?.interfaces.length ?? 0} />
      </section>

      {inventory.isLoading && <LoadingPanel label="NetBox inventarı yüklənir..." />}
      {inventory.isError && <div className={cn(ui.panel, 'border-rose-200 bg-rose-50 text-rose-700')}>NetBox inventar xətası: {(inventory.error as Error).message}</div>}
      {data && data.status.status !== 'ok' && (
        <div className={cn(ui.panel, 'border-amber-200 bg-amber-50 text-amber-700')}>NetBox statusu: {data.status.message ?? data.status.status}</div>
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

      <nav className="flex flex-wrap gap-3 rounded-3xl border border-slate-200 bg-white p-2 shadow-[0_14px_45px_rgba(15,23,42,0.06)]" aria-label="NetLens bölmələri">
        <TabButton active={activeTab === 'inventory'} icon={<Boxes size={18} />} onClick={() => setActiveTab('inventory')}>İnventar</TabButton>
        <TabButton active={activeTab === 'graph'} icon={<Waypoints size={18} />} onClick={() => setActiveTab('graph')}>Qraf</TabButton>
        <TabButton active={activeTab === 'mac'} icon={<Cpu size={18} />} onClick={() => setActiveTab('mac')}>MAC/OUI</TabButton>
        <TabButton active={activeTab === 'ip'} icon={<Radar size={18} />} onClick={() => setActiveTab('ip')}>IP analizi</TabButton>
      </nav>

      {activeTab === 'inventory' && (
        <motion.section className={ui.inventoryLayout} {...motionPreset.page}>
          <aside className={ui.stickyPanel}>
            <div className={ui.panelTitle}><MapPinned size={20} /> Regionlar</div>
            <div className="mt-4 space-y-2">
              {(filteredRegions ?? []).map((region) => (
                <button
                  className={cn('flex w-full items-center justify-between gap-3 rounded-2xl border p-4 text-left transition focus:outline-none focus:ring-4 focus:ring-blue-100', region.name === selectedRegion ? 'border-blue-500 bg-blue-50 text-blue-700 shadow-[0_12px_30px_rgba(37,99,235,0.12)]' : 'border-slate-200 bg-slate-50 text-slate-800 hover:border-blue-200 hover:bg-blue-50')}
                  key={region.id}
                  onClick={() => setSelectedRegionName(region.name)}
                  type="button"
                >
                  <b>{region.name}</b>
                  <span className="text-xs font-black uppercase text-slate-500">{sitesByRegion.get(region.name)?.length ?? 0} sahə</span>
                </button>
              ))}
              {!data?.regions.length && <p className={ui.muted}>Region yoxdur və ya NetBox qoşulmayıb.</p>}
            </div>
          </aside>

          <section className={ui.panel}>
            <div className={ui.panelHeader}>
              <div>
                <div className={ui.panelTitle}><Layers3 size={20} /> {selectedRegion ?? 'Region seçilməyib'}</div>
                <p className={cn(ui.muted, 'mt-2')}>Sahələr: {selectedRegionSites.length} · Qurğular: {selectedRegionDevices.length} · İnterfeyslər: {selectedRegionInterfaceCount}</p>
              </div>
              <button className={ui.ghostButton} type="button" onClick={() => setActiveTab('graph')}>
                <GitBranch size={16} /> Qrafı aç
              </button>
            </div>

            <div className="mt-5 grid gap-4 lg:grid-cols-2">
              {selectedRegionSites.map((site) => (
                <motion.article className={ui.siteCard} key={site.id} layout>
                  <header className="mb-3 flex items-start justify-between gap-3">
                    <b className="text-slate-950">{site.name}</b>
                    <span className={statusClass(site.status)}>{emptyLabel(site.status)}</span>
                  </header>
                  <p className={cn(ui.muted, 'mb-4')}>{emptyLabel(site.physical_address ?? site.facility)}</p>
                  <div className="space-y-2">
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
                </motion.article>
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
        </motion.section>
      )}

      {activeTab === 'graph' && (
        <motion.section className={ui.graphLayout} {...motionPreset.page}>
          <article className={cn(ui.panel, 'space-y-4')}>
            <div className={ui.panelHeader}>
              <div>
                <div className={ui.panelTitle}><Waypoints size={20} /> Region qrafı</div>
                <p className={cn(ui.muted, 'mt-2')}>Region seçin və qrafdan obyekt açın.</p>
              </div>
              <select
                className={ui.select}
                value={selectedRegion ?? ''}
                onChange={(event) => {
                  setSelectedRegionName(event.target.value);
                  animateDeviceCollapse(expandedGraphDeviceId);
                  animateSiteCollapse(expandedSiteId);
                  setExpandedGraphDeviceId(null);
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
              expandedDeviceId={expandedGraphDeviceId}
              onToggleDevice={toggleDeviceInterfaces}
              onReset={resetGraphView}
              onToggleSite={toggleSiteDevices}
            />
          </article>
          <GraphInspector node={selectedGraphNode} onSelectDevice={selectDevice} />
        </motion.section>
      )}

      {activeTab === 'mac' && (
        <motion.section {...motionPreset.page}>
          <article className={ui.panel}>
            <div className={ui.panelHeader}>
              <div>
                <div className={ui.panelTitle}><Cpu size={20} /> MAC/OUI</div>
                <OuiStatus dataset={data?.oui_dataset} />
              </div>
              <div className="flex flex-wrap gap-2">
                <button className={ui.ghostButton} type="button" onClick={() => navigator.clipboard?.writeText(JSON.stringify(macInterfaces, null, 2))}>
                  <Copy size={16} /> Kopyala
                </button>
                <button className={ui.ghostButton} type="button" onClick={() => downloadJson('netlens-mac-oui.json', macInterfaces)}>
                  <Download size={16} /> JSON
                </button>
              </div>
            </div>
            <InterfaceList interfaces={macInterfaces} showDevice showVendor />
          </article>
        </motion.section>
      )}

      {activeTab === 'ip' && (
        <motion.section className="space-y-5" {...motionPreset.page}>
          <form className={cn(ui.panel, 'space-y-4')} onSubmit={submit}>
            <div className="grid gap-4 md:grid-cols-[auto_minmax(0,1fr)_auto] md:items-center">
              <Search className="text-blue-600" size={22} />
              <input className={ui.input} value={input} onChange={(event) => setInput(event.target.value)} placeholder="Əsas IP / fallback" />
              <button className={ui.primaryButton} type="submit" disabled={summary.isFetching}>
                {summary.isFetching ? <Loader2 className="animate-spin" size={16} /> : <Search size={16} />}
                Logları yoxla
              </button>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <label className="space-y-1 text-xs font-black uppercase tracking-wide text-slate-500">
                Src IP
                <input className={ui.input} value={logSrcIp} onChange={(event) => setLogSrcIp(event.target.value)} placeholder="10.1.1.10" />
              </label>
              <label className="space-y-1 text-xs font-black uppercase tracking-wide text-slate-500">
                Dst IP
                <input className={ui.input} value={logDstIp} onChange={(event) => setLogDstIp(event.target.value)} placeholder="8.8.8.8" />
              </label>
              <label className="space-y-1 text-xs font-black uppercase tracking-wide text-slate-500">
                Dst port
                <input className={ui.input} value={logDstPort} onChange={(event) => setLogDstPort(event.target.value)} inputMode="numeric" placeholder="443" />
              </label>
            </div>
            <p className={ui.muted}>Src/Dst boşdursa əsas IP həm mənbə, həm də təyinat kimi axtarılır. Src və ya Dst göstərsən, OpenSearch filter kimi tətbiq olunur.</p>
          </form>

          {summary.isFetching && <LoadingPanel label="NetBox və OpenSearch məlumatı yüklənir..." />}
          {summary.isError && <div className={cn(ui.panel, 'border-rose-200 bg-rose-50 text-rose-700')}>Xəta: {(summary.error as Error).message}</div>}

          {summary.data && (
            <section className={ui.twoColumnLayout}>
              <article className={cn(ui.panel, 'lg:row-span-2')}>
                <div className={ui.panelTitle}><Database size={20} /> NetBox konteksti</div>
                <dl className={cn(ui.dl, 'mt-4')}>
                  <dt>IP</dt><dd>{summary.data.ip}</dd>
                  <dt>Məlumdur</dt><dd>{summary.data.netbox.known ? 'bəli' : 'xeyr'}</dd>
                  <dt>ARP MAC</dt><dd className="font-mono">{summary.data.netbox.arp_mac_address ?? '—'}</dd>
                  <dt>Qurğu</dt><dd>{summary.data.netbox.device ?? '—'}</dd>
                  <dt>Sahə</dt><dd>{summary.data.netbox.site ?? '—'}</dd>
                  <dt>Region / Şəhər</dt><dd>{summary.data.netbox.region ?? '—'} / {summary.data.netbox.city ?? '—'}</dd>
                  <dt>Rol</dt><dd>{summary.data.netbox.role ?? '—'}</dd>
                </dl>
                <InterfaceList interfaces={summary.data.netbox.interfaces as NetBoxInterface[]} showVendor />
              </article>

              <article className={ui.panel}>
                <div className={ui.panelTitle}><Radar size={20} /> Skan</div>
                <div className="mt-4 text-4xl font-black uppercase text-emerald-700">{summary.data.scan.status}</div>
                <p className={cn(ui.muted, 'mt-3')}>Portlar: {summary.data.scan.open_ports.length ? summary.data.scan.open_ports.join(', ') : 'hələ skan edilməyib'}</p>
                <p className={ui.muted}>OS: {summary.data.scan.os_guess ?? 'bilinmir'}</p>
              </article>

              <article className={ui.panel}>
                <div className={ui.panelTitle}><Activity size={20} /> Aktivlik / {summary.data.activity.window}</div>
                {summary.data.activity.status.status !== 'ok' && (
                  <div className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm font-bold text-amber-700">
                    OpenSearch statusu: {summary.data.activity.status.message ?? summary.data.activity.status.status}
                  </div>
                )}
                <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <span className="rounded-2xl border border-slate-200 bg-slate-50 p-3 text-slate-500"><b className="block text-2xl font-black text-slate-950">{summary.data.activity.internal_connections}</b> daxili</span>
                  <span className="rounded-2xl border border-slate-200 bg-slate-50 p-3 text-slate-500"><b className="block text-2xl font-black text-slate-950">{summary.data.activity.external_connections}</b> xarici</span>
                  <span className="rounded-2xl border border-slate-200 bg-slate-50 p-3 text-slate-500"><b className="block text-2xl font-black text-slate-950">{summary.data.activity.security_events}</b> təhlükəsizlik</span>
                </div>
                <CounterpartyList title="Əsas daxili istiqamətlər" items={summary.data.activity.top_internal_destinations} />
                <CounterpartyList title="Əsas xarici istiqamətlər" items={summary.data.activity.top_external_destinations} />
                <CounterpartyList title="Daxili portlar" items={summary.data.activity.top_internal_ports} />
                <CounterpartyList title="Xarici portlar" items={summary.data.activity.top_external_ports} />
                <CounterpartyList title="Domainlər" items={summary.data.activity.top_domains} />
                <StatMap title="Mənbə statistikası" stats={summary.data.activity.source_stats} />
                <StatMap title="İndeks statistikası" stats={summary.data.activity.index_stats} />
                <ActivityEventList events={summary.data.activity.events} />
              </article>
            </section>
          )}
        </motion.section>
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

function LoadingPanel({ label }: { label: string }) {
  return (
    <div className={cn(ui.panel, 'flex items-center gap-3 text-sm font-black text-blue-700')}>
      <Loader2 className="animate-spin" size={20} />
      {label}
    </div>
  );
}

function CounterpartyList({ items, title }: { items: ActivityCounterparty[]; title: string }) {
  return (
    <div className="mt-5">
      <h3 className="text-sm font-black uppercase tracking-[0.18em] text-slate-500">{title}</h3>
      {items.length ? (
        <ul className="mt-3 space-y-2 text-sm font-semibold text-slate-700">
          {items.map((item) => (
            <li className="grid gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-3 sm:grid-cols-[minmax(0,1fr)_auto_auto]" key={`${item.ip}-${item.port}-${item.count}`}>
              <code className="break-all font-mono text-slate-950">{item.ip || '—'}</code>
              <span>dst port: {item.port ?? '*'}</span>
              <b>{item.count}</b>
            </li>
          ))}
        </ul>
      ) : (
        <p className={cn(ui.muted, 'mt-3')}>Məlumat yoxdur.</p>
      )}
    </div>
  );
}

function StatMap({ stats, title }: { stats: Record<string, number>; title: string }) {
  const entries = Object.entries(stats ?? {}).sort(([, left], [, right]) => right - left);

  return (
    <div className="mt-5">
      <h3 className="text-sm font-black uppercase tracking-[0.18em] text-slate-500">{title}</h3>
      {entries.length ? (
        <ul className="mt-3 space-y-2 text-sm font-semibold text-slate-700">
          {entries.map(([name, count]) => (
            <li className="flex items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-3" key={name}>
              <code className="min-w-0 break-all font-mono text-slate-950">{name}</code>
              <b>{count}</b>
            </li>
          ))}
        </ul>
      ) : (
        <p className={cn(ui.muted, 'mt-3')}>Məlumat yoxdur.</p>
      )}
    </div>
  );
}

function ActivityEventList({ events }: { events: UnifiedActivityEvent[] }) {
  return (
    <div className="mt-5">
      <h3 className="text-sm font-black uppercase tracking-[0.18em] text-slate-500">OpenSearch hadisələri</h3>
      {events.length ? (
        <div className="mt-3 max-h-[520px] space-y-3 overflow-auto pr-1">
          {events.map((event, index) => (
            <article className="rounded-2xl border border-slate-200 bg-slate-50 p-3 text-sm" key={`${event.index}-${event.timestamp}-${event.source_ip}-${event.destination_ip}-${index}`}>
              <div className="mb-2 flex flex-wrap items-center gap-2 text-xs font-black uppercase text-slate-500">
                <span className="rounded-full bg-white px-2 py-1 ring-1 ring-slate-200">{event.source_name}</span>
                <span className="rounded-full bg-white px-2 py-1 ring-1 ring-slate-200">{event.index}</span>
                <span>{event.timestamp ?? '—'}</span>
              </div>
              <dl className="grid gap-2 sm:grid-cols-2">
                <EventField label="src" value={`${event.source_ip ?? '—'}:${event.source_port ?? '*'}`} mono />
                <EventField label="dst" value={`${event.destination_ip ?? '—'}:${event.destination_port ?? '*'}`} mono />
                <EventField label="action" value={event.action ?? '—'} />
                <EventField label="protocol" value={event.protocol ?? '—'} />
                <EventField label="application" value={event.application ?? '—'} />
                <EventField label="user" value={event.user ?? '—'} />
                <EventField label="rule" value={event.rule ?? '—'} />
                <EventField label="policy" value={event.policy ?? '—'} />
                <EventField label="domain" value={event.domain ?? '—'} />
                <EventField label="url" value={event.url ?? '—'} />
                <EventField label="bytes/packets" value={`${event.bytes ?? '—'} / ${event.packets ?? '—'}`} />
                <EventField label="direction" value={event.direction ?? '—'} />
              </dl>
            </article>
          ))}
        </div>
      ) : (
        <p className={cn(ui.muted, 'mt-3')}>Məlumat yoxdur.</p>
      )}
    </div>
  );
}

function EventField({ label, mono = false, value }: { label: string; mono?: boolean; value: string }) {
  return (
    <div className="min-w-0 rounded-xl bg-white px-3 py-2 ring-1 ring-slate-200">
      <dt className="text-[10px] font-black uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className={cn('min-w-0 break-words font-semibold text-slate-800', mono && 'break-all font-mono text-xs')}>{value}</dd>
    </div>
  );
}

function DeviceRow({ device, interfaceCount, selected, onSelect }: { device: NetBoxDevice; interfaceCount: number; selected: boolean; onSelect: () => void }) {
  return (
    <button className={cn(ui.cardButton, selected ? ui.cardButtonActive : ui.cardButtonIdle)} type="button" onClick={onSelect}>
      <span className="min-w-0">
        <b className="block truncate text-slate-950">{device.name}</b>
        <small className="block truncate font-semibold text-slate-500">{emptyLabel(device.role)} · {interfaceCount} interfeys · {emptyLabel(device.primary_ip)}</small>
      </span>
      <em className={cn(statusClass(device.status), 'not-italic')}>{emptyLabel(device.status)}</em>
    </button>
  );
}
