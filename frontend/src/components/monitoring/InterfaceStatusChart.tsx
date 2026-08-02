import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import { ui } from '../../lib/ui';
import type { AggregateMetrics } from '../../api';

type InterfaceStatusChartProps = {
  metrics: AggregateMetrics[];
};

export function InterfaceStatusChart({ metrics }: InterfaceStatusChartProps) {
  // Count all interfaces across all devices
  let upCount = 0;
  let downCount = 0;
  let unknownCount = 0;

  for (const m of metrics) {
    for (const iface of m.interfaces) {
      if (iface.operational_status === 'UP') upCount++;
      else if (iface.operational_status === 'DOWN') downCount++;
      else unknownCount++;
    }
  }

  const total = upCount + downCount + unknownCount;

  if (total === 0) {
    return (
      <div className={ui.panel}>
        <div className={ui.panelTitle}>Interface Status</div>
        <p className="mt-4 text-center text-sm text-gray-400">Məlumat yoxdur</p>
      </div>
    );
  }

  const data = [
    { name: 'UP', value: upCount, color: '#10b981' },
    { name: 'DOWN', value: downCount, color: '#ef4444' },
    { name: 'Unknown', value: unknownCount, color: '#9ca3af' },
  ].filter((d) => d.value > 0);

  return (
    <div className={ui.panel}>
      <div className={ui.panelTitle}>Interface Status</div>
      <div className="mt-2 flex items-center justify-center">
        <ResponsiveContainer width="100%" height={200}>
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={45}
              outerRadius={70}
              paddingAngle={3}
              dataKey="value"
              strokeWidth={0}
            >
              {data.map((entry) => (
                <Cell key={entry.name} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                backgroundColor: '#fff',
                border: '1px solid #e5e7eb',
                borderRadius: '8px',
                fontSize: '12px',
              }}
              formatter={(value, name) => [`${value} port`, name]}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex justify-center gap-4 text-xs">
        <span className="flex items-center gap-1 text-emerald-600">
          <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" /> {upCount} UP
        </span>
        <span className="flex items-center gap-1 text-red-600">
          <span className="inline-block h-2 w-2 rounded-full bg-red-500" /> {downCount} DOWN
        </span>
        {unknownCount > 0 && (
          <span className="flex items-center gap-1 text-gray-400">
            <span className="inline-block h-2 w-2 rounded-full bg-gray-400" /> {unknownCount} ?
          </span>
        )}
      </div>
    </div>
  );
}
