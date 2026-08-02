import { Download, Monitor, Search } from 'lucide-react';
import type { ScannerProfilesResponse } from '../api';
import { downloadJson, emptyLabel, toBakuTime } from '../lib/format';
import { cn, ui } from '../lib/ui';

type Props = {
  data?: ScannerProfilesResponse;
  isError: boolean;
  isLoading: boolean;
  error: Error | null;
  search: string;
  onSearchChange: (value: string) => void;
};

export function ScannerProfilesPanel({
  data,
  isError,
  isLoading,
  error,
  search,
  onSearchChange,
}: Props) {
  const normalizedSearch = search.trim().toLowerCase();
  const profiles = (data?.profiles ?? []).filter((profile) => (
    !normalizedSearch
    || profile.ip.toLowerCase().includes(normalizedSearch)
    || profile.hostname?.toLowerCase().includes(normalizedSearch)
    || profile.category?.toLowerCase().includes(normalizedSearch)
    || profile.fingerprinting?.os_guess?.toLowerCase().includes(normalizedSearch)
  ));

  if (isLoading) {
    return <div className={ui.panel}>Skan nəticələri yüklənir...</div>;
  }

  return (
    <section className={cn(ui.panel, 'space-y-4')}>
      <div className={ui.panelHeader}>
        <div>
          <div className={ui.panelTitle}><Monitor size={16} /> Şəbəkə skanı</div>
          <p className={cn(ui.muted, 'mt-1')}>
            {data?.updated_at ? `Son yenilənmə: ${toBakuTime(data.updated_at)}` : 'Hələ uğurlu skan yoxdur'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="relative min-w-[220px]">
            <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={15} />
            <input
              className={cn(ui.input, 'pl-9')}
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder="IP, host və ya OS"
              value={search}
            />
          </label>
          <button
            className={ui.ghostButton}
            disabled={!data?.profiles.length}
            onClick={() => downloadJson('netlens-scanner-profiles.json', data?.profiles ?? [])}
            type="button"
          >
            <Download size={15} /> JSON
          </button>
        </div>
      </div>

      {isError && <p className={ui.errorText}>Skan API xətası: {error?.message}</p>}
      {!isError && data?.status === 'unavailable' && (
        <p className={ui.emptyText}>Redis-də skan nəticəsi yoxdur. Növbəti cron və ya manual skandan sonra məlumat görünəcək.</p>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Metric label="Tapılan host" value={data?.hosts_total ?? 0} />
        <Metric label="Yeni host" value={(data?.profiles ?? []).filter((item) => item.is_new).length} />
        <Metric label="Açıq port" value={(data?.profiles ?? []).reduce((sum, item) => sum + (item.ports ?? []).length, 0)} />
        <Metric label="OS müəyyənləşib" value={(data?.profiles ?? []).filter((item) => item.fingerprinting?.success).length} />
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="min-w-full divide-y divide-gray-200 text-left text-sm">
          <thead className="bg-gray-50 text-xs font-medium text-gray-500">
            <tr>
              <th className="px-4 py-3">IP / host</th>
              <th className="px-4 py-3">Kateqoriya</th>
              <th className="px-4 py-3">Portlar</th>
              <th className="px-4 py-3">Əməliyyat sistemi</th>
              <th className="px-4 py-3">NetBox</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {profiles.map((profile) => (
              <tr className="hover:bg-gray-50" key={profile.ip}>
                <td className="px-4 py-3">
                  <div className="font-mono text-xs font-semibold text-gray-900">{profile.ip}</div>
                  <div className="mt-1 text-xs text-gray-500">{emptyLabel(profile.hostname)}</div>
                </td>
                <td className="px-4 py-3 text-gray-700">{emptyLabel(profile.category)}</td>
                <td className="px-4 py-3">
                  <div className="flex max-w-[360px] flex-wrap gap-1">
                    {(profile.ports ?? []).length
                      ? profile.ports.map((port) => <span className={ui.badgeGood} key={port}>{port}</span>)
                      : <span className="text-xs text-gray-400">Yoxdur</span>}
                  </div>
                </td>
                <td className="max-w-[360px] px-4 py-3 text-gray-700">
                  <div className="break-words">{emptyLabel(profile.fingerprinting?.os_guess)}</div>
                  {profile.fingerprinting?.accuracy ? <div className="mt-1 text-xs text-gray-400">Dəqiqlik: {profile.fingerprinting.accuracy}%</div> : null}
                </td>
                <td className="px-4 py-3">
                  <span className={profile.is_new ? ui.badgeWarn : ui.badgeGood}>
                    {profile.is_new ? 'Yeni' : 'Mövcud'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!profiles.length && data?.status === 'ready' && <p className="p-5 text-center text-sm text-gray-500">Uyğun host tapılmadı.</p>}
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="border-l-2 border-blue-500 bg-gray-50 px-3 py-2">
      <div className="text-lg font-semibold text-gray-900">{value}</div>
      <div className="text-xs text-gray-500">{label}</div>
    </div>
  );
}
