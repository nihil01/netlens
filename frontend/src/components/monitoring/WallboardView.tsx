import { useEffect, useMemo, useState } from 'react';
import { Maximize2, X } from 'lucide-react';
import type { AggregateMetrics, MonitoringDashboard } from '../../api';
import { DeviceMetricsCharts } from './DeviceMetricsCharts';

const DEVICES_PER_PAGE = 4;

function metricValue(metric: AggregateMetrics, key: 'cpu_percent' | 'memory_percent' | 'disk_percent') {
  const value = metric[key];
  return value === null ? 'N/A' : `${value.toFixed(1)}%`;
}

export function WallboardView({ data, onClose }: { data: MonitoringDashboard; onClose: () => void }) {
  const [page, setPage] = useState(0);
  const devices = useMemo(
    () => [...data.devices]
      .filter((device) => device.id)
      .sort((a, b) => (a.name || a.host_name || '').localeCompare(b.name || b.host_name || '')),
    [data.devices],
  );
  const metricsByDevice = useMemo(
    () => new Map(data.aggregate_metrics.map((item) => [item.device_id, item])),
    [data.aggregate_metrics],
  );
  const pageCount = 1 + Math.max(1, Math.ceil(devices.length / DEVICES_PER_PAGE));

  useEffect(() => {
    const timer = window.setInterval(() => setPage((current) => (current + 1) % pageCount), 15_000);
    return () => window.clearInterval(timer);
  }, [pageCount]);

  useEffect(() => {
    if (page >= pageCount) setPage(0);
  }, [page, pageCount]);

  const topCpu = useMemo(
    () => [...data.aggregate_metrics]
      .filter((item) => item.cpu_percent !== null)
      .sort((a, b) => (b.cpu_percent ?? -1) - (a.cpu_percent ?? -1))
      .slice(0, 8),
    [data.aggregate_metrics],
  );
  const stale = data.source_freshness.filter((item) => item.state !== 'FRESH');
  const visibleDevices = page === 0
    ? []
    : devices.slice((page - 1) * DEVICES_PER_PAGE, page * DEVICES_PER_PAGE);

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-slate-950 p-6 text-white">
      <header className="flex items-center justify-between border-b border-slate-700 pb-4">
        <div>
          <div className="text-sm font-bold uppercase tracking-[0.25em] text-cyan-400">NetLens NOC Wallboard</div>
          <div className="mt-1 flex items-center gap-3 text-xs text-slate-400">
            <span>{data.collected_at ? new Date(data.collected_at).toLocaleString('az-AZ') : 'Never collected'}</span>
            <span className="rounded-full border border-cyan-900 bg-cyan-950 px-2 py-0.5 text-cyan-300">Metrics · 5 dəqiqədən bir</span>
          </div>
        </div>
        <button onClick={onClose} className="rounded-lg border border-slate-600 p-2 hover:bg-slate-800"><X /></button>
      </header>

      {page === 0 ? (
        <main className="mt-6 grid h-[calc(100vh-110px)] grid-cols-4 grid-rows-[auto_1fr] gap-4">
          {[
            ['Devices', data.devices_total, 'text-white'],
            ['Connected', data.devices_connected, 'text-emerald-400'],
            ['Disconnected', data.devices_total - data.devices_connected, 'text-red-400'],
            ['VPN UP', data.tunnel_up, 'text-emerald-400'],
            ['VPN DOWN', data.tunnel_down, 'text-red-400'],
            ['Alerts', data.alerts_count, 'text-amber-400'],
            ['Stale sources', stale.length, stale.length ? 'text-red-400' : 'text-emerald-400'],
            ['Unknown VPN', data.tunnel_unknown, 'text-slate-300'],
          ].map(([label, value, color]) => (
            <section key={label} className="rounded-2xl border border-slate-700 bg-slate-900 p-5">
              <div className="text-sm uppercase tracking-wider text-slate-400">{label}</div>
              <div className={`mt-2 text-5xl font-black ${color}`}>{value}</div>
            </section>
          ))}
          <section className="col-span-2 overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 p-5">
            <h2 className="text-xl font-bold">Top CPU</h2>
            <div className="mt-4 space-y-3">
              {topCpu.map((metric) => (
                <div key={metric.device_id} className="grid grid-cols-[1fr_100px] items-center gap-3">
                  <span className="truncate text-lg">{metric.device_name || metric.device_id}</span>
                  <span className="text-right text-xl font-bold text-cyan-400">{metricValue(metric, 'cpu_percent')}</span>
                </div>
              ))}
            </div>
          </section>
          <section className="col-span-2 overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 p-5">
            <h2 className="text-xl font-bold">Data freshness</h2>
            <div className="mt-4 grid grid-cols-2 gap-3">
              {data.source_freshness.map((source) => (
                <div key={source.source} className="rounded-lg bg-slate-800 p-3">
                  <div className="truncate text-sm text-slate-300">{source.source.replaceAll('_', ' ')}</div>
                  <div className={`mt-1 text-xl font-black ${source.state === 'FRESH' ? 'text-emerald-400' : source.state === 'DEGRADED' ? 'text-amber-400' : 'text-red-400'}`}>{source.state}</div>
                </div>
              ))}
            </div>
          </section>
        </main>
      ) : (
        <main className="mt-4 grid h-[calc(100vh-100px)] grid-cols-2 grid-rows-2 gap-3 overflow-hidden">
          {visibleDevices.map((device) => (
            <DeviceMetricsCharts
              key={device.id}
              deviceId={device.id as string}
              deviceName={device.name || device.host_name || device.id || 'Unknown device'}
              metrics={metricsByDevice.get(device.id)}
              variant="wallboard"
            />
          ))}
        </main>
      )}

      <div className="fixed bottom-2 left-1/2 flex -translate-x-1/2 items-center gap-2 text-xs text-slate-500">
        <Maximize2 size={12} />Auto rotation · {page + 1}/{pageCount}
      </div>
    </div>
  );
}
