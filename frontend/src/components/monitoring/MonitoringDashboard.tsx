import { useState } from 'react';
import { Loader2, Maximize2, RefreshCw, RotateCcw } from 'lucide-react';
import { ui } from '../../lib/ui';
import { MonitoringTabBar, type MonitoringTab } from './MonitoringTabs';
import { StatusSummaryCards } from './StatusSummaryCards';
import { TunnelChart } from './TunnelChart';
import { InterfaceStatusChart } from './InterfaceStatusChart';
import { TunnelStatusCard } from './TunnelStatusCard';
import { DeviceHealthCard } from './DeviceHealthCard';
import { HaPairsPanel } from './HaPairsPanel';
import { HealthAlertsPanel } from './HealthAlertsPanel';
import { PolicyAnalysisPanel } from './PolicyAnalysisPanel';
import { WallboardView } from './WallboardView';
import { DeviceMetricsGallery } from './DeviceMetricsGallery';
import type { AggregateMetrics, FmcDevice, MonitoringDashboard, TunnelStatus, TunnelSummary } from '../../api';

type Props = {
  tunnel_statuses: TunnelStatus[];
  tunnel_summaries: TunnelSummary[];
  devices: FmcDevice[];
  aggregate_metrics: AggregateMetrics[];
  tunnel_up: number;
  tunnel_down: number;
  tunnel_unknown: number;
  devices_connected: number;
  devices_total: number;
  alerts_count: number;
  source_freshness: MonitoringDashboard['source_freshness'];
  wallboardData: MonitoringDashboard;
  onRefresh?: () => void;
  onReset?: () => void;
  isResetting?: boolean;
  resetMessage?: string;
  resetError?: boolean;
};

export function MonitoringDashboardComponent({
  tunnel_statuses, tunnel_summaries, devices, aggregate_metrics,
  tunnel_up, tunnel_down, tunnel_unknown, devices_connected, devices_total, alerts_count, source_freshness,
  wallboardData,
  onRefresh, onReset, isResetting, resetMessage, resetError,
}: Props) {
  const [tab, setTab] = useState<MonitoringTab>('overview');
  const [wallboard, setWallboard] = useState(false);
  const metricsMap = new Map(aggregate_metrics.map((m) => [m.device_id, m]));
  const vpnFreshness = source_freshness.find((source) => source.source === 'fmc_vpn');

  return (
    <div className="flex flex-col gap-4">
      {wallboard && <WallboardView data={wallboardData} onClose={() => setWallboard(false)} />}
      {/* Tab bar + refresh */}
      <div className="flex items-center justify-between">
        <MonitoringTabBar active={tab} onChange={setTab} alertCount={alerts_count} />
        <div className="flex gap-2">
          <button onClick={() => setWallboard(true)} className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-2 text-xs font-medium text-white transition hover:bg-slate-800"><Maximize2 size={12} /> Wallboard</button>
          {onRefresh && (
            <button onClick={onRefresh} className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-2 text-xs font-medium text-gray-600 transition hover:bg-gray-50">
              <RefreshCw size={12} /> Yenilə
            </button>
          )}
          {onReset && (
            <button
              onClick={onReset}
              disabled={isResetting}
              className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium text-red-700 transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isResetting ? <Loader2 className="animate-spin" size={12} /> : <RotateCcw size={12} />}
              {isResetting ? 'Sıfırlanır…' : 'FMC-ni sıfırla'}
            </button>
          )}
        </div>
      </div>

      {resetMessage && (
        <div className={`rounded-lg border px-3 py-2 text-xs ${resetError ? 'border-red-200 bg-red-50 text-red-700' : 'border-blue-200 bg-blue-50 text-blue-700'}`}>
          {resetMessage}
        </div>
      )}

      <div className="flex flex-wrap gap-2" aria-label="Data freshness">
        {source_freshness.map((source) => {
          const color = source.state === 'FRESH'
            ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
            : source.state === 'DEGRADED'
              ? 'border-amber-200 bg-amber-50 text-amber-700'
              : 'border-red-200 bg-red-50 text-red-700';
          return (
            <span key={source.source} className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${color}`} title={source.error ?? undefined}>
              {source.source.replaceAll('_', ' ')} · {source.state}
            </span>
          );
        })}
      </div>

      {/* Tab content */}
      <div className="min-h-0 flex-1 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 200px)' }}>

        {/* === OVERVIEW === */}
        {tab === 'overview' && (
          <div className="space-y-5">
            <StatusSummaryCards
              tunnel_up={tunnel_up} tunnel_down={tunnel_down} tunnel_unknown={tunnel_unknown}
              devices_connected={devices_connected} devices_total={devices_total} alerts_count={alerts_count}
            />
            <div className="grid gap-4 lg:grid-cols-2">
              <TunnelChart tunnel_up={tunnel_up} tunnel_down={tunnel_down} tunnel_unknown={tunnel_unknown} />
              <InterfaceStatusChart metrics={aggregate_metrics} />
            </div>
            <DeviceMetricsGallery devices={devices} metrics={aggregate_metrics} />
          </div>
        )}

        {/* === VPN TUNNELS === */}
        {tab === 'vpn' && (
          <div className="space-y-3">
            {vpnFreshness?.state === 'ERROR' && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                VPN collector xətası: {vpnFreshness.error || 'FMC məlumatı əlçatan deyil'}
              </div>
            )}
            {/* Summary badges */}
            {tunnel_summaries.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {tunnel_summaries.map((s, i) => (
                  <div key={i} className="flex items-center gap-3 rounded-lg border border-gray-200 bg-white px-4 py-2.5">
                    <span className="text-sm font-medium text-gray-900">{s.group_name}</span>
                    <div className="flex items-center gap-1.5 text-xs">
                      <span className="rounded bg-emerald-100 px-1.5 py-0.5 font-bold text-emerald-700">↑ {s.tunnel_up_count}</span>
                      <span className="rounded bg-red-100 px-1.5 py-0.5 font-bold text-red-700">↓ {s.tunnel_down_count}</span>
                      {s.tunnel_unknown_count > 0 && (
                        <span className="rounded bg-gray-100 px-1.5 py-0.5 font-bold text-gray-500">? {s.tunnel_unknown_count}</span>
                      )}
                      <span className="text-gray-400">({s.tunnel_count} total)</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
            {/* Tunnel list */}
            <div className="space-y-2">
              {tunnel_statuses.length === 0 && (
                <div className={ui.panel}>
                  <p className="py-8 text-center text-sm text-gray-400">VPN tunnel məlumatı yoxdur</p>
                </div>
              )}
              {tunnel_statuses.map((tunnel) => (
                <TunnelStatusCard key={tunnel.id || tunnel.name} tunnel={tunnel} />
              ))}
            </div>
          </div>
        )}

        {/* === DEVICES === */}
        {tab === 'devices' && (
          <div className="space-y-3">
            {devices.length === 0 ? (
              <div className={ui.panel}>
                <p className="py-8 text-center text-sm text-gray-400">Device məlumatı yoxdur</p>
              </div>
            ) : (
              <div className="grid gap-3 lg:grid-cols-2">
                {devices.map((device) => (
                  <DeviceHealthCard key={device.id || device.host_name} device={device} metrics={metricsMap.get(device.id ?? '')} />
                ))}
              </div>
            )}
          </div>
        )}

        {tab === 'ha' && <HaPairsPanel />}

        {tab === 'policy' && <PolicyAnalysisPanel />}

        {/* === HEALTH ALERT HISTORY === */}
        {tab === 'alerts' && <HealthAlertsPanel />}
      </div>
    </div>
  );
}
