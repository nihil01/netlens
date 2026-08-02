import { FormEvent, useState } from 'react';
import { motion } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import {
  exportIpExcel,
  exportPdfReport,
  fetchFullAggregation,
  type FullAggregationResponse,
} from '../api';
import { AggTable } from '../components/ip-analysis/AggTable';
import { SearchForm } from '../components/ip-analysis/SearchForm';
import { LoadingPanel } from '../components/LoadingPanel';
import { toBakuTime } from '../lib/format';
import { cn, ui } from '../lib/ui';

function getDefaultDateFrom() {
  const d = new Date();
  d.setDate(d.getDate() - 7);
  return d.toISOString().slice(0, 10);
}

export function IpAnalysisPage() {
  const [searchSrcIp, setSearchSrcIp] = useState('');
  const [searchDstIp, setSearchDstIp] = useState('');
  const [searchDstPort, setSearchDstPort] = useState('');
  const [dateFrom, setDateFrom] = useState(getDefaultDateFrom);
  const [timeFrom, setTimeFrom] = useState('09:00');
  const [dateTo, setDateTo] = useState(new Date().toISOString().slice(0, 10));
  const [timeTo, setTimeTo] = useState('18:00');
  const [submittedFilters, setSubmittedFilters] = useState<{
    srcIp: string; dstIp: string; dstPort: string; start: string; end: string;
  } | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportingPdf, setExportingPdf] = useState(false);

  const fullQuery = useQuery<FullAggregationResponse>({
    queryKey: ['full-aggregation', submittedFilters],
    queryFn: () => fetchFullAggregation(
      submittedFilters!.srcIp || submittedFilters!.dstIp,
      submittedFilters!.start,
      submittedFilters!.end,
      {
        srcIp: submittedFilters!.srcIp || undefined,
        dstIp: submittedFilters!.dstIp || undefined,
        dstPort: submittedFilters!.dstPort || undefined,
      },
    ),
    enabled: submittedFilters !== null,
    staleTime: 0,
    gcTime: 0,
    refetchOnMount: true,
    refetchOnWindowFocus: false,
  });

  const hasSearch = submittedFilters !== null;
  const canSearch = Boolean((searchSrcIp.trim() || searchDstIp.trim()) && dateFrom && timeFrom && dateTo && timeTo);

  function submitSearch(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const targetIp = searchSrcIp.trim() || searchDstIp.trim();
    if (!targetIp) return;
    setSubmittedFilters({
      srcIp: searchSrcIp.trim(),
      dstIp: searchDstIp.trim(),
      dstPort: searchDstPort.trim(),
      start: dateFrom && timeFrom ? `${dateFrom}T${timeFrom}:00+04:00` : '',
      end: dateTo && timeTo ? `${dateTo}T${timeTo}:00+04:00` : '',
    });
  }

  async function handleExportExcel() {
    const targetIp = searchSrcIp.trim() || searchDstIp.trim();
    if (!targetIp) return;
    setExporting(true);
    try {
      await exportIpExcel(targetIp, {
        srcIp: searchSrcIp.trim() || undefined,
        dstIp: searchDstIp.trim() || undefined,
        dstPort: searchDstPort.trim() || undefined,
        start: dateFrom && timeFrom ? `${dateFrom}T${timeFrom}:00+04:00` : undefined,
        end: dateTo && timeTo ? `${dateTo}T${timeTo}:00+04:00` : undefined,
      });
    } catch (err) { console.error('Export failed:', err); }
    finally { setExporting(false); }
  }

  async function handleExportPdf() {
    const targetIp = searchSrcIp.trim() || searchDstIp.trim();
    if (!targetIp || !submittedFilters) return;
    setExportingPdf(true);
    try {
      await exportPdfReport(targetIp, submittedFilters.start, submittedFilters.end);
    } catch (err) { console.error('PDF export failed:', err); }
    finally { setExportingPdf(false); }
  }

  return (
    <motion.section className="space-y-4" {...{ initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.2, ease: 'easeOut' } }}>
      <SearchForm
        srcIp={searchSrcIp} dstIp={searchDstIp} dstPort={searchDstPort}
        dateFrom={dateFrom} timeFrom={timeFrom} dateTo={dateTo} timeTo={timeTo}
        onSrcIpChange={setSearchSrcIp} onDstIpChange={setSearchDstIp} onDstPortChange={setSearchDstPort}
        onDateFromChange={setDateFrom} onTimeFromChange={setTimeFrom}
        onDateToChange={setDateTo} onTimeToChange={setTimeTo}
        onSubmit={submitSearch} onExportExcel={handleExportExcel} onExportPdf={handleExportPdf}
        isFetching={fullQuery.isFetching} exporting={exporting} exportingPdf={exportingPdf}
        canSearch={canSearch} hasSearch={hasSearch}
      />

      {fullQuery.isFetching && <LoadingPanel label="Məlumatlar yüklənir..." />}
      {fullQuery.isError && <div className={cn(ui.panel, 'border-red-200 bg-red-50 text-red-700 text-sm')}>Xəta: {(fullQuery.error as Error).message}</div>}

      {fullQuery.data && (() => {
        const d = fullQuery.data as FullAggregationResponse;
        return (<>
          {d.asn_info?.asn && (
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-3">
              <div className="flex items-center gap-4 text-sm">
                <span className="font-semibold text-blue-900">ASN: AS{d.asn_info.asn}</span>
                <span className="text-blue-700">{d.asn_info.asn_org}</span>
                <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800">{d.asn_info.vendor}</span>
                <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800">{d.asn_info.category}</span>
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
              <div className="text-lg font-bold text-gray-900">{d.total_hits.toLocaleString()}</div>
              <div className="text-[11px] text-gray-500">Ümumi hadisə</div>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
              <div className="text-lg font-bold text-gray-900">{d.domains.total}</div>
              <div className="text-[11px] text-gray-500">Domen</div>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
              <div className="text-lg font-bold text-gray-900">{d.ports.length}</div>
              <div className="text-[11px] text-gray-500">Port</div>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
              <div className="text-lg font-bold text-gray-900">{d.users.length}</div>
              <div className="text-[11px] text-gray-500">İstifadəçi</div>
            </div>
          </div>

          <AggTable
            title="Domainlər və Tətbiqlər"
            count={d.domains.total}
            headers={['#', 'Domain', 'Tətbiq', 'Say', 'İlk', 'Son']}
            rows={d.domains.buckets.map((b, i) => [
              String(i + 1),
              b.key.domain,
              b.key.application,
              b.doc_count.toLocaleString(),
              toBakuTime(b.first_seen.value_as_string),
              toBakuTime(b.last_seen.value_as_string),
            ])}
          />

          <AggTable
            title="Mənbə IP-ləri (Source)"
            count={d.ips.as_source.length}
            headers={['#', 'IP', 'ASN', 'Təşkilat', 'Vendor', 'Ölkə', 'Say']}
            rows={d.ips.as_source.map((item, i) => [
              String(i + 1),
              item.key,
              item.asn ? `AS${item.asn}` : '—',
              item.asn_org ?? '—',
              item.vendor ?? '—',
              item.country_name ?? item.country ?? '—',
              item.doc_count.toLocaleString(),
            ])}
          />
          <AggTable
            title="Təyinat IP-ləri (Destination)"
            count={d.ips.as_destination.length}
            headers={['#', 'IP', 'ASN', 'Təşkilat', 'Vendor', 'Ölkə', 'Say']}
            rows={d.ips.as_destination.map((item, i) => [
              String(i + 1),
              item.key,
              item.asn ? `AS${item.asn}` : '—',
              item.asn_org ?? '—',
              item.vendor ?? '—',
              item.country_name ?? item.country ?? '—',
              item.doc_count.toLocaleString(),
            ])}
          />

          <AggTable
            title="Portlar"
            count={d.ports.length}
            headers={['#', 'Port', 'Say']}
            rows={d.ports.map((item, i) => [String(i + 1), item.key, item.doc_count.toLocaleString()])}
          />

          <div className="grid gap-4 lg:grid-cols-2">
            <AggTable
              title="Protokollar"
              count={d.protocols.length}
              headers={['Protokol', 'Say']}
              rows={d.protocols.map((item) => [item.key, item.doc_count.toLocaleString()])}
            />
            <AggTable
              title="Əməliyyatlar"
              count={d.actions.length}
              headers={['Əməliyyat', 'Say']}
              rows={d.actions.map((item) => [item.key, item.doc_count.toLocaleString()])}
            />
          </div>

          {d.users.length > 0 && (
            <AggTable
              title="İstifadəçilər"
              count={d.users.length}
              headers={['İstifadəçi', 'Say']}
              rows={d.users.map((item) => [item.key, item.doc_count.toLocaleString()])}
            />
          )}
        </>
        );
      })()}

      {!hasSearch && (
        <div className={cn(ui.panel, 'text-center text-sm text-gray-400')}>
          Src IP və ya Dst IP daxil edin, tarix seçin və "Axtar" düyməsinə basın
        </div>
      )}
    </motion.section>
  );
}
