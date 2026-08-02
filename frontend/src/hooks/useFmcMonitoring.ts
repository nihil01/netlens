import { useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchMonitoringDashboard, subscribeMonitoringEvents } from '../api';

export function useMonitoringDashboard() {
  const queryClient = useQueryClient();
  const lastEventId = useRef<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let reconnectTimer: number | undefined;
    let backoff = 1_000;

    const connect = async () => {
      try {
        await subscribeMonitoringEvents(
          (event) => {
            lastEventId.current = event.id;
            backoff = 1_000;
            void queryClient.invalidateQueries({ queryKey: ['monitoring-dashboard'] });
            void queryClient.invalidateQueries({ queryKey: ['ha-pairs'] });
            void queryClient.invalidateQueries({ queryKey: ['fmc-policy-analysis'] });
            void queryClient.invalidateQueries({ queryKey: ['health-alert-history'] });
          },
          controller.signal,
          lastEventId.current,
        );
      } catch {
        // Short polling below remains the fallback when SSE is unavailable.
      }
      if (!controller.signal.aborted) {
        reconnectTimer = window.setTimeout(connect, backoff);
        backoff = Math.min(backoff * 2, 30_000);
      }
    };

    void connect();
    return () => {
      controller.abort();
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
    };
  }, [queryClient]);

  return useQuery({
    queryKey: ['monitoring-dashboard'],
    queryFn: fetchMonitoringDashboard,
    refetchInterval: 300_000,
    staleTime: 30_000,
  });
}
