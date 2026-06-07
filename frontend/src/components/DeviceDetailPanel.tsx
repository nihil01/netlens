import { Database } from 'lucide-react';
import type { NetBoxDevice, NetBoxDeviceDetail } from '../api';
import { emptyLabel } from '../lib/format';
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
    <article className="panel detail-panel">
      <div className="panel-title"><Database size={20} /> Qurğu detalları</div>
      {!selectedDevice && <p className="muted-text">Qurğu seçin.</p>}
      {isLoading && <p className="muted-text">Detallar yüklənir...</p>}
      {isError && <p className="error-text">{error?.message}</p>}
      {detail && (
        <>
          <div className="cache-line">
            <span className={detail.cache.hit ? 'badge good' : 'badge warn'}>Keş: {detail.cache.hit ? 'hit' : 'miss'}</span>
            <code>{String(detail.cache.key ?? '')}</code>
          </div>
          <dl>
            <dt>Ad</dt><dd>{detail.name}</dd>
            <dt>Sahə / Region</dt><dd>{emptyLabel(detail.site)} / {emptyLabel(detail.region)}</dd>
            <dt>Rol</dt><dd>{emptyLabel(detail.role)}</dd>
            <dt>Tip</dt><dd>{emptyLabel(detail.manufacturer)} {emptyLabel(detail.device_type)}</dd>
            <dt>Platforma</dt><dd>{emptyLabel(detail.platform)}</dd>
            <dt>Seriya nömrəsi</dt><dd>{emptyLabel(detail.serial)}</dd>
            <dt>Əsas IP</dt><dd>{emptyLabel(detail.primary_ip)}</dd>
          </dl>
          <InterfaceList interfaces={detail.interfaces} showVendor />
        </>
      )}
    </article>
  );
}
