import { Filter, Search, X } from 'lucide-react';
import type { QuickFilter, RiskSummary } from '../types';
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
    <section className="command-bar">
      <div className="global-search">
        <Search size={18} />
        <input
          value={query}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Hostname, IP, MAC, vendor, sahə, region..."
        />
        {(query || filter !== 'all') && <button type="button" onClick={onClear}><X size={16} /> Təmizlə</button>}
      </div>
      <div className="filter-row" aria-label="Sürətli filtrlər">
        <Filter size={16} />
        {QUICK_FILTERS.map((item) => (
          <button className={filter === item.value ? 'selected' : ''} key={item.value} type="button" onClick={() => onFilterChange(item.value)}>
            {item.label}
          </button>
        ))}
        <span className="result-pill">Nəticə: {resultCount}</span>
      </div>
      <div className="risk-strip">
        <RiskPill label="Unknown vendor" value={riskSummary.unknownVendor} />
        <RiskPill label="İnterfeys" value={riskSummary.interfaceProblems} />
        <RiskPill label="Primary IP yoxdur" value={riskSummary.missingPrimaryIp} />
        <RiskPill label="Offline" value={riskSummary.offlineDevices} />
      </div>
    </section>
  );
}
