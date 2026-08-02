import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { Clock, GitBranch, Loader2, RefreshCw, RotateCcw, Search } from 'lucide-react';
import type { InventoryStatus, NetBoxDevice, NetBoxInterface, NetBoxRegion, NetBoxSite } from '../api';
import { DeviceDetailPanel } from '../components/DeviceDetailPanel';
import { DeviceRow } from '../components/DeviceRow';
import { LoadingPanel } from '../components/LoadingPanel';
import { groupDevicesBySite, groupInterfacesByDevice, groupSitesByRegion } from '../lib/grouping';
import {
  devicePassesFilters,
  interfacePassesFilters,
  regionPassesFilters,
  sitePassesFilters,
} from '../lib/inventoryFilters';
import { emptyLabel, statusClass } from '../lib/format';
import { cn, ui } from '../lib/ui';

type InventoryPageProps = {
  data: {
    regions: NetBoxRegion[];
    sites: NetBoxSite[];
    devices: NetBoxDevice[];
    interfaces: NetBoxInterface[];
  } | undefined;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  selectedDeviceId: number | null;
  onSelectDevice: (id: number) => void;
  onOpenGraph: () => void;
  search: string;
  onSearchChange: (v: string) => void;
  selectedRegionName: string | null;
  onRegionChange: (name: string) => void;
  selectedDeviceDetail: {
    data: import('../api').NetBoxDeviceDetail | undefined;
    isLoading: boolean;
    isError: boolean;
    error: Error | null;
  };
  inventoryStatus?: InventoryStatus;
  onRefreshInventory?: () => void;
  onResetInventory?: () => void;
  isResettingInventory?: boolean;
  resetInventoryMessage?: string;
  resetInventoryError?: boolean;
};

export function InventoryPage({
  data, isLoading, isError, error,
  selectedDeviceId, onSelectDevice, onOpenGraph,
  search, onSearchChange,
  selectedRegionName, onRegionChange,
  selectedDeviceDetail,
  inventoryStatus, onRefreshInventory, onResetInventory, isResettingInventory,
  resetInventoryMessage, resetInventoryError,
}: InventoryPageProps) {
  const normalizedSearch = search.trim().toLowerCase();

  const allInterfacesByDevice = useMemo(() => groupInterfacesByDevice(data?.interfaces ?? []), [data?.interfaces]);
  const filteredDevices = useMemo(
    () => (data?.devices ?? []).filter((d) => devicePassesFilters(d, allInterfacesByDevice.get(d.id) ?? [], normalizedSearch, 'all')),
    [allInterfacesByDevice, data?.devices, normalizedSearch],
  );
  const filteredInterfaces = useMemo(
    () => (data?.interfaces ?? []).filter((i) => interfacePassesFilters(i, filteredDevices, normalizedSearch, 'all')),
    [data?.interfaces, filteredDevices, normalizedSearch],
  );
  const filteredSites = useMemo(
    () => (data?.sites ?? []).filter((s) => sitePassesFilters(s, filteredDevices, filteredInterfaces, normalizedSearch, 'all')),
    [data?.sites, filteredDevices, filteredInterfaces, normalizedSearch],
  );
  const filteredRegions = useMemo(
    () => (data?.regions ?? []).filter((r) => regionPassesFilters(r, filteredSites, filteredDevices, normalizedSearch, 'all')),
    [data?.regions, filteredDevices, filteredSites, normalizedSearch],
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

  if (isLoading) return <LoadingPanel label="NetBox inventarı yüklənir..." />;
  if (isError) return <div className={cn(ui.panel, 'border-red-200 bg-red-50 text-red-700 text-sm')}>NetBox xətası: {error?.message}</div>;

  return (
    <motion.section className={ui.inventoryLayout} {...{ initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.2, ease: 'easeOut' } }}>
      <aside className={ui.stickyPanel}>
        <div className={ui.panelTitle}>Regionlar</div>
        <div className="relative mt-3"><Search size={13} className="absolute left-3 top-3 text-gray-400" /><input className={cn(ui.input, 'pl-8')} value={search} onChange={(event) => onSearchChange(event.target.value)} placeholder="Axtar…" /></div>
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
              onClick={() => onRegionChange(region.name)}
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
            {inventoryStatus?.last_refresh_at && (
              <p className="mt-1 flex items-center gap-1 text-[11px] text-gray-400">
                <Clock size={10} />
                Son yenilənmə: {new Date(inventoryStatus.last_refresh_at).toLocaleString('az-AZ')}
              </p>
            )}
            {resetInventoryMessage && (
              <p className={`mt-1 text-[11px] ${resetInventoryError ? 'text-red-600' : 'text-blue-600'}`}>
                {resetInventoryMessage}
              </p>
            )}
          </div>
          <div className="flex gap-2">
            {onRefreshInventory && (
              <button className={ui.ghostButton} type="button" onClick={onRefreshInventory}>
                <RefreshCw size={14} /> Yenilə
              </button>
            )}
            {onResetInventory && (
              <button
                className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium text-red-700 transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60"
                type="button"
                onClick={onResetInventory}
                disabled={isResettingInventory}
              >
                {isResettingInventory ? <Loader2 className="animate-spin" size={14} /> : <RotateCcw size={14} />}
                {isResettingInventory ? 'Yenidən yüklənir…' : 'NetBox-u sıfırla'}
              </button>
            )}
            <button className={ui.ghostButton} type="button" onClick={onOpenGraph}><GitBranch size={14} /> Qraf</button>
          </div>
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
                  <DeviceRow key={device.id} device={device} interfaceCount={interfacesByDevice.get(device.id)?.length ?? 0} selected={device.id === selectedDeviceId} onSelect={() => onSelectDevice(device.id)} />
                ))}
              </div>
            </article>
          ))}
        </div>
      </section>

      <DeviceDetailPanel detail={selectedDeviceDetail.data} isError={selectedDeviceDetail.isError} isLoading={selectedDeviceDetail.isLoading} error={selectedDeviceDetail.error} selectedDevice={selectedDevice} />
    </motion.section>
  );
}
