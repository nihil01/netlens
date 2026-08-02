import { useState } from 'react';
import { ChevronDown, ChevronUp, Server, ArrowDown, ArrowUp } from 'lucide-react';
import { cn } from '../../lib/ui';
import type { AggregateMetrics, FmcDevice, MetricStatus } from '../../api';
import { DeviceMetricsCharts } from './DeviceMetricsCharts';

function formatBytes(bytes: number | null) {
  if (bytes === null) return 'N/A';
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function metricLabel(value: number | null, status: MetricStatus) {
  if (value !== null) return `${Math.round(Math.min(value, 100))}%`;
  if (status === 'PERMISSION_ERROR' || status === 'TEMPORARY_ERROR' || status === 'INVALID_RESPONSE') return 'Error';
  if (status === 'STALE_DEVICE') return 'Stale';
  return 'N/A';
}

function GaugeRing({ value, label, color, status }: { value: number | null; label: string; color: string; status: MetricStatus }) {
  const pct = value !== null ? Math.min(value, 100) : 0;
  const r = 28;
  const circ = 2 * Math.PI * r;
  const off = circ - (pct / 100) * circ;
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative h-16 w-16">
        <svg className="h-16 w-16 -rotate-90" viewBox="0 0 64 64">
          <circle cx="32" cy="32" r={r} fill="none" stroke="#f3f4f6" strokeWidth="5" />
          <circle cx="32" cy="32" r={r} fill="none" stroke={color} strokeWidth="5" strokeDasharray={circ} strokeDashoffset={off} strokeLinecap="round" className="transition-all duration-700" />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-[10px] font-bold text-gray-900">{metricLabel(value, status)}</span>
        </div>
      </div>
      <span className="text-[10px] font-medium text-gray-500">{label}</span>
    </div>
  );
}

function gaugeColor(v: number | null) {
  if (v === null) return '#d1d5db';
  if (v >= 90) return '#ef4444';
  if (v >= 70) return '#f59e0b';
  return '#10b981';
}

function TrafficBar({ label, rx, tx }: { label: string; rx: number | null; tx: number | null }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-24 shrink-0 truncate text-gray-500">{label}</span>
      <div className="flex flex-1 items-center gap-1">
        <ArrowDown size={10} className="shrink-0 text-emerald-500" />
        <span className="font-mono text-gray-700">{formatBytes(rx)}</span>
        <span className="text-gray-300">|</span>
        <ArrowUp size={10} className="shrink-0 text-blue-500" />
        <span className="font-mono text-gray-700">{formatBytes(tx)}</span>
      </div>
    </div>
  );
}

