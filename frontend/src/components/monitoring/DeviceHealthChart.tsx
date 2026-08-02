import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { ui } from '../../lib/ui';
import type { AggregateMetrics } from '../../api';

type DeviceHealthChartProps = {
  metrics: AggregateMetrics[];
};

export function DeviceHealthChart({ metrics }: DeviceHealthChartProps) {
  if (metrics.length === 0) {
    return (
      <div className={ui.panel}>
        <div className={ui.panelTitle}>Device Health</div>
        <p className="mt-4 text-center text-sm text-gray-400">Məlumat yoxdur</p>
      </div>
    );
  }

  const cpuData = metrics
    .filter((m) =>
      m.cpu_percent !== null || m.memory_percent !== null || m.disk_percent !== null)
    .map((m) => ({
      name: m.device_name || 'Unknown',
      CPU: m.cpu_percent === null ? null : Math.round(m.cpu_percent),
      Memory: m.memory_percent === null ? null : Math.round(m.memory_percent),
      Disk: m.disk_percent === null ? null : Math.round(m.disk_percent),
    }));

  return (
    <div className={ui.panel}>
      <div className={ui.panelTitle}>Device Health — CPU / Memory / Disk</div>
      <div className="mt-4">
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={cpuData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
            <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#6b7280' }} />
            <YAxis tick={{ fontSize: 11, fill: '#6b7280' }} domain={[0, 100]} unit="%" />
            <Tooltip
              contentStyle={{
                backgroundColor: '#fff',
                border: '1px solid #e5e7eb',
                borderRadius: '8px',
                fontSize: '12px',
              }}
              formatter={(value, name) => [value === null ? 'N/A' : `${value}%`, name]}
            />
            <Bar dataKey="CPU" fill="#3b82f6" radius={[4, 4, 0, 0]} maxBarSize={32} />
            <Bar dataKey="Memory" fill="#8b5cf6" radius={[4, 4, 0, 0]} maxBarSize={32} />
            <Bar dataKey="Disk" fill="#f59e0b" radius={[4, 4, 0, 0]} maxBarSize={32} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      {/* Legend */}
      <div className="mt-2 flex justify-center gap-4 text-xs text-gray-500">
        <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-blue-500" /> CPU</span>
        <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-purple-500" /> Memory</span>
        <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-amber-500" /> Disk</span>
      </div>
    </div>
  );
}
