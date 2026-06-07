import type { ReactNode } from 'react';
import { motion } from 'framer-motion';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { cn, motionPreset, ui } from '../lib/ui';

export function RiskPill({ label, value }: { label: string; value: number }) {
  return (
    <span className={value ? ui.badgeWarn : ui.badgeGood}>
      <AlertTriangle size={14} /> {label}: {value}
    </span>
  );
}

export function OuiStatus({ dataset }: { dataset?: { source?: string; source_url?: string; created_at?: string | null; records?: number; cache?: string } }) {
  return (
    <div className="mt-3 flex flex-wrap gap-2 text-xs font-bold text-slate-500">
      <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1"><RefreshCw size={14} /> Mənbə: {dataset?.source ?? 'Wireshark'}</span>
      <span className="rounded-full bg-slate-100 px-3 py-1">Yazılar: {dataset?.records ?? 0}</span>
      <span className="rounded-full bg-slate-100 px-3 py-1">Keş: {dataset?.cache ?? 'memory'}</span>
      <span className="rounded-full bg-slate-100 px-3 py-1">Yaradılıb: {dataset?.created_at ?? '—'}</span>
    </div>
  );
}

export function TabButton({ active, children, icon, onClick }: { active: boolean; children: ReactNode; icon: ReactNode; onClick: () => void }) {
  return (
    <button
      className={cn(
        'inline-flex items-center gap-2 rounded-2xl border px-5 py-3 text-sm font-black transition focus:outline-none focus:ring-4 focus:ring-blue-100',
        active ? 'border-blue-600 bg-blue-600 text-white shadow-[0_16px_38px_rgba(37,99,235,0.22)]' : 'border-transparent bg-white text-slate-700 hover:border-blue-100 hover:bg-blue-50 hover:text-blue-700',
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
      className="rounded-3xl border border-blue-100 bg-white p-5 shadow-[0_18px_60px_rgba(15,23,42,0.08)] ring-1 ring-white/80"
      {...motionPreset.panel}
    >
      <div className="mb-4 inline-flex rounded-2xl bg-blue-50 p-3 text-blue-600 ring-1 ring-blue-100">{icon}</div>
      <span className="block text-xs font-black uppercase tracking-[0.18em] text-slate-500">{label}</span>
      <b className="mt-1 block text-4xl font-black text-slate-950">{value}</b>
    </motion.article>
  );
}