export function DeviceHealthCard({ device, metrics }: { device: FmcDevice; metrics?: AggregateMetrics }) {
  const [expanded, setExpanded] = useState(false);
  const upCount = metrics?.interfaces.filter((i) => i.operational_status === 'UP').length ?? 0;
  const downCount = metrics?.interfaces.filter((i) => i.operational_status === 'DOWN').length ?? 0;
  const totalIf = metrics?.interfaces.length ?? 0;
  const totalTraffic = metrics?.interface_traffic.reduce((sum, t) => sum + (t.input_bytes_avg ?? 0) + (t.output_bytes_avg ?? 0), 0) ?? 0;

  return (
    <div className={cn('rounded-xl border bg-white transition-all', device.is_connected ? 'border-gray-200 hover:border-gray-300' : 'border-red-200 bg-red-50/30')}>
      {/* Header */}
      <button className="flex w-full items-start gap-3 p-4 text-left" onClick={() => setExpanded(!expanded)} type="button">
        <div className={cn('mt-0.5 rounded-lg p-2', device.is_connected ? 'bg-blue-50' : 'bg-red-50')}>
          <Server size={18} className={device.is_connected ? 'text-blue-600' : 'text-red-500'} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-bold text-gray-900">{device.name || device.host_name || 'Unknown'}</span>
            <span className={cn('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold', device.is_connected ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700')}>
              <span className={cn('h-1.5 w-1.5 rounded-full', device.is_connected ? 'bg-emerald-500' : 'bg-red-500')} />
              {device.is_connected ? 'Online' : 'Offline'}
            </span>
          </div>
          <div className="mt-0.5 text-xs text-gray-500">{device.model} · {device.sw_version || '—'}</div>
          {/* Quick traffic */}
          {totalTraffic > 0 && (
            <div className="mt-1 text-[11px] text-gray-400">Traffic: <span className="font-medium text-gray-600">{formatBytes(totalTraffic)}</span></div>
          )}
        </div>
        {expanded ? <ChevronUp size={14} className="mt-1 shrink-0 text-gray-400" /> : <ChevronDown size={14} className="mt-1 shrink-0 text-gray-400" />}
      </button>

      {/* Gauge rings */}
      {metrics && (
        <div className="flex items-center justify-center gap-6 border-t border-gray-100 px-4 py-3">
          <GaugeRing value={metrics.cpu_percent} status={metrics.metric_status} label="CPU" color={gaugeColor(metrics.cpu_percent)} />
          <GaugeRing value={metrics.memory_percent} status={metrics.metric_status} label="Memory" color={gaugeColor(metrics.memory_percent)} />
          <GaugeRing value={metrics.disk_percent} status={metrics.metric_status} label="Disk" color={gaugeColor(metrics.disk_percent)} />
          {totalIf > 0 && (
            <div className="flex flex-col items-center gap-1">
              <div className="flex h-16 items-center gap-1">
                <span className="rounded bg-emerald-100 px-1.5 py-1 text-xs font-bold text-emerald-700">{upCount}</span>
                <span className="text-[10px] text-gray-400">/</span>
                <span className="rounded bg-red-100 px-1.5 py-1 text-xs font-bold text-red-700">{downCount}</span>
              </div>
              <span className="text-[10px] font-medium text-gray-500">Interfaces</span>
            </div>
          )}
        </div>
      )}

      {/* Expanded */}
      {expanded && (
        <div className="border-t border-gray-100 px-4 pb-4 pt-3 space-y-3">
          {device.id && (
            <DeviceMetricsCharts
              deviceId={device.id}
              deviceName={device.name || device.host_name || device.id}
              metrics={metrics}
            />
          )}
          {/* Hardware info */}
          <div className="rounded-lg bg-gray-50 p-3">
            <div className="text-[11px] font-bold uppercase tracking-wider text-gray-400">Hardware</div>
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              {device.serial_number && <><dt className="text-gray-500">Serial</dt><dd className="font-mono text-gray-900">{device.serial_number}</dd></>}
              {device.model_number && <><dt className="text-gray-500">Model #</dt><dd className="text-gray-900">{device.model_number}</dd></>}
              {device.performance_tier && <><dt className="text-gray-500">Performance</dt><dd className="text-gray-900">{device.performance_tier}</dd></>}
              {device.ftd_mode && <><dt className="text-gray-500">Mode</dt><dd className="text-gray-900">{device.ftd_mode}</dd></>}
              {device.snort_engine && <><dt className="text-gray-500">Snort</dt><dd className="text-gray-900">{device.snort_engine}</dd></>}
              {device.inventory?.cpu_type && <><dt className="text-gray-500">CPU</dt><dd className="text-gray-900">{device.inventory.cpu_type} ({device.inventory.cpu_cores} cores)</dd></>}
              {device.inventory?.memory_mb && <><dt className="text-gray-500">RAM</dt><dd className="text-gray-900">{device.inventory.memory_mb} MB</dd></>}
              {device.inventory?.storage_gb && <><dt className="text-gray-500">Storage</dt><dd className="text-gray-900">{device.inventory.storage_gb} GB</dd></>}
              {device.access_policy && <><dt className="text-gray-500">Access Policy</dt><dd className="text-gray-900">{device.access_policy}</dd></>}
              {device.deployment_status && <><dt className="text-gray-500">Deployment</dt><dd className="text-gray-900">{device.deployment_status}</dd></>}
            </dl>
          </div>

          {/* Licenses */}
          {device.license_caps.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {device.license_caps.map((cap) => (
                <span key={cap} className="rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium text-blue-700">{cap}</span>
              ))}
            </div>
          )}

          {/* Interface traffic */}
          {metrics && metrics.interface_traffic.length > 0 && (
            <div className="rounded-lg bg-gray-50 p-3">
              <div className="text-[11px] font-bold uppercase tracking-wider text-gray-400">Interface Traffic</div>
              <div className="mt-2 space-y-1">
                {metrics.interface_traffic
                  .filter((t) => (t.input_bytes_avg ?? 0) > 0 || (t.output_bytes_avg ?? 0) > 0)
                  .sort((a, b) => ((b.input_bytes_avg ?? 0) + (b.output_bytes_avg ?? 0)) - ((a.input_bytes_avg ?? 0) + (a.output_bytes_avg ?? 0)))
                  .slice(0, 8)
                  .map((t) => (
                    <TrafficBar key={t.interface_id || t.name} label={t.name || '—'} rx={t.input_bytes_avg} tx={t.output_bytes_avg} />
                  ))}
              </div>
            </div>
          )}

          {/* Interfaces */}
          {metrics && metrics.interfaces.length > 0 && (
            <div>
              <div className="text-[11px] font-bold uppercase tracking-wider text-gray-400">Interfaces ({totalIf})</div>
              <div className="mt-1 flex flex-wrap gap-1">
                {metrics.interfaces.map((iface) => (
                  <span key={iface.interface_name} className={cn('inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium ring-1', iface.operational_status === 'UP' ? 'bg-emerald-50 text-emerald-700 ring-emerald-200' : 'bg-red-50 text-red-700 ring-red-200')}>
                    {iface.interface_name}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
