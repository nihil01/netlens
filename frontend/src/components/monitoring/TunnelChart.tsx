import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';
import { ui } from '../../lib/ui';

type TunnelChartProps = {
  tunnel_up: number;
  tunnel_down: number;
  tunnel_unknown: number;
};

const COLORS = {
  UP: '#10b981',
  DOWN: '#ef4444',
  UNKNOWN: '#9ca3af',
};

export function TunnelChart({ tunnel_up, tunnel_down, tunnel_unknown }: TunnelChartProps) {
  const data = [
    { name: 'UP', value: tunnel_up, color: COLORS.UP },
    { name: 'DOWN', value: tunnel_down, color: COLORS.DOWN },
    { name: 'UNKNOWN', value: tunnel_unknown, color: COLORS.UNKNOWN },
  ].filter((d) => d.value > 0);

  const total = tunnel_up + tunnel_down + tunnel_unknown;

  if (total === 0) {
    return (
      <div className={ui.panel}>
        <div className={ui.panelTitle}>Tunnel Status</div>
        <p className="mt-4 text-center text-sm text-gray-400">Məlumat yoxdur</p>
      </div>
    );
  }

  return (
    <div className={ui.panel}>
      <div className={ui.panelTitle}>Tunnel Status</div>
      <div className="mt-4 flex items-center justify-center">
        <ResponsiveContainer width="100%" height={220}>
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={55}
              outerRadius={85}
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
              formatter={(value, name) => [`${value} tunnel`, name]}
            />
            <Legend
              verticalAlign="bottom"
              height={36}
              formatter={(value: string) => <span className="text-xs text-gray-600">{value}</span>}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      {/* Center label */}
      <div className="-mt-2 text-center">
        <span className="text-2xl font-bold text-gray-900">{total}</span>
        <span className="ml-1 text-xs text-gray-500">ümumi</span>
      </div>
    </div>
  );
}
