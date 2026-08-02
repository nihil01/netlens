import { useQuery } from '@tanstack/react-query';
import { fetchVpnTimeline } from '../../api';

function duration(seconds: number | null | undefined) {
  if (seconds === null || seconds === undefined) return 'N/A';
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

export function TunnelAnalytics({ tunnelId }: { tunnelId: string }) {
  const query = useQuery({ queryKey: ['vpn-timeline', tunnelId], queryFn: () => fetchVpnTimeline(tunnelId), staleTime: 30_000 });
  if (query.isLoading) return <p className="mt-3 text-xs text-gray-400">VPN analytics yüklənir…</p>;
  if (query.isError || !query.data?.analytics) return <p className="mt-3 text-xs text-gray-400">VPN transition history hələ əlçatan deyil</p>;
  const analytics = query.data.analytics;
  return (
    <div className="mt-3 border-t border-gray-100 pt-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
        {[
          ['Availability', analytics.availability_percent === null ? 'N/A' : `${analytics.availability_percent.toFixed(3)}%`],
          ['Transitions', analytics.transition_count], ['Longest outage', duration(analytics.longest_outage_seconds)],
          ['MTBF', duration(analytics.mtbf_seconds)], ['MTTR', duration(analytics.mttr_seconds)],
          ['Downtime', duration(analytics.down_seconds)], ['Unknown', duration(analytics.unknown_seconds)],
        ].map(([label, value]) => <div key={label} className="rounded bg-gray-50 p-2"><div className="text-[9px] uppercase text-gray-400">{label}</div><div className="mt-1 text-xs font-bold text-gray-800">{value}</div></div>)}
      </div>
      <div className="mt-3 flex h-8 overflow-hidden rounded bg-gray-100" title="Recent transition timeline">
        {query.data.transitions.slice(-50).map((item, index) => (
          <div key={`${item.changed_at}-${index}`} className={item.new_status === 'UP' ? 'min-w-2 flex-1 bg-emerald-500' : item.new_status === 'DOWN' ? 'min-w-2 flex-1 bg-red-500' : 'min-w-2 flex-1 bg-gray-400'} title={`${item.new_status} · ${new Date(item.changed_at).toLocaleString('az-AZ')}`} />
        ))}
      </div>
    </div>
  );
}
