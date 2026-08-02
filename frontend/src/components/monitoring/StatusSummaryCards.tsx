import { Server, AlertTriangle, Shield, Wifi, WifiOff } from 'lucide-react';
import { cn } from '../../lib/ui';

type SummaryCardProps = {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  subValue?: string;
  color: string;
};

function SummaryCard({ icon, label, value, subValue, color }: SummaryCardProps) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 transition hover:shadow-md">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium text-gray-500">{label}</p>
          <p className="mt-1 text-3xl font-bold text-gray-900">{value}</p>
          {subValue && <p className="mt-0.5 text-xs text-gray-400">{subValue}</p>}
        </div>
        <div className={cn('rounded-xl p-3', color)}>
          {icon}
        </div>
      </div>
    </div>
  );
}

type StatusSummaryProps = {
  tunnel_up: number;
  tunnel_down: number;
  tunnel_unknown: number;
  devices_connected: number;
  devices_total: number;
  alerts_count: number;
};

export function StatusSummaryCards({
  tunnel_up, tunnel_down, tunnel_unknown,
  devices_connected, devices_total, alerts_count,
}: StatusSummaryProps) {
  const totalTunnels = tunnel_up + tunnel_down + tunnel_unknown;

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <SummaryCard
        icon={<Shield size={24} className="text-emerald-600" />}
        label="VPN Tunnels"
        value={totalTunnels}
        subValue={`${tunnel_up} UP · ${tunnel_down} DOWN · ${tunnel_unknown} ?`}
        color="bg-emerald-50"
      />
      <SummaryCard
        icon={<Server size={24} className="text-blue-600" />}
        label="FTD Devices"
        value={`${devices_connected}/${devices_total}`}
        subValue={devices_connected === devices_total ? 'Hamısı bağlı' : `${devices_total - devices_connected} bağlı deyil`}
        color="bg-blue-50"
      />
      <SummaryCard
        icon={<AlertTriangle size={24} className="text-amber-600" />}
        label="Health Alerts"
        value={alerts_count}
        subValue={alerts_count === 0 ? 'Problem yoxdur' : 'Diqqət tələb olunur'}
        color="bg-amber-50"
      />
      <SummaryCard
        icon={tunnel_down > 0 ? <WifiOff size={24} className="text-red-600" /> : <Wifi size={24} className="text-emerald-600" />}
        label="Network Health"
        value={tunnel_down === 0 && devices_connected === devices_total ? 'YAXŞI' : 'DİQQƏT'}
        subValue={tunnel_down === 0 ? 'Bütün tunnellər aktiv' : `${tunnel_down} tunnel aşağı`}
        color={tunnel_down === 0 && devices_connected === devices_total ? 'bg-emerald-50' : 'bg-red-50'}
      />
    </div>
  );
}
