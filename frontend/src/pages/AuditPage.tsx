import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { CalendarRange, ChevronLeft, ChevronRight, Download, History, Search, ShieldAlert, X } from 'lucide-react';
import { downloadAuditCsv, fetchAuditDashboard, fetchAuditRecord, fetchAuditRecords } from '../api';
import { cn, ui } from '../lib/ui';

function bakuDateBoundary(date: string, endOfDay = false) {
  if (!date) return undefined;
  const time = endOfDay ? '23:59:59.999' : '00:00:00.000';
  return new Date(`${date}T${time}+04:00`).toISOString();
}

export function AuditPage() {
  const [user, setUser] = useState('');
  const [action, setAction] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string | null>(null);
  const invalidRange = Boolean(dateFrom && dateTo && dateFrom > dateTo);
  const dateFromIso = bakuDateBoundary(dateFrom);
  const dateToIso = bakuDateBoundary(dateTo, true);
  const filters = { user, action, dateFrom: dateFromIso, dateTo: dateToIso };

  const dashboard = useQuery({
    queryKey: ['audit-dashboard'],
    queryFn: fetchAuditDashboard,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
  const records = useQuery({
    queryKey: ['audit-records', user, action, dateFrom, dateTo, page],
    queryFn: () => fetchAuditRecords({ ...filters, page }),
    enabled: !invalidRange,
    staleTime: 20_000,
    refetchInterval: 60_000,
  });
  const detail = useQuery({
    queryKey: ['audit-record', selected],
    queryFn: () => fetchAuditRecord(selected as string),
    enabled: Boolean(selected),
  });

  function clearPeriod() {
    setDateFrom('');
    setDateTo('');
    setPage(1);
    setSelected(null);
  }

  if (dashboard.isError || records.isError) {
    return <div className={cn(ui.panel, 'text-red-600')}>FMC Audit local history əlçatan deyil.</div>;
  }

  return (
    <section className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {[
          ['Total', dashboard.data?.total_records ?? 0],
          ['Today', dashboard.data?.records_today ?? 0],
          ['This week', dashboard.data?.records_this_week ?? 0],
          ['High risk', (dashboard.data?.risk_distribution.high ?? 0) + (dashboard.data?.risk_distribution.critical ?? 0)],
          ['Deploy failed', dashboard.data?.deployment_stats.failed ?? 0],
        ].map(([label, value]) => (
          <div key={label} className={ui.panel}>
            <div className="text-xs uppercase text-gray-400">{label}</div>
            <div className="mt-1 text-3xl font-black">{value}</div>
          </div>
        ))}
      </div>

      <div className={ui.panel}>
        <div className="grid gap-3 xl:grid-cols-[minmax(220px,1fr)_160px_170px_170px_auto] xl:items-end">
          <label className="relative block">
            <span className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-gray-500">İstifadəçi</span>
            <Search size={14} className="absolute bottom-3 left-3 text-gray-400" />
            <input
              className={cn(ui.input, 'pl-9')}
              value={user}
              onChange={(event) => { setUser(event.target.value); setPage(1); setSelected(null); }}
              placeholder="Username axtar…"
            />
          </label>
          <label>
            <span className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-gray-500">Action</span>
            <select className={cn(ui.select, 'w-full')} value={action} onChange={(event) => { setAction(event.target.value); setPage(1); setSelected(null); }}>
              <option value="">Bütün actions</option>
              <option value="ADD">ADD</option>
              <option value="UPDATE">UPDATE</option>
              <option value="DELETE">DELETE</option>
            </select>
          </label>
          <label>
            <span className="mb-1 flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-gray-500"><CalendarRange size={11} />Tarixdən (с)</span>
            <input
              type="date"
              className={cn(ui.input, invalidRange && 'border-red-300')}
              value={dateFrom}
              max={dateTo || undefined}
              onChange={(event) => { setDateFrom(event.target.value); setPage(1); setSelected(null); }}
            />
          </label>
          <label>
            <span className="mb-1 flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-gray-500"><CalendarRange size={11} />Tarixədək (по)</span>
            <input
              type="date"
              className={cn(ui.input, invalidRange && 'border-red-300')}
              value={dateTo}
              min={dateFrom || undefined}
              onChange={(event) => { setDateTo(event.target.value); setPage(1); setSelected(null); }}
            />
          </label>
          <div className="flex gap-2">
            {(dateFrom || dateTo) && <button type="button" className={ui.ghostButton} onClick={clearPeriod}><X size={14} />Təmizlə</button>}
            <button
              type="button"
              className={ui.ghostButton}
              disabled={invalidRange}
              onClick={() => void downloadAuditCsv(filters)}
            >
              <Download size={14} />CSV
            </button>
          </div>
        </div>

        {invalidRange && <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">Başlanğıc tarix son tarixdən gec ola bilməz.</div>}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-gray-500">
          <span>{dateFrom || dateTo ? `Seçilmiş period: ${dateFrom || 'əvvəldən'} — ${dateTo || 'indiyədək'} (Baku)` : 'Period seçilməyib — bütün tarix göstərilir.'}</span>
          <div className="flex items-center gap-2">
            <span>Göstərilir: {records.data?.records.length ?? 0} / {records.data?.total ?? 0}</span>
            <button type="button" className="rounded border border-gray-200 p-1 disabled:opacity-30" disabled={page <= 1} onClick={() => { setPage((value) => Math.max(1, value - 1)); setSelected(null); }} aria-label="Əvvəlki audit səhifəsi"><ChevronLeft size={13} /></button>
            <span className="min-w-14 text-center">{page}/{Math.max(1, Math.ceil((records.data?.total ?? 0) / 200))}</span>
            <button type="button" className="rounded border border-gray-200 p-1 disabled:opacity-30" disabled={page >= Math.max(1, Math.ceil((records.data?.total ?? 0) / 200))} onClick={() => { setPage((value) => value + 1); setSelected(null); }} aria-label="Növbəti audit səhifəsi"><ChevronRight size={13} /></button>
          </div>
        </div>

        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[920px] text-left text-xs">
            <thead className="border-b text-gray-500">
              <tr><th className="p-2">Local time (Baku)</th><th>User</th><th>Action</th><th>Entity</th><th>Subsystem</th><th>Message</th><th>Risk</th><th>Deployment</th></tr>
            </thead>
            <tbody>
              {(records.data?.records ?? []).map((record) => (
                <tr key={record.fmc_id} onClick={() => setSelected(record.fmc_id)} className="cursor-pointer border-b border-gray-100 hover:bg-blue-50">
                  <td className="p-2">{record.local_timestamp ? new Date(record.local_timestamp).toLocaleString('az-AZ') : '—'}</td>
                  <td className="font-medium">{record.user_name || 'unknown'}</td>
                  <td><span className={record.action === 'DELETE' ? ui.badgeError : record.action === 'UPDATE' ? ui.badgeWarn : ui.badgeGood}>{record.action}</span></td>
                  <td>{record.object_name || record.object_type || '—'}</td>
                  <td>{record.subsystem || '—'}</td>
                  <td className="max-w-72 truncate" title={record.message ?? undefined}>{record.message || '—'}</td>
                  <td><span className={record.risk_score >= 70 ? ui.badgeError : record.risk_score >= 40 ? ui.badgeWarn : ui.badgeGood}>{record.risk_score}</span></td>
                  <td>{record.deployed ? record.deploy_success === false ? 'Failed' : 'Deployed' : 'Pending/unknown'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!records.isLoading && !records.data?.records.length && !invalidRange && <div className="py-10 text-center text-sm text-gray-400">Bu period üçün audit qeydi tapılmadı.</div>}
        </div>
      </div>

      {selected && (
        <div className={ui.panel}>
          <div className="flex items-center justify-between"><h2 className="flex items-center gap-2 font-semibold"><History size={16} />Before / After Diff</h2><button className={ui.ghostButton} onClick={() => setSelected(null)}>Bağla</button></div>
          {detail.data?.record && <div className="mt-3 flex flex-wrap gap-2 text-xs"><span className={ui.badgeGood}>recordId: {detail.data.record.record_id || 'N/A'}</span><span className={ui.badgeGood}>auditId: {detail.data.record.audit_id || 'N/A'}</span><span className={ui.badgeGood}>snapshotId: {detail.data.record.snapshot_id || 'N/A'}</span></div>}
          <div className="mt-4 space-y-2">
            {(detail.data?.field_diffs ?? []).map((diff) => <div key={diff.field} className="grid gap-2 rounded-lg border border-gray-200 p-3 text-xs md:grid-cols-[180px_1fr_1fr]"><div className="flex items-center gap-1 font-bold"><ShieldAlert size={12} />{diff.field}</div><pre className="overflow-auto rounded bg-red-50 p-2 text-red-800">{JSON.stringify(diff.before, null, 2)}</pre><pre className="overflow-auto rounded bg-emerald-50 p-2 text-emerald-800">{JSON.stringify(diff.after, null, 2)}</pre></div>)}
          </div>
          {!detail.isLoading && !detail.data?.field_diffs.length && <p className="mt-4 text-sm text-gray-400">Bu fact üçün before/after diff verilməyib.</p>}
        </div>
      )}
    </section>
  );
}
