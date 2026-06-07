import type { ReactNode } from 'react';
import { motion } from 'framer-motion';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { cn, ui } from '../lib/ui';

export function RiskPill({ label, value }: { label: string; value: number }) {
  return (
    <span className={value ? ui.badgeWarn : ui.badgeGood}>
      <AlertTriangle size={14} /> {label}: {value}
    </span>
  );
}

export function OuiStatus({ dataset }: { dataset?: { source?: string; source_url?: string; created_at?: string | null; records?: number; cache?: string } }) {
  return (
    <div className="mt-2 flex flex-wrap gap-2 text-xs font-bold text-slate-500">
      <span className="inline-flex items-center gap-1"><RefreshCw size={14} /> Mənbə: {dataset?.source ?? 'Wireshark'}</span>
      <span>Yazılar: {dataset?.records ?? 0}</span>
      <span>Keş: {dataset?.cache ?? 'memory'}</span>
      <span>Yaradılıb: {dataset?.created_at ?? '—'}</span>
    </div>
  );
}

export function TabButton({ active, children, icon, onClick }: { active: boolean; children: ReactNode; icon: ReactNode; onClick: () => void }) {
  return (
    <button
      className={cn(
        'inline-flex items-center gap-2 rounded-full border px-5 py-3 text-sm font-black text-slate-700 transition focus:outline-none focus:ring-4 focus:ring-blue-100',
        active ? 'border-blue-600 bg-blue-600 text-white shadow-glow' : 'border-blue-100 bg-white/80 hover:border-blue-300 hover:bg-blue-50',
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
    <motion.article
      className="rounded-[24px] border border-blue-100 bg-white/85 p-5 shadow-panel backdrop-blur"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22 }}
    >
      <div className="mb-4 inline-flex rounded-2xl bg-blue-50 p-3 text-blue-600">{icon}</div>
      <span className="block text-xs font-black uppercase tracking-[0.18em] text-slate-500">{label}</span>
      <b className="mt-1 block text-4xl font-black text-slate-950">{value}</b>
    </motion.article>
  );
}
