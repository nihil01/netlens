import type { NetBoxDevice } from '../api';
import { cn, ui } from '../lib/ui';
import { emptyLabel, statusClass } from '../lib/format';

export function DeviceRow({ device, interfaceCount, selected, onSelect }: { device: NetBoxDevice; interfaceCount: number; selected: boolean; onSelect: () => void }) {
  return (
    <button className={cn(ui.cardButton, selected ? ui.cardButtonActive : ui.cardButtonIdle)} type="button" onClick={onSelect}>
      <span className="min-w-0">
        <b className="block truncate text-sm text-gray-900">{device.name}</b>
        <small className="block truncate text-xs text-gray-500">{emptyLabel(device.role)} · {interfaceCount} · {emptyLabel(device.primary_ip)}</small>
      </span>
      <em className={cn(statusClass(device.status), 'not-italic shrink-0')}>{emptyLabel(device.status)}</em>
    </button>
  );
}
