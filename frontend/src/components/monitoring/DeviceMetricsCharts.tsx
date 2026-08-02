import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Activity, ChevronLeft, ChevronRight, History, RefreshCw } from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { fetchDeviceMetricHistory } from '../../api';
import type { AggregateMetrics } from '../../api';
import { cn } from '../../lib/ui';

const FIVE_MINUTES = 300_000;

type ChartRow = {
  timestamp: string;
  time: string;
  cpu: number | null;
  memory: number | null;
  disk: number | null;
};

type TrafficRow = {
  interfaceId: string;
  name: string;
  rx: number | null;
  tx: number | null;
};

type TrafficSnapshot = {
  timestamp: string;
  items: TrafficRow[];
};

function formatPercent(value: number | null | undefined) {
  return value === null || value === undefined ? 'N/A' : `${value.toFixed(1)}%`;
}

function formatBytes(value: number | null | undefined, compact = false) {
  if (value === null || value === undefined) return 'N/A';
  if (value === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const unit = Math.min(Math.floor(Math.log(Math.abs(value)) / Math.log(1024)), units.length - 1);
  const result = value / 1024 ** Math.max(0, unit);
  return `${result.toFixed(compact ? 0 : 1)} ${units[Math.max(0, unit)]}`;
}

function MetricLineChart({
  data,
  dataKey,
  label,
  color,
  current,
  dark,
  compact,
}: {
  data: ChartRow[];
  dataKey: 'cpu' | 'memory' | 'disk';
  label: string;
  color: string;
  current: number | null;
  dark: boolean;
  compact: boolean;
}) {
  return (
    <div className={cn('rounded-lg border p-2', dark ? 'border-slate-700 bg-slate-900' : 'border-gray-100 bg-gray-50/60')}>
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className={cn('text-[10px] font-bold uppercase tracking-wider', dark ? 'text-slate-400' : 'text-gray-500')}>{label}</span>
        <span className="text-sm font-black" style={{ color }}>{formatPercent(current)}</span>
      </div>
      <div className={compact ? 'h-16' : 'h-24'}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -30 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={dark ? '#334155' : '#e5e7eb'} />
            <XAxis dataKey="time" tick={{ fontSize: 8, fill: dark ? '#94a3b8' : '#6b7280' }} minTickGap={24} />
            <YAxis domain={[0, 100]} tick={{ fontSize: 8, fill: dark ? '#94a3b8' : '#6b7280' }} />
            <Tooltip
              formatter={(value) => [formatPercent(typeof value === 'number' ? value : null), label]}
              contentStyle={dark ? { background: '#0f172a', borderColor: '#475569', color: '#fff' } : undefined}
            />
            <Line
              type="monotone"
              dataKey={dataKey}
              name={label}
              stroke={color}
              strokeWidth={2}
              dot={data.length < 2}
              connectNulls={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function DeviceMetricsCharts({
  deviceId,
  deviceName,
  metrics,
  variant = 'standard',
}: {
  deviceId: string;
  deviceName: string;
  metrics?: AggregateMetrics;
  variant?: 'standard' | 'wallboard';
}) {
  const dark = variant === 'wallboard';
  const compact = variant === 'wallboard';
  const [historyHours, setHistoryHours] = useState(2);
  const [selectedTrafficTimestamp, setSelectedTrafficTimestamp] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ['device-metric-history', deviceId, 'charts', historyHours],
    queryFn: () => fetchDeviceMetricHistory(deviceId, undefined, historyHours),
    staleTime: FIVE_MINUTES - 30_000,
    refetchInterval: FIVE_MINUTES,
    refetchIntervalInBackground: true,
  });

  const history = useMemo(() => {
    const byTime = new Map<string, ChartRow>();
    for (const item of query.data?.items ?? []) {
      if (item.interface_id) continue;
      const row = byTime.get(item.timestamp) ?? {
        timestamp: item.timestamp,
        time: new Date(item.timestamp).toLocaleTimeString('az-AZ', { hour: '2-digit', minute: '2-digit' }),
        cpu: null,
        memory: null,
        disk: null,
      };
      if (item.metric_name === 'cpu.system') row.cpu = item.metric_value;
      if (item.metric_name === 'memory.system') row.memory = item.metric_value;
      if (item.metric_name === 'disk.usage') row.disk = item.metric_value;
      byTime.set(item.timestamp, row);
    }
    const rows = Array.from(byTime.values()).sort((a, b) => a.timestamp.localeCompare(b.timestamp));
    if (!rows.length && metrics) {
      const now = new Date().toISOString();
      rows.push({
        timestamp: now,
        time: new Date(now).toLocaleTimeString('az-AZ', { hour: '2-digit', minute: '2-digit' }),
        cpu: metrics.cpu_percent,
        memory: metrics.memory_percent,
        disk: metrics.disk_percent,
      });
    }
    return rows;
  }, [metrics, query.data?.items]);

  const trafficSnapshots = useMemo<TrafficSnapshot[]>(() => {
    const interfaceNames = new Map(
      (metrics?.interface_traffic ?? []).map((item) => [item.interface_id, item.name || item.interface_id]),
    );
    const snapshots = new Map<string, Map<string, TrafficRow>>();
    for (const item of query.data?.items ?? []) {
      if (!item.interface_id || !['interface.input_bytes_avg', 'interface.output_bytes_avg'].includes(item.metric_name)) continue;
      const interfaces = snapshots.get(item.timestamp) ?? new Map<string, TrafficRow>();
      const row = interfaces.get(item.interface_id) ?? {
        interfaceId: item.interface_id,
        name: interfaceNames.get(item.interface_id) || item.interface_id,
        rx: null,
        tx: null,
      };
      if (item.metric_name === 'interface.input_bytes_avg') row.rx = item.metric_value;
      if (item.metric_name === 'interface.output_bytes_avg') row.tx = item.metric_value;
      interfaces.set(item.interface_id, row);
      snapshots.set(item.timestamp, interfaces);
    }
    return Array.from(snapshots.entries())
      .map(([timestamp, interfaces]) => ({
        timestamp,
        items: Array.from(interfaces.values())
          .sort((a, b) => ((b.rx ?? 0) + (b.tx ?? 0)) - ((a.rx ?? 0) + (a.tx ?? 0))),
      }))
      .sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  }, [metrics?.interface_traffic, query.data?.items]);

  const requestedTrafficIndex = selectedTrafficTimestamp
    ? trafficSnapshots.findIndex((snapshot) => snapshot.timestamp === selectedTrafficTimestamp)
    : trafficSnapshots.length - 1;
  const selectedTrafficIndex = requestedTrafficIndex >= 0
    ? requestedTrafficIndex
    : Math.max(0, trafficSnapshots.length - 1);
  const selectedTrafficSnapshot = trafficSnapshots[selectedTrafficIndex];
  const traffic = selectedTrafficSnapshot?.items ?? [...(metrics?.interface_traffic ?? [])]
    .map((item) => ({
      interfaceId: item.interface_id || item.name || 'unknown',
      name: item.name || item.interface_id || 'unknown',
      rx: item.input_bytes_avg,
      tx: item.output_bytes_avg,
    }))
    .sort((a, b) => ((b.rx ?? 0) + (b.tx ?? 0)) - ((a.rx ?? 0) + (a.tx ?? 0)));
  const trafficIsLatest = !trafficSnapshots.length || selectedTrafficIndex === trafficSnapshots.length - 1;
  const latestTimestamp = history.at(-1)?.timestamp;
  const updatedLabel = latestTimestamp
    ? new Date(latestTimestamp).toLocaleString('az-AZ')
    : query.dataUpdatedAt
      ? new Date(query.dataUpdatedAt).toLocaleString('az-AZ')
      : 'gözlənilir';

  return (
    <article className={cn(
      'rounded-xl border p-3',
      dark ? 'border-slate-700 bg-slate-950/70 text-white' : 'border-gray-200 bg-white',
    )}>
      <header className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 truncate text-sm font-bold"><Activity size={14} className="shrink-0 text-cyan-500" />{deviceName || deviceId}</h3>
          <div className={cn('mt-1 truncate font-mono text-[9px]', dark ? 'text-slate-500' : 'text-gray-400')}>{deviceId}</div>
        </div>
        <div className={cn('shrink-0 text-right text-[9px]', dark ? 'text-slate-400' : 'text-gray-500')}>
          <div className="flex items-center justify-end gap-1 font-semibold"><RefreshCw size={9} className={query.isFetching ? 'animate-spin' : ''} />5 dəqiqədən bir</div>
          <div className="mt-0.5">Son nümunə: {updatedLabel}</div>
        </div>
      </header>

      {query.isError && <div className="mb-2 text-xs text-red-500">Metric history əlçatan deyil; cari snapshot göstərilir.</div>}
      <div className="grid grid-cols-3 gap-2">
        <MetricLineChart data={history} dataKey="cpu" label="CPU" color="#06b6d4" current={metrics?.cpu_percent ?? null} dark={dark} compact={compact} />
        <MetricLineChart data={history} dataKey="memory" label="Memory" color="#8b5cf6" current={metrics?.memory_percent ?? null} dark={dark} compact={compact} />
        <MetricLineChart data={history} dataKey="disk" label="Disk" color="#f59e0b" current={metrics?.disk_percent ?? null} dark={dark} compact={compact} />
      </div>

      <div className={cn('mt-2 rounded-lg border p-2', dark ? 'border-slate-700 bg-slate-900' : 'border-gray-100 bg-gray-50/60')}>
        <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
          <div>
            <span className={cn('text-[10px] font-bold uppercase tracking-wider', dark ? 'text-slate-400' : 'text-gray-500')}>Interface traffic · bir histogram</span>
            <div className={cn('mt-0.5 flex items-center gap-1 text-[9px]', dark ? 'text-slate-500' : 'text-gray-400')}>
              <History size={9} />RX / TX average · saxlanılan 5m snapshot
            </div>
          </div>
          {!compact && (
            <div className="flex flex-wrap items-center justify-end gap-1">
              {[2, 6].map((hours) => (
                <button
                  key={hours}
                  type="button"
                  onClick={() => { setHistoryHours(hours); setSelectedTrafficTimestamp(null); }}
                  className={cn(
                    'rounded border px-1.5 py-1 text-[9px] font-semibold',
                    historyHours === hours
                      ? 'border-cyan-300 bg-cyan-50 text-cyan-700'
                      : 'border-gray-200 bg-white text-gray-500',
                  )}
                >
                  {hours} saat
                </button>
              ))}
              <button
                type="button"
                aria-label="Əvvəlki snapshot"
                disabled={!trafficSnapshots.length || selectedTrafficIndex === 0}
                onClick={() => setSelectedTrafficTimestamp(trafficSnapshots[selectedTrafficIndex - 1]?.timestamp ?? null)}
                className="rounded border border-gray-200 bg-white p-1 text-gray-500 disabled:opacity-30"
              >
                <ChevronLeft size={11} />
              </button>
              <select
                aria-label="Interface traffic snapshot vaxtı"
                value={selectedTrafficSnapshot?.timestamp ?? ''}
                onChange={(event) => setSelectedTrafficTimestamp(event.target.value || null)}
                className="max-w-40 rounded border border-gray-200 bg-white px-1.5 py-1 text-[9px] text-gray-600"
              >
                {!trafficSnapshots.length && <option value="">Cari snapshot</option>}
                {trafficSnapshots.map((snapshot) => (
                  <option key={snapshot.timestamp} value={snapshot.timestamp}>
                    {new Date(snapshot.timestamp).toLocaleString('az-AZ')}
                  </option>
                ))}
              </select>
              <button
                type="button"
                aria-label="Növbəti snapshot"
                disabled={!trafficSnapshots.length || trafficIsLatest}
                onClick={() => setSelectedTrafficTimestamp(trafficSnapshots[selectedTrafficIndex + 1]?.timestamp ?? null)}
                className="rounded border border-gray-200 bg-white p-1 text-gray-500 disabled:opacity-30"
              >
                <ChevronRight size={11} />
              </button>
              {!trafficIsLatest && (
                <button type="button" onClick={() => setSelectedTrafficTimestamp(null)} className="rounded bg-cyan-600 px-1.5 py-1 text-[9px] font-semibold text-white">
                  Son
                </button>
              )}
            </div>
          )}
        </div>
        <div className={cn('mb-1 text-[9px]', dark ? 'text-slate-500' : 'text-gray-400')}>
          {selectedTrafficSnapshot
            ? `${new Date(selectedTrafficSnapshot.timestamp).toLocaleString('az-AZ')} · ${selectedTrafficIndex + 1}/${trafficSnapshots.length}`
            : 'Tarixi snapshot gözlənilir; cari dəyər göstərilir'}
        </div>
        {traffic.length ? (
          <div className="overflow-x-auto overflow-y-hidden">
            <div style={{ width: Math.max(420, traffic.length * (compact ? 45 : 58)) }} className={compact ? 'h-20' : 'h-32'}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={traffic} margin={{ top: 4, right: 4, bottom: compact ? 0 : 18, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={dark ? '#334155' : '#e5e7eb'} />
                  <XAxis dataKey="name" angle={compact ? 0 : -25} textAnchor={compact ? 'middle' : 'end'} interval={0} tick={{ fontSize: 8, fill: dark ? '#94a3b8' : '#6b7280' }} height={compact ? 18 : 38} />
                  <YAxis tickFormatter={(value) => formatBytes(Number(value), true)} tick={{ fontSize: 8, fill: dark ? '#94a3b8' : '#6b7280' }} width={48} />
                  <Tooltip formatter={(value, name) => [formatBytes(typeof value === 'number' ? value : null), name]} contentStyle={dark ? { background: '#0f172a', borderColor: '#475569', color: '#fff' } : undefined} />
                  {!compact && <Legend wrapperStyle={{ fontSize: 10 }} />}
                  <Bar dataKey="rx" name="RX" fill="#10b981" radius={[2, 2, 0, 0]} isAnimationActive={false} />
                  <Bar dataKey="tx" name="TX" fill="#3b82f6" radius={[2, 2, 0, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        ) : (
          <div className={cn('flex items-center justify-center text-xs', compact ? 'h-20' : 'h-32', dark ? 'text-slate-500' : 'text-gray-400')}>Interface traffic məlumatı yoxdur</div>
        )}
      </div>
    </article>
  );
}
