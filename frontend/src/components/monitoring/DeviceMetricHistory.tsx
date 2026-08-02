import { useQuery } from '@tanstack/react-query';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { fetchDeviceMetricHistory } from '../../api';

export function DeviceMetricHistory({ deviceId }: { deviceId: string }) {
  const query = useQuery({
    queryKey: ['device-metric-history', deviceId],
    queryFn: () => fetchDeviceMetricHistory(deviceId),
    staleTime: 30_000,
  });
  if (query.isLoading) return <p className="text-xs text-gray-400">Tarix yüklənir…</p>;
  if (query.isError) return <p className="text-xs text-red-500">Metric history əlçatan deyil</p>;
  const byTime = new Map<string, Record<string, string | number | null>>();
  for (const item of query.data?.items ?? []) {
    const row = byTime.get(item.timestamp) ?? {
      timestamp: item.timestamp,
      time: new Date(item.timestamp).toLocaleTimeString('az-AZ', { hour: '2-digit', minute: '2-digit' }),
    };
    row[item.metric_name] = item.metric_value;
    byTime.set(item.timestamp, row);
  }
  const data = Array.from(byTime.values());
  if (!data.length) return <p className="text-xs text-gray-400">Tarixi metric hələ toplanmayıb</p>;
  return (
    <div className="h-44 rounded-lg border border-gray-200 bg-white p-2">
      <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-gray-400">24 saatlıq tarix</div>
      <ResponsiveContainer width="100%" height="90%">
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis dataKey="time" tick={{ fontSize: 9 }} minTickGap={28} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 9 }} />
          <Tooltip />
          <Line type="monotone" dataKey="cpu.system" name="CPU" stroke="#3b82f6" dot={false} connectNulls={false} />
          <Line type="monotone" dataKey="memory.system" name="Memory" stroke="#8b5cf6" dot={false} connectNulls={false} />
          <Line type="monotone" dataKey="disk.usage" name="Disk" stroke="#f59e0b" dot={false} connectNulls={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
