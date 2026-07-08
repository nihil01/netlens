import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import {
  Boxes,
  Copy,
  Download,
  FileSpreadsheet,
  GitBranch,
  Layers3,
  Loader2,
  LogIn,
  LogOut,
  MapPinned,
  Radar,
  Search,
  Server,
  User,
  Waypoints,
} from 'lucide-react';
import {
  exportIpExcel,
  exportPdfReport,
  fetchFullAggregation,
  fetchNetBoxDeviceDetail,
  fetchNetBoxInventory,
  type FullAggregationResponse,
  type NetBoxDevice,
  type NetBoxInterface,
  type NetBoxSite,
} from './api';
import { isAuthenticated, getUser, login, logout, initAuth } from './auth';
import { DeviceDetailPanel } from './components/DeviceDetailPanel';
import { DeviceRow } from './components/DeviceRow';
import { ErrorBoundary } from './components/ErrorBoundary';
import { GraphInspector, GraphLevelToggles, InventoryGraph } from './components/InventoryGraph';
import { InventoryCommandBar } from './components/InventoryCommandBar';
import { InterfaceList } from './components/InterfaceList';
import { LoadingPanel } from './components/LoadingPanel';
import { OuiStatus, TabButton } from './components/common';
import { downloadJson, emptyLabel, isLikelyIp, statusClass, toBakuTime } from './lib/format';
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

function getDefaultDateFrom() {
  const d = new Date();
  d.setDate(d.getDate() - 7);
  return d.toISOString().slice(0, 10);
}
function getDefaultTimeFrom() {
  return '09:00';
}
function getDefaultDateTo() {
  return new Date().toISOString().slice(0, 10);
}
function getDefaultTimeTo() {
  return '18:00';
}

