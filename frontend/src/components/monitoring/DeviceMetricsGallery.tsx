import { useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, Search } from 'lucide-react';
import type { AggregateMetrics, FmcDevice } from '../../api';
import { cn, ui } from '../../lib/ui';
import { DeviceMetricsCharts } from './DeviceMetricsCharts';

const PAGE_SIZE = 6;

export function DeviceMetricsGallery({ devices, metrics }: { devices: FmcDevice[]; metrics: AggregateMetrics[] }) {
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const metricsByDevice = useMemo(() => new Map(metrics.map((item) => [item.device_id, item])), [metrics]);
  const filtered = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return devices
      .filter((device) => device.id)
      .filter((device) => !needle || [device.host_name, device.name, device.id].some((value) => value?.toLocaleLowerCase().includes(needle)))
      .sort((a, b) => (a.name || a.host_name || '').localeCompare(b.name || b.host_name || ''));
  }, [devices, search]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const visible = filtered.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-gray-900">Device performance</h2>
          <p className="text-xs text-gray-500">CPU, Memory, Disk və bütün interface traffic · 5 dəqiqəlik snapshot</p>
        </div>
        <div className="flex items-center gap-2">
          <label className="relative">
            <Search className="absolute left-2.5 top-2.5 text-gray-400" size={13} />
            <input
              className={cn(ui.input, 'w-60 py-2 pl-8 text-xs')}
              value={search}
              onChange={(event) => { setSearch(event.target.value); setPage(0); }}
              placeholder="Device adı və ya UUID…"
            />
          </label>
          <button type="button" className={ui.ghostButton} disabled={safePage === 0} onClick={() => setPage((value) => Math.max(0, value - 1))}><ChevronLeft size={14} /></button>
          <span className="min-w-16 text-center text-xs text-gray-500">{safePage + 1}/{pageCount}</span>
          <button type="button" className={ui.ghostButton} disabled={safePage + 1 >= pageCount} onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))}><ChevronRight size={14} /></button>
        </div>
      </div>
      {visible.length ? (
        <div className="grid gap-4 xl:grid-cols-2">
          {visible.map((device) => (
            <DeviceMetricsCharts
              key={device.id}
              deviceId={device.id as string}
              deviceName={device.name || device.host_name || device.id || 'Unknown device'}
              metrics={metricsByDevice.get(device.id)}
            />
          ))}
        </div>
      ) : (
        <div className={ui.panel}>Uyğun device tapılmadı.</div>
      )}
    </section>
  );
}
