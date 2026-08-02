import { AlertTriangle, Info } from 'lucide-react';
import { ui } from '../../lib/ui';
import type { HealthAlert } from '../../api';

type AlertsListProps = {
  alerts: HealthAlert[];
};

const MODULE_LABELS: Record<string, string> = {
  CPU: 'CPU',
  MEMORY_USAGE: 'Memory',
  DISK_USAGE: 'Disk',
  INTERFACE: 'Interface',
  VPN: 'VPN',
  HIGH_AVAILABILITY: 'HA',
  HEARTBEAT: 'Heartbeat',
  HEALTH_MONITOR: 'Health Monitor',
  SNORT_STATS: 'Snort',
};

function moduleLabel(moduleId: string | null) {
  if (!moduleId) return 'General';
  return MODULE_LABELS[moduleId] || moduleId;
}

export function AlertsList({ alerts }: AlertsListProps) {
  if (alerts.length === 0) {
    return (
      <div className={ui.panel}>
        <div className="flex items-center gap-2">
          <AlertTriangle size={16} className="text-emerald-400" />
          <div className={ui.panelTitle}>Health Alerts</div>
        </div>
        <div className="mt-4 flex items-center justify-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 py-6 text-sm text-emerald-700">
          <Info size={16} />
          Aktiv alert yoxdur — bütün sistemlər normal işləyir
        </div>
      </div>
    );
  }

  return (
    <div className={ui.panel}>
      <div className="flex items-center gap-2">
        <AlertTriangle size={16} className="text-amber-400" />
        <div className={ui.panelTitle}>Health Alerts</div>
        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-700">
          {alerts.length}
        </span>
      </div>
      <div className="mt-3 space-y-2">
        {alerts.map((alert) => (
          <div
            key={alert.id}
            className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3"
          >
            <AlertTriangle size={14} className="mt-0.5 shrink-0 text-amber-500" />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-amber-900">
                  {alert.name || 'Alert'}
                </span>
                <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700">
                  {moduleLabel(alert.module_id)}
                </span>
              </div>
              {alert.details && (
                <p className="mt-1 text-xs text-amber-700">{alert.details}</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
