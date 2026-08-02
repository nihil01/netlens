import { motion } from 'framer-motion';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { resetFmcMonitoringData } from '../api';
import { useMonitoringDashboard } from '../hooks/useFmcMonitoring';
import { MonitoringDashboardComponent } from '../components/monitoring/MonitoringDashboard';
import { LoadingPanel } from '../components/LoadingPanel';
import { cn, ui } from '../lib/ui';

export function MonitoringPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError, error, refetch } = useMonitoringDashboard();
  const resetInProgress = ['queued', 'clearing', 'refetching'].includes(
    data?.reset_status?.state ?? 'idle',
  );
  const fmcReset = useMutation({
    mutationFn: resetFmcMonitoringData,
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        predicate: (query) => {
          const source = query.queryKey[0];
          return typeof source === 'string' && [
            'monitoring-dashboard',
            'device-metric-history',
            'ha-pairs',
            'health-alert-history',
            'fmc-policy-analysis',
            'vpn-timeline',
          ].includes(source);
        },
      });
    },
  });

  function handleFmcReset() {
    const confirmed = window.confirm(
      'FMC monitoring keş və tarixçə məlumatları silinəcək. Audit tarixçəsi saxlanacaq və bütün FMC məlumatları yenidən yüklənəcək. Davam edilsin?',
    );
    if (confirmed) fmcReset.mutate();
  }

  if (isLoading) return <LoadingPanel label="FMC Monitoring yüklənir..." />;

  if (isError) {
    return (
      <div className={cn(ui.panel, 'border-red-200 bg-red-50 text-red-700 text-sm')}>
        FMC xətası: {(error as Error).message}
      </div>
    );
  }

  if (!data || data.status === 'not_configured') {
    return (
      <div className={cn(ui.panel, 'text-center text-sm text-gray-400')}>
        <p>FMC konfiqurasiya edilməyib.</p>
        <p className="mt-1">FMC_URL, FMC_USERNAME, FMC_PASSWORD dəyərlərini .env faylında təyin edin.</p>
      </div>
    );
  }

  return (
    <motion.section {...{ initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.2, ease: 'easeOut' } }}>
      <MonitoringDashboardComponent
        tunnel_statuses={data.tunnel_statuses}
        tunnel_summaries={data.tunnel_summaries}
        devices={data.devices}
        aggregate_metrics={data.aggregate_metrics}
        tunnel_up={data.tunnel_up}
        tunnel_down={data.tunnel_down}
        tunnel_unknown={data.tunnel_unknown}
        devices_connected={data.devices_connected}
        devices_total={data.devices_total}
        alerts_count={data.alerts_count}
        source_freshness={data.source_freshness}
        wallboardData={data}
        onRefresh={() => refetch()}
        onReset={handleFmcReset}
        isResetting={fmcReset.isPending || resetInProgress}
        resetMessage={
          fmcReset.isError
            ? (fmcReset.error as Error).message
            : data?.reset_status?.state === 'failed'
              ? `FMC yenidən yüklənməsi uğursuz oldu: ${data.reset_status.error ?? 'naməlum xəta'}`
              : resetInProgress
                ? `FMC yenidən yüklənir: ${(data.reset_status.completed_scopes ?? []).join(', ') || 'növbədə'}.`
                : fmcReset.isSuccess
                  ? fmcReset.data.status === 'already_running'
                    ? 'FMC yenidən yüklənməsi artıq davam edir.'
                    : 'FMC məlumatları yenidən yükləndi.'
                  : undefined
        }
        resetError={fmcReset.isError}
      />
    </motion.section>
  );
}
