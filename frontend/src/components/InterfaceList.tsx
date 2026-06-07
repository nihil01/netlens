import { motion } from 'framer-motion';
import type { NetBoxInterface } from '../api';
import { emptyLabel } from '../lib/format';
import { cn, ui } from '../lib/ui';

export function InterfaceList({ interfaces, showDevice = false, showVendor = false }: { interfaces: NetBoxInterface[]; showDevice?: boolean; showVendor?: boolean }) {
  if (!interfaces.length) return <p className={ui.emptyText}>İnterfeys yoxdur</p>;

  return (
    <div className="mt-4 space-y-3">
      <h3 className="text-sm font-black uppercase tracking-[0.18em] text-slate-500">İnterfeyslər</h3>
      <div className="space-y-2">
        {interfaces.map((item, index) => (
          <motion.div
            className="rounded-2xl border border-slate-200 bg-slate-50/80 p-3 text-sm text-slate-700 shadow-sm"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.18, delay: Math.min(index * 0.025, 0.18) }}
            key={item.id ?? item.name}
          >
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <b className="block break-words text-slate-950">{item.name}</b>
                <small className="block break-words font-semibold text-slate-500">{emptyLabel(item.type)} · {item.enabled ? 'aktiv' : 'deaktiv'}</small>
              </div>
              <span className={cn('w-fit rounded-full px-3 py-1 text-xs font-black uppercase', item.enabled ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-400')}>{item.enabled ? 'aktiv' : 'deaktiv'}</span>
            </div>

            <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {showDevice && <Info label="Qurğu" value={emptyLabel(item.device)} />}
              <Info label="MAC" value={emptyLabel(item.mac_address)} mono />
              <Info label="Portda MAC" value={`${item.learned_mac_addresses?.length ?? 0}`} />
              {showVendor && <Info label="Vendor" value={`${emptyLabel(item.mac_vendor)} · ${emptyLabel(item.mac_oui)} · ${emptyLabel(item.mac_vendor_source)}`} />}
              <Info label="Təsvir" value={emptyLabel(item.description)} wide />
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

function Info({ label, mono = false, value, wide = false }: { label: string; mono?: boolean; value: string; wide?: boolean }) {
  return (
    <span className={cn('min-w-0 rounded-xl bg-white px-3 py-2 ring-1 ring-slate-200', wide && 'sm:col-span-2 xl:col-span-3')}>
      <small className="block text-[10px] font-black uppercase tracking-wide text-slate-400">{label}</small>
      <span className={cn('block min-w-0 break-words font-semibold text-slate-800', mono && 'break-all font-mono text-xs')}>{value}</span>
    </span>
  );
}
