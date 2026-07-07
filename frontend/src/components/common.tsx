import type { ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { cn, ui } from '../lib/ui';

export function RiskPill({ label, value }: { label: string; value: number }) {
  return (
    <span className={value ? ui.badgeWarn : ui.badgeGood}>
      <AlertTriangle size={12} /> {label}: {value}
    </span>
  );
}

export function OuiStatus({ dataset }: { dataset?: { source?: string; source_url?: string; created_at?: string | null; records?: number; cache?: string } }) {
  return (
    <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-gray-400">
      <span className="flex items-center gap-1"><RefreshCw size={12} /> {dataset?.source ?? 'Wireshark'}</span>
      <span>{dataset?.records ?? 0} yazı</span>
      <span>{dataset?.cache ?? 'memory'}</span>
    </div>
  );
}

export function TabButton({ active, children, icon, onClick }: { active: boolean; children: ReactNode; icon: ReactNode; onClick: () => void }) {
  return (
    <button
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition focus:outline-none focus:ring-2 focus:ring-blue-500',
        active ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-100',
      )}
      onClick={onClick}
      type="button"
    >
      {icon}{children}
    </button>
  );
}

export function MetricCard({ icon, label, value }: { icon: ReactNode; label: string; value: number }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="flex items-center gap-2 text-gray-400">{icon}<span className="text-xs font-medium text-gray-500">{label}</span></div>
      <div className="mt-2 text-2xl font-bold text-gray-900">{value}</div>
    </div>
  );
}
