import type { ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

export function RiskPill({ label, value }: { label: string; value: number }) {
  return <span className={`risk-pill ${value ? 'warn' : 'good'}`}><AlertTriangle size={14} /> {label}: {value}</span>;
}

export function OuiStatus({ dataset }: { dataset?: { source?: string; source_url?: string; created_at?: string | null; records?: number; cache?: string } }) {
  return (
    <div className="oui-status">
      <span><RefreshCw size={14} /> Mənbə: {dataset?.source ?? 'Wireshark'}</span>
      <span>Yazılar: {dataset?.records ?? 0}</span>
      <span>Keş: {dataset?.cache ?? 'memory'}</span>
      <span>Yaradılıb: {dataset?.created_at ?? '—'}</span>
    </div>
  );
}

export function TabButton({ active, children, icon, onClick }: { active: boolean; children: ReactNode; icon: ReactNode; onClick: () => void }) {
  return <button className={`tab-button ${active ? 'active' : ''}`} onClick={onClick} type="button">{icon}{children}</button>;
}

export function MetricCard({ icon, label, value }: { icon: ReactNode; label: string; value: number }) {
  return (
    <article className="metric-card">
      {icon}
      <span>{label}</span>
      <b>{value}</b>
    </article>
  );
}
