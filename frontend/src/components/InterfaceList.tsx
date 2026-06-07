import type { NetBoxInterface } from '../api';
import { emptyLabel } from '../lib/format';

export function InterfaceList({ interfaces, showDevice = false, showVendor = false }: { interfaces: NetBoxInterface[]; showDevice?: boolean; showVendor?: boolean }) {
  if (!interfaces.length) return <p className="muted-text">İnterfeys yoxdur</p>;
  return (
    <div className="interface-table">
      <h3>İnterfeyslər</h3>
      {interfaces.map((item) => (
        <div className="interface-row" key={item.id ?? item.name}>
          <b>{item.name}</b>
          {showDevice && <span>{emptyLabel(item.device)}</span>}
          <span>{emptyLabel(item.type)}</span>
          <span className={item.enabled ? 'good' : 'muted'}>{item.enabled ? 'aktiv' : 'deaktiv'}</span>
          <span className="mono">{emptyLabel(item.mac_address)}</span>
          <span>{item.learned_mac_addresses?.length ?? 0} MAC <small>portda</small></span>
          {showVendor && <span>{emptyLabel(item.mac_vendor)} <small>{emptyLabel(item.mac_oui)} · {emptyLabel(item.mac_vendor_source)}</small></span>}
          <small>{emptyLabel(item.description)}</small>
        </div>
      ))}
    </div>
  );
}
