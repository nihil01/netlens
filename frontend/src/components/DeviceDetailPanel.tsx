import { motion } from 'framer-motion';
import { Database } from 'lucide-react';
import type { NetBoxDevice, NetBoxDeviceDetail } from '../api';
import { emptyLabel } from '../lib/format';
import { cn, motionPreset, ui } from '../lib/ui';
import { InterfaceList } from './InterfaceList';

export function DeviceDetailPanel({
  detail,
  error,
  isError,
  isLoading,
  selectedDevice,
}: {
  detail: NetBoxDeviceDetail | undefined;
  error: Error | null;
  isError: boolean;
  isLoading: boolean;
  selectedDevice: NetBoxDevice | null;
}) {
  return (
    <motion.article className={ui.stickyPanel} {...motionPreset.side}>
      <div className={ui.panelTitle}><Database size={20} /> Qurğu detalları</div>
      {!selectedDevice && <p className={cn(ui.emptyText, 'mt-4')}>Qurğu seçin.</p>}
      {isLoading && <p className={cn(ui.muted, 'mt-4 animate-pulse')}>Detallar yüklənir...</p>}
      {isError && <p className={cn(ui.errorText, 'mt-4')}>{error?.message}</p>}
      {detail && (
        <div className="mt-4 space-y-4">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span className={detail.cache.hit ? ui.badgeGood : ui.badgeWarn}>Keş: {detail.cache.hit ? 'hit' : 'miss'}</span>
            <code className={ui.mono}>{String(detail.cache.key ?? '')}</code>
          </div>
          <dl className={ui.dl}>
            <dt>Ad</dt><dd>{detail.name}</dd>
            <dt>Sahə / Region</dt><dd>{emptyLabel(detail.site)} / {emptyLabel(detail.region)}</dd>
            <dt>Rol</dt><dd>{emptyLabel(detail.role)}</dd>
            <dt>Tip</dt><dd>{emptyLabel(detail.manufacturer)} {emptyLabel(detail.device_type)}</dd>
            <dt>Platforma</dt><dd>{emptyLabel(detail.platform)}</dd>
            <dt>Seriya nömrəsi</dt><dd>{emptyLabel(detail.serial)}</dd>
            <dt>Əsas IP</dt><dd>{emptyLabel(detail.primary_ip)}</dd>
          </dl>
          <InterfaceList interfaces={detail.interfaces} showVendor />
        </div>
      )}
    </motion.article>
  );
}
