import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, Search } from 'lucide-react';
import { fetchHealthAlertHistory } from '../../api';
import { cn, ui } from '../../lib/ui';

export function HealthAlertsPanel() {
  const [search, setSearch] = useState('');
  const [severity, setSeverity] = useState('');
  const [lifecycle, setLifecycle] = useState('');
  const query = useQuery({
    queryKey: ['health-alert-history', search, severity, lifecycle],
    queryFn: () => fetchHealthAlertHistory({ search, severity, lifecycle }),
    staleTime: 20_000,
  });
  return (
    <div className={ui.panel}>
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-56 flex-1"><Search size={14} className="absolute left-3 top-3 text-gray-400" /><input className={cn(ui.input, 'pl-9')} value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Alert axtar…" /></div>
        <select className={ui.select} value={severity} onChange={(event) => setSeverity(event.target.value)}><option value="">Bütün severity</option><option>RED</option><option>YELLOW</option></select>
        <select className={ui.select} value={lifecycle} onChange={(event) => setLifecycle(event.target.value)}><option value="">Bütün lifecycle</option><option>NEW</option><option>ACTIVE</option><option>RESOLVED</option><option>REOPENED</option><option>FLAPPING</option></select>
      </div>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[900px] text-left text-xs">
          <thead className="border-b text-gray-500"><tr><th className="p-2">Severity</th><th>Device</th><th>Module</th><th>Description</th><th>Lifecycle</th><th>First seen</th><th>Last seen</th><th>Repeats</th></tr></thead>
          <tbody>
            {(query.data?.items ?? []).map((alert) => (
              <tr key={alert.alert_id} className="border-b border-gray-100">
                <td className="p-2"><span className={alert.severity === 'RED' ? ui.badgeError : ui.badgeWarn}><AlertTriangle size={11} className="mr-1" />{alert.severity || 'UNKNOWN'}</span></td>
                <td className="max-w-32 truncate font-mono" title={alert.device_id ?? undefined}>{alert.device_id || '—'}</td>
                <td>{alert.module_id || 'General'}</td><td className="max-w-72 truncate" title={alert.details ?? undefined}>{alert.description || alert.details || '—'}</td>
                <td><span className={alert.lifecycle_state === 'RESOLVED' ? ui.badgeGood : alert.lifecycle_state === 'FLAPPING' ? ui.badgeWarn : ui.badgeError}>{alert.lifecycle_state}</span></td>
                <td>{new Date(alert.first_seen_at).toLocaleString('az-AZ')}</td><td>{new Date(alert.last_seen_at).toLocaleString('az-AZ')}</td><td>{alert.repeat_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!query.isLoading && !query.data?.items.length && <p className="py-8 text-center text-gray-400">Filterə uyğun alert yoxdur</p>}
        {query.isError && <p className="py-8 text-center text-red-500">Alert history API xətası</p>}
      </div>
    </div>
  );
}