export function App() {
  const [authReady, setAuthReady] = useState(false);
  const [loggedIn, setLoggedIn] = useState(isAuthenticated());
  const user = getUser();

  useEffect(() => {
    initAuth().then(() => {
      setLoggedIn(isAuthenticated());
      setAuthReady(true);
    });
  }, []);

  // --- IP Analysis state ---
  const [searchSrcIp, setSearchSrcIp] = useState('');
  const [searchDstIp, setSearchDstIp] = useState('');
  const [searchDstPort, setSearchDstPort] = useState('');
  const [dateFrom, setDateFrom] = useState(getDefaultDateFrom);
  const [timeFrom, setTimeFrom] = useState(getDefaultTimeFrom);
  const [dateTo, setDateTo] = useState(getDefaultDateTo);
  const [timeTo, setTimeTo] = useState(getDefaultTimeTo);
  const [submittedFilters, setSubmittedFilters] = useState<{
    srcIp: string; dstIp: string; dstPort: string; start: string; end: string;
  } | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportingPdf, setExportingPdf] = useState(false);

  // --- Inventory state ---
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

  // --- Queries ---
  const fullQuery = useQuery<FullAggregationResponse>({
    queryKey: ['full-aggregation', submittedFilters],
    queryFn: () => fetchFullAggregation(
      submittedFilters!.srcIp || submittedFilters!.dstIp,
      submittedFilters!.start,
      submittedFilters!.end,
      {
        srcIp: submittedFilters!.srcIp || undefined,
        dstIp: submittedFilters!.dstIp || undefined,
        dstPort: submittedFilters!.dstPort || undefined,
      },
    ),
    enabled: submittedFilters !== null,
    staleTime: 0,
    gcTime: 0,
    refetchOnMount: true,
    refetchOnWindowFocus: false,
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
    () => (data?.devices ?? []).filter((d) => devicePassesFilters(d, allInterfacesByDevice.get(d.id) ?? [], normalizedSearch, quickFilter)),
    [allInterfacesByDevice, data?.devices, normalizedSearch, quickFilter],
  );
  const filteredInterfaces = useMemo(
    () => (data?.interfaces ?? []).filter((i) => interfacePassesFilters(i, filteredDevices, normalizedSearch, quickFilter)),
    [data?.interfaces, filteredDevices, normalizedSearch, quickFilter],
  );
  const filteredSites = useMemo(
    () => (data?.sites ?? []).filter((s) => sitePassesFilters(s, filteredDevices, filteredInterfaces, normalizedSearch, quickFilter)),
    [data?.sites, filteredDevices, filteredInterfaces, normalizedSearch, quickFilter],
  );
  const filteredRegions = useMemo(
    () => (data?.regions ?? []).filter((r) => regionPassesFilters(r, filteredSites, filteredDevices, normalizedSearch, quickFilter)),
    [data?.regions, filteredDevices, filteredSites, normalizedSearch, quickFilter],
  );

  const selectedRegion = selectedRegionName && filteredRegions.some((r) => r.name === selectedRegionName)
    ? selectedRegionName
    : filteredRegions[0]?.name ?? data?.regions[0]?.name ?? null;

  const sitesByRegion = useMemo(() => groupSitesByRegion(filteredSites), [filteredSites]);
  const devicesBySite = useMemo(() => groupDevicesBySite(filteredDevices), [filteredDevices]);
  const interfacesByDevice = useMemo(() => groupInterfacesByDevice(filteredInterfaces), [filteredInterfaces]);

  const selectedDevice = useMemo(() => {
    if (!selectedDeviceId) return null;
    return data?.devices.find((d) => d.id === selectedDeviceId) ?? null;
  }, [data?.devices, selectedDeviceId]);

  const selectedRegionSites = useMemo(
    () => (selectedRegion ? sitesByRegion.get(selectedRegion) ?? [] : []),
    [selectedRegion, sitesByRegion],
  );
  const selectedRegionDevices = useMemo(
    () => selectedRegionSites.flatMap((s) => devicesBySite.get(s.name) ?? []),
    [devicesBySite, selectedRegionSites],
  );
  const selectedRegionInterfaceCount = selectedRegionDevices.reduce(
    (total, d) => total + (interfacesByDevice.get(d.id)?.length ?? 0),
    0,
  );

  const macInterfaces = useMemo(() => filteredInterfaces.filter((i) => i.mac_address), [filteredInterfaces]);

  useEffect(() => {
    return () => {
      if (siteCollapseTimerRef.current !== null) window.clearTimeout(siteCollapseTimerRef.current);
      if (deviceCollapseTimerRef.current !== null) window.clearTimeout(deviceCollapseTimerRef.current);
    };
  }, []);

  function clearSiteCollapseTimer() {
    if (siteCollapseTimerRef.current !== null) { window.clearTimeout(siteCollapseTimerRef.current); siteCollapseTimerRef.current = null; }
  }
  function clearDeviceCollapseTimer() {
    if (deviceCollapseTimerRef.current !== null) { window.clearTimeout(deviceCollapseTimerRef.current); deviceCollapseTimerRef.current = null; }
  }
  function animateSiteCollapse(siteId: number | null) {
    clearSiteCollapseTimer();
    if (siteId === null) { setCollapsingSiteId(null); return; }
    setCollapsingSiteId(siteId);
    siteCollapseTimerRef.current = window.setTimeout(() => { setCollapsingSiteId(null); siteCollapseTimerRef.current = null; }, 200);
  }
  function animateDeviceCollapse(deviceId: number | null) {
    clearDeviceCollapseTimer();
    if (deviceId === null) { setCollapsingGraphDeviceId(null); return; }
    setCollapsingGraphDeviceId(deviceId);
    deviceCollapseTimerRef.current = window.setTimeout(() => { setCollapsingGraphDeviceId(null); deviceCollapseTimerRef.current = null; }, 200);
  }
  function toggleSiteDevices(siteId: number) {
    if (expandedSiteId === siteId) {
      animateDeviceCollapse(expandedGraphDeviceId); animateSiteCollapse(expandedSiteId);
      setExpandedGraphDeviceId(null); setExpandedSiteId(null); return;
    }
    animateDeviceCollapse(expandedGraphDeviceId); animateSiteCollapse(expandedSiteId);
    setExpandedGraphDeviceId(null); setExpandedSiteId(siteId);
  }
  function toggleDeviceInterfaces(deviceId: number) {
    if (expandedGraphDeviceId === deviceId) { animateDeviceCollapse(expandedGraphDeviceId); setExpandedGraphDeviceId(null); return; }
    animateDeviceCollapse(expandedGraphDeviceId); setExpandedGraphDeviceId(deviceId);
  }
  function resetGraphView() {
    clearSiteCollapseTimer(); clearDeviceCollapseTimer();
    setExpandedSiteId(null); setCollapsingSiteId(null);
    setExpandedGraphDeviceId(null); setCollapsingGraphDeviceId(null); setSelectedGraphNode(null);
  }

  const graph = useMemo(
    () => buildGraph(selectedRegion, selectedRegionSites, selectedRegionDevices, interfacesByDevice, graphLevels, expandedSiteId, collapsingSiteId, expandedGraphDeviceId, collapsingGraphDeviceId),
    [selectedRegion, selectedRegionSites, selectedRegionDevices, interfacesByDevice, graphLevels, expandedSiteId, collapsingSiteId, expandedGraphDeviceId, collapsingGraphDeviceId],
  );

  const riskSummary = useMemo(() => buildRiskSummary(data?.devices ?? [], data?.interfaces ?? []), [data?.devices, data?.interfaces]);

  // --- IP Analysis handlers ---
  function submitSearch(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const targetIp = searchSrcIp.trim() || searchDstIp.trim();
    if (!targetIp) return;
    setSubmittedFilters({
      srcIp: searchSrcIp.trim(),
      dstIp: searchDstIp.trim(),
      dstPort: searchDstPort.trim(),
      start: dateFrom && timeFrom ? `${dateFrom}T${timeFrom}:00+04:00` : '',
      end: dateTo && timeTo ? `${dateTo}T${timeTo}:00+04:00` : '',
    });
  }

  async function handleExportExcel() {
    const targetIp = searchSrcIp.trim() || searchDstIp.trim();
    if (!targetIp) return;
    setExporting(true);
    try {
      await exportIpExcel(targetIp, {
        srcIp: searchSrcIp.trim() || undefined,
        dstIp: searchDstIp.trim() || undefined,
        dstPort: searchDstPort.trim() || undefined,
        start: dateFrom && timeFrom ? `${dateFrom}T${timeFrom}:00+04:00` : undefined,
        end: dateTo && timeTo ? `${dateTo}T${timeTo}:00+04:00` : undefined,
      });
    } catch (err) { console.error('Export failed:', err); }
    finally { setExporting(false); }
  }

  async function handleExportPdf() {
    const targetIp = searchSrcIp.trim() || searchDstIp.trim();
    if (!targetIp || !submittedFilters) return;
    setExportingPdf(true);
    try {
      await exportPdfReport(targetIp, submittedFilters.start, submittedFilters.end);
    } catch (err) { console.error('PDF export failed:', err); }
    finally { setExportingPdf(false); }
  }

  function selectDevice(deviceId: number) { setSelectedDeviceId(deviceId); setActiveTab('inventory'); }

  const hasSearch = submittedFilters !== null;
  const canSearch = (searchSrcIp.trim() || searchDstIp.trim()) && dateFrom && timeFrom && dateTo && timeTo;

  return (
    <ErrorBoundary>
      <main className={ui.appShell}>
        {/* Header */}
        <motion.header {...motionPreset.page}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <img src="/logo.png" alt="Logo" className="h-10 w-10 object-contain" />
              <div>
                <h1 className="text-xl font-bold text-gray-900">NetLens</h1>
                <p className="text-sm text-gray-500">Şəbəkə Auditi · NetBox · OpenSearch</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-4 text-xs text-gray-400">
                <span className="flex items-center gap-1"><MapPinned size={14} /> {data?.regions.length ?? 0} region</span>
                <span className="flex items-center gap-1"><Layers3 size={14} /> {data?.sites.length ?? 0} sahə</span>
                <span className="flex items-center gap-1"><Server size={14} /> {data?.devices.length ?? 0} qurğu</span>
              </div>
              {authReady && (
                loggedIn ? (
                  <div className="flex items-center gap-2">
                    <span className="flex items-center gap-1 text-sm text-gray-600">
                      <User size={14} />
                      {user?.preferred_username ?? user?.sub}
                    </span>
                    <button className={ui.ghostButton} onClick={logout}>
                      <LogOut size={14} /> Çıxış
                    </button>
                  </div>
                ) : (
                  <button className={ui.primaryButton} onClick={login}>
                    <LogIn size={14} /> Giriş
                  </button>
                )
              )}
            </div>
          </div>
        </motion.header>

        {/* Status */}
        {inventory.isLoading && <LoadingPanel label="NetBox inventarı yüklənir..." />}
        {inventory.isError && <div className={cn(ui.panel, 'border-red-200 bg-red-50 text-red-700 text-sm')}>NetBox xətası: {(inventory.error as Error).message}</div>}

        {/* Tabs */}
        <nav className="flex gap-1 rounded-lg border border-gray-200 bg-white p-1">
          <TabButton active={activeTab === 'inventory'} icon={<Boxes size={16} />} onClick={() => setActiveTab('inventory')}>İnventar</TabButton>
          <TabButton active={activeTab === 'graph'} icon={<Waypoints size={16} />} onClick={() => setActiveTab('graph')}>Qraf</TabButton>
          <TabButton active={activeTab === 'mac'} icon={<Radar size={16} />} onClick={() => setActiveTab('mac')}>MAC/OUI</TabButton>
          <TabButton active={activeTab === 'ip'} icon={<Radar size={16} />} onClick={() => setActiveTab('ip')}>IP analizi</TabButton>
        </nav>

        {/* Inventory Tab */}
        {activeTab === 'inventory' && (
          <motion.section className={ui.inventoryLayout} {...motionPreset.page}>
            <aside className={ui.stickyPanel}>
              <div className={ui.panelTitle}>Regionlar</div>
              <div className="mt-3 space-y-1.5">
                {(filteredRegions ?? []).map((region) => (
                  <button
                    className={cn(
                      'flex w-full items-center justify-between rounded-lg border px-3 py-2.5 text-left text-sm transition focus:outline-none focus:ring-2 focus:ring-blue-500',
                      region.name === selectedRegion
                        ? 'border-blue-500 bg-blue-50 font-medium text-blue-700'
                        : 'border-transparent bg-gray-50 text-gray-700 hover:bg-gray-100',
                    )}
                    key={region.id}
                    onClick={() => setSelectedRegionName(region.name)}
                    type="button"
                  >
                    <span>{region.name}</span>
                    <span className="text-xs text-gray-400">{sitesByRegion.get(region.name)?.length ?? 0}</span>
                  </button>
                ))}
                {!data?.regions.length && <p className={ui.muted}>Region yoxdur.</p>}
              </div>
            </aside>

            <section className={ui.panel}>
              <div className={ui.panelHeader}>
                <div>
                  <div className={ui.panelTitle}>{selectedRegion ?? 'Region seçilməyib'}</div>
                  <p className={cn(ui.muted, 'mt-1')}>{selectedRegionSites.length} sahə · {selectedRegionDevices.length} qurğu · {selectedRegionInterfaceCount} interfeys</p>
                </div>
                <button className={ui.ghostButton} type="button" onClick={() => setActiveTab('graph')}><GitBranch size={14} /> Qraf</button>
              </div>
              <div className="mt-4 grid gap-3 lg:grid-cols-2">
                {selectedRegionSites.map((site) => (
                  <article className={ui.siteCard} key={site.id}>
                    <header className="mb-2 flex items-center justify-between">
                      <b className="text-sm text-gray-900">{site.name}</b>
                      <span className={statusClass(site.status)}>{emptyLabel(site.status)}</span>
                    </header>
                    <p className={cn(ui.muted, 'mb-3')}>{emptyLabel(site.physical_address ?? site.facility)}</p>
                    <div className="space-y-1.5">
                      {(devicesBySite.get(site.name) ?? []).map((device) => (
                        <DeviceRow key={device.id} device={device} interfaceCount={interfacesByDevice.get(device.id)?.length ?? 0} selected={device.id === selectedDeviceId} onSelect={() => selectDevice(device.id)} />
                      ))}
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <DeviceDetailPanel detail={selectedDeviceDetail.data} isError={selectedDeviceDetail.isError} isLoading={selectedDeviceDetail.isLoading} error={selectedDeviceDetail.error as Error | null} selectedDevice={selectedDevice} />
          </motion.section>
        )}

        {/* Graph Tab */}
        {activeTab === 'graph' && (
          <motion.section className={ui.graphLayout} {...motionPreset.page}>
            <article className={cn(ui.panel, 'space-y-4')}>
              <div className={ui.panelHeader}>
                <div className={ui.panelTitle}>Region qrafı</div>
                <select className={ui.select} value={selectedRegion ?? ''} onChange={(e) => { setSelectedRegionName(e.target.value); animateDeviceCollapse(expandedGraphDeviceId); animateSiteCollapse(expandedSiteId); setExpandedGraphDeviceId(null); setExpandedSiteId(null); setSelectedGraphNode(null); }}>
                  {(filteredRegions ?? []).map((r) => <option key={r.id} value={r.name}>{r.name}</option>)}
                </select>
              </div>
              <GraphLevelToggles levels={graphLevels} onChange={setGraphLevels} />
              <InventoryGraph graph={graph} selectedNode={selectedGraphNode} onSelect={setSelectedGraphNode} expandedSiteId={expandedSiteId} expandedDeviceId={expandedGraphDeviceId} onToggleDevice={toggleDeviceInterfaces} onReset={resetGraphView} onToggleSite={toggleSiteDevices} />
            </article>
            <GraphInspector node={selectedGraphNode} onSelectDevice={selectDevice} />
          </motion.section>
        )}

        {/* MAC Tab */}
        {activeTab === 'mac' && (
          <motion.section {...motionPreset.page}>
            <article className={ui.panel}>
              <div className={ui.panelHeader}>
                <div><div className={ui.panelTitle}>MAC/OUI</div><OuiStatus dataset={data?.oui_dataset} /></div>
                <div className="flex gap-2">
                  <button className={ui.ghostButton} type="button" onClick={() => navigator.clipboard?.writeText(JSON.stringify(macInterfaces, null, 2))}><Copy size={14} /> Kopyala</button>
                  <button className={ui.ghostButton} type="button" onClick={() => downloadJson('netlens-mac-oui.json', macInterfaces)}><Download size={14} /> JSON</button>
                </div>
              </div>
              <InterfaceList interfaces={macInterfaces} showDevice showVendor />
            </article>
          </motion.section>
        )}

        {/* IP Analysis Tab */}
        {activeTab === 'ip' && (
          <motion.section className="space-y-4" {...motionPreset.page}>
            {/* Search form */}
            <form className={ui.panel} onSubmit={submitSearch}>
              <div className="grid gap-3 md:grid-cols-5 md:items-end">
                <label className="space-y-1">
                  <span className="text-xs font-medium text-gray-500">Src IP</span>
                  <input className={ui.input} value={searchSrcIp} onChange={(e) => setSearchSrcIp(e.target.value)} placeholder="10.168.195.19" />
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-gray-500">Dst IP</span>
                  <input className={ui.input} value={searchDstIp} onChange={(e) => setSearchDstIp(e.target.value)} placeholder="8.8.8.8" />
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-gray-500">Dst Port</span>
                  <input className={ui.input} value={searchDstPort} onChange={(e) => setSearchDstPort(e.target.value)} inputMode="numeric" placeholder="443" />
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-gray-500">Tarixdən</span>
                  <div className="flex gap-1">
                    <input className={ui.input} type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} lang="en-GB" />
                    <input className={ui.input} type="time" value={timeFrom} onChange={(e) => setTimeFrom(e.target.value)} step="1" lang="en-GB" />
                  </div>
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-gray-500">Tarixədək</span>
                  <div className="flex gap-1">
                    <input className={ui.input} type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} lang="en-GB" />
                    <input className={ui.input} type="time" value={timeTo} onChange={(e) => setTimeTo(e.target.value)} step="1" lang="en-GB" />
                  </div>
                </label>
              </div>
              <div className="mt-3 flex gap-2">
                <button className={ui.primaryButton} type="submit" disabled={!canSearch || fullQuery.isFetching}>
                  {fullQuery.isFetching ? <Loader2 className="animate-spin" size={14} /> : <Search size={14} />}
                  Axtar
                </button>
                <button className={ui.ghostButton} type="button" disabled={exporting || !hasSearch} onClick={handleExportExcel}>
                  {exporting ? <Loader2 className="animate-spin" size={14} /> : <FileSpreadsheet size={14} />}
                  Excel
                </button>
                <button className={ui.ghostButton} type="button" disabled={exportingPdf || !hasSearch} onClick={handleExportPdf}>
                  {exportingPdf ? <Loader2 className="animate-spin" size={14} /> : <Download size={14} />}
                  PDF hesabat
                </button>
              </div>
            </form>

            {/* Results */}
            {fullQuery.isFetching && <LoadingPanel label="Məlumatlar yüklənir..." />}
            {fullQuery.isError && <div className={cn(ui.panel, 'border-red-200 bg-red-50 text-red-700 text-sm')}>Xəta: {(fullQuery.error as Error).message}</div>}

            {fullQuery.data && (() => {
              const d = fullQuery.data as FullAggregationResponse;
              return (<>
                {/* ASN Info */}
                {d.asn_info?.asn && (
                  <div className="rounded-lg border border-blue-200 bg-blue-50 p-3">
                    <div className="flex items-center gap-4 text-sm">
                      <span className="font-semibold text-blue-900">ASN: AS{d.asn_info.asn}</span>
                      <span className="text-blue-700">{d.asn_info.asn_org}</span>
                      <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800">{d.asn_info.vendor}</span>
                      <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800">{d.asn_info.category}</span>
                    </div>
                  </div>
                )}

                {/* Summary bar */}
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
                    <div className="text-lg font-bold text-gray-900">{d.total_hits.toLocaleString()}</div>
                    <div className="text-[11px] text-gray-500">Ümumi hadisə</div>
                  </div>
                  <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
                    <div className="text-lg font-bold text-gray-900">{d.domains.total}</div>
                    <div className="text-[11px] text-gray-500">Domen</div>
                  </div>
                  <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
                    <div className="text-lg font-bold text-gray-900">{d.ports.length}</div>
                    <div className="text-[11px] text-gray-500">Port</div>
                  </div>
                  <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
                    <div className="text-lg font-bold text-gray-900">{d.users.length}</div>
                    <div className="text-[11px] text-gray-500">İstifadəçi</div>
                  </div>
                </div>

                {/* Domains */}
                <AggTable
                  title="Domainlər və Tətbiqlər"
                  count={d.domains.total}
                  headers={['#', 'Domain', 'Tətbiq', 'Say', 'İlk', 'Son']}
                  rows={d.domains.buckets.map((b, i) => [
                    String(i + 1),
                    b.key.domain,
                    b.key.application,
                    b.doc_count.toLocaleString(),
                    toBakuTime(b.first_seen.value_as_string),
                    toBakuTime(b.last_seen.value_as_string),
                  ])}
                />

                {/* Top IPs with ASN + Country */}
                <AggTable
                  title="Mənbə IP-ləri (Source)"
                  count={d.ips.as_source.length}
                  headers={['#', 'IP', 'ASN', 'Təşkilat', 'Vendor', 'Ölkə', 'Say']}
                  rows={d.ips.as_source.map((item, i) => [
                    String(i + 1),
                    item.key,
                    item.asn ? `AS${item.asn}` : '—',
                    item.asn_org ?? '—',
                    item.vendor ?? '—',
                    item.country_name ?? item.country ?? '—',
                    item.doc_count.toLocaleString(),
                  ])}
                />
                <AggTable
                  title="Təyinat IP-ləri (Destination)"
                  count={d.ips.as_destination.length}
                  headers={['#', 'IP', 'ASN', 'Təşkilat', 'Vendor', 'Ölkə', 'Say']}
                  rows={d.ips.as_destination.map((item, i) => [
                    String(i + 1),
                    item.key,
                    item.asn ? `AS${item.asn}` : '—',
                    item.asn_org ?? '—',
                    item.vendor ?? '—',
                    item.country_name ?? item.country ?? '—',
                    item.doc_count.toLocaleString(),
                  ])}
                />

                {/* Ports */}
                <AggTable
                  title="Portlar"
                  count={d.ports.length}
                  headers={['#', 'Port', 'Say']}
                  rows={d.ports.map((item: { key: string; doc_count: number }, i: number) => [String(i + 1), item.key, item.doc_count.toLocaleString()])}
                />

                {/* Protocols + Actions side by side */}
                <div className="grid gap-4 lg:grid-cols-2">
                  <AggTable
                    title="Protokollar"
                    count={d.protocols.length}
                    headers={['Protokol', 'Say']}
                    rows={d.protocols.map((item: { key: string; doc_count: number }) => [item.key, item.doc_count.toLocaleString()])}
                  />
                  <AggTable
                    title="Əməliyyatlar"
                    count={d.actions.length}
                    headers={['Əməliyyat', 'Say']}
                    rows={d.actions.map((item: { key: string; doc_count: number }) => [item.key, item.doc_count.toLocaleString()])}
                  />
                </div>

                {/* Users */}
                {d.users.length > 0 && (
                  <AggTable
                    title="İstifadəçilər"
                    count={d.users.length}
                    headers={['İstifadəçi', 'Say']}
                    rows={d.users.map((item: { key: string; doc_count: number }) => [item.key, item.doc_count.toLocaleString()])}
                  />
                )}
              </>
              );
            })()}

            {!hasSearch && (
              <div className={cn(ui.panel, 'text-center text-sm text-gray-400')}>
                Src IP və ya Dst IP daxil edin, tarix seçin və "Axtar" düyməsinə basın
              </div>
            )}
          </motion.section>
        )}
      </main>
    </ErrorBoundary>
  );
}

/* --- Aggregation table component --- */
function AggTable({ title, count, headers, rows }: { title: string; count: number; headers: string[]; rows: string[][] }) {
  if (!rows.length) return null;
  return (
    <div className={ui.panel}>
      <div className="flex items-center justify-between">
        <div className={ui.panelTitle}>{title}</div>
        <span className="text-xs text-gray-400">{count} nəticə</span>
      </div>
      <div className="mt-2 max-h-[300px] overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-white">
            <tr className="border-b border-gray-200 text-left text-[11px] font-semibold uppercase text-gray-400">
              {headers.map((h) => <th className="px-3 py-1.5" key={h}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr className="border-b border-gray-50 hover:bg-gray-50" key={i}>
                {row.map((cell, j) => <td className="px-3 py-1.5 text-xs text-gray-700" key={j}>{cell}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* --- Grouping helpers --- */
function groupInterfacesByDevice(interfaces: NetBoxInterface[]) {
  const grouped = new Map<number, NetBoxInterface[]>();
  for (const item of interfaces) { if (!item.device_id) continue; grouped.set(item.device_id, [...(grouped.get(item.device_id) ?? []), item]); }
  return grouped;
}
function groupSitesByRegion(sites: NetBoxSite[]) {
  const grouped = new Map<string, NetBoxSite[]>();
  for (const site of sites) { if (!site.region) continue; grouped.set(site.region, [...(grouped.get(site.region) ?? []), site]); }
  return grouped;
}
function groupDevicesBySite(devices: NetBoxDevice[]) {
  const grouped = new Map<string, NetBoxDevice[]>();
  for (const device of devices) { if (!device.site) continue; grouped.set(device.site, [...(grouped.get(device.site) ?? []), device]); }
  return grouped;
}
