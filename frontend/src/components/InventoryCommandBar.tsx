import { motion } from 'framer-motion';
import { Filter, Search, X } from 'lucide-react';
import type { QuickFilter, RiskSummary } from '../types';
import { cn, ui } from '../lib/ui';
import { RiskPill } from './common';

const QUICK_FILTERS: Array<{ value: QuickFilter; label: string }> = [
  { value: 'all', label: 'Hamısı' },
  { value: 'active', label: 'Aktiv' },
  { value: 'offline', label: 'Offline' },
  { value: 'unknownVendor', label: 'Vendor boşdur' },
  { value: 'interfaceProblems', label: 'İnterfeys problemi' },
  { value: 'missingPrimaryIp', label: 'IP boşdur' },
];

export function InventoryCommandBar({
  filter,
  onClear,
  onFilterChange,
  onSearchChange,
  query,
  resultCount,
  riskSummary,
}: {
  filter: QuickFilter;
  onClear: () => void;
  onFilterChange: (filter: QuickFilter) => void;
  onSearchChange: (query: string) => void;
  query: string;
  resultCount: number;
  riskSummary: RiskSummary;
}) {
  return (
    <motion.section className={cn(ui.panel, 'space-y-4')} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
      <div className="grid gap-3 rounded-3xl border border-slate-200 bg-slate-50 p-3 md:grid-cols-[auto_minmax(0,1fr)_auto] md:items-center">
        <Search className="text-blue-600" size={18} />
        <input
          className="min-w-0 bg-transparent text-sm font-semibold text-slate-900 outline-none placeholder:text-slate-400"
          value={query}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Hostname, IP, MAC, vendor, sahə, region..."
        />
        {(query || filter !== 'all') && <button className={ui.ghostButton} type="button" onClick={onClear}><X size={16} /> Təmizlə</button>}
      </div>
      <div className="flex flex-wrap items-center gap-2" aria-label="Sürətli filtrlər">
        <Filter className="text-blue-600" size={16} />
        {QUICK_FILTERS.map((item) => (
          <button className={cn(ui.pillButton, filter === item.value && ui.selectedPill)} key={item.value} type="button" onClick={() => onFilterChange(item.value)}>
            {item.label}
          </button>
        ))}
        <span className="rounded-full bg-slate-100 px-4 py-2 text-xs font-black uppercase text-slate-600">Nəticə: {resultCount}</span>
      </div>
      <div className="flex flex-wrap gap-2">
        <RiskPill label="Unknown vendor" value={riskSummary.unknownVendor} />
        <RiskPill label="İnterfeys" value={riskSummary.interfaceProblems} />
        <RiskPill label="Primary IP yoxdur" value={riskSummary.missingPrimaryIp} />
        <RiskPill label="Offline" value={riskSummary.offlineDevices} />
      </div>
    </motion.section>
  );
}
