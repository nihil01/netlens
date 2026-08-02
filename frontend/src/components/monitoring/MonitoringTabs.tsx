import { LayoutDashboard, Shield, Server, AlertTriangle, Activity, ScanSearch } from 'lucide-react';
import { cn } from '../../lib/ui';

export type MonitoringTab = 'overview' | 'vpn' | 'devices' | 'ha' | 'policy' | 'alerts';

const TABS: { key: MonitoringTab; label: string; icon: React.ReactNode; count?: number }[] = [
  { key: 'overview', label: 'Ümumi', icon: <LayoutDashboard size={14} /> },
  { key: 'vpn', label: 'VPN Tunnels', icon: <Shield size={14} /> },
  { key: 'devices', label: 'Devices', icon: <Server size={14} /> },
  { key: 'ha', label: 'HA', icon: <Activity size={14} /> },
  { key: 'policy', label: 'Policy Review', icon: <ScanSearch size={14} /> },
  { key: 'alerts', label: 'Health Alerts', icon: <AlertTriangle size={14} /> },
];

export function MonitoringTabBar({ active, onChange, alertCount }: {
  active: MonitoringTab;
  onChange: (tab: MonitoringTab) => void;
  alertCount: number;
}) {
  return (
    <div className="flex gap-1 rounded-lg border border-gray-200 bg-white p-1">
      {TABS.map((tab) => (
        <button
          key={tab.key}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition focus:outline-none focus:ring-2 focus:ring-blue-500',
            active === tab.key ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-100',
          )}
          onClick={() => onChange(tab.key)}
          type="button"
        >
          {tab.icon}
          {tab.label}
          {tab.key === 'alerts' && alertCount > 0 && (
            <span className={cn(
              'ml-1 inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1 text-[10px] font-bold',
              active === tab.key ? 'bg-white text-blue-600' : 'bg-red-100 text-red-700',
            )}>
              {alertCount}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
