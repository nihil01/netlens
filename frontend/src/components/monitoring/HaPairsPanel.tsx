import { useQuery } from '@tanstack/react-query';
import { Activity, ArrowRightLeft } from 'lucide-react';
import { fetchHaPairs } from '../../api';
import { cn, ui } from '../../lib/ui';

export function HaPairsPanel() {
  const query = useQuery({ queryKey: ['ha-pairs'], queryFn: fetchHaPairs, refetchInterval: 60_000 });
  if (query.isLoading) return <div className={ui.panel}>HA məlumatı yüklənir…</div>;
  if (query.isError) return <div className={cn(ui.panel, 'text-red-600')}>HA history API əlçatan deyil</div>;
  const items = query.data?.items ?? [];
  if (!items.length) return <div className={ui.panel}>HA pair tapılmadı və ya hələ toplanmayıb.</div>;
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {items.map((pair) => {
        const failed = pair.pair_state === 'FAILED';
        const degraded = pair.pair_state === 'DEGRADED' || pair.pair_state === 'UNKNOWN';
        return (
          <article key={pair.pair_id} className={cn(ui.panel, failed ? 'border-red-300' : degraded ? 'border-amber-300' : 'border-emerald-200')}>
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2"><Activity size={16} /><h3 className="font-semibold">{pair.name || pair.pair_id}</h3></div>
              <span className={failed ? ui.badgeError : degraded ? ui.badgeWarn : ui.badgeGood}>{pair.pair_state}</span>
            </div>
            <div className="mt-4 grid grid-cols-[1fr_auto_1fr] items-center gap-3 text-xs">
              <div className="min-w-0 rounded-lg bg-blue-50 p-3">
                <div className="text-gray-500">Primary (configured)</div>
                <div className="mt-1 truncate text-sm font-bold text-blue-950">{pair.primary_device_name || pair.primary_device_id}</div>
                <div className="mt-0.5 break-all font-mono text-[9px] text-blue-700">{pair.primary_device_id}</div>
              </div>
              <ArrowRightLeft size={16} className="text-gray-400" />
              <div className="min-w-0 rounded-lg bg-slate-50 p-3">
                <div className="text-gray-500">Secondary (configured)</div>
                <div className="mt-1 truncate text-sm font-bold text-slate-950">{pair.secondary_device_name || pair.secondary_device_id}</div>
                <div className="mt-0.5 break-all font-mono text-[9px] text-slate-600">{pair.secondary_device_id}</div>
              </div>
            </div>
            <dl className="mt-3 grid grid-cols-[130px_1fr] gap-1 text-xs">
              <dt className="text-gray-500">Active runtime</dt><dd><span className="font-semibold">{pair.active_member_name || 'Unknown'}</span>{pair.active_member_id && <span className="ml-1 break-all font-mono text-[9px] text-gray-400">({pair.active_member_id})</span>}</dd>
              <dt className="text-gray-500">Standby runtime</dt><dd><span className="font-semibold">{pair.standby_member_name || 'Unknown'}</span>{pair.standby_member_id && <span className="ml-1 break-all font-mono text-[9px] text-gray-400">({pair.standby_member_id})</span>}</dd>
              <dt className="text-gray-500">Role transition</dt><dd>{pair.last_role_transition_at ? new Date(pair.last_role_transition_at).toLocaleString('az-AZ') : '—'}</dd>
              <dt className="text-gray-500">Monitored interfaces</dt><dd>{pair.monitored_interfaces.length}</dd>
            </dl>
            {pair.monitored_interfaces.length > 0 && (
              <div className="mt-3 space-y-2">
                {pair.monitored_interfaces.map((iface) => (
                  <div key={iface.id || iface.name} className="rounded-lg border border-gray-100 bg-gray-50 p-2 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold">{iface.interface_logical_name || iface.name || iface.id}</span>
                      <span className={iface.monitor_for_failures ? ui.badgeGood : ui.badgeWarn}>
                        {iface.monitor_for_failures ? 'Monitored' : 'Not monitored'}
                      </span>
                    </div>
                    <dl className="mt-2 grid grid-cols-[90px_1fr] gap-1">
                      <dt className="text-gray-500">Active IPv4</dt><dd className="font-mono">{iface.ipv4.active_address || '—'}{iface.ipv4.active_mask ? `/${iface.ipv4.active_mask}` : ''}</dd>
                      <dt className="text-gray-500">Standby IPv4</dt><dd className="font-mono">{iface.ipv4.standby_address || '—'}</dd>
                      <dt className="text-gray-500">Active IPv6</dt><dd className="break-all font-mono">{iface.ipv6.active_link_local_address || '—'}</dd>
                      <dt className="text-gray-500">Standby IPv6</dt><dd className="break-all font-mono">{iface.ipv6.standby_link_local_address || '—'}</dd>
                    </dl>
                    {iface.collection_errors.length > 0 && <div className="mt-2 text-amber-700">Detail unavailable</div>}
                  </div>
                ))}
              </div>
            )}
            {pair.health_message && <p className="mt-3 rounded bg-gray-50 p-2 text-xs text-gray-600">{pair.health_message}</p>}
          </article>
        );
      })}
    </div>
  );
}
