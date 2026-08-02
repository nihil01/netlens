import { FormEvent } from 'react';
import { Loader2, Search, FileSpreadsheet, Download } from 'lucide-react';
import { ui } from '../../lib/ui';

type SearchFormProps = {
  srcIp: string;
  dstIp: string;
  dstPort: string;
  dateFrom: string;
  timeFrom: string;
  dateTo: string;
  timeTo: string;
  onSrcIpChange: (v: string) => void;
  onDstIpChange: (v: string) => void;
  onDstPortChange: (v: string) => void;
  onDateFromChange: (v: string) => void;
  onTimeFromChange: (v: string) => void;
  onDateToChange: (v: string) => void;
  onTimeToChange: (v: string) => void;
  onSubmit: (e: FormEvent<HTMLFormElement>) => void;
  onExportExcel: () => void;
  onExportPdf: () => void;
  isFetching: boolean;
  exporting: boolean;
  exportingPdf: boolean;
  canSearch: boolean;
  hasSearch: boolean;
};

export function SearchForm({
  srcIp, dstIp, dstPort, dateFrom, timeFrom, dateTo, timeTo,
  onSrcIpChange, onDstIpChange, onDstPortChange,
  onDateFromChange, onTimeFromChange, onDateToChange, onTimeToChange,
  onSubmit, onExportExcel, onExportPdf,
  isFetching, exporting, exportingPdf, canSearch, hasSearch,
}: SearchFormProps) {
  return (
    <form className={ui.panel} onSubmit={onSubmit}>
      <div className="grid gap-3 md:grid-cols-5 md:items-end">
        <label className="space-y-1">
          <span className="text-xs font-medium text-gray-500">Src IP</span>
          <input className={ui.input} value={srcIp} onChange={(e) => onSrcIpChange(e.target.value)} placeholder="10.168.195.19 / 10.0.0.0/8" />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium text-gray-500">Dst IP</span>
          <input className={ui.input} value={dstIp} onChange={(e) => onDstIpChange(e.target.value)} placeholder="8.8.8.8 / 192.168.1.0/24" />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium text-gray-500">Dst Port</span>
          <input className={ui.input} value={dstPort} onChange={(e) => onDstPortChange(e.target.value)} inputMode="numeric" placeholder="443" />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium text-gray-500">Tarixdən</span>
          <div className="flex gap-1">
            <input className={ui.input} type="date" value={dateFrom} onChange={(e) => onDateFromChange(e.target.value)} lang="en-GB" />
            <input className={ui.input} type="time" value={timeFrom} onChange={(e) => onTimeFromChange(e.target.value)} step="1" lang="en-GB" />
          </div>
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium text-gray-500">Tarixədək</span>
          <div className="flex gap-1">
            <input className={ui.input} type="date" value={dateTo} onChange={(e) => onDateToChange(e.target.value)} lang="en-GB" />
            <input className={ui.input} type="time" value={timeTo} onChange={(e) => onTimeToChange(e.target.value)} step="1" lang="en-GB" />
          </div>
        </label>
      </div>
      <div className="mt-3 flex gap-2">
        <button className={ui.primaryButton} type="submit" disabled={!canSearch || isFetching}>
          {isFetching ? <Loader2 className="animate-spin" size={14} /> : <Search size={14} />}
          Axtar
        </button>
        <button className={ui.ghostButton} type="button" disabled={exporting || !hasSearch} onClick={onExportExcel}>
          {exporting ? <Loader2 className="animate-spin" size={14} /> : <FileSpreadsheet size={14} />}
          Excel
        </button>
        <button className={ui.ghostButton} type="button" disabled={exportingPdf || !hasSearch} onClick={onExportPdf}>
          {exportingPdf ? <Loader2 className="animate-spin" size={14} /> : <Download size={14} />}
          PDF hesabat
        </button>
      </div>
    </form>
  );
}
